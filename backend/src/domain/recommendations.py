"""Find the smallest same-variant reference substitution that restores a boundary score."""

from itertools import combinations

from .calibration import calibrate
from .novelty import fit_models
from .records import normalize_rows
from .reports import queue
from .settings import FIELDS, parse_options

FIELD_KEYS = list(FIELDS)
UNAVAILABLE = 'reference_unavailable'
NO_SOLUTION = 'no_passing_substitution'
RECOMMENDED = 'recommended'


def _base_advice(part):
    return {
        'part_id': part['part_id'],
        'bench_lot': part.get('bench_lot'),
        'clip_variant': part['clip_variant'],
        'original_readings': {field: part[field] for field in FIELD_KEYS},
    }


def _unavailable(part, reason_code, note):
    return {
        **_base_advice(part),
        'found': False,
        'status': reason_code,
        'measurement_count': None,
        'measurements': [],
        'minimum_items': None,
        'reference_part': None,
        'donor_part_id': None,
        'reference_readings': None,
        'replacement_readings': {},
        'replacements': {},
        'replacement': {},
        'total_change': None,
        'change_cost': None,
        'candidate_score': None,
        'score_after_replacement': None,
        'original_score': None,
        'threshold': None,
        'changes': [],
        'note': note,
    }


def _standardized_cost(part, donor, fields, scales):
    changes = []
    total = 0.0
    for field in fields:
        raw_change = float(donor[field] - part[field])
        standardized = raw_change / float(scales[FIELD_KEYS.index(field)])
        total += abs(standardized)
        changes.append({
            'field': field,
            'from': float(part[field]),
            'to': float(donor[field]),
            'raw_change': raw_change,
            'standardized_change': float(standardized),
            'absolute_standardized_change': abs(float(standardized)),
        })
    return float(total), changes


def recommend_for_part(part, references, model=None, threshold=None):
    """Return the minimum-field, minimum-scale-cost donor substitution for one part.

    Every candidate takes all replacement values from one same-variant reference row.
    A score equal to or below the calibration line is inside the retest boundary.
    """
    if model is None or threshold is None:
        return _unavailable(part, UNAVAILABLE, '当前版型缺少可用模型或复测线，无法试算替换。')

    donors = sorted(
        (row for row in references if row.get('clip_variant') == part.get('clip_variant')),
        key=lambda row: row['part_id'],
    )
    if not donors:
        return _unavailable(part, UNAVAILABLE, '找不到同版型参照件实测值。')

    threshold = float(threshold)
    original_score = float(model.score([part])[0])
    scales = model.scaler.scale_

    for count in range(1, len(FIELD_KEYS) + 1):
        feasible = []
        for donor in donors:
            for fields in combinations(FIELD_KEYS, count):
                candidate = dict(part)
                for field in fields:
                    candidate[field] = donor[field]
                candidate_score = float(model.score([candidate])[0])
                if candidate_score > threshold:
                    continue
                total_change, changes = _standardized_cost(part, donor, fields, scales)
                replacement = {field: float(donor[field]) for field in fields}
                feasible.append({
                    'reference_part': donor['part_id'],
                    'fields': fields,
                    'score': candidate_score,
                    'cost': total_change,
                    'donor': donor,
                    'replacement': replacement,
                    'changes': changes,
                })

        if not feasible:
            continue

        best = min(feasible, key=lambda item: (item['cost'], item['reference_part'], item['fields']))
        donor = best['donor']
        fields = list(best['fields'])
        reference_readings = {field: float(donor[field]) for field in FIELD_KEYS}
        result = {
            **_base_advice(part),
            'found': True,
            'status': RECOMMENDED,
            'measurement_count': count,
            'minimum_items': count,
            'measurements': fields,
            'reference_part': best['reference_part'],
            'donor_part_id': best['reference_part'],
            'reference_readings': reference_readings,
            'replacement_readings': best['replacement'],
            'replacements': best['replacement'],
            'replacement': best['replacement'],
            'total_change': best['cost'],
            'change_cost': best['cost'],
            'change_metric': 'standard_scaler_abs_sum',
            'original_score': original_score,
            'threshold': threshold,
            'candidate_score': best['score'],
            'score_after_replacement': best['score'],
            'changes': best['changes'],
            'note': None,
        }
        # Preserve the useful descending contribution order without changing the
        # canonical ``measurements`` contract.
        result['priority_order'] = [change['field'] for change in sorted(
            best['changes'], key=lambda change: change['absolute_standardized_change'], reverse=True)]
        return result

    result = _unavailable(
        part, NO_SOLUTION, '已试借同版型任一参照件的全部测项，替换后仍未回到复测线内。'
    )
    result.update(original_score=original_score, threshold=threshold)
    return result


def build_boundary_context(rows, settings=None):
    """Validate rows and rebuild the exact frozen-run model/calibration context."""
    nu, quantile = parse_options(settings or {})
    validated = normalize_rows(rows)
    models = fit_models([row for row in validated if row['partition'] == 'reference'], nu)
    thresholds, diagnostic = calibrate(
        [row for row in validated if row['partition'] == 'calibration'], models, quantile
    )
    return validated, models, thresholds, diagnostic


def recommend_retests(rows, settings=None, include_manual=False):
    """Calculate advice independently from the ordinary screening report."""
    validated, models, thresholds, _ = build_boundary_context(rows, settings)
    pending = [row for row in validated if row['partition'] == 'pending']
    items = queue(pending, models, thresholds)
    references = [row for row in validated if row['partition'] == 'reference']

    advice = []
    for item in items:
        if item['action'] == 'retest':
            series = item['clip_variant']
            calibration = thresholds.get(series)
            advice.append(recommend_for_part(
                item,
                references,
                models.get(series),
                calibration.threshold if calibration is not None else None,
            ))
        elif include_manual and item['action'] == 'manual':
            advice.append(_unavailable(item, UNAVAILABLE, item.get('reason') or '版型参照或校准不足。'))
    return advice
