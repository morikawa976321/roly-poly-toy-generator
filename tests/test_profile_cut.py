import math

import numpy as np

from backend.app.mesh_plane_cut import clip_mesh_below_plane, cut_would_change
from backend.app.mesh_revolve import revolve_mesh
from backend.app.models import Gene
from backend.app.profile_extension import effective_profile
from backend.app.smoothing import smooth_profile


def _sample_gene(**kw) -> Gene:
    n = 36
    radii = [0.0]
    for i in range(1, n - 1):
        t = i / (n - 1)
        radii.append(20.0 * math.sin(math.pi * t))
    radii.append(2.0)
    data = dict(
        version=2,
        N=n,
        height=50.0,
        bottom_radius=0.0,
        radii=radii,
        z_warp=2.0,
        top_extension_mm=0.0,
        top_cut_height_mm=0.0,
        top_cut_angle_deg=0.0,
    )
    data.update(kw)
    return Gene(**data)


def test_horizontal_mesh_cut_reduces_height():
    gene = _sample_gene(top_cut_height_mm=40.0)
    z, r = effective_profile(gene)
    verts, tris = revolve_mesh(z, r)
    cut_verts, _ = clip_mesh_below_plane(verts, tris, 40.0, 0.0)
    assert float(np.max(cut_verts[:, 2])) <= 40.0 + 1e-2


def test_cut_mesh_cap_is_watertight():
    """切断面キャップ後も同一位置の各エッジが2面で共有される。"""
    gene = _sample_gene(top_cut_height_mm=40.0, top_cut_angle_deg=12.0)
    z, r = effective_profile(gene)
    verts, tris = revolve_mesh(z, r, radial_segments=32)
    cut_verts, cut_tris = clip_mesh_below_plane(verts, tris, 40.0, 12.0)
    edge_count: dict[str, int] = {}

    def pos_key(i: int) -> str:
        v = cut_verts[i]
        return f"{round(v[0]*1e4)}:{round(v[1]*1e4)}:{round(v[2]*1e4)}"

    def add_edge(a: int, b: int) -> None:
        ka, kb = pos_key(a), pos_key(b)
        key = f"{ka}|{kb}" if ka < kb else f"{kb}|{ka}"
        edge_count[key] = edge_count.get(key, 0) + 1

    for tri in cut_tris:
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        assert a != b and b != c and c != a
        add_edge(a, b)
        add_edge(b, c)
        add_edge(c, a)

    for key, cnt in edge_count.items():
        assert cnt == 2, f"edge {key} shared by {cnt} faces"


def test_angled_mesh_cut_breaks_symmetry():
    z0, r0 = smooth_profile(_sample_gene())
    verts, tris = revolve_mesh(z0, r0)
    z_cut = float(z0[-1]) - 5.0
    cut_verts, _ = clip_mesh_below_plane(verts, tris, z_cut, 15.0)
    mask_pos = cut_verts[:, 0] > 1.0
    mask_neg = cut_verts[:, 0] < -1.0
    assert np.any(mask_pos) and np.any(mask_neg)
    z_pos = float(np.max(cut_verts[mask_pos, 2]))
    z_neg = float(np.max(cut_verts[mask_neg, 2]))
    assert z_pos > z_neg + 0.5


def test_cut_fields_excluded_from_design_id():
    from backend.app.identify import design_id_for

    base = _sample_gene()
    cut = base.model_copy(
        update={"top_cut_height_mm": 30.0, "top_cut_angle_deg": 10.0}
    )
    assert design_id_for(base) == design_id_for(cut)
