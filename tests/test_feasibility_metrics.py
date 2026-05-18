"""z_cog_max が smooth_profile 経由で 0 にならないことの回帰テスト。

役割: 生成時 feasibility と compute_metrics 連携の回帰ガード。
働き: サンプル gene・カットスイープ・既存 DB 設計で z_cog_max が正の有限値になることを検証する。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from backend.app.feasibility_metrics import feasibility_extras_for_gene
from backend.app.gene import sample_gene_with_feasibility
from backend.app.metrics import compute_metrics
from backend.app.models import Gene
from backend.app.physics import rolypoly_feasibility
from backend.app.profile_extension import feasibility_profile


def test_compute_metrics_uses_generation_feasibility():
    gene, feas = sample_gene_with_feasibility(seed=42)
    metrics = compute_metrics(gene, feasibility=feas)
    assert metrics.z_cog_max is not None
    assert metrics.z_cog_max == pytest.approx(feas.z_cog_max, rel=0, abs=1e-9)


def test_compute_metrics_without_feasibility_returns_positive_z_cog_max():
    gene, _ = sample_gene_with_feasibility(seed=7)
    metrics = compute_metrics(gene)
    assert metrics.z_cog_max is not None
    assert metrics.z_cog_max > 0.0


def test_rolypoly_feasibility_positive_for_sampled_gene():
    gene, _feas = sample_gene_with_feasibility(seed=100)
    feas2 = rolypoly_feasibility(gene)
    assert feas2.is_feasible
    assert feas2.z_cog_max > 0.0


def test_cut_height_sweep_changes_z_cog_with_extension():
    from pathlib import Path

    path = Path("docs/designs/6d7afe17fed27c7c/gene.json")
    if not path.is_file():
        pytest.skip("docs design gene missing")
    gene = Gene.model_validate_json(path.read_text())
    gene = gene.model_copy(update={"top_extension_mm": 30.0, "top_cut_angle_deg": 35.0})
    vals = [
        feasibility_extras_for_gene(
            gene.model_copy(update={"top_cut_height_mm": h})
        )["z_cog_max"]
        for h in (25.0, 40.0, 55.0)
    ]
    assert all(v is not None for v in vals)
    assert len({round(v, 3) for v in vals}) > 1


def test_angled_cut_lowers_z_cog_max_vs_uncut():
    gene, _ = sample_gene_with_feasibility(seed=7)
    uncut = feasibility_extras_for_gene(gene)
    assert uncut["z_cog_max"] is not None

    z, r = feasibility_profile(gene)
    z_peak = float(z[int(np.argmax(r))])
    cut_h = max(5.0, 0.45 * z_peak)

    cut_gene = gene.model_copy(
        update={
            "top_cut_height_mm": cut_h,
            "top_cut_angle_deg": 25.0,
        }
    )
    cut = feasibility_extras_for_gene(cut_gene)
    assert cut["z_cog_max"] is not None
    assert cut["z_cog_max"] < uncut["z_cog_max"]


def test_compute_metrics_with_cut_has_z_cog_max():
    gene, _ = sample_gene_with_feasibility(seed=7)
    z, r = feasibility_profile(gene)
    z_peak = float(z[int(np.argmax(r))])
    gene = gene.model_copy(
        update={
            "top_cut_height_mm": max(5.0, 0.5 * z_peak),
            "top_cut_angle_deg": 30.0,
        }
    )
    m = compute_metrics(gene)
    assert m.z_cog_max is not None
    assert m.z_cog_max > 0.0


@pytest.mark.skipif(
    not Path("data/app.db").is_file(),
    reason="local app.db not present",
)
def test_existing_db_design_recomputes_z_cog_max():
    row = sqlite3.connect("data/app.db").execute(
        "SELECT gene_json FROM designs LIMIT 1"
    ).fetchone()
    gene = Gene.model_validate_json(row[0])
    metrics = compute_metrics(gene)
    assert metrics.z_cog_max is not None
    assert metrics.z_cog_max > 0.0
