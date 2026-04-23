"""Metrics computation from gene.

This module is intentionally backend-only and limited to numeric metrics
needed for storage / API responses. Asset generation (SVG/mesh/STL/GLB) is
handled in the frontend per DESIGN_DECISIONS.md.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from .models import Gene, Metrics
from .smoothing import smooth_profile


def profile_points(
    gene: Gene,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return dense (z, r) samples for the revolved profile."""

    return smooth_profile(gene)


def compute_metrics(
    gene: Gene,
) -> Metrics:
    """Compute volume / height / max_width / centroid_z.

    Each segment between samples is treated as a frustum and integrated
    analytically.
    """

    z, r = profile_points(gene)
    dz = np.diff(z)
    a = r[:-1]
    b = r[1:]

    # Volume per frustum.
    k = a * a + a * b + b * b  # >= 0
    vol_i = (np.pi / 3.0) * dz * k

    # Centroid per frustum (global z).
    eps = 1e-12
    z_c_local = dz * (a * a + 2.0 * a * b + 3.0 * b * b) / (4.0 * np.maximum(k, eps))
    z_c_global = z[:-1] + z_c_local

    volume = float(np.sum(vol_i))
    centroid_z = float(np.sum(vol_i * z_c_global) / volume) if volume > 0.0 else 0.0

    return Metrics(
        volume=volume,
        height=float(gene.height),
        max_width=float(2.0 * np.max(r)),
        centroid_z=centroid_z,
    )

