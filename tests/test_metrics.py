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

