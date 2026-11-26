"""Assemble reference, calibration, and pending steps for a worker run."""

from .calibration import calibrate
from .novelty import fit_models
from .fixtures import demo_rows
from .records import normalize_rows
from .reports import build_report, queue
from .settings import SPEC, parse_options

__all__ = ['SPEC', 'analyze', 'demo_rows', 'normalize_rows']


def analyze(rows, settings):
    nu, quantile = parse_options(settings)
    validated = normalize_rows(rows)
    models = fit_models([row for row in validated if row['partition'] == 'reference'], nu)
    thresholds, diagnostic = calibrate([row for row in validated if row['partition'] == 'calibration'], models, quantile)
    items = queue([row for row in validated if row['partition'] == 'pending'], models, thresholds)
    return build_report(items, diagnostic, models, thresholds, quantile)
