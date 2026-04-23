"""起き上がりこぼしとしての物理的成立条件（feasibility）を判定する。

子午面プロファイル ``r(z)`` について、傾き θ ∈ [0, θ_max] のすべての接地点で
「接地点の曲率中心より重心が下」（= 接地点から重心への内向き法線射影が
曲率半径より小さい）を保証する。重心高さ ``z_CoG`` は、モデル内部の重り配置や
肉抜きで自由に調整できるという前提で、**存在すればよい**（形状単独の feasibility）
として扱う。

## 数式

接地点 P = (r(z*), z*)、外向き単位法線 n = (1, -r') / sqrt(1+r'²)、
子午面曲率半径 ρ_m(z) = (1+r'²)^{3/2} / |r''|。

重心 G = (0, z_CoG) について、(G-P) を内向き法線に射影した長さは
    (r(z*) + r'(z*)·(z_CoG - z*)) / sqrt(1+r'²)
となり、これが ρ_m(z*) 未満なら安定（復元力が出る）。整理すると r' > 0 の登り側で

    z_CoG < z* + (ρ_m·sqrt(1+r'²) - r(z*)) / r'(z*)
          = z* + ((1+r'²)² / |r''| - r(z*)) / r'(z*)

対象 z* は r'(z*) ≥ cot(θ_max) の範囲（θ=θ_max 時の接地点までに対応）。
この範囲で min を取ったものが ``z_cog_max``。ρ_m を ``eps_mm`` だけ差し引いて
曲率に安全余裕を与え、最後に ``safety_margin`` を掛けて実用上の上限にする。

## 数値微分のノイズ対策

``gene.radii`` は N_NODES=36 点しかないため、BSpline で密サンプルしてから
np.gradient で r'', r'' を取ると、スプラインと微分の合成が高周波ノイズを
生みやすい。対策として、

- gene 生成時は **パラメトリックな密プロファイル**（281 点）を直接 feasibility
  判定にかけることを推奨（``feasibility_from_profile``）。
- 既存の gene から判定する ``rolypoly_feasibility`` では、GAUSSIAN 平滑化を
  デフォルトとし、導関数を評価したあと軽い gaussian フィルタで整えてから使う。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import BSpline
from scipy.ndimage import gaussian_filter1d

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

    suggested_z_cog: float
    """設計値として推奨する z_CoG（mm）。通常は z_cog_max/2。"""

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
            suggested_z_cog=0.0,
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
            suggested_z_cog=0.0,
            worst_margin=float("-inf"),
        )

    z_asc = z[: peak_idx + 1]
    r_asc = r[: peak_idx + 1]

    rp = np.gradient(r_asc, z_asc)
    rpp = np.gradient(rp, z_asc)

    if smooth_derivatives:
        # サンプル間隔の約 2 倍程度で軽く平滑化（高周波ノイズの抑制）
        sigma = max(1.0, len(z_asc) / 60.0)
        rp = gaussian_filter1d(rp, sigma=sigma, mode="nearest")
        rpp = gaussian_filter1d(rpp, sigma=sigma, mode="nearest")

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
            suggested_z_cog=0.0,
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
    suggested = 0.5 * z_cog_max if is_feasible else 0.0

    return Feasibility(
        is_feasible=is_feasible,
        z_cog_max=z_cog_max,
        limiting_z=limiting_z,
        rho_m_bottom=rho_m_bottom,
        suggested_z_cog=suggested,
        worst_margin=worst_margin,
    )


def rolypoly_feasibility(
    gene: Gene,
    theta_max_deg: float = TILT_MAX_DEG,
    eps_mm: float = EPS_MM,
    safety_margin: float = 0.85,
) -> Feasibility:
    """gene（radii）から feasibility を判定する（API / 既存 gene 用）。

    radii を Gaussian で事前平滑化したあと PCHIP で補間し、その解析 2 階微分
    で曲率を評価する。jitter 由来の高周波ノイズを除いたうえで radii の全体形を
    評価できるので、生成時に付けた摂動が False Negative に結び付きにくい。

    ただし **生成時の値より保守的** な結果になることがある（平滑化で曲率が少し
    緩くなり、z_cog_max が小さめに出る傾向）。正確な値が欲しい場合は、生成時に
    ``feasibility_from_profile(z_dense, r_dense)`` で計算し、DB に保存された
    ``suggested_z_cog`` を使う。
    """
    radii = np.asarray(gene.radii, dtype=float)
    height = float(gene.height)
    n = len(radii)
    if n < 6:
        return Feasibility(
            is_feasible=False, z_cog_max=0.0, limiting_z=0.0,
            rho_m_bottom=0.0, suggested_z_cog=0.0, worst_margin=float("-inf"),
        )

    # radii をクランプト B-スプラインの制御多角形として扱い、その解析 2 階微分
    # から曲率を得る。variation-diminishing 性で高周波 jitter が減衰し、C² の
    # 連続性で r'' が滑らかに出る。PCHIP（radii を exact に通る）と比べて、
    # √z 型の底特異点を「球に近い連続曲線」として表現できる点が重要。
    k = 3
    # クランプトノット（smoothing.py._bspline と同じ構成）
    t = np.concatenate([np.zeros(k), np.linspace(0.0, 1.0, n - k + 1), np.ones(k)])
    spline = BSpline(t, radii, k, extrapolate=False)

    n_dense = 513
    u_dense = np.linspace(0.0, 1.0, n_dense)
    r_dense = np.asarray(spline(u_dense), dtype=float)

    # z 配置規則:  z(u) = height · u ** alpha
    #   alpha=1（v1 / 旧 v2）: z = height·u, 線形
    #   alpha=2（v2 既定）   : z = height·u², u=0 近傍で dz/du→0 ＝ dr/dz→∞
    # rp, rpp は dr/dz, d²r/dz² を chain rule で計算する。
    alpha_raw = getattr(gene, "z_warp", None)
    alpha = float(alpha_raw) if alpha_raw is not None and alpha_raw > 0 else 1.0
    dr_du = np.asarray(spline.derivative(1)(u_dense), dtype=float)
    d2r_du2 = np.asarray(spline.derivative(2)(u_dense), dtype=float)
    if abs(alpha - 1.0) < 1e-9:
        # 旧パス: z = height·u → dz/du=height 定数。
        rp = dr_du / height
        rpp = d2r_du2 / (height * height)
        z_dense = height * u_dense
    else:
        # dz/du = α·h·u^(α-1)、d²z/du² = α(α-1)·h·u^(α-2)。u=0 で 0/0 になるが、
        # HEAD_SKIP で該当領域は評価から除外する（そもそも √z 型特異点領域）。
        eps_u = 1e-12
        u_safe = np.where(u_dense > eps_u, u_dense, eps_u)
        dz_du = alpha * height * u_safe ** (alpha - 1.0)
        d2z_du2 = alpha * (alpha - 1.0) * height * u_safe ** (alpha - 2.0)
        rp = dr_du / dz_du
        # d²r/dz² = (d²r/du² · dz/du − dr/du · d²z/du²) / (dz/du)³
        rpp = (d2r_du2 * dz_du - dr_du * d2z_du2) / (dz_du ** 3)
        z_dense = height * u_dense ** alpha

    peak_idx = int(np.argmax(r_dense))
    if peak_idx < 3:
        return Feasibility(
            is_feasible=False, z_cog_max=0.0, limiting_z=0.0,
            rho_m_bottom=0.0, suggested_z_cog=0.0, worst_margin=float("-inf"),
        )

    z_asc = z_dense[: peak_idx + 1]
    r_asc = r_dense[: peak_idx + 1]
    rp_asc = rp[: peak_idx + 1]
    rpp_asc = rpp[: peak_idx + 1]

    # 3次 B-スプラインの 2 階微分は区分線形（C⁰）なので、制御点境界で小さな
    # ギザつきが残ることがある。軽い Gaussian で均す。
    sigma = max(1.0, len(z_asc) / 80.0)
    rpp_asc = gaussian_filter1d(rpp_asc, sigma=sigma, mode="nearest")

    rho_m = (1.0 + rp_asc * rp_asc) ** 1.5 / np.maximum(np.abs(rpp_asc), 1e-12)
    rho_eff = rho_m - eps_mm

    # radii 経由では、最初の 1〜2 制御点区間は √z 型特異点を表現できない
    # （補間多項式は sqrt(z) を再現できない）。先頭 1 node 相当を強めに除外。
    node_pitch_samples = n_dense // max(n - 1, 1)
    head_skip = max(
        int(HEAD_SKIP_FRACTION * len(z_asc)),
        int(1.2 * node_pitch_samples),
    )
    cot_thmax = 1.0 / np.tan(np.deg2rad(theta_max_deg))
    valid = (
        (rp_asc >= cot_thmax)
        & (rp_asc > 1e-6)
        & np.isfinite(rho_eff)
        & (rho_eff > 0)
        & (rho_m < RHO_M_CAP_MM)
    )
    valid[:head_skip] = False

    if not np.any(valid):
        rho_pos = rho_m[rho_m > 0]
        return Feasibility(
            is_feasible=False, z_cog_max=0.0, limiting_z=0.0,
            rho_m_bottom=float(np.median(rho_pos)) if rho_pos.size else 0.0,
            suggested_z_cog=0.0, worst_margin=float("-inf"),
        )

    sqrt_term = np.sqrt(1.0 + rp_asc * rp_asc)
    numer = rho_eff * sqrt_term - r_asc
    with np.errstate(divide="ignore", invalid="ignore"):
        z_cog_upper = z_asc + numer / np.where(rp_asc > 1e-9, rp_asc, np.nan)

    z_cog_upper_valid = np.where(valid, z_cog_upper, np.inf)
    limit_idx = int(np.argmin(z_cog_upper_valid))
    z_cog_max_raw = float(z_cog_upper_valid[limit_idx])
    limiting_z = float(z_asc[limit_idx])

    projection_at_zero = (r_asc + rp_asc * (0.0 - z_asc)) / sqrt_term
    margin_per = rho_eff - projection_at_zero
    worst_margin = float(np.min(margin_per[valid]))

    head_lo = max(head_skip, peak_idx // 20)
    head_hi = max(head_lo + 2, peak_idx // 6)
    rho_m_bottom = (
        float(np.median(rho_m[head_lo:head_hi])) if head_hi > head_lo else float(rho_m[head_skip])
    )

    is_feasible = z_cog_max_raw > 0.0 and worst_margin > 0.0
    z_cog_max = max(0.0, z_cog_max_raw) * safety_margin
    suggested = 0.5 * z_cog_max if is_feasible else 0.0

    return Feasibility(
        is_feasible=is_feasible,
        z_cog_max=z_cog_max,
        limiting_z=limiting_z,
        rho_m_bottom=rho_m_bottom,
        suggested_z_cog=suggested,
        worst_margin=worst_margin,
    )
