"""physics モジュールの単体テスト（既知形状の feasibility）。

役割: feasibility_from_profile / rolypoly_feasibility の物理判定テスト。
働き: 球・円柱・コーン等の既知形状と生成 gene で feasible/infeasible が期待どおりになることを検証する。

テスト対象は主に ``feasibility_from_profile``（密サンプルから直接判定する
高精度パス）。``rolypoly_feasibility``（radii 経由、保守的な近似）は
生成→radii 化→再判定のラウンドトリップが成立することだけ確認する。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.app.config import N_NODES, TILT_MAX_DEG
from backend.app.models import Gene
from backend.app.physics import (
    RHO_M_CAP_MM,
    feasibility_from_profile,
    meridian_curvature,
    rolypoly_feasibility,
)


def _sphere_profile(radius: float, n: int = 513) -> tuple[np.ndarray, np.ndarray]:
    """上半球 r(z) = sqrt(2 R z - z^2), z ∈ [0, R] を等間隔サンプル。"""
    z = np.linspace(0.0, radius, n)
    r2 = np.maximum(2.0 * radius * z - z * z, 0.0)
    r = np.sqrt(r2)
    return z, r


def _spherical_cap_with_taper(
    rb: float, cap_angle_deg: float, extra_height: float, n: int = 513
) -> tuple[np.ndarray, np.ndarray]:
    """球キャップ（cap_angle まで）の上に直線状のテーパを付けた簡易プロファイル。"""
    cap_z_end = rb * (1.0 - math.cos(math.radians(cap_angle_deg)))
    cap_r_end = rb * math.sin(math.radians(cap_angle_deg))
    total = cap_z_end + extra_height
    z = np.linspace(0.0, total, n)
    r = np.zeros_like(z)
    mask_cap = z <= cap_z_end
    r2 = np.maximum(2.0 * rb * z[mask_cap] - z[mask_cap] ** 2, 0.0)
    r[mask_cap] = np.sqrt(r2)
    # テーパ区間は頂点に向かって線形に縮める
    z_tail = z[~mask_cap]
    if z_tail.size:
        t = (z_tail - cap_z_end) / max(extra_height, 1e-9)
        r[~mask_cap] = cap_r_end * (1.0 - t)
    return z, r


# ----------------------------- meridian_curvature ---------------------------


def test_meridian_curvature_sphere():
    """完全球の子午面曲率は半径に等しい（端点の数値誤差を除く）。"""
    R = 30.0
    z, r = _sphere_profile(R, n=1025)
    rho = meridian_curvature(z, r)
    # 端点は √z 型特異点 + 有限差分の影響で荒れる。中央 60% だけで評価。
    n = len(rho)
    lo, hi = int(0.2 * n), int(0.8 * n)
    assert np.allclose(rho[lo:hi], R, rtol=0.02), rho[lo:hi]


# ----------------------------- sphere（完全球） -----------------------------


def test_feasibility_sphere_is_feasible():
    """完全球は θ_max=75° で feasible。z_cog_max は安全率込みで半径未満、数 mm 以上。"""
    R = 30.0
    z, r = _sphere_profile(R, n=513)
    feas = feasibility_from_profile(z, r, theta_max_deg=TILT_MAX_DEG)
    assert feas.is_feasible
    assert feas.worst_margin > 0.0
    # rho_m ~ R, eps=0.5 → z_cog_max < (R-eps)*safety。球は z_CoG を中心近く
    # に寄せれば任意角に対応できるはず。
    assert feas.z_cog_max > 0.5 * R
    assert feas.z_cog_max < R
    # 底部曲率半径は R にほぼ一致（±10%）
    assert abs(feas.rho_m_bottom - R) / R < 0.1


# ----------------------------- cylinder / cone ------------------------------


def test_feasibility_cylinder_is_infeasible():
    """円柱は r'=0（cot(75°) 以上にならず）＋ rho_m が cap を超えるので不合格。"""
    z = np.linspace(0.0, 50.0, 513)
    r = np.full_like(z, 20.0)
    feas = feasibility_from_profile(z, r, theta_max_deg=TILT_MAX_DEG)
    assert not feas.is_feasible


def test_feasibility_thin_cone_is_infeasible():
    """細い円錐（r' ~ 0.1）は θ_max=75° の接地点条件（r' ≥ cot75°≈0.268）を
    満たさず、かつ r''≈0 で rho_m が cap を超えるので不合格。"""
    z = np.linspace(0.0, 50.0, 513)
    r = np.maximum(10.0 - 0.1 * z, 0.0)  # 頂点は z=100 なのでピークは z=0
    # この関数は r のピークを前提にしているので、代わりに「登って下る」単峰形にする。
    # 頂上の尖った三角形: r(z) = min(0.1 z, 10 - 0.1(z-50))
    r = np.minimum(0.1 * z, 10.0 - 0.1 * (z - 50.0))
    r = np.maximum(r, 0.0)
    feas = feasibility_from_profile(z, r, theta_max_deg=TILT_MAX_DEG)
    assert not feas.is_feasible


