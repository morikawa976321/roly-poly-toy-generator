"""gene から SVG サムネイルを描画するモジュール。

サムネイルは、z 軸の両側にミラーした完全な断面 + 重心位置に小さな
十字マーカーを重ねたもの。表示上は z が上方向に増えるように座標系を反転して
いる。
"""

from __future__ import annotations

import numpy as np

from .geometry import profile_points
from .models import Gene, Metrics


def render_thumbnail_svg(
    gene: Gene,
    metrics: Metrics,
) -> str:
    z, r = profile_points(gene)
    height = float(gene.height)
    max_r = float(r.max())

    # (x, z) 空間で左右ミラーした閉多角形を構築する:
    # 右側を下から上へ、続けて左側（符号反転）を上から下へ並べる。
    xs = list(r) + list(-r[::-1])
    zs = list(z) + list(z[::-1])

    # 表示座標への変換: svg_x = x、svg_y = height - z（z=0 が下端になる）。
    pts = [(x, height - zz) for x, zz in zip(xs, zs)]

    pad = max(2.0, 0.05 * max(height, max_r * 2.0))
    view_x = -max_r - pad
    view_y = -pad
    view_w = 2.0 * max_r + 2.0 * pad
    view_h = height + 2.0 * pad

    points_attr = " ".join(f"{x:.3f},{y:.3f}" for x, y in pts)

    # 重心マーカー: z 軸上、z = centroid_z の位置に十字で描く。
    cx = 0.0
    cy = height - metrics.centroid_z
    cross_size = max(1.0, 0.03 * max(height, max_r * 2.0))

    # 「θ_max まで自己復元するために重心をこれより下にする必要がある」上限位置。
    # 現在の重心（赤）と同じ座標系で、z = z_cog_max に青い十字を描く。
    z_cog_max = metrics.z_cog_max
    cy_req = None
    if z_cog_max is not None and np.isfinite(z_cog_max):
        cy_req = height - float(z_cog_max)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_x:.3f} {view_y:.3f} {view_w:.3f} {view_h:.3f}" preserveAspectRatio="xMidYMid meet">
  <g>
    <polygon points="{points_attr}" fill="#cbd5e1" stroke="#334155" stroke-width="{max(0.3, cross_size * 0.15):.3f}" stroke-linejoin="round" />
    <line x1="{-max_r - pad * 0.5:.3f}" y1="{cy:.3f}" x2="{max_r + pad * 0.5:.3f}" y2="{cy:.3f}" stroke="#94a3b8" stroke-width="{max(0.2, cross_size * 0.08):.3f}" stroke-dasharray="{cross_size * 0.6:.3f},{cross_size * 0.4:.3f}" />
    {"" if cy_req is None else f'<g stroke="#3b82f6" stroke-width="{max(0.3, cross_size * 0.2):.3f}" stroke-linecap="round"><line x1="{cx - cross_size:.3f}" y1="{cy_req:.3f}" x2="{cx + cross_size:.3f}" y2="{cy_req:.3f}" /><line x1="{cx:.3f}" y1="{cy_req - cross_size:.3f}" x2="{cx:.3f}" y2="{cy_req + cross_size:.3f}" /></g>'}
    <g stroke="#ef4444" stroke-width="{max(0.3, cross_size * 0.2):.3f}" stroke-linecap="round">
      <line x1="{cx - cross_size:.3f}" y1="{cy:.3f}" x2="{cx + cross_size:.3f}" y2="{cy:.3f}" />
      <line x1="{cx:.3f}" y1="{cy - cross_size:.3f}" x2="{cx:.3f}" y2="{cy + cross_size:.3f}" />
    </g>
  </g>
</svg>
"""
    return svg
