"""gene の折れ線プロファイルを滑らか化するモジュール。

現行の gene は N_NODES 個の (z, r) 制御点から成る単峰な折れ線プロファイル。
このモジュールは gene を入力として、密な (z, r) サンプル列を返す。
3D メッシュ化・体積計算・サムネイル描画の下流処理はどれもこの (z, r) 列だけを
前提にしている。

実装は「折れ線を密サンプリング → 1D ガウシアンで平滑化」。
単峰入力 + 対称カーネルなので実用上単峰性は保たれる。
端点は畳み込みで崩れるため、事後に端点をハード固定する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Tuple

import numpy as np

if TYPE_CHECKING:
    from .models import Gene
else:
    # 実行環境によっては pydantic が無いことがあるため、
    # import 時に落ちないよう型は遅延させる（実体は smooth_profile 呼び出し側が担保）。
    Gene = Any  # type: ignore


# 折れ線制御点を中間点で細分化するときの倍率。
# 大きいほど滑らかさが忠実に再現されるが、メッシュ頂点数が増えて重くなる。
DENSE_FACTOR: int = 24

# feasibility 判定専用: メッシュ用の DENSE_FACTOR 平滑化は曲率を過小評価し
# z_cog_max が 0 になる偽不合格が多い。パラメトリック生成時に近い軽い平滑化を使う。
FEASIBILITY_PROFILE_N: int = 281
FEASIBILITY_SMOOTH_SIGMA: float = 8.0

# 手法 5 (B3): 64 制御点 smoothing spline — tools/compare_profile_smoothing と同じ
B3_SPLINE_S: float = 0.8
# 密サンプル再フィット用: 64 点向け s を点数比でスケール（≈同程度の平滑化強度）
B3_REFIT_S_PER_NODE: float = B3_SPLINE_S


def _gaussian_filter1d(x: np.ndarray, sigma: float) -> np.ndarray:
    """1D Gaussian smoothing with nearest edge handling (SciPy-free)."""
    x = np.asarray(x, dtype=float)
    sigma = float(sigma)
    if not np.isfinite(sigma) or sigma <= 0.0:
        return x
    radius = int(max(3, round(4.0 * sigma)))
    xs = np.arange(-radius, radius + 1, dtype=float)
    k = np.exp(-0.5 * (xs / sigma) ** 2)
    k /= np.sum(k)
    pad_left = np.full(radius, x[0], dtype=float)
    pad_right = np.full(radius, x[-1], dtype=float)
    padded = np.concatenate([pad_left, x, pad_right])
    return np.convolve(padded, k, mode="valid")


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
        _gaussian_filter1d(r_lin, sigma=sigma),
        dtype=float,
    )


def smooth_profile(
    gene: Gene,
) -> Tuple[np.ndarray, np.ndarray]:
    """gene から (z, r) サンプル列を計算する。

    DENSE_FACTOR 倍に細かい z でサンプルした (z_dense, r_dense) を返す。

    v2 gene（``z_warp`` 指定あり）では、制御点 z_i = height·(i/(N-1))**z_warp と
    同じ配置則で dense z を生成する。これにより球キャップ極付近（z=0 近傍）の
    サンプルが密になって √z 型の曲率を潰さずに再現できる。

    以下を保証する:
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
    r_dense = _gaussian(z_nodes, r_nodes, z_dense)

    # 端点のハード固定 + 負値のクリップ（数値誤差対策）。
    # v2 gene では r_nodes[0]=0（球キャップの極点）、r_nodes[-1]=rt≥0（上端丸め半径）。
    # v1 gene では r_nodes[0]=bottom_radius>0、r_nodes[-1]=0。どちらもそのまま使う。
    r_dense[0] = float(r_nodes[0])
    r_dense[-1] = float(r_nodes[-1])
    np.maximum(r_dense, 0.0, out=r_dense)
    return z_dense, r_dense


