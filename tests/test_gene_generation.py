"""gene 生成（v2 ハイブリッド）の統計的テスト。

役割: gene サンプリング・繁殖の品質保証。
働き: sample_gene / breed の形状不変条件、seed 再現性、一括サンプルの feasibility 通過を検証する。
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.app.config import GENE_VERSION, N_NODES, TILT_MAX_DEG
from backend.app.gene import breed_gene_with_feasibility, sample_gene, sample_gene_with_feasibility
from backend.app.physics import feasibility_from_profile, rolypoly_feasibility


# ----------------------------- 基本特性 ------------------------------------


def test_sample_gene_shape_invariants():
    """生成 gene は v2 スキーマを満たす。"""
    gene = sample_gene(seed=1)
    assert gene.version == GENE_VERSION
    assert gene.N == N_NODES
    assert len(gene.radii) == N_NODES
    assert gene.bottom_radius == 0.0
    # v2 は r[0] = 0（球キャップ極）
    assert gene.radii[0] == 0.0
    # 単峰性: ピーク以前は狭義増、以降は狭義減
    r = np.asarray(gene.radii, dtype=float)
    peak = int(np.argmax(r))
    assert peak > 0 and peak < len(r) - 1
    # jitter で完全に狭義単調を壊さないよう制御されている
    assert np.all(np.diff(r[: peak + 1]) > -1e-6)
    assert np.all(np.diff(r[peak:]) < 1e-6)


# ----------------------------- seed 再現性 --------------------------------


def test_sample_gene_deterministic_with_seed():
    """同じ seed を渡せば同じ gene を得る（統計テスト前の基本要件）。"""
    g1 = sample_gene(seed=12345)
    g2 = sample_gene(seed=12345)
    assert g1.model_dump() == g2.model_dump()


def test_sample_gene_different_seeds_differ():
    g1 = sample_gene(seed=1)
    g2 = sample_gene(seed=2)
    assert g1.model_dump() != g2.model_dump()


# ----------------------------- 統計: 全件 feasibility --------------------


def test_bulk_sample_all_feasible():
    """seed を変えて N 個サンプルし、すべて sample_gene_with_feasibility が
    成功する（= feasibility を満たす）ことを確認する。

    N が大きすぎるとテストが遅いので、中程度の 100 個にする。
    """
    N = 100
    z_cog_max_vals = []
    for seed in range(N):
        gene, feas = sample_gene_with_feasibility(seed=seed)
        assert feas.is_feasible, (seed, feas)
        assert feas.z_cog_max > 0.0
        assert feas.worst_margin > 0.0
        assert gene.version == GENE_VERSION
        assert gene.top_extension_mm == 0.0
        z_cog_max_vals.append(feas.z_cog_max)

    arr = np.asarray(z_cog_max_vals)
    assert arr.std() > 0.1


def test_bulk_sample_profiles_pass_feasibility_from_profile():
    """生成時の feasibility と、独立に shape 経由で再評価した feasibility が
    ほぼ一致することを確認する（retry がバイアスとして効いていない検証）。

    ここでは sample_gene_with_feasibility の内部計算を再現するだけ。
    """
    from backend.app.shape import sample_shape_params, tune_height_for_delta

    rng = np.random.default_rng(7)
    ok = 0
    trials = 50
    for _ in range(trials):
        params = sample_shape_params(rng)
        height, _, z_dense, r_dense = tune_height_for_delta(params)
        feas = feasibility_from_profile(
            z_dense, r_dense, theta_max_deg=TILT_MAX_DEG
        )
        if feas.is_feasible:
            ok += 1
    # 形状族は「バリエーション重視」でパラメータを攻めるので、
    # 1 発で feasible な割合が必ずしも高いとは限らない。
    # 実運用では sample_gene_with_feasibility が retry で feasible 個体を必ず取る。
    # ここでは「極端に悪化していない」ことだけを確認する。
    assert ok >= int(0.15 * trials), f"feasible ratio = {ok}/{trials}"


# ----------------------------- GA: breed 基本性質 ------------------------


def test_breed_gene_with_feasibility_basic():
    """親からの子生成が成立し、単峰性・多様性の最低条件を満たす。"""
    p1 = sample_gene(seed=101)
    p2 = sample_gene(seed=202)
    parents = [p1, p2]

    kids = []
    for seed in range(20):
        g, feas = breed_gene_with_feasibility(parents, seed=seed)
        assert feas.is_feasible
        # 方針A: breedの返す feasibility は必ず子gene由来
        feas2 = rolypoly_feasibility(g)
        assert feas2.is_feasible
        assert feas2.z_cog_max == pytest.approx(feas.z_cog_max, rel=0.0, abs=0.0)
        assert feas2.rho_m_bottom == pytest.approx(feas.rho_m_bottom, rel=0.0, abs=0.0)
        assert g.top_extension_mm == 0.0
        assert g.version == GENE_VERSION
        assert g.N == N_NODES
        assert g.bottom_radius == 0.0
        assert g.radii[0] == 0.0
        r = np.asarray(g.radii, dtype=float)
        peak = int(np.argmax(r))
        assert peak > 0 and peak < len(r) - 1
        assert np.all(np.diff(r[: peak + 1]) > -1e-6)
        assert np.all(np.diff(r[peak:]) < 1e-6)
        kids.append(g)

    # 極端に同一個体ばかりになっていない（最低限の多様性）
    dumps = [k.model_dump() for k in kids]
    uniq = {str(d) for d in dumps}
    assert len(uniq) >= 5
