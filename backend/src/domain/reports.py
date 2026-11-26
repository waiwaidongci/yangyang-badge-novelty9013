"""Build maintenance decisions with original readings and traceable nearest donors."""

from collections import Counter

from .novelty import by_series
from .settings import FIELDS


def queue(rows, models, thresholds):
    result = []
    for series, parts in by_series(rows).items():
        threshold = thresholds.get(series)
        if threshold is None:
            lack = '独立校准件不足' if series in models else '缺少同系列参考样本'
            result.extend(dict(part, score=None, threshold=None, nearest_part=None, nearest_distance=None,
                               neighbors=0, action='manual', reason=lack) for part in parts)
            continue
        model = models[series]
        for part, score, observed in zip(parts, model.score(parts), model.references(parts)):
            distance, nearest, support = observed
            action = 'retest' if score > threshold.threshold else 'record'
            result.append(dict(part, score=float(score), threshold=threshold.threshold, nearest_part=nearest,
                               nearest_distance=distance, neighbors=support, action=action,
                               reason='超过本系列复测分位' if action == 'retest' else '分数在校准范围'))
    return sorted(result, key=lambda row: ({'retest': 0, 'manual': 1, 'record': 2}[row['action']], row['part_id']))


def table(key, title, columns, rows):
    return {'key': key, 'title': title, 'columns': columns,
            'rows': [{column: round(row[column], 8) if isinstance(row[column], float) else row[column]
                      for column in columns} for row in rows]}


def build_report(items, diagnostic, models, thresholds, quantile):
    counts = Counter(row['action'] for row in items)
    series_rows = [{'clip_variant': name, 'reference_rows': len(models[name].ids),
                    'calibration_rows': len(calibration.scores), 'calibration_quantile': quantile,
                    'threshold': calibration.threshold,
                    'calibration_exceedances': sum(score > calibration.threshold for score in calibration.scores)}
                   for name, calibration in sorted(thresholds.items())]
    return {
        'summary': f'{len(items)} 件返回证件夹滑扣完成分流，{counts["retest"]} 件优先复测，'
                   f'{counts["manual"]} 件需人工查系列或校准覆盖。',
        'metrics': {'已校准夹体版型': len(thresholds), '需优先复测': counts['retest'],
                    '人工核对系列': counts['manual'], '范围内留档': counts['record']},
        'warnings': ['核边界新颖度用于安排人工复测。有偏差的参考件会影响复测阈值。'],
        'tables': [
            table('badge_retest', '证件夹滑扣复测交接', ['part_id', 'bench_lot', 'clip_variant', *FIELDS,
                  'score', 'threshold', 'nearest_part', 'nearest_distance', 'neighbors', 'action', 'reason'], items),
            table('series_calibration', '夹体版型校准', ['clip_variant', 'reference_rows', 'calibration_rows',
                  'calibration_quantile', 'threshold', 'calibration_exceedances'], series_rows),
            table('calibration_parts', '独立校准测件分数', ['part_id', 'clip_variant', 'score', 'threshold',
                  'above_threshold'], diagnostic),
        ],
    }
