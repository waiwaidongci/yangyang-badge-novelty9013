"""Idempotent recommendation tickets and resumable per-buckle calculation."""

import json
import logging
import uuid
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.constants.workflow import RunStatus
from src.domain.recommendations import build_boundary_context, recommend_for_part
from src.domain.settings import FIELDS
from src.models.dataset import Dataset
from src.models.recommendation import Recommendation
from src.models.run import Run
from src.services.audit import record
from src.services.runs import get_run
from src.utils.time import utc_stamp

LOGGER = logging.getLogger(__name__)
UNFINISHED = (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.FAILED)
CLAIMABLE = (RunStatus.QUEUED, RunStatus.FAILED)
ADVICE_TABLE_KEY = 'retest_advice'


def recommendation_info(row: Recommendation):
    fields = (
        'id', 'run_id', 'part_id', 'clip_variant', 'status', 'found',
        'reference_part', 'measurements', 'replacement_readings', 'total_change',
        'original_score', 'threshold', 'candidate_score', 'note', 'attempts',
        'error', 'created_at', 'updated_at', 'completed_at',
    )
    data = {key: getattr(row, key) for key in fields}
    data['advice'] = row.result
    return data


def overview(session: Session, run_id: int):
    rows = list(session.scalars(
        select(Recommendation).where(Recommendation.run_id == run_id).order_by(Recommendation.id)
    ))
    counts = Counter(row.status for row in rows)
    if not rows:
        status = 'empty'
    elif counts.get(RunStatus.FAILED):
        status = RunStatus.FAILED
    elif any(row.status in (RunStatus.QUEUED, RunStatus.RUNNING) for row in rows):
        status = RunStatus.RUNNING
    else:
        status = RunStatus.COMPLETED
    found = sum(1 for row in rows if row.found is True)
    missing = sum(1 for row in rows if row.found is False and row.status == RunStatus.COMPLETED)
    return {
        'run_id': run_id,
        'status': status,
        'total': len(rows),
        'recommended': found,
        'not_found': missing,
        'items': [recommendation_info(row) for row in rows],
    }


def _retest_part_ids(run: Run):
    if not isinstance(run.result, dict):
        raise HTTPException(409, '筛查单尚未生成结果，不能另算建议')
    for table in run.result.get('tables', []):
        if table.get('key') == 'badge_retest':
            return [row['part_id'] for row in table.get('rows', []) if row.get('action') == 'retest']
    raise HTTPException(409, '筛查结果中找不到复测交接表')


def enqueue_missing(session: Session, run: Run, actor_id: int | None = None):
    """Create exactly one natural-key ticket per over-line buckle."""
    part_ids = _retest_part_ids(run)
    existing = {
        row.part_id: row
        for row in session.scalars(select(Recommendation).where(Recommendation.run_id == run.id))
    }
    dataset = session.get(Dataset, run.dataset_id)
    if dataset is None:
        raise LookupError('找不到来源台账')
    source_rows = {row['part_id']: row for row in dataset.rows}
    now = utc_stamp()
    added = 0
    for part_id in part_ids:
        if part_id in existing:
            continue
        source = source_rows.get(part_id)
        if source is None:
            continue
        session.add(Recommendation(
            run_id=run.id,
            part_id=part_id,
            clip_variant=source['clip_variant'],
            status=RunStatus.QUEUED,
            measurements=[],
            replacement_readings={},
            attempts=0,
            created_at=now,
            updated_at=now,
        ))
        added += 1
    if added and actor_id is not None:
        record(session, 'recommendation.queued', run.id, actor_id)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent retry won the unique (run_id, part_id) insert. The natural
        # key is the authoritative duplicate guard.
        session.rollback()
    return list(session.scalars(
        select(Recommendation).where(Recommendation.run_id == run.id).order_by(Recommendation.id)
    ))


def recover_interrupted(session: Session, run_id: int | None = None):
    """Return crashed running tickets to the claimable queue."""
    statement = update(Recommendation).where(Recommendation.status == RunStatus.RUNNING)
    if run_id is not None:
        statement = statement.where(Recommendation.run_id == run_id)
    session.execute(statement.values(status=RunStatus.QUEUED, lease_token=None,
                                     updated_at=utc_stamp()))
    session.commit()


