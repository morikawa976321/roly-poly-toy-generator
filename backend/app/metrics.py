"""Metrics computation from gene.

This module is intentionally backend-only and limited to numeric metrics
needed for storage / API responses. Asset generation (SVG/mesh) is
handled in the frontend per README.md.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from .mesh_plane_cut import clip_mesh_below_plane, mesh_volume
from .mesh_revolve import revolve_mesh
from .models import Gene, Metrics
from .feasibility_metrics import feasibility_extras_for_gene
from .physics import Feasibility
from .profile_extension import effective_profile


def profile_points(
    gene: Gene,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return dense (z, r) samples for the revolved profile (extension included)."""

    return effective_profile(gene)


def compute_metrics_from_profile(
    z: np.ndarray,
    r: np.ndarray,
) -> Metrics:
    """Compute volume / height / max_width / centroid_z from a dense profile."""

    dz = np.diff(z)
    a = r[:-1]
    b = r[1:]

    k = a * a + a * b + b * b
    vol_i = (np.pi / 3.0) * dz * k

    eps = 1e-12
    z_c_local = dz * (a * a + 2.0 * a * b + 3.0 * b * b) / (4.0 * np.maximum(k, eps))
    z_c_global = z[:-1] + z_c_local

    volume = float(np.sum(vol_i))
    centroid_z = float(np.sum(vol_i * z_c_global) / volume) if volume > 0.0 else 0.0

    return Metrics(
        volume=volume,
        height=float(z[-1]),
        max_width=float(2.0 * np.max(r)),
        centroid_z=centroid_z,
    )


def compute_metrics(
    gene: Gene,
    feasibility: Optional[Feasibility] = None,
) -> Metrics:
    """Compute all stored metrics for a gene (including extension and feasibility).

    体積・高さ・幅・重心は常に effective_profile の回転体をカットしたメッシュから求め、
    フロントの 3D 表示と一致させる。clip は変更が無いとき元メッシュをそのまま返す。
    """

    extras = feasibility_extras_for_gene(gene, feasibility)
    z, r = profile_points(gene)

    z_cut = float(getattr(gene, "top_cut_height_mm", 0.0) or 0.0)
    angle = float(getattr(gene, "top_cut_angle_deg", 0.0) or 0.0)

    verts, tris = revolve_mesh(z, r, radial_segments=96)
    cut_verts, cut_tris = clip_mesh_below_plane(verts, tris, z_cut, angle)
    volume, centroid_z = mesh_volume(cut_verts, cut_tris)
    z_max = float(np.max(cut_verts[:, 2])) if len(cut_verts) else 0.0
    max_r = (
        float(np.max(np.hypot(cut_verts[:, 0], cut_verts[:, 1])))
        if len(cut_verts)
        else 0.0
    )
    return Metrics(
        volume=volume,
        height=z_max,
        max_width=2.0 * max_r,
        centroid_z=centroid_z,
        **extras,
    )
