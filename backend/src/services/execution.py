import json
import logging

from sqlalchemy import select, update

from src.config.database import Session
from src.constants.workflow import RunStatus
from src.domain.project import analyze
from src.domain.recommendations import build_boundary_context, recommend_for_part
from src.models.dataset import Dataset
from src.models.recommendation import Recommendation
from src.models.run import Run
from src.services.audit import record
from src.services.recommendations import claim_next


def recover_jobs():
    with Session.begin() as session:
        session.execute(update(Run).where(Run.status == RunStatus.RUNNING).values(status=RunStatus.QUEUED))


def claim():
    with Session.begin() as session:
        run = session.scalar(select(Run).where(Run.status == RunStatus.QUEUED)
                             .order_by(Run.id).limit(1).with_for_update(skip_locked=True))
        if run is None:
            return None
        run.status = RunStatus.RUNNING
        dataset = session.get(Dataset, run.dataset_id)
        record(session, 'run.started', run.id)
        return run.id, dataset.rows, run.settings


def execute(job):
    run_id, rows, settings = job
    result = None
    error_message = None
    try:
        result = analyze(rows, settings)
        json.dumps(result, ensure_ascii=False, allow_nan=False)
    except ValueError as error:
        result = None
        error_message = str(error)
    except Exception:
        logging.getLogger(__name__).exception('计算运行 %s 失败', run_id)
        result = None
        error_message = '计算遇到内部错误，请检查台账后重试。'
    with Session.begin() as session:
        run = session.get(Run, run_id)
        run.status = RunStatus.FAILED if error_message is not None else RunStatus.COMPLETED
        run.result = result
        run.error = error_message
        record(session, 'run.' + run.status, run.id)


def claim_recommendation():
    """Claim one resumable per-buckle advice ticket for the background worker."""
    with Session.begin() as session:
        claim = claim_next(session)
        if claim is None:
            return None
        rec_id, run_id, part_id, token = claim
        run = session.get(Run, run_id)
        dataset = session.get(Dataset, run.dataset_id)
        return {
            'rec_id': rec_id,
            'run_id': run_id,
            'part_id': part_id,
            'token': token,
            'rows': dataset.rows,
            'settings': run.settings,
        }


def execute_recommendation(job):
    error_message = None
    values = {}
    try:
        validated, models, thresholds, _ = build_boundary_context(job['rows'], job['settings'])
        series = next(row['clip_variant'] for row in validated
                      if row['partition'] == 'pending' and row['part_id'] == job['part_id'])
        calibration = thresholds.get(series)
        advice = recommend_for_part(
            next(row for row in validated
                 if row['partition'] == 'pending' and row['part_id'] == job['part_id']),
            [row for row in validated if row['partition'] == 'reference'],
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
        }
    except ValueError as error:
        error_message = str(error)
    except Exception:
        logging.getLogger(__name__).exception('建议计算 %s 失败', job['rec_id'])
        error_message = '建议计算遇到内部错误，请稍后重试。'

    from src.utils.time import utc_stamp

    with Session.begin() as session:
        if error_message is not None:
            session.execute(
                update(Recommendation)
                .where(Recommendation.id == job['rec_id'], Recommendation.lease_token == job['token'])
                .values(status=RunStatus.FAILED, error=error_message, updated_at=utc_stamp())
            )
            return
        result = session.execute(
            update(Recommendation)
            .where(Recommendation.id == job['rec_id'], Recommendation.lease_token == job['token'])
            .values(**values, updated_at=utc_stamp(), completed_at=utc_stamp())
        )
        if result.rowcount == 1:
            record(session, 'recommendation.completed', job['run_id'])
