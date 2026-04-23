"""gene の折れ線プロファイルを滑らか化する比較用モジュール（一時的）。

現行の gene は N_NODES 個の (z, r) 制御点から成る単峰な折れ線プロファイル。
このモジュールは、同じ gene を入力として、複数の滑らか化手法で密な
(z, r) サンプル列を返す。3D メッシュ化・体積計算・サムネイル描画の
下流処理はどれもこの (z, r) 列だけを前提にしているので、ここを差し替える
だけで全体の見た目が切り替わる。

比較対象は 2 手法:
    - BSPLINE  : 3 次クランプト B-スプライン。radii を制御多角形として
                  扱い、全体 C² で滑らか。variation-diminishing 性より
                  制御多角形の単峰性が曲線の単峰性に引き継がれる。
                  両端点（z=0 と z=height）は制御点を厳密に通る。
    - GAUSSIAN : 折れ線を密サンプリングしたあと 1D ガウシアンで平滑化。
                  単峰入力 + 対称カーネルなので実用上単峰性は保たれる。
                  端点は畳み込みで崩れるため、事後に端点をハード固定する。
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Tuple

import numpy as np
from scipy.interpolate import BSpline
from scipy.ndimage import gaussian_filter1d

if TYPE_CHECKING:
    from .models import Gene
else:
    # 実行環境によっては pydantic が無いことがあるため、
    # import 時に落ちないよう型は遅延させる（実体は smooth_profile 呼び出し側が担保）。
    Gene = Any  # type: ignore


class SmoothingMethod(str, Enum):
    BSPLINE = "bspline"
    GAUSSIAN = "gaussian"


# 折れ線制御点を中間点で細分化するときの倍率。
# 大きいほど滑らかさが忠実に再現されるが、メッシュ頂点数が増えて重くなる。
DENSE_FACTOR: int = 24


def _effective_z_warp(z_warp: Any) -> float:
    """Gene.z_warp（Optional[float]）を有効な指数に正規化する。

    None や 0 以下は等間隔扱い（= 1.0）にフォールバックする。
    """
    if z_warp is None:
        return 1.0
    try:
        w = float(z_warp)
    except (TypeError, ValueError):
        return 1.0
    return w if w > 0.0 else 1.0


def gene_z_nodes(gene: Gene) -> np.ndarray:
    """Gene の制御点 z 座標を返す: ``z_i = height · (i/(N-1))**z_warp``。

    ``z_warp=1.0`` なら等間隔。v2 は 2.0 で z=0 付近を密にサンプリングする。
    """
    n = int(gene.N)
    height = float(gene.height)
    w = _effective_z_warp(getattr(gene, "z_warp", None))
    u = np.linspace(0.0, 1.0, n)
    return height * u ** w


def _dense_z(height: float, n_nodes: int, factor: int, z_warp: float = 1.0) -> np.ndarray:
    """制御点と端点を共有する、factor 倍に細かい z サンプルを返す。

    z_warp を与えると、同じ配置規則を dense 側にも適用し、制御点位置と
    dense サンプルが厳密に一致する（= 区間内部にサブサンプルが均等に入る）。
    """
    u = np.linspace(0.0, 1.0, (n_nodes - 1) * factor + 1)
    return height * u ** z_warp


def _bspline(r_nodes: np.ndarray, n_dense: int) -> np.ndarray:
    """3 次クランプト B-スプラインで radii を制御多角形として評価する。

    クランプトノット（両端で多重度 k+1=4）のおかげで、曲線は最初と最後の
    制御点を厳密に通る（= r(0)=bottom_radius, r(height)=0）。内部は制御点
    を通らないが、variation-diminishing 性により単峰な制御多角形から
    単峰な曲線が得られる。

    z(u) に対して r(u) を評価するが、z 方向の制御点は等間隔なので z(u) は
    u の 1 次式となり、呼び出し側で z_dense と 1 対 1 に対応付ければよい
    （= 別途 z 用 B-スプラインは不要）。
    """
    k = 3
    n = len(r_nodes)
    if n < k + 1:
        # 制御点が足りない場合は線形補間にフォールバック。
        u = np.linspace(0.0, 1.0, n_dense)
        return np.interp(u, np.linspace(0.0, 1.0, n), r_nodes)

    # クランプトノット: 両端に 0, 1 をそれぞれ k+1 個、中間に均等な (n-k-1) 点。
    t = np.concatenate(
        [
            np.zeros(k),
            np.linspace(0.0, 1.0, n - k + 1),
            np.ones(k),
        ]
    )
    spline = BSpline(t, r_nodes, k, extrapolate=False)
    u_dense = np.linspace(0.0, 1.0, n_dense)
    return np.asarray(spline(u_dense), dtype=float)


def _gaussian(
    z_nodes: np.ndarray,
    r_nodes: np.ndarray,
    z_dense: np.ndarray,
) -> np.ndarray:
    """折れ線を密に線形サンプリング → 対称ガウシアン畳み込み。

    カーネル幅 sigma は「制御点 1 ピッチぶん」に相当する DENSE_FACTOR 個の
    サンプルに設定する（= 約 1 ノード分の平滑化）。端は mode='nearest' で
    外挿し、最後に両端の値を bottom_radius / 0 にハード固定する。
    """
    r_lin = np.interp(z_dense, z_nodes, r_nodes)
    sigma = float(DENSE_FACTOR)
    return np.asarray(
        gaussian_filter1d(r_lin, sigma=sigma, mode="nearest"),
        dtype=float,
    )


def smooth_profile(
    gene: Gene,
    method: SmoothingMethod = SmoothingMethod.BSPLINE,
) -> Tuple[np.ndarray, np.ndarray]:
    """gene から (z, r) サンプル列を計算する。

    DENSE_FACTOR 倍に細かい z でサンプルした (z_dense, r_dense) を返す。

    v2 gene（``z_warp`` 指定あり）では、制御点 z_i = height·(i/(N-1))**z_warp と
    同じ配置則で dense z を生成する。これにより BSpline の u 空間評価と z 空間
    評価が厳密に対応し、かつ球キャップ極付近（z=0 近傍）のサンプルが密になって
    √z 型の曲率を潰さずに再現できる。

    どの手法でも以下を保証する:
        r[0] == gene.radii[0]
        r[-1] == gene.radii[-1]
        r >= 0
    """
    n = gene.N
    height = float(gene.height)
    w = _effective_z_warp(getattr(gene, "z_warp", None))

    z_nodes = gene_z_nodes(gene)
    r_nodes = np.asarray(gene.radii, dtype=float)

    z_dense = _dense_z(height, n, DENSE_FACTOR, z_warp=w)

    if method == SmoothingMethod.BSPLINE:
        # BSpline は radii を制御多角形として u ∈ [0,1] 空間で評価する。
        # dense 側の u は z_dense の配置規則（= 同じ z_warp）と整合するよう
        # 作ってあるので、そのまま 1 対 1 に z_dense と対応付けできる。
        r_dense = _bspline(r_nodes, len(z_dense))
    elif method == SmoothingMethod.GAUSSIAN:
        r_dense = _gaussian(z_nodes, r_nodes, z_dense)
    else:
        raise ValueError(f"Unknown smoothing method: {method}")

    # 端点のハード固定 + 負値のクリップ（数値誤差対策）。
    # v2 gene では r_nodes[0]=0（球キャップの極点）、r_nodes[-1]=rt≥0（上端丸め半径）。
    # v1 gene では r_nodes[0]=bottom_radius>0、r_nodes[-1]=0。どちらもそのまま使う。
    r_dense[0] = float(r_nodes[0])
    r_dense[-1] = float(r_nodes[-1])
    np.maximum(r_dense, 0.0, out=r_dense)
    return z_dense, r_dense
