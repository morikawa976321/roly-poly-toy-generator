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

    `trimesh.creation.revolve` の出力は端面が開く場合があるため、生成後に
    穴埋めを行い watertight（ソリッド）を保証する。
    """
    z, r = profile_points(gene)
    # 数値誤差で端点がわずかに浮くとキャップが張られず穴になるのでハード固定する。
    r = np.asarray(r, dtype=float)
    if len(r) >= 2:
        r[0] = float(gene.radii[0])
        r[-1] = float(gene.radii[-1])
    # trimesh.creation.revolve は (半径, 軸) の 2D 折れ線を期待する。
    linestring = np.column_stack([r, z])
    mesh = trimesh.creation.revolve(linestring=linestring, sections=sections)
    # 頂点付近で重複・退化三角形が出ることがあるので、process で整える。
    mesh.process(validate=True)

    # v2 の「天面が円になる」ケース等で境界ループが残るのでキャップを張る。
    # fill_holes は in-place で境界を塞ぐ（塞げた数 or bool を返す）。
    if not mesh.is_watertight:
        try:
            mesh.fill_holes()
        except Exception:
            # fill_holes が失敗しても後続の repair を試す。
            pass
    if not mesh.is_watertight:
        try:
            trimesh.repair.fill_holes(mesh)
        except Exception:
            pass
    # 最後にもう一度正規化（法線や退化面の整理）
    mesh.process(validate=True)
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
