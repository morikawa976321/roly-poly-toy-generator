import math

import numpy as np

from backend.app.models import Gene
from backend.app.profile_extension import (
    base_gene,
    effective_profile,
    max_top_extension_mm,
)
from backend.app.smoothing import smooth_profile


def _sample_gene() -> Gene:
    n = 36
    radii = [0.0]
    for i in range(1, n - 1):
        t = i / (n - 1)
        radii.append(20.0 * math.sin(math.pi * t))
    radii.append(2.0)
    return Gene(
        version=2,
        N=n,
        height=50.0,
        bottom_radius=0.0,
        radii=radii,
        z_warp=2.0,
        top_extension_mm=0.0,
    )


def test_extension_zero_matches_smooth_profile():
    gene = _sample_gene()
    z0, r0 = smooth_profile(gene)
    z1, r1 = effective_profile(gene)
    np.testing.assert_allclose(z0, z1, rtol=0, atol=1e-12)
    np.testing.assert_allclose(r0, r1, rtol=0, atol=1e-12)


def test_reversibility():
    gene = _sample_gene()
    z0, r0 = smooth_profile(gene)
    z_back, r_back = effective_profile(gene)
    np.testing.assert_allclose(z0, z_back, rtol=0, atol=1e-10)
    np.testing.assert_allclose(r0, r_back, rtol=0, atol=1e-10)

    g_ext = gene.model_copy(update={"top_extension_mm": 5.0})
    z_ext, r_ext = effective_profile(g_ext)
    assert len(z_ext) > len(z0)
    np.testing.assert_allclose(z0, z_ext[: len(z0)], rtol=0, atol=1e-10)
    # 延長時のみ上端 1 点を滑らか曲線へ補正（gene 保存値は不変）
    np.testing.assert_allclose(r0[:-1], r_ext[: len(r0) - 1], rtol=0, atol=1e-10)


def test_extension_increases_height():
    from backend.app.profile_extension import max_top_extension_mm

    gene = _sample_gene()
    d_max = max_top_extension_mm(gene)
    delta = min(3.0, d_max * 0.5)
    g_ext = gene.model_copy(update={"top_extension_mm": delta})
    z0, _ = smooth_profile(gene)
    z1, _ = effective_profile(g_ext)
    assert abs(z1[-1] - (z0[-1] + delta)) < 1e-3


def test_max_extension_endpoint_near_zero():
    gene = _sample_gene()
    d_max = max_top_extension_mm(gene)
    assert d_max > 0.0
    g_max = gene.model_copy(update={"top_extension_mm": d_max})
    _, r = effective_profile(g_max)
    assert r[-1] < 0.1


def test_extension_tail_monotonic():
    gene = _sample_gene()
    delta = 4.0
    g_ext = gene.model_copy(update={"top_extension_mm": delta})
    z, r = effective_profile(g_ext)
    peak = int(np.argmax(r))
    tail = r[peak:]
    assert np.all(np.diff(tail) <= 1e-6)


def test_extension_c2_continuous_at_junction():
    """接合部で半径・傾きが局所曲線と一致（C² 外挿）。"""
    import json
    from pathlib import Path

    from backend.app.profile_extension import _junction_state

    dump = Path(__file__).resolve().parents[1] / "docs/designs/6d7afe17fed27c7c/dump.json"
    with open(dump, encoding="utf-8") as f:
        gene = Gene(**json.load(f)["gene"])

    z0, r0 = smooth_profile(gene)
    H = z0[-1]
    _, r_junc, dr_j, _ = _junction_state(z0, r0)

    z1, r1 = effective_profile(gene.model_copy(update={"top_extension_mm": 5.0}))
    mask = z1 > H + 1e-9
    ze = z1[mask]
    re = r1[mask]
    assert abs(re[0] - r_junc) < 0.02, f"radius jump at junction: {re[0]:.3f} vs {r_junc:.3f}"
    assert abs(r1[len(z0) - 1] - r_junc) < 0.02, "base top should match smooth junction radius"
    assert len(re) >= 2
    dr_ext = (re[1] - re[0]) / (ze[1] - ze[0])
    assert dr_ext < 0, f"extension should taper down: dr={dr_ext:.3f}"
    assert abs(dr_ext - dr_j) < 0.35, f"junction dr mismatch: {dr_ext:.3f} vs {dr_j:.3f}"


def test_extension_spreads_taper_over_delta_max():
    """延長区間の中点半径が、Δ_max までの均等テーパより急には細くならない。"""
    import json
    from pathlib import Path

    dump = Path(__file__).resolve().parents[1] / "docs/designs/6d7afe17fed27c7c/dump.json"
    if dump.is_file():
        with open(dump, encoding="utf-8") as f:
            g = json.load(f)["gene"]
        gene = Gene(**g)
    else:
        gene = _sample_gene()

    from backend.app.profile_extension import _compute_delta_max

    z0, r0 = smooth_profile(gene)
    d_max = _compute_delta_max(z0, r0)
    delta = min(5.0, 0.4 * d_max)
    assert d_max > delta

    z1, r1 = effective_profile(gene.model_copy(update={"top_extension_mm": delta}))
    H = z0[-1]
    r_H = r0[-1]
    r_prop_mid = r_H * (1.0 - 0.5 * delta / d_max)
    z_mid = H + 0.5 * delta
    idx = int(np.argmin(np.abs(z1 - z_mid)))
    r_mid = r1[idx]
    assert r_mid >= r_prop_mid * 0.85 - 0.1, (
        f"mid radius {r_mid:.3f} pinches below proportional {r_prop_mid:.3f}"
    )
    # 延長前半で r=0 に張り付かない
    mask = z1 > H + 1e-6
    ext = r1[mask]
    assert float(np.mean(ext[: max(1, len(ext) // 4)])) > 0.5, "extension starts at r≈0"
