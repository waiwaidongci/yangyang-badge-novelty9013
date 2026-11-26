"""Freeze operational thresholds using unseen calibration parts only."""

from dataclasses import dataclass

import numpy as np

from .novelty import by_series

MIN_CALIBRATION = 10


@dataclass(frozen=True)
class Calibration:
    threshold: float
    scores: list


def calibrate(rows, models, quantile):
    thresholds, diagnostic = {}, []
    for series, samples in sorted(by_series(rows).items()):
        if series not in models or len(samples) < MIN_CALIBRATION:
            continue
        scores = models[series].score(samples)
        cutoff = float(np.quantile(scores, quantile, method='higher'))
        thresholds[series] = Calibration(cutoff, [float(score) for score in scores])
        diagnostic.extend({'part_id': row['part_id'], 'clip_variant': series,
                           'score': float(score), 'threshold': cutoff, 'above_threshold': bool(score > cutoff)}
                          for row, score in zip(samples, scores))
    if not thresholds:
        raise ValueError(f'至少一个已建模系列须有 {MIN_CALIBRATION} 条独立校准记录')
    return thresholds, diagnostic
