"""ジオメトリ処理: gene から metrics とメッシュを計算する。

gene は折れ線 r(z) プロファイルを表しており、本モジュールでは以下を行う:
- z 値を等間隔に展開する。
- (z, r) を細かくサンプリングする。
- 各サンプル区間を円錐台とみなし、公式で体積・重心・最大幅を解析的に
  求める（サンプル密度が十分なら平滑曲線の回転体体積の良い近似になる）。
- 3D 表示用に回転体メッシュを作り、GLB バイト列としてエクスポートする。
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import trimesh

from .config import REVOLVE_SEGMENTS
from .models import Gene, Metrics
from .smoothing import smooth_profile


def profile_points(
    gene: Gene,
) -> Tuple[np.ndarray, np.ndarray]:
    """(z, r) サンプル列を返す。

    DENSE_FACTOR 倍に細かいサンプルが返る。どれも r[0]=bottom_radius, r[-1]=0 を満たす。
    """
    return smooth_profile(gene)


def compute_metrics(
    gene: Gene,
) -> Metrics:
    """volume / height / max_width / centroid_z を求める。

    サンプル列の各区間を円錐台とみなして解析的に積分する。下端半径 a を
    z_i、上端半径 b を z_i + dz とすると:

        V = (pi/3) * dz * (a^2 + a*b + b^2)
        z_c （区間底からの相対値） = dz * (a^2 + 2ab + 3b^2)
                                     / (4 * (a^2 + ab + b^2))
    """
    z, r = profile_points(gene)
    dz = np.diff(z)
    a = r[:-1]
    b = r[1:]

    # 円錐台ごとの体積
    k = a * a + a * b + b * b  # 非負
    vol_i = (np.pi / 3.0) * dz * k

    # 円錐台ごとの重心 z（グローバル座標）
    eps = 1e-12
    z_c_local = dz * (a * a + 2.0 * a * b + 3.0 * b * b) / (4.0 * np.maximum(k, eps))
    z_c_global = z[:-1] + z_c_local

    volume = float(np.sum(vol_i))
    if volume > 0.0:
        centroid_z = float(np.sum(vol_i * z_c_global) / volume)
    else:
        centroid_z = 0.0

    return Metrics(
        volume=volume,
        height=float(gene.height),
        max_width=float(2.0 * np.max(r)),
        centroid_z=centroid_z,
    )


def build_revolve_mesh(
    gene: Gene,
    sections: int = REVOLVE_SEGMENTS,
) -> trimesh.Trimesh:
    """2D プロファイルを z 軸回りに回転させて「閉じた」3D メッシュを作る。

    gene v1/v2 で端点条件が異なる:
    - v1: r(0)=bottom_radius>0, r(height)=0（上端は軸上、下端は円盤キャップが必要）
    - v2: r(0)=0（下端は軸上）, r(height)=rt>=0（上端が円盤になり得るのでキャップが必要）

    v2 gene では通常 r(height)=rt>0 のため、側面だけでは天面に境界ループ（穴）が残る。
    そのため、ここでは端面（天面/底面）のキャップを明示的に生成し、決定的に
    watertight（ソリッド）なメッシュを構築する。
    """
    z, r = profile_points(gene)
    # 数値誤差で端点がわずかに浮くとキャップが張られず穴になるのでハード固定する。
    r = np.asarray(r, dtype=float)
    if len(r) >= 2:
        r[0] = float(gene.radii[0])
        r[-1] = float(gene.radii[-1])

    def _revolve_watertight(
        z_line: np.ndarray, r_line: np.ndarray, *, n_theta: int, eps: float = 1e-6
    ) -> trimesh.Trimesh:
        z_line = np.asarray(z_line, dtype=float).reshape(-1)
        r_line = np.asarray(r_line, dtype=float).reshape(-1)
        if z_line.size != r_line.size or z_line.size < 2:
            raise ValueError("profile must have same-length z and r with >= 2 points")
        if n_theta < 3:
            raise ValueError("n_theta must be >= 3")

        # 数値誤差で極小の半径が残ると、境界が残って watertight を壊しやすい。
        # 端点は「軸上にあるべき」なら 0 にスナップする。
        r0 = float(r_line[0])
        r1 = float(r_line[-1])
        if abs(r0) <= eps:
            r0 = 0.0
        if abs(r1) <= eps:
            r1 = 0.0
        r_line = r_line.copy()
        r_line[0] = r0
        r_line[-1] = r1

        theta = np.linspace(0.0, 2.0 * np.pi, int(n_theta), endpoint=False)
        ct = np.cos(theta)
        st = np.sin(theta)

        verts: list[tuple[float, float, float]] = []
        ring_index: list[int] = []
        axis_index: list[int | None] = []

        for zi, ri in zip(z_line.tolist(), r_line.tolist()):
            if ri <= eps:
                axis_index.append(len(verts))
                ring_index.append(-1)
                verts.append((0.0, 0.0, float(zi)))
            else:
                axis_index.append(None)
                ring_index.append(len(verts))
                for c, s in zip(ct.tolist(), st.tolist()):
                    verts.append((float(ri * c), float(ri * s), float(zi)))

        faces: list[tuple[int, int, int]] = []

        def ring_vert(i: int, j: int) -> int:
            base = ring_index[i]
            if base < 0:
                raise RuntimeError("ring_vert called for axis point")
            return base + (j % n_theta)

        # 側面（隣接断面を接続）
        for i in range(len(z_line) - 1):
            r_a = float(r_line[i])
            r_b = float(r_line[i + 1])
            a_axis = axis_index[i]
            b_axis = axis_index[i + 1]
            for j in range(n_theta):
                jn = (j + 1) % n_theta
                if r_a <= eps and r_b <= eps:
                    continue
                if r_a <= eps:
                    # 下側が軸点（扇形）
                    assert a_axis is not None
                    b0 = ring_vert(i + 1, j)
                    b1 = ring_vert(i + 1, jn)
                    # 外向きになるように順序を揃える（z が上方向）
                    faces.append((b0, b1, a_axis))
                elif r_b <= eps:
                    # 上側が軸点（扇形）
                    assert b_axis is not None
                    a0 = ring_vert(i, j)
                    a1 = ring_vert(i, jn)
                    faces.append((a1, a0, b_axis))
                else:
                    a0 = ring_vert(i, j)
                    a1 = ring_vert(i, jn)
                    b0 = ring_vert(i + 1, j)
                    b1 = ring_vert(i + 1, jn)
                    # 四角形を 2 三角形に分割
                    faces.append((a0, b0, b1))
                    faces.append((a0, b1, a1))

        # 天面キャップ（上端が円なら円盤で塞ぐ）
        z_top = float(z_line[-1])
        if float(r_line[-1]) > eps:
            top_center = len(verts)
            verts.append((0.0, 0.0, z_top))
            top_i = len(z_line) - 1
            for j in range(n_theta):
                jn = (j + 1) % n_theta
                a = ring_vert(top_i, j)
                b = ring_vert(top_i, jn)
                # 上面の法線が +z を向く向き
                faces.append((a, b, top_center))

        # 底面キャップ（v1 互換: 下端が円なら円盤で塞ぐ）
        z_bot = float(z_line[0])
        if float(r_line[0]) > eps:
            bot_center = len(verts)
            verts.append((0.0, 0.0, z_bot))
            bot_i = 0
            for j in range(n_theta):
                jn = (j + 1) % n_theta
                a = ring_vert(bot_i, j)
                b = ring_vert(bot_i, jn)
                # 底面の法線が -z を向く向き
                faces.append((b, a, bot_center))

        mesh = trimesh.Trimesh(
            vertices=np.asarray(verts, dtype=float),
            faces=np.asarray(faces, dtype=np.int64),
            process=False,
        )
        # trimesh の process() は環境によって SciPy 依存（連結成分など）を踏むことがある。
        # ここでは決定的に構築した面をそのまま使い、軽量な後処理のみを試す。
        try:
            mesh.remove_duplicate_faces()
        except Exception:
            pass
        try:
            mesh.remove_degenerate_faces()
        except Exception:
            pass
        try:
            mesh.remove_unreferenced_vertices()
        except Exception:
            pass
        return mesh

    mesh = _revolve_watertight(z, r, n_theta=int(sections), eps=1e-6)
    if not mesh.is_watertight:
        # 後段で穴あきアセットがキャッシュされると永続的に壊れるため、ここで失敗扱いにする。
        raise RuntimeError(
            "build_revolve_mesh: generated mesh is not watertight "
            f"(sections={sections}, r0={float(r[0]):.6g}, r1={float(r[-1]):.6g}, "
            f"verts={int(mesh.vertices.shape[0])}, faces={int(mesh.faces.shape[0])})"
        )
    return mesh


def export_glb(mesh: trimesh.Trimesh) -> bytes:
    """メッシュを GLB のバイト列にエクスポートする。"""
    data = mesh.export(file_type="glb")
    if isinstance(data, str):
        data = data.encode("utf-8")
    return data


def export_stl(mesh: trimesh.Trimesh) -> bytes:
    """メッシュを STL のバイト列にエクスポートする。"""
    data = mesh.export(file_type="stl")
    if isinstance(data, str):
        data = data.encode("utf-8")
    return data
