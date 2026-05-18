"""effective_profile と上部延長（quintic + B3 再フィット）のテスト。

役割: profile_extension モジュールの幾何・数値契約の検証。
働き: legacy→B3 再フィット、延長の単調性/C2、最大延長端点、本番延長形状の回帰を確認する。
"""


import numpy as np

from backend.app.models import Gene
from backend.app.profile_extension import (
    effective_profile,
    legacy_mesh_profile,
    max_top_extension_mm,
)
from backend.app.smoothing import b3_refit_profile, smooth_profile
from backend.app.profile_extension import base_gene

from tests.factories import sample_gene_profile


def test_effective_is_b3_refit_of_legacy():
    gene = sample_gene_profile()
    z_l, r_l = legacy_mesh_profile(gene)
    z_e, r_e = effective_profile(gene)
    z_r, r_r = b3_refit_profile(z_l, r_l, n_control=gene.N)
    np.testing.assert_allclose(z_e, z_r, rtol=0, atol=1e-12)
    np.testing.assert_allclose(r_e, r_r, rtol=0, atol=1e-10)


def test_reversibility():
    gene = sample_gene_profile()
    z0, r0 = legacy_mesh_profile(gene)
    z_back, r_back = effective_profile(gene)
    np.testing.assert_allclose(z0, z_back, rtol=0, atol=1e-10)

    g_ext = gene.model_copy(update={"top_extension_mm": 5.0})
    z_ext, r_ext = effective_profile(g_ext)
    assert len(z_ext) > len(z0)
    assert z_ext[-1] > z0[-1] + 4.0
    peak = int(np.argmax(r_ext))
    assert np.all(np.diff(r_ext[peak:]) <= 1e-6)


def test_extension_increases_height():
    gene = sample_gene_profile()
    d_max = max_top_extension_mm(gene)
    delta = min(3.0, d_max * 0.5)
    g_ext = gene.model_copy(update={"top_extension_mm": delta})
    z0, _ = smooth_profile(gene)
    z1, _ = effective_profile(g_ext)
    assert abs(z1[-1] - (z0[-1] + delta)) < 1e-3


def test_max_extension_endpoint_near_zero():
    gene = sample_gene_profile()
    d_max = max_top_extension_mm(gene)
    assert d_max > 0.0
    g_max = gene.model_copy(update={"top_extension_mm": d_max})
    _, r = effective_profile(g_max)
    assert r[-1] < 0.1


def test_production_extension_near_legacy_quintic():
    """再 B3 後も延長区間はレガシーに近い（z 格子は同一）。"""
    import json
    from pathlib import Path

    dump = Path(__file__).resolve().parents[1] / "docs/designs/6d7afe17fed27c7c/gene.json"
    gene = Gene.model_validate(json.loads(dump.read_text(encoding="utf-8")))
    delta = 5.0
    g_ext = gene.model_copy(update={"top_extension_mm": delta})
    z_legacy, r_legacy = legacy_mesh_profile(g_ext)
    z_prod, r_prod = effective_profile(g_ext)
    H = float(smooth_profile(base_gene(g_ext))[0][-1])
    mask_p = z_prod > H + 1e-6
    mask_l = z_legacy > H + 1e-6
    assert int(np.sum(mask_p)) > 0 and int(np.sum(mask_l)) > 0
    np.testing.assert_allclose(z_prod[mask_p], z_legacy[mask_l], rtol=0, atol=1e-9)
    r_legacy_on_prod = np.interp(z_prod[mask_p], z_legacy, r_legacy)
    np.testing.assert_allclose(r_prod[mask_p], r_legacy_on_prod, rtol=0, atol=0.15)


def test_extension_tail_monotonic():
    gene = sample_gene_profile()
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
    assert re[0] <= r_junc + 0.15, (
        f"extension must not bulge outward at junction: {re[0]:.3f} > {r_junc:.3f}"
    )
    assert len(re) >= 2
    dr_ext = (re[1] - re[0]) / (ze[1] - ze[0])
    assert dr_ext < 0, f"extension should taper down: dr={dr_ext:.3f}"
    assert abs(dr_ext - dr_j) < 0.4, f"junction dr mismatch: {dr_ext:.3f} vs {dr_j:.3f}"


def test_extension_no_outward_bulge_at_junction():
    """延長先頭点を r_junc へ張り付けない（付け根の盛り上がり防止）。"""
    import json
    from pathlib import Path

    from backend.app.profile_extension import _extension_segment, _junction_state

    dump = Path(__file__).resolve().parents[1] / "docs/designs/6d7afe17fed27c7c/dump.json"
    with open(dump, encoding="utf-8") as f:
        gene = Gene(**json.load(f)["gene"])

    z0, r0 = smooth_profile(gene)
    H = z0[-1]
    _, r_junc, dr, d2r = _junction_state(z0, r0)
    d_max = max_top_extension_mm(gene)
    delta = 0.5 * d_max
    _, r_seg = _extension_segment(H, r_junc, dr, d2r, delta, max(delta, d_max))
    assert len(r_seg) >= 2
    assert r_seg[0] < r_junc - 1e-4
    assert r_seg[1] <= r_seg[0] + 1e-6


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
        gene = sample_gene_profile()

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
    mask = z1 > H + 1e-6
    ext = r1[mask]
    assert float(np.mean(ext[: max(1, len(ext) // 4)])) > 0.5, "extension starts at r≈0"
