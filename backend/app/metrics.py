"""Metrics computation from gene.

This module is intentionally backend-only and limited to numeric metrics
needed for storage / API responses. Asset generation (SVG/mesh/STL) is
handled in the frontend per README.md.
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np

from .mesh_plane_cut import clip_mesh_below_plane, cut_would_change, mesh_volume
from .mesh_revolve import revolve_mesh
from .models import Gene, Metrics
from .physics import feasibility_from_profile
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
) -> Metrics:
    """Compute all stored metrics for a gene (including extension and feasibility)."""

    z, r = profile_points(gene)
    feas = feasibility_from_profile(z, r, smooth_derivatives=False)
    extras = {
        "bottom_curvature_radius": feas.rho_m_bottom,
        "z_cog_max": feas.z_cog_max if feas.z_cog_max > 0.0 else None,
    }

    z_cut = float(getattr(gene, "top_cut_height_mm", 0.0) or 0.0)
    angle = float(getattr(gene, "top_cut_angle_deg", 0.0) or 0.0)
    tan_a = math.tan(math.radians(angle)) if abs(angle) > 1e-12 else 0.0

    verts, tris = revolve_mesh(z, r, radial_segments=96)
    if cut_would_change(verts, z_cut, tan_a):
        cut_verts, cut_tris = clip_mesh_below_plane(verts, tris, z_cut, angle)
        volume, centroid_z = mesh_volume(cut_verts, cut_tris)
        z_max = float(np.max(cut_verts[:, 2])) if len(cut_verts) else 0.0
        max_r = float(np.max(np.hypot(cut_verts[:, 0], cut_verts[:, 1]))) if len(cut_verts) else 0.0
        return Metrics(
            volume=volume,
            height=z_max,
            max_width=2.0 * max_r,
            centroid_z=centroid_z,
            **extras,
        )

    base = compute_metrics_from_profile(z, r)
    return base.model_copy(update=extras)
