"""
gene から feasibility 付加指標を算出。

役割: ``z_cog_max`` / ``bottom_curvature_radius`` などカット後子午線に基づく指標。
働き: 上部カットが有効ならメッシュ子午線を再構成し ``physics`` を適用。``metrics`` / ``storage`` が利用する。
"""

from __future__ import annotations

import math
from typing import Iterator, Optional, Tuple

import numpy as np

from .config import REVOLVE_SEGMENTS
from .models import Gene
from .physics import Feasibility, feasibility_from_profile
from .profile_cut import (
    clip_open_profile_half,
    cut_profile_silhouette,
)
from .profile_extension import feasibility_profile

_CUT_EPS = 1e-6


def _gene_cut_params(gene: Gene) -> Tuple[float, float, float]:
    z_cut = float(getattr(gene, "top_cut_height_mm", 0.0) or 0.0)
    angle = float(getattr(gene, "top_cut_angle_deg", 0.0) or 0.0)
    tan_a = math.tan(math.radians(angle)) if abs(angle) > _CUT_EPS else 0.0
    return z_cut, tan_a, angle


def has_active_top_cut(gene: Gene) -> bool:
    z_cut, tan_a, _ = _gene_cut_params(gene)
    return z_cut > _CUT_EPS or abs(tan_a) > _CUT_EPS


def _mesh_silhouette_meridian(
    z: np.ndarray,
    r: np.ndarray,
    z_cut: float,
    angle_deg: float,
) -> Tuple[np.ndarray, np.ndarray]:
    from .mesh_plane_cut import clip_mesh_below_plane, cut_would_change
    from .mesh_revolve import revolve_mesh

    verts, tris = revolve_mesh(z, r, radial_segments=REVOLVE_SEGMENTS)
    tan_a = math.tan(math.radians(angle_deg)) if abs(angle_deg) > _CUT_EPS else 0.0
    if not cut_would_change(verts, z_cut, tan_a):
        return z, r
    cut_verts, _ = clip_mesh_below_plane(verts, tris, z_cut, angle_deg)
    by_z: dict[float, float] = {}
    for row in cut_verts:
        zz = round(float(row[2]) * 400.0) / 400.0
        rr = float(np.hypot(row[0], row[1]))
        by_z[zz] = max(by_z.get(zz, 0.0), rr)
    if not by_z:
        return z, r
    zs = np.array(sorted(by_z.keys()), dtype=float)
    rs = np.array([by_z[k] for k in zs], dtype=float)
    return zs, rs


def iter_feasibility_meridians(gene: Gene) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
    """feasibility 判定に使う子午面 (z, r) 列（カット後・複数候補）。"""
    z, r = feasibility_profile(gene)
    if not has_active_top_cut(gene):
        yield z, r
        return

    z_cut, tan_a, angle = _gene_cut_params(gene)
    sil = cut_profile_silhouette(z, r, z_cut, angle)
    yield sil.z_right, sil.r_right
    yield sil.z_left, sil.r_left

    # 傾斜カット時も z=const 平面でのクリップを評価（カット高さの変化に追従）
    if z_cut > _CUT_EPS and abs(tan_a) > _CUT_EPS:
        z_h, r_h = clip_open_profile_half(z, r, z_cut, 0.0, "right")
        yield z_h, r_h

    z_m, r_m = _mesh_silhouette_meridian(z, r, z_cut, angle)
    if len(z_m) >= 8:
        yield z_m, r_m


def _best_feasibility(meridians: Iterator[Tuple[np.ndarray, np.ndarray]]) -> Optional[Feasibility]:
    best: Optional[Feasibility] = None
    for z_m, r_m in meridians:
        if len(z_m) < 8:
            continue
        feas = feasibility_from_profile(z_m, r_m, smooth_derivatives=True)
        if feas.z_cog_max <= 0.0:
            continue
        if best is None or feas.z_cog_max < best.z_cog_max:
            best = feas
    return best


def feasibility_extras_for_gene(
    gene: Gene,
    feasibility: Optional[Feasibility] = None,
) -> dict[str, Optional[float]]:
    """z_cog_max / bottom_curvature_radius。カット時は候補子午面の最小 z_cog_max。"""
    if not has_active_top_cut(gene):
        if feasibility is not None and feasibility.z_cog_max > 0.0:
            return {
                "bottom_curvature_radius": feasibility.rho_m_bottom,
                "z_cog_max": feasibility.z_cog_max,
            }
        z, r = feasibility_profile(gene)
        feas = feasibility_from_profile(z, r, smooth_derivatives=True)
        return {
            "bottom_curvature_radius": feas.rho_m_bottom if feas.rho_m_bottom > 0.0 else None,
            "z_cog_max": feas.z_cog_max if feas.z_cog_max > 0.0 else None,
        }

    best = _best_feasibility(iter_feasibility_meridians(gene))
    if best is None:
        return {"bottom_curvature_radius": None, "z_cog_max": None}
    return {
        "bottom_curvature_radius": best.rho_m_bottom if best.rho_m_bottom > 0.0 else None,
        "z_cog_max": best.z_cog_max,
    }
