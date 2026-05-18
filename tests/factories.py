"""テスト用 Gene / Metrics ファクトリ。

役割: API・storage・profile 系テストで共有する最小 gene / metrics 生成。
働き: スキーマ変更時の修正箇所を一箇所に集約する。
"""

from __future__ import annotations

import math
from typing import Any

from backend.app.models import Gene, Metrics


def make_gene(**overrides: Any) -> Gene:
    data: dict[str, Any] = dict(
        version=2,
        N=5,
        height=30.0,
        bottom_radius=0.0,
        radii=[0.0, 5.0, 10.0, 5.0, 0.0],
        z_warp=2.0,
        top_extension_mm=0.0,
        top_cut_height_mm=0.0,
        top_cut_angle_deg=0.0,
    )
    data.update(overrides)
    return Gene(**data)


def make_metrics(**overrides: Any) -> Metrics:
    data: dict[str, Any] = dict(
        volume=100.0,
        height=30.0,
        max_width=20.0,
        centroid_z=10.0,
        bottom_curvature_radius=25.0,
        z_cog_max=12.5,
    )
    data.update(overrides)
    return Metrics(**data)


def sample_gene_profile(**overrides: Any) -> Gene:
    """36 制御点・sin プロファイル（profile_cut / extension テスト用）。"""
    n = int(overrides.pop("N", 36))
    radii = [0.0]
    for i in range(1, n - 1):
        t = i / (n - 1)
        radii.append(20.0 * math.sin(math.pi * t))
    radii.append(float(overrides.pop("top_radius", 2.0)))
    data: dict[str, Any] = dict(
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
    data.update(overrides)
    return Gene(**data)
