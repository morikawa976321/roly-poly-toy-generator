"""metrics.compute_metrics の基本不変条件テスト。

役割: 体積・幅・重心などメトリクス出力の健全性検証。
働き: 単純な Gene で compute_metrics を呼び、有限・非負・重心 z が高さ内にあることを確認する。
"""

import math

from backend.app.metrics import compute_metrics
from backend.app.models import Gene


def test_compute_metrics_basic_invariants():
    gene = Gene(
        version=2,
        N=36,
        height=10.0,
        bottom_radius=0.0,
        radii=[0.0] + [1.0] * 34 + [0.5],
        z_warp=2.0,
    )

    m = compute_metrics(gene)

    assert m.height == 10.0
    assert math.isfinite(m.volume)
    assert m.volume >= 0.0
    assert math.isfinite(m.max_width)
    assert m.max_width >= 0.0
    assert 0.0 <= m.centroid_z <= m.height

