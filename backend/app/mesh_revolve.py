"""
(z, r) プロファイルから回転体三角メッシュを生成。

役割: 子午面プロファイルの z 軸回転メッシュ化。
働き: フロント ``mesh.ts`` と同等。頂点・三角インデックスを返し、``metrics`` / ``mesh_plane_cut`` が利用する。
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def revolve_mesh(
    z_line: np.ndarray,
    r_line: np.ndarray,
    radial_segments: int = 96,
    eps: float = 1e-6,
) -> Tuple[np.ndarray, np.ndarray]:
    """頂点 (N,3) と三角インデックス (M,3) を返す。"""
    z_line = np.asarray(z_line, dtype=float)
    r_line = np.asarray(r_line, dtype=float)
    if len(z_line) != len(r_line) or len(z_line) < 2:
        raise ValueError("profile must have >= 2 points")
    if radial_segments < 3:
        raise ValueError("radial_segments must be >= 3")

    theta = np.linspace(0, 2 * np.pi, radial_segments, endpoint=False)
    verts: list[list[float]] = []
    ring_index: list[int] = []
    axis_index: list[int | None] = []

    for i in range(len(z_line)):
        zi = float(z_line[i])
        ri = 0.0 if abs(r_line[i]) <= eps else float(r_line[i])
        if ri <= eps:
            axis_index.append(len(verts))
            ring_index.append(-1)
            verts.append([0.0, 0.0, zi])
            continue
        axis_index.append(None)
        ring_index.append(len(verts))
        for t in theta:
            verts.append([ri * np.cos(t), ri * np.sin(t), zi])

    def ring_vert(i: int, j: int) -> int:
        base = ring_index[i]
        if base < 0:
            raise ValueError("ring_vert on axis")
        return base + (j % radial_segments)

    tris: list[list[int]] = []

    for i in range(len(z_line) - 1):
        ra = r_line[i]
        rb = r_line[i + 1]
        a_axis = axis_index[i]
        b_axis = axis_index[i + 1]
        for j in range(radial_segments):
            jn = (j + 1) % radial_segments
            if ra <= eps and rb <= eps:
                continue
            if ra <= eps:
                assert a_axis is not None
                tris.append([ring_vert(i + 1, jn), ring_vert(i + 1, j), a_axis])
            elif rb <= eps:
                assert b_axis is not None
                tris.append([ring_vert(i, j), ring_vert(i, jn), b_axis])
            else:
                a0 = ring_vert(i, j)
                a1 = ring_vert(i, jn)
                b0 = ring_vert(i + 1, j)
                b1 = ring_vert(i + 1, jn)
                tris.append([a0, b1, b0])
                tris.append([a0, a1, b1])

    if r_line[-1] > eps:
        top_center = len(verts)
        verts.append([0.0, 0.0, float(z_line[-1])])
        top_i = len(z_line) - 1
        for j in range(radial_segments):
            jn = (j + 1) % radial_segments
            tris.append([top_center, ring_vert(top_i, j), ring_vert(top_i, jn)])

    if r_line[0] > eps:
        bot_center = len(verts)
        verts.append([0.0, 0.0, float(z_line[0])])
        for j in range(radial_segments):
            jn = (j + 1) % radial_segments
            tris.append([ring_vert(0, jn), ring_vert(0, j), bot_center])

    return np.asarray(verts, dtype=float), np.asarray(tris, dtype=int)