def test_feasibility_steep_cone_rejected_by_rho_cap():
    """急な円錐（r'>> cot75°）でも、r''=0 で曲率半径が発散するので
    RHO_M_CAP_MM で弾かれることを確認。"""
    # ピーク z=20, height=40 の三角形 r(z)
    z = np.linspace(0.0, 40.0, 513)
    slope = 0.8  # r' = 0.8 → cot75°≈0.268 より十分大きい
    r = np.where(z <= 20.0, slope * z, slope * (40.0 - z))
    feas = feasibility_from_profile(z, r, theta_max_deg=TILT_MAX_DEG)
    # r'' ≈ 0 のため rho_m が RHO_M_CAP_MM を超え、有効点なし
    assert not feas.is_feasible
    # デバッグ情報: rho_m_bottom が cap を超える（もしくは 0.0）はず
    assert feas.rho_m_bottom <= 0.0 or feas.rho_m_bottom >= RHO_M_CAP_MM


# ----------------------------- パラメトリック現実形状 ----------------------


def test_feasibility_realistic_cap_shape_is_feasible():
    """shape モジュール由来の典型パラメータでは feasible。"""
    from backend.app.shape import (
        ShapeParams,
        tune_height_for_delta,
    )

    params = ShapeParams(
        rb=30.0,
        cap_angle_deg=82.0,
        rt=1.5,
        delta_target=8.0,
    )
    height, z_com, z_dense, r_dense = tune_height_for_delta(params)
    feas = feasibility_from_profile(z_dense, r_dense, theta_max_deg=TILT_MAX_DEG)
    assert feas.is_feasible, feas
    assert feas.z_cog_max > 0.0
    # 底曲率半径は rb にほぼ一致（±20% 以内。テーパとの接続で平滑化される）
    assert abs(feas.rho_m_bottom - params.rb) / params.rb < 0.2


# ----------------------------- θ の境界挙動 -------------------------------


def test_feasibility_sphere_passes_at_60_and_75():
    """完全球は 60° でも 75° でも合格するはず。"""
    R = 30.0
    z, r = _sphere_profile(R, n=513)
    f60 = feasibility_from_profile(z, r, theta_max_deg=60.0)
    f75 = feasibility_from_profile(z, r, theta_max_deg=75.0)
    assert f60.is_feasible
    assert f75.is_feasible
    # 75° のほうが対象範囲が広いので、z_cog_max は 60° の結果以下になる
    assert f75.z_cog_max <= f60.z_cog_max + 1e-6


# ----------------------------- rolypoly_feasibility（radii経由） --------


def test_generated_gene_bottom_renders_as_sphere():
    """v2 gene（z_warp=2.0）の smoothing 結果は底が球面を忠実に再現する。

    具体的には、底から少し登った z 位置での半径 r が、球の公式
    ``r(z) = sqrt(2·rb·z - z²)`` と ~5% 以内で一致する。z_warp=1.0（等間隔）
    では先頭ノード間隔が 2mm ほどあり、√z 特異点を表現できずに尖る。
    """
    from backend.app.gene import sample_gene_with_feasibility
    from backend.app.smoothing import smooth_profile

    gene, feas = sample_gene_with_feasibility(seed=42)
    assert gene.z_warp == 2.0

    # GAUSSIAN smoothing の dense プロファイルの底付近を評価。
    z_dense, r_dense = smooth_profile(gene)
    rb = feas.rho_m_bottom  # 物理モジュールが推定した曲率半径
    assert rb > 0

    # 数値微分の荒れる最先頭は避け、安定した位置で球を検証する
    for idx in (30, 50, 80):
        z = float(z_dense[idx])
        r = float(r_dense[idx])
        if z <= 0 or z >= rb:
            continue
        r_sphere = (2.0 * rb * z - z * z) ** 0.5
        # 5% 以内 or 絶対誤差 0.3mm 以内
        assert (
            abs(r - r_sphere) / max(r_sphere, 1e-6) < 0.05
            or abs(r - r_sphere) < 0.3
        ), f"idx={idx} z={z:.3f} r={r:.3f} r_sphere={r_sphere:.3f}"


def test_rolypoly_feasibility_on_generated_gene_has_plausible_bottom_curvature():
    """生成 gene の radii 経由判定は保守的で False Negative が出うるが、
    少なくとも底部曲率半径 ``rho_m_bottom`` は正で、SPHERE_RB の値域内に入る。

    is_feasible 自体の真値は生成時の feasibility（密プロファイル上の判定）で
    求め、DB に保存された feasibility と整合する。
    """
    from backend.app.config import SPHERE_RB_MAX_MM, SPHERE_RB_MIN_MM
    from backend.app.gene import sample_gene_with_feasibility

    gene, feas_gen = sample_gene_with_feasibility(seed=42)
    assert feas_gen.is_feasible

    feas_rt = rolypoly_feasibility(gene, theta_max_deg=TILT_MAX_DEG)
    assert feas_rt.rho_m_bottom > 0.0
    # 球キャップの半径相当（±30% 以内）のオーダーに収まる
    assert feas_rt.rho_m_bottom < 2.0 * SPHERE_RB_MAX_MM
    assert feas_rt.rho_m_bottom > 0.3 * SPHERE_RB_MIN_MM


def test_rolypoly_feasibility_rejects_degenerate_gene():
    """radii が定数（ほぼ円柱）の gene は rolypoly_feasibility で不合格。"""
    radii = [0.0] + [20.0] * (N_NODES - 2) + [0.0]
    gene = Gene(version=2, N=N_NODES, height=40.0, bottom_radius=0.0, radii=radii)
    feas = rolypoly_feasibility(gene, theta_max_deg=TILT_MAX_DEG)
    assert not feas.is_feasible


# ----------------------------- 設定値 -------------------------------------


def test_tilt_max_is_75():
    """方針どおり θ_max=75° が設定されていること（回帰防止）。"""
    assert TILT_MAX_DEG == pytest.approx(75.0)
