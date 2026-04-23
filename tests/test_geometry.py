from __future__ import annotations

import pytest


def test_build_revolve_mesh_is_watertight_for_generated_genes():
    trimesh = pytest.importorskip("trimesh")

    from backend.app.gene import sample_gene
    from backend.app.geometry import build_revolve_mesh

    # seed 固定で再現可能な範囲を複数確認（退化しやすい端面も含む）。
    for seed in (0, 1, 2, 3, 4, 42, 123, 999):
        gene = sample_gene(seed=seed)
        mesh = build_revolve_mesh(gene, sections=128)
        assert isinstance(mesh, trimesh.Trimesh)
        assert mesh.is_watertight, f"seed={seed} r_top={gene.radii[-1]}"


def test_build_revolve_mesh_handles_rt_zero_tip():
    pytest.importorskip("trimesh")

    from backend.app.config import N_NODES
    from backend.app.geometry import build_revolve_mesh
    from backend.app.models import Gene

    # 上端を尖らせる（rt=0）ケースでも、境界が残らないことを確認。
    radii = [0.0] + [10.0] * (N_NODES - 2) + [0.0]
    gene = Gene(version=2, N=N_NODES, height=50.0, bottom_radius=0.0, radii=radii, z_warp=2.0)
    mesh = build_revolve_mesh(gene, sections=128)
    assert mesh.is_watertight

