"""Convert CSV values into finite measurements and enforce whole-lot splits."""

import math
import re

from .settings import COLUMNS, FIELDS, PARTITIONS


def label(raw, field):
    if not isinstance(raw, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,39}', raw):
        raise ValueError(f'{field} 应为 1–40 位字母、数字或编号符号')
    return raw


def bounded(raw, bounds, field, part_id):
    try:
        if isinstance(raw, bool):
            raise ValueError
        point = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{part_id} 的 {field} 必须填写数字') from error
    if not math.isfinite(point) or not bounds[0] <= point <= bounds[1]:
        raise ValueError(f'{part_id} 的 {field} 超出仪器量程')
    return point if point else 0.0


def normalize_rows(rows):
    records, ids, splits = [], set(), {}
    for i, row in enumerate(rows, 1):
        if set(row) != set(COLUMNS):
            raise ValueError(f'第 {i} 行与测力台账列不一致')
        part_id = label(row['part_id'], 'part_id')
        lot = label(row['bench_lot'], 'bench_lot')
        series = label(row['clip_variant'], 'clip_variant')
        split = row['partition']
        if split not in PARTITIONS or splits.setdefault(lot, split) != split:
            raise ValueError(f'{lot} 的分区无效或同批跨分区')
        if part_id in ids:
            raise ValueError(f'重复扣件编号 {part_id}')
        ids.add(part_id)
        measurements = {field: bounded(row[field], bounds, field, part_id) for field, bounds in FIELDS.items()}
        records.append({'part_id': part_id, 'bench_lot': lot, 'partition': split,
                        'clip_variant': series, **measurements})
    if not records:
        raise ValueError('扣件台账没有记录')
    return records