def claim_next(session: Session, run_id: int | None = None):
    """Atomically claim one unfinished ticket using an attempts compare-and-set."""
    while True:
        statement = select(Recommendation).where(Recommendation.status.in_(CLAIMABLE))
        if run_id is not None:
            statement = statement.where(Recommendation.run_id == run_id)
        rec = session.scalar(statement.order_by(Recommendation.id).limit(1))
        if rec is None:
            return None
        rec_id = rec.id
        old_attempts = int(rec.attempts or 0)
        token = str(uuid.uuid4())
        now = utc_stamp()
        changed = session.execute(
            update(Recommendation)
            .where(
                Recommendation.id == rec_id,
                Recommendation.attempts == old_attempts,
                Recommendation.status.in_(CLAIMABLE),
            )
            .values(status=RunStatus.RUNNING, attempts=old_attempts + 1,
                    lease_token=token, updated_at=now, error=None)
        )
        if changed.rowcount == 1:
            session.flush()
            return rec_id, rec.run_id, rec.part_id, token
        # Lost a concurrent claim race. The conditional UPDATE affected no row;
        # continue to the next candidate without invalidating the caller's tx.


def _context(session: Session, run_id: int):
    run = session.get(Run, run_id)
    if run is None:
        raise LookupError('找不到运行')
    dataset = session.get(Dataset, run.dataset_id)
    if dataset is None:
        raise LookupError('找不到来源台账')
    validated, models, thresholds, _ = build_boundary_context(dataset.rows, run.settings)
    references = [row for row in validated if row['partition'] == 'reference']
    pending = {row['part_id']: row for row in validated if row['partition'] == 'pending'}
    return run, references, models, thresholds, pending


def process_pending(session: Session, run_id: int, limit: int | None = None):
    """Calculate only tickets that have not reached the completed terminal state."""
    _, references, models, thresholds, pending = _context(session, run_id)
    processed = []
    while limit is None or len(processed) < limit:
        claim = claim_next(session, run_id)
        if claim is None:
            session.commit()
            break
        rec_id, claimed_run_id, part_id, token = claim
        if claimed_run_id != run_id:
            session.rollback()
            break
        session.commit()

        try:
            part = pending[part_id]
            series = part['clip_variant']
            calibration = thresholds.get(series)
            advice = recommend_for_part(
                part,
                references,
                models.get(series),
                calibration.threshold if calibration is not None else None,
            )
            values = {
                'status': RunStatus.COMPLETED,
                'found': bool(advice['found']),
                'reference_part': advice.get('reference_part'),
                'measurements': advice.get('measurements', []),
                'replacement_readings': advice.get('replacement_readings', {}),
                'total_change': advice.get('total_change'),
                'original_score': advice.get('original_score'),
                'threshold': advice.get('threshold'),
                'candidate_score': advice.get('candidate_score'),
                'note': advice.get('note'),
                'result': advice,
                'error': None,
                'updated_at': utc_stamp(),
                'completed_at': utc_stamp(),
            }
            result = session.execute(
                update(Recommendation)
                .where(Recommendation.id == rec_id, Recommendation.lease_token == token)
                .values(**values)
            )
            if result.rowcount != 1:
                session.rollback()
                continue
            session.commit()
            processed.append(rec_id)
        except Exception as error:  # keep the durable queue available for resume
            session.rollback()
            LOGGER.exception('建议计算 %s 失败', rec_id)
            message = str(error) if isinstance(error, ValueError) else '建议计算遇到内部错误，可后续重试。'
            session.execute(
                update(Recommendation)
                .where(Recommendation.id == rec_id, Recommendation.lease_token == token)
                .values(status=RunStatus.FAILED, error=message, updated_at=utc_stamp())
            )
            session.commit()
            processed.append(rec_id)
    return processed


def generate_for_run(session: Session, run_id: int, actor):
    run, _ = get_run(session, run_id, actor)
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(409, '筛查单完成后才能另算复测建议')
    enqueue_missing(session, run, actor.id)
    recover_interrupted(session, run_id)
    process_pending(session, run_id)
    return overview(session, run_id)


def list_for_run(session: Session, run_id: int, actor):
    get_run(session, run_id, actor)
    return overview(session, run_id)


def advice_export(session: Session, run_id: int):
    rows = list(session.scalars(
        select(Recommendation)
        .where(Recommendation.run_id == run_id, Recommendation.status == RunStatus.COMPLETED)
        .order_by(Recommendation.id)
    ))
    columns = [
        'part_id', 'clip_variant', 'found', 'measurement_count', 'measurements',
        'reference_part', *FIELDS, 'replacement_readings', 'total_change',
        'original_score', 'threshold', 'candidate_score', 'status', 'note',
    ]
    table_rows = []
    for row in rows:
        item = recommendation_info(row)
        replacements = item.get('replacement_readings') or {}
        item['measurement_count'] = len(item.get('measurements') or []) if item.get('found') else None
        item['measurements'] = ';'.join(item['measurements'] or [])
        for field in FIELDS:
            item[field] = replacements.get(field)
        item['replacement_readings'] = json.dumps(
            replacements, ensure_ascii=False, sort_keys=True
        )
        table_rows.append({column: item.get(column) for column in columns})
    return {'key': ADVICE_TABLE_KEY, 'title': '越线滑扣先测项建议', 'columns': columns, 'rows': table_rows}
