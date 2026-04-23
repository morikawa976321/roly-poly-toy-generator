"""球キャップ底 + 5次テーパのパラメトリック形状族（v2 gene の生成基盤）。

形状の構成:
    z ∈ [0, z_cap_end]       : 半径 rb の球面 r(z) = sqrt(2·rb·z - z²)
    z ∈ [z_cap_end, height]  : 端点で (r, dr/dz, d²r/dz²) を球面と一致させる
                               5次多項式で r_cap_end → rt までテーパ

ランダム化パラメータ:
    rb                    : 球面半径（SPHERE_RB_MIN..MAX）
    cap_angle_deg         : 球キャップの極角（CAP_ANGLE_MIN..MAX、TILT_MAX_DEG+3° 以上）
    rt                    : 上端半径。球キャップ終端半径 r_cap_end に対する
                            比 ``RT_RATIO_MIN..MAX`` をサンプルして決める。スケール不変に
                            「尖り〜ずん胴」の全域をカバーでき、見た目の多様性を出せる。
    top_tangent_angle_deg : 上端における子午線の接線角（水平基準,
                            TOP_TANGENT_ANGLE_MIN..MAX_DEG）。0° で水平着地（平坦な天面,
                            従来挙動）、正の値で肩が外向きに落ちた truncated dome 風。
                            慣性モーメント経由で揺れ周期にも直接効く。
    delta_target          : 狙いの delta = rb - z_com（DELTA_TARGET_MIN..MAX）

delta_target を達成するよう、全体高さ ``height`` を二分探索で調整する
（高さを上げるほど上部の体積比が増えて重心が上がり、delta が小さくなる）。

元実装は ``generate_roly_poly_stl.py``（独立スクリプト）。本モジュールはそれを
NumPy 化・再利用できる形で抽出し、backend の生成パイプラインから呼ばれる。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from .config import (
    CAP_ANGLE_MAX_DEG,
    CAP_ANGLE_MIN_DEG,
    DELTA_TARGET_MAX_MM,
    DELTA_TARGET_MIN_MM,
    HEIGHT_HI_RB_FACTOR,
    HEIGHT_OPT_GRID_POINTS,
    HEIGHT_OPT_REFINE_POINTS,
    HEIGHT_OPT_W_DELTA,
    HEIGHT_OPT_W_DELTA_UNDER,
    HEIGHT_OPT_W_FEAS,
    HEIGHT_OPT_W_SLENDER,
    CAP_DOMINANCE_MAX_FRACTION,
    CAP_TOP_MIN_MM,
    PEAK_ACTIVE_PROB,
    PEAK_CURVATURE_KAPPA_MAX,
    PEAK_CURVATURE_KAPPA_MIN,
    PEAK_R_RATIO_MAX,
    PEAK_R_RATIO_MIN,
    PEAK_Z_RATIO_MAX,
    PEAK_Z_RATIO_MIN,
    RT_RATIO_MAX,
    RT_RATIO_MIN,
    SPHERE_RB_MAX_MM,
    SPHERE_RB_MIN_MM,
    TILT_MAX_DEG,
    TOP_TANGENT_ANGLE_MAX_DEG,
    TOP_TANGENT_ANGLE_ACTIVE_MIN_DEG,
    TOP_TANGENT_ANGLE_FLAT_PROB,
    TOP_TANGENT_ANGLE_MIN_DEG,
    TOP_TANGENT_ANGLE_RT_FLOOR_SLOPE,
)


@dataclass(frozen=True)
class ShapeParams:
    """パラメトリック形状族を決めるパラメータセット。"""

    rb: float
    cap_angle_deg: float
    rt: float
    delta_target: float
    top_tangent_angle_deg: float = 0.0
    # デフォルトは「旧挙動（ピーク=球キャップ終端）」に寄せる。
    # 案Aによるピーク形状は sample_shape_params 側で有効化する。
    peak_z_ratio: float = 0.0
    peak_r_ratio: float = 1.0
    peak_curvature_kappa: float = 0.0
    """上端 (z=height) の子午線接線角（deg, 水平基準）。

    0° で dr/dz|_{z=height}=0（水平着地, 従来挙動）。正の値で上端が外向きに落ち込み、
    肩の丸い truncated dome 風の形になる。dr/dz|_{z=height} = -tan(angle) として
    5 次多項式の端点条件に流し込む。
    """


# --- 球面プロファイル ---------------------------------------------------------


def sphere_r(rb: float, z: np.ndarray | float) -> np.ndarray | float:
    """r(z) = sqrt(2·rb·z - z²)  （球の中心は (0, rb)、最下点 z=0 で r=0）。"""
    v = 2.0 * rb * z - z * z
    if isinstance(v, np.ndarray):
        return np.sqrt(np.maximum(v, 0.0))
    return math.sqrt(max(v, 0.0))


def sphere_dr_dz(rb: float, z: float) -> float:
    r = sphere_r(rb, z)
    if r <= 1e-12:
        return 0.0
    return (rb - z) / r


def sphere_d2r_dz2(rb: float, z: float) -> float:
    """球面 r(z) の 2 階微分:  -1/r - (rb-z)²/r³。"""
    r = sphere_r(rb, z)
    if r <= 1e-12:
        return 0.0
    a = rb - z
    return -1.0 / r - (a * a) / (r * r * r)


# --- 5次多項式による C2 連続テーパ -------------------------------------------


def _quintic_coeffs(
    r0: float,
    dr0: float,
    d2r0: float,
    r1: float,
    dr1: float,
    d2r1: float,
    L: float,
) -> Tuple[float, float, float, float, float, float]:
    """r(t) = a0 + a1 t + a2 t² + a3 t³ + a4 t⁴ + a5 t⁵（t=(z-z0)/L）の係数を返す。

    端点 t=0, t=1 で r, dr/dt, d²r/dt² を一致させる。dr/dz=dr/dt/L, d²r/dz²=d²r/dt²/L²。
    """
    a0 = r0
    a1 = dr0 * L
    a2 = 0.5 * d2r0 * L * L

    v1 = dr1 * L
    acc1 = d2r1 * L * L
    b0 = r1 - (a0 + a1 + a2)
    b1 = v1 - (a1 + 2.0 * a2)
    b2 = acc1 - 2.0 * a2

    # 手計算で解いた 3x3 消去の結果（generate_roly_poly_stl.py と同一式）
    a5 = (b2 - 6.0 * b1 + 12.0 * b0) / 2.0
    a4 = b1 - 3.0 * b0 - 2.0 * a5
    a3 = b0 - a4 - a5
    return a0, a1, a2, a3, a4, a5


def _eval_quintic(
    z: np.ndarray, z0: float, z1: float, coeffs: Tuple[float, ...]
) -> np.ndarray:
    a0, a1, a2, a3, a4, a5 = coeffs
    L = z1 - z0
    t = np.clip((z - z0) / L, 0.0, 1.0) if L > 1e-12 else np.zeros_like(z)
    return (
        a0
        + a1 * t
        + a2 * t**2
        + a3 * t**3
        + a4 * t**4
        + a5 * t**5
    )


# --- プロファイル生成 --------------------------------------------------------


def build_parametric_profile(
    params: ShapeParams,
    height: float,
    n_dense: int = 513,
) -> Tuple[np.ndarray, np.ndarray]:
    """球キャップ + テーパのプロファイル (z_dense, r_dense) を返す。

    両端: r(0) = 0, r(height) = rt（rt=0 なら先端が尖る）。
    n_dense は子午面曲率の数値微分が滑らかになる程度（>=~200）を目安にする。
    """
    rb = params.rb
    cap_angle = math.radians(params.cap_angle_deg)
    z_cap_end = rb * (1.0 - math.cos(cap_angle))
    r_cap_end = rb * math.sin(cap_angle)

    z_cap_end = min(z_cap_end, 0.999 * height)  # height がキャップ高さを下回る異常ケース保険

    # 案A: ピーク（最大半径）をキャップ終端より上に置けるようにする。
    # ただし ShapeParams のデフォルト（peak_z_ratio<=0 or peak_r_ratio<=1）では
    # 旧挙動（キャップ終端が最大）にフォールバックする。
    use_peak = (params.peak_z_ratio is not None and params.peak_z_ratio > 1e-6) and (
        params.peak_r_ratio is not None and params.peak_r_ratio > 1.0001
    )
    if use_peak:
        # z_peak は (z_cap_end, height) の内点。ピークで dr/dz=0 を強制し、r''<0 で丸みを持たせる。
        peak_ratio = float(np.clip(params.peak_z_ratio, 0.05, 0.95))
        z_peak = z_cap_end + peak_ratio * (height - z_cap_end)
        # 念のためのガード（区間長が 0 だと係数が不安定）
        z_peak = float(np.clip(z_peak, z_cap_end + 0.5, height - 0.5))
        r_peak = float(max(r_cap_end, params.peak_r_ratio * r_cap_end))
        L_left = max(1e-6, z_peak - z_cap_end)
        L_right = max(1e-6, height - z_peak)
        L_min = min(L_left, L_right)
        kappa = float(np.clip(params.peak_curvature_kappa, 0.0, 10.0))
        # kappa=0 でも dr=0 のみで峰はできるが、台地状になりやすいので
        # sample_shape_params 側で通常は正の範囲を使う。
        d2r_peak = -kappa * r_peak / (L_min * L_min) if kappa > 0 else 0.0
    else:
        z_peak = float(z_cap_end)
        r_peak = float(r_cap_end)
        d2r_peak = 0.0

    dr0 = sphere_dr_dz(rb, z_cap_end)
    d2r0 = sphere_d2r_dz2(rb, z_cap_end)
    # 上端の接線角を params から反映させる:
    #   angle=0° → dr1=0 （水平着地; 従来の平坦な天面）
    #   angle>0° → dr1<0（肩が外向きに落ちた truncated dome 風）
    # d²r/dz² は 0 のまま: 上端で加速度方向を強制すると、5 次多項式が中腹で
    # 大きく波打って二峰化する余地が増えるため保守的に据え置き。
    dr1 = -math.tan(math.radians(params.top_tangent_angle_deg))
    d2r1 = 0.0

    z_dense = np.linspace(0.0, float(height), int(n_dense))
    r_dense = np.zeros_like(z_dense)

    mask_cap = z_dense <= z_cap_end
    r_dense[mask_cap] = sphere_r(rb, z_dense[mask_cap])

    if height > z_cap_end + 1e-9:
        if use_peak:
            # セグメント1: キャップ終端 → ピーク（増加, dr/dz が 0 に着地）
            if z_peak > z_cap_end + 1e-9:
                coeffs_up = _quintic_coeffs(
                    r0=r_cap_end,
                    dr0=dr0,
                    d2r0=d2r0,
                    r1=r_peak,
                    dr1=0.0,
                    d2r1=d2r_peak,
                    L=z_peak - z_cap_end,
                )
                mask_up = (z_dense > z_cap_end) & (z_dense <= z_peak)
                r_dense[mask_up] = _eval_quintic(
                    z_dense[mask_up], z_cap_end, z_peak, coeffs_up
                )

            # セグメント2: ピーク → 上端（減少, 上端で指定角度に着地）
            if height > z_peak + 1e-9:
                coeffs_down = _quintic_coeffs(
                    r0=r_peak,
                    dr0=0.0,
                    d2r0=d2r_peak,
                    r1=params.rt,
                    dr1=dr1,
                    d2r1=d2r1,
                    L=height - z_peak,
                )
                mask_down = z_dense > z_peak
                r_dense[mask_down] = _eval_quintic(
                    z_dense[mask_down], z_peak, height, coeffs_down
                )

            # 単峰性クランプ:
            # - (z_cap_end, z_peak] は非減少
            # - (z_peak, height] は非増加
            for i in range(1, len(z_dense)):
                if z_dense[i] <= z_cap_end:
                    continue
                if z_dense[i] <= z_peak:
                    if r_dense[i] < r_dense[i - 1]:
                        r_dense[i] = r_dense[i - 1]
                else:
                    if r_dense[i] > r_dense[i - 1]:
                        r_dense[i] = r_dense[i - 1]
        else:
            # 旧挙動（キャップ終端→上端を単一の 5 次多項式で接続）
            coeffs = _quintic_coeffs(
                r0=r_cap_end,
                dr0=dr0,
                d2r0=d2r0,
                r1=params.rt,
                dr1=dr1,
                d2r1=d2r1,
                L=height - z_cap_end,
            )
            mask_taper = ~mask_cap
            r_dense[mask_taper] = _eval_quintic(z_dense[mask_taper], z_cap_end, height, coeffs)
            # 旧クランプ: キャップ終端以降は非増加
            for i in range(1, len(z_dense)):
                if z_dense[i] > z_cap_end and r_dense[i] > r_dense[i - 1]:
                    r_dense[i] = r_dense[i - 1]

    np.maximum(r_dense, 0.0, out=r_dense)
    # 端点を厳密に固定
    r_dense[0] = 0.0
    r_dense[-1] = max(params.rt, 0.0)
    return z_dense, r_dense


# --- 体積・重心（中実・一様密度） --------------------------------------------


def integrate_volume_and_com_z(
    z: np.ndarray, r: np.ndarray
) -> Tuple[float, float]:
    """一様密度の回転体の体積 V と重心 z_com を台形則で返す。

    V = π ∫ r² dz,   z_com = (π / V) ∫ z r² dz
    """
    if len(z) < 2:
        raise ValueError("profile too short")

    r2 = r * r
    dz = np.diff(z)
    v_segments = 0.5 * (r2[:-1] + r2[1:]) * dz
    z_mid_integrand = 0.5 * (z[:-1] * r2[:-1] + z[1:] * r2[1:]) * dz

    V = float(math.pi * v_segments.sum())
    if V <= 0:
        raise ValueError("non-positive volume")
    z_com = float(math.pi * z_mid_integrand.sum() / V)
    return V, z_com


# --- 高さの選択（案C: 多目的最適化） ------------------------------------------


def tune_height_for_delta(
    params: ShapeParams,
    n_dense: int = 513,
    max_iter: int = 60,
    tol_mm: float = 1e-3,
) -> Tuple[float, float, np.ndarray, np.ndarray]:
    """形状パラメータに対し、高さ ``height`` を選ぶ。

    旧実装は「delta = rb - z_com が delta_target に一致する高さ」を二分探索していたが、
    それだと細長さ（height/幅）や feasibility の余裕を作りにくい。

    現実の設計では「delta を厳密一致させる」よりも、
    - 細長さ（見た目）
    - feasibility の余裕（成立しやすさ）
    - delta_target からの逸脱（復元余裕の確保）
    を同時に見て “良い” 高さを選びたい。

    本関数は候補 height を評価し、上記の加点・減点でスコア最大の height を返す。
    戻り値は (height, z_com, z_dense, r_dense)。
    """
    rb = params.rb
    cap_angle = math.radians(params.cap_angle_deg)
    z_cap_end = rb * (1.0 - math.cos(cap_angle))

    h_lo = z_cap_end + 0.5
    h_hi = rb * float(HEIGHT_HI_RB_FACTOR)

    # delta のスケール（正規化用）
    delta_span = max(1.0, float(DELTA_TARGET_MAX_MM - DELTA_TARGET_MIN_MM))

    # feasibility の計算は physics にあるが循環は起きない（physics は shape を import しない）。
    from .physics import feasibility_from_profile

    def _score_for(h: float) -> Tuple[float, float, float, np.ndarray, np.ndarray]:
        # 「半球の下半分」っぽい形を弾く: 球キャップが全高の大半を占める候補は不採用。
        cap_fraction = float(z_cap_end / max(h, 1e-9))
        if cap_fraction > float(CAP_DOMINANCE_MAX_FRACTION):
            return float("-inf"), float("nan"), float("nan"), np.array([]), np.array([])
        if (h - z_cap_end) < float(CAP_TOP_MIN_MM):
            return float("-inf"), float("nan"), float("nan"), np.array([]), np.array([])

        z, r = build_parametric_profile(params, h, n_dense=n_dense)
        _, zc = integrate_volume_and_com_z(z, r)
        delta = rb - zc
        max_r = float(np.max(r))
        slender = float(h / max(1e-6, (2.0 * max_r)))

        feas = feasibility_from_profile(z, r, theta_max_deg=TILT_MAX_DEG, smooth_derivatives=False)
        feas_term = max(0.0, float(feas.worst_margin)) / 10.0  # 10mm を 1.0 目安に正規化
        # delta の目標からの逸脱
        delta_err = abs(delta - float(params.delta_target)) / delta_span
        delta_under = max(0.0, float(params.delta_target) - delta) / delta_span

        score = (
            HEIGHT_OPT_W_SLENDER * slender
            + HEIGHT_OPT_W_FEAS * feas_term
            - HEIGHT_OPT_W_DELTA * delta_err
            - HEIGHT_OPT_W_DELTA_UNDER * delta_under
        )

        # 形状単独で不可能（worst_margin<=0）は強めに減点して避ける
        if not feas.is_feasible:
            score -= 5.0

        return float(score), float(delta), float(zc), z, r

    # 粗探索: log っぽく広く見る（低い側の刻みも欲しい）
    hs = np.geomspace(max(h_lo, 1e-3), max(h_hi, h_lo + 1.0), int(HEIGHT_OPT_GRID_POINTS))
    best = None  # (score, h, delta, zc, z, r)
    for h in hs:
        sc, d, zc, z, r = _score_for(float(h))
        if not np.isfinite(sc):
            continue
        cand = (sc, float(h), d, zc, z, r)
        if best is None or cand[0] > best[0]:
            best = cand

    if best is None:
        # 全候補が弾かれた場合は、最小高さ（=キャップ終端+α）でフォールバックする。
        # 生成側は retry で回るので、ここで無限に落ちるより保守的に返す。
        z, r = build_parametric_profile(params, h_lo, n_dense=n_dense)
        _, zc = integrate_volume_and_com_z(z, r)
        return float(h_lo), float(zc), np.asarray(z, dtype=float), np.asarray(r, dtype=float)
    _best_sc, best_h, _best_d, best_zc, best_z, best_r = best

    # 局所再探索: best_h 近傍を線形に詰める
    h0 = max(h_lo, best_h * 0.75)
    h1 = min(h_hi, best_h * 1.35)
    hs2 = np.linspace(h0, h1, int(HEIGHT_OPT_REFINE_POINTS))
    for h in hs2:
        sc, d, zc, z, r = _score_for(float(h))
        if not np.isfinite(sc):
            continue
        if sc > _best_sc:
            _best_sc, best_h, _best_d, best_zc, best_z, best_r = sc, float(h), d, zc, z, r

    return float(best_h), float(best_zc), np.asarray(best_z, dtype=float), np.asarray(best_r, dtype=float)


# --- ランダムサンプリング ----------------------------------------------------


def sample_shape_params(rng: np.random.Generator) -> ShapeParams:
    """config.py の値域から ShapeParams をランダムに引く。

    ``rt`` は球キャップ終端半径 ``r_cap_end = rb·sin(cap_angle)`` に対する
    比 ``RT_RATIO_MIN..MAX`` をサンプルして絶対値に直す。こうすることで rb の
    スケールに依らず「尖った先端〜ずん胴の上部」の全域が均等に出る。

    ``top_tangent_angle_deg`` は上端の接線角（水平基準）。0° で水平着地、
    正の値で肩の下がった truncated dome 風になる。視認性のため「ほぼフラット」と
    「明確に肩が落ちる角度」の二峰でサンプリングする。角度が大きいときは rt=0
    と組み合わさると 3D で円錐頂点（鋭いコーン）ができてしまうので、
    ``TOP_TANGENT_ANGLE_RT_FLOOR_SLOPE`` を介して rt_ratio の下限を引き上げ、
    角度に応じて上端半径を最低限確保する。
    """
    # cap_angle の下限は TILT_MAX_DEG + 3° を保証（config の値域は既にこれを満たす想定）
    cap_low = max(CAP_ANGLE_MIN_DEG, TILT_MAX_DEG + 3.0)
    cap_high = max(CAP_ANGLE_MAX_DEG, cap_low + 1.0)

    rb = float(rng.uniform(SPHERE_RB_MIN_MM, SPHERE_RB_MAX_MM))
    cap_angle_deg = float(rng.uniform(cap_low, cap_high))
    r_cap_end = rb * math.sin(math.radians(cap_angle_deg))

    if float(rng.random()) < TOP_TANGENT_ANGLE_FLAT_PROB:
        # 従来に近い「平たい天面」を残すクラスタ
        top_tangent_angle_deg = float(
            rng.uniform(TOP_TANGENT_ANGLE_MIN_DEG, TOP_TANGENT_ANGLE_ACTIVE_MIN_DEG)
        )
    else:
        # 一覧カードでも形の差が見える「アクティブ角度」クラスタ
        top_tangent_angle_deg = float(
            rng.uniform(TOP_TANGENT_ANGLE_ACTIVE_MIN_DEG, TOP_TANGENT_ANGLE_MAX_DEG)
        )
    # 鋭いコーン頂点（rt=0 かつ有限な負スロープ）を避ける:
    # 上端接線角が大きいほど rt_ratio の下限を引き上げる。
    top_slope = math.tan(math.radians(top_tangent_angle_deg))
    rt_ratio_min_eff = max(
        RT_RATIO_MIN, TOP_TANGENT_ANGLE_RT_FLOOR_SLOPE * top_slope
    )
    rt_ratio_min_eff = min(rt_ratio_min_eff, RT_RATIO_MAX)
    rt_ratio = float(rng.uniform(rt_ratio_min_eff, RT_RATIO_MAX))
    rt = rt_ratio * r_cap_end

    use_peak = float(rng.random()) < float(PEAK_ACTIVE_PROB)
    if use_peak:
        peak_z_ratio = float(rng.uniform(PEAK_Z_RATIO_MIN, PEAK_Z_RATIO_MAX))
        peak_r_ratio = float(rng.uniform(PEAK_R_RATIO_MIN, PEAK_R_RATIO_MAX))
        peak_kappa = float(rng.uniform(PEAK_CURVATURE_KAPPA_MIN, PEAK_CURVATURE_KAPPA_MAX))
    else:
        # 旧挙動（球キャップ終端が最大半径）
        peak_z_ratio = 0.0
        peak_r_ratio = 1.0
        peak_kappa = 0.0

    return ShapeParams(
        rb=rb,
        cap_angle_deg=cap_angle_deg,
        rt=rt,
        delta_target=float(rng.uniform(DELTA_TARGET_MIN_MM, DELTA_TARGET_MAX_MM)),
        top_tangent_angle_deg=top_tangent_angle_deg,
        peak_z_ratio=peak_z_ratio,
        peak_r_ratio=peak_r_ratio,
        peak_curvature_kappa=peak_kappa,
    )


# --- 密プロファイル → 等間隔 N_NODES radii 配列 -----------------------------


def profile_to_radii(
    z_dense: np.ndarray,
    r_dense: np.ndarray,
    n_nodes: int,
    height: float,
    z_warp: float = 1.0,
) -> List[float]:
    """gene.radii 用に、``n_nodes`` 点にダウンサンプル。

    z_warp でノード配置を制御する。``z_warp=1.0`` で等間隔、``z_warp=2.0`` で
    z=0 付近に密にサンプル（v2 既定）。球キャップの極（r ∝ √z）を忠実に捉えるため
    に、v2 では 2.0 を使う。
    """
    u = np.linspace(0.0, 1.0, int(n_nodes))
    z_nodes = float(height) * u ** float(z_warp)
    r_nodes = np.interp(z_nodes, z_dense, r_dense)
    # 両端を厳密に固定（数値誤差対策）
    r_nodes[0] = 0.0
    r_nodes[-1] = float(r_dense[-1])
    return [float(v) for v in r_nodes]
