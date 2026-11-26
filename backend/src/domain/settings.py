"""Instruments, input limits, and the slide-lock model contract."""

FIELDS = {'stroke_mm': (0, 20), 'slide_force_n': (0, 32), 'settle_ms': (0, 500), 'guide_gap_mm': (0, 4)}
PARTITIONS = ('reference', 'calibration', 'pending')
COLUMNS = ['part_id', 'bench_lot', 'partition', 'clip_variant', *FIELDS]
PARAMETERS = [
    {'key': 'nu', 'label': '核边界 ν', 'min': 0.05, 'max': 0.40, 'default': 0.12, 'step': 0.01},
    {'key': 'reference_quantile', 'label': '校准新颖度分位', 'min': 0.70, 'max': 0.99, 'default': 0.92, 'step': 0.01},
]
SPEC = {
    'title': '展会周转证件夹滑扣回库复测',
    'dataset_name': '回展仓 WK-48 证件夹滑扣测力记录',
    'description': '按夹体版型拟合一类 SVM，用独立校准批确定核边界新颖度阈值。',
    'columns': COLUMNS,
    'settings': PARAMETERS,
    'partitions': list(PARTITIONS),
}


def parse_options(values):
    if values.keys() - {param['key'] for param in PARAMETERS}:
        raise ValueError('发现未定义的新颖度筛查参数')
    resolved = []
    for param in PARAMETERS:
        value = values.get(param['key'], param['default'])
        if type(value) not in (int, float) or not param['min'] <= value <= param['max']:
            raise ValueError(f"{param['label']} 超出范围")
        resolved.append(value)
    return resolved
