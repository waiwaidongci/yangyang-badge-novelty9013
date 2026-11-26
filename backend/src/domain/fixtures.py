"""Simulate two approved slide-lock variants and incoming parts with shifted mechanics."""

from random import Random


def demo_rows():
    rng = Random(261198)
    rows = []
    for split, lots, count in [('reference', 8, 12), ('calibration', 4, 12), ('pending', 2, 14)]:
        for i in range(lots):
            lot = f'{split[:3].upper()}-{i + 1:02d}'
            for j in range(count):
                variant = 'SLIM' if j % 2 == 0 else 'WIDE'
                wide = int(variant == 'WIDE')
                jig = rng.uniform(-1, 1)
                row = {'part_id': f'{lot}-{j + 1:02d}', 'bench_lot': lot,
                       'partition': split, 'clip_variant': variant,
                       'stroke_mm': round(3.2 + 2.2 * wide + .22 * jig + rng.gauss(0, .08), 3),
                       'slide_force_n': round(6 + 5 * wide + .8 * jig + rng.gauss(0, .3), 3),
                       'settle_ms': round(35 + 20 * wide - 4 * jig + rng.gauss(0, 2), 3),
                       'guide_gap_mm': round(.18 + .23 * wide + .05 * jig + rng.gauss(0, .015), 3)}
                if split == 'pending' and j == 3:
                    row['settle_ms'] += 40
                    row['slide_force_n'] -= 3
                if split == 'pending' and j == 9:
                    row['clip_variant'] = 'MINI'
                rows.append(row)
    return rows