def b3_refit_s(n_samples: int, n_control: int = 64) -> float:
    """``UnivariateSpline`` 用 s。制御点 N 個向け ``B3_SPLINE_S`` を密サンプル数に比例させる。"""
    n = max(int(n_samples), 1)
    nc = max(int(n_control), 1)
    return float(B3_REFIT_S_PER_NODE) * n / nc


def b3_refit_profile(
    z: np.ndarray,
    r: np.ndarray,
    *,
    s: float | None = None,
    n_control: int = 64,
) -> Tuple[np.ndarray, np.ndarray]:
    """レガシー (z,r) 列上で B3 平滑化スプラインを再フィットし、同じ z 格子で評価。"""
    from scipy.interpolate import UnivariateSpline

    z = np.asarray(z, dtype=float)
    r = np.asarray(r, dtype=float)
    if len(z) != len(r) or len(z) < 4:
        raise ValueError("b3_refit_profile requires same-length z, r with >= 4 points")
    s_val = float(b3_refit_s(len(z), n_control)) if s is None else float(s)
    spl = UnivariateSpline(z, r, s=s_val, k=3)
    r_out = np.asarray(spl(z), dtype=float)
    r_out[0] = float(r[0])
    r_out[-1] = float(r[-1])
    np.maximum(r_out, 0.0, out=r_out)
    peak = int(np.argmax(r_out))
    for i in range(peak + 1, len(r_out)):
        if r_out[i] > r_out[i - 1]:
            r_out[i] = r_out[i - 1]
    return z, r_out


def b3_smooth_profile(
    gene: Gene,
) -> Tuple[np.ndarray, np.ndarray]:
    """手法 5 (B3): 制御点 smoothing cubic spline (s=B3_SPLINE_S) → 密 z 格子。

    ``UnivariateSpline(z_nodes, r_nodes, s=B3_SPLINE_S, k=3)`` 相当。
    詳細ビュー・STEP 出力用。feasibility には ``mild_smooth_profile`` を使う。
    """
    from scipy.interpolate import UnivariateSpline

    n = int(gene.N)
    height = float(gene.height)
    w = _effective_z_warp(getattr(gene, "z_warp", None))

    z_nodes = gene_z_nodes(gene)
    r_nodes = np.asarray(gene.radii, dtype=float)
    z_dense = _dense_z(height, n, DENSE_FACTOR, z_warp=w)

    spl = UnivariateSpline(z_nodes, r_nodes, s=float(B3_SPLINE_S), k=3)
    r_dense = np.asarray(spl(z_dense), dtype=float)
    r_dense[0] = float(r_nodes[0])
    r_dense[-1] = float(r_nodes[-1])
    np.maximum(r_dense, 0.0, out=r_dense)
    return z_dense, r_dense


def mild_smooth_profile(
    gene: Gene,
    *,
    n_dense: int = FEASIBILITY_PROFILE_N,
    sigma: float = FEASIBILITY_SMOOTH_SIGMA,
) -> Tuple[np.ndarray, np.ndarray]:
    """gene 制御点から feasibility 向けの (z, r) を返す。

    z は ``linspace(0, height)``（生成時パラメトリックプロファイルと同型）。
    半径は線形補間のあと ``sigma`` で軽くガウシアン平滑化する（``DENSE_FACTOR``
    ほど強くしない）。メッシュ描画用 ``smooth_profile`` とは別経路。
    """
    z_nodes = gene_z_nodes(gene)
    r_nodes = np.asarray(gene.radii, dtype=float)
    z_dense = np.linspace(0.0, float(gene.height), int(n_dense))
    r_lin = np.interp(z_dense, z_nodes, r_nodes)
    if sigma > 0.0:
        r_dense = _gaussian_filter1d(r_lin, sigma=float(sigma))
    else:
        r_dense = np.asarray(r_lin, dtype=float)
    r_dense[0] = float(r_nodes[0])
    r_dense[-1] = float(r_nodes[-1])
    np.maximum(r_dense, 0.0, out=r_dense)
    return z_dense, r_dense
