"""
起き上がりこぼしの物理成立条件（feasibility）判定。

役割: 子午面 r(z) について傾き θ≤θ_max の自己復元可能性を評価。
働き: 接地点の曲率半径と重心射影から ``z_cog_max`` を求める。密プロファイル推奨・折れ線は平滑化後に数値微分（``gene`` 生成・指標で使用）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import EPS_MM, TILT_MAX_DEG
from .models import Gene


# 南極付近で r(z) ~ sqrt(2rb·z) の √z 型特異点があるため、np.gradient の
# 端点差分は高い誤差を持つ。登り区間の先頭 HEAD_SKIP_FRACTION だけ評価から
# 外すことで、feasibility 判定を安定させる（本当の物理的制約は球面上では
# 一様に rho_m=rb なので、少々内側で評価しても保守的な近似になる）。
HEAD_SKIP_FRACTION: float = 0.03


# 曲率半径の上限。ρ_m がこれを超える領域は「ほぼ直線」で、鉛直軸対称体として
# 転がるときに接触点が連続に動かない（= 起き上がりこぼしにならない）。
# 円錐や円柱を rejects するための閾値。典型サイズの 3〜5 倍を目安にする。
RHO_M_CAP_MM: float = 200.0


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


@dataclass(frozen=True)
class Feasibility:
    """プロファイル単独の起き上がりこぼし成立条件。"""

    is_feasible: bool
    z_cog_max: float
    """安全マージン込みで許容される z_CoG の上限（mm）。"""

    limiting_z: float
    """上限を決めた接地点 z*（mm）。"""

    rho_m_bottom: float
    """南極近傍での有効曲率半径（mm）。~= 球キャップ半径。"""

    worst_margin: float
    """もっとも厳しい接地点での ρ_eff - (z_CoG=0 時の投影距離) の最小値（mm）。負なら不合格。"""


def meridian_curvature(z: np.ndarray, r: np.ndarray) -> np.ndarray:
    """プロファイル r(z) の子午面曲率半径 ρ_m(z) = (1+r'²)^{3/2} / |r''| を返す。"""
    rp = np.gradient(r, z)
    rpp = np.gradient(rp, z)
    rho = (1.0 + rp * rp) ** 1.5 / np.maximum(np.abs(rpp), 1e-12)
    return rho


def feasibility_from_profile(
    z: np.ndarray,
    r: np.ndarray,
    theta_max_deg: float = TILT_MAX_DEG,
    eps_mm: float = EPS_MM,
    safety_margin: float = 0.85,
    smooth_derivatives: bool = False,
) -> Feasibility:
    """(z, r) の密サンプル列から feasibility を判定する。

    ``smooth_derivatives=True`` のときは r', r'' に軽い Gaussian を掛けてから
    曲率を評価する（既存 gene の radii を smooth_profile で密化したような、
    サンプル間隔に対してやや粗い入力向け）。パラメトリックに密生成した
    プロファイルであれば ``False`` で十分。
    """
    z = np.asarray(z, dtype=float)
    r = np.asarray(r, dtype=float)
    n = len(z)
    if n < 8:
        return Feasibility(
            is_feasible=False,
            z_cog_max=0.0,
            limiting_z=0.0,
            rho_m_bottom=0.0,
            worst_margin=float("-inf"),
        )

    # ピーク位置を特定し、登り区間（z=0 からピークまで）に絞る。
    peak_idx = int(np.argmax(r))
    if peak_idx < 3:
        return Feasibility(
            is_feasible=False,
            z_cog_max=0.0,
            limiting_z=0.0,
            rho_m_bottom=0.0,
            worst_margin=float("-inf"),
        )

    z_asc = z[: peak_idx + 1]
    r_asc = r[: peak_idx + 1]

    rp = np.gradient(r_asc, z_asc)
    rpp = np.gradient(rp, z_asc)

    if smooth_derivatives:
        # サンプル間隔の約 2 倍程度で軽く平滑化（高周波ノイズの抑制）
        sigma = max(1.0, len(z_asc) / 60.0)
        rp = _gaussian_filter1d(rp, sigma=sigma)
        rpp = _gaussian_filter1d(rpp, sigma=sigma)

    # 南極近傍の √z 型特異点による数値微分誤差を除くため、登り区間先頭を除外。
    head_skip = max(3, int(HEAD_SKIP_FRACTION * len(z_asc)))

    rho_m = (1.0 + rp * rp) ** 1.5 / np.maximum(np.abs(rpp), 1e-12)
    rho_eff = rho_m - eps_mm

    # 対象区間: r' ≥ cot(θ_max)。θ_max=75° なら cot≈0.2679。先頭の数値誤差領域は除外。
    # ρ_m が過大（RHO_M_CAP_MM 以上）な点は「ほぼ直線」で接触点が連続に動かないため、
    # valid から外して「全点が無効 → 不合格」となるように扱う（円柱/円錐をリジェクト）。
    cot_thmax = 1.0 / np.tan(np.deg2rad(theta_max_deg))
    valid = (
        (rp >= cot_thmax)
        & (rp > 1e-6)
        & np.isfinite(rho_eff)
        & (rho_eff > 0)
        & (rho_m < RHO_M_CAP_MM)
    )
    valid[:head_skip] = False

    if not np.any(valid):
        rho_pos = rho_m[rho_m > 0]
        return Feasibility(
            is_feasible=False,
            z_cog_max=0.0,
            limiting_z=0.0,
            rho_m_bottom=float(np.median(rho_pos)) if rho_pos.size else 0.0,
            worst_margin=float("-inf"),
        )

    # 各 z* における z_CoG 上限: z_CoG < z* + (rho_eff·sqrt(1+r'²) - r) / r'
    sqrt_term = np.sqrt(1.0 + rp * rp)
    numer = rho_eff * sqrt_term - r_asc
    with np.errstate(divide="ignore", invalid="ignore"):
        z_cog_upper = z_asc + numer / np.where(rp > 1e-9, rp, np.nan)

    z_cog_upper_valid = np.where(valid, z_cog_upper, np.inf)
    limit_idx = int(np.argmin(z_cog_upper_valid))
    z_cog_max_raw = float(z_cog_upper_valid[limit_idx])
    limiting_z = float(z_asc[limit_idx])

    # worst_margin: z_CoG=0（最下点に重りを寄せた理想ケース）での
    # (ρ_eff - 投影距離) の最小値。負なら「どう z_CoG を動かしても不合格」。
    projection_at_zero = (r_asc + rp * (0.0 - z_asc)) / sqrt_term
    margin_per = rho_eff - projection_at_zero
    worst_margin = float(np.min(margin_per[valid]))

    # 南極近傍の有効曲率半径（ログ用）。z=0 直近のサンプルは r' が極めて大きく
    # 数値微分が荒れるため、先頭 5〜12% の中央値を使う。
    head_lo = max(head_skip, peak_idx // 20)
    head_hi = max(head_lo + 2, peak_idx // 8)
    rho_m_bottom = float(np.median(rho_m[head_lo:head_hi])) if head_hi > head_lo else float(rho_m[head_skip])

    is_feasible = z_cog_max_raw > 0.0 and worst_margin > 0.0
    z_cog_max = max(0.0, z_cog_max_raw) * safety_margin

    return Feasibility(
        is_feasible=is_feasible,
        z_cog_max=z_cog_max,
        limiting_z=limiting_z,
        rho_m_bottom=rho_m_bottom,
        worst_margin=worst_margin,
    )


def rolypoly_feasibility(
    gene: Gene,
    theta_max_deg: float = TILT_MAX_DEG,
    eps_mm: float = EPS_MM,
    safety_margin: float = 0.85,
) -> Feasibility:
    """gene（radii）から feasibility を判定する（API / 既存 gene 用）。

    radii を密サンプルしてから、導関数評価前後で軽い Gaussian を掛けて
    高周波ノイズを抑える。radii の全体形を保ったまま評価できるので、
    生成時に付けた摂動が False Negative に結び付きにくい。

    ただし **生成時の値より保守的** な結果になることがある（平滑化で曲率が少し
    緩くなり、z_cog_max が小さめに出る傾向）。
    """
    from .profile_extension import feasibility_profile

    z_dense, r_dense = feasibility_profile(gene)
    n = len(z_dense)
    if n < 6:
        return Feasibility(
            is_feasible=False, z_cog_max=0.0, limiting_z=0.0,
            rho_m_bottom=0.0, worst_margin=float("-inf"),
        )

    return feasibility_from_profile(
        z_dense,
        r_dense,
        theta_max_deg=theta_max_deg,
        eps_mm=eps_mm,
        safety_margin=safety_margin,
        smooth_derivatives=True,
    )
