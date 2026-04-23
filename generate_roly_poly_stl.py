"""
鉛直軸対称・一様密度・内部空洞なしの「起き上がりこぼし」STL を生成します。

## 形状の考え方
- 接地しうる領域（底側）を**半径 Rb の完全な球面**にして、接地点の子午面曲率半径を
  広い傾き角でも **常に Rb** に保ちます。
- 上側は先細り（体積を減らす）にして、一様密度でも重心を球中心より少し下へ落とします。

## 条件（ユーザー指定の「重心が曲率半径よりもわずかに下」）
傾き角度 theta が [-60°, +60°] の範囲で、接地点が球面上にあるとき:

  法線方向距離 d = Rb - delta * cos(|theta|)

ここで delta = (球中心の z) - (重心の z) = rb - z_com > 0。
要求は「重心が曲率半径より eps だけ下」なので:

  d < Rb - eps   （全 theta で）

最も厳しいのは |theta|=60° なので、
  delta * cos(60°) > eps  =>  delta > 2 * eps

このスクリプトは回転体の断面 r(z) を作り、上部高さを調整して delta を狙い値に合わせ、
角度グリッドで不等式を検証してから ASCII STL を出力します（外部依存なし）。
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, List, Optional, Sequence, Tuple


Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class Params:
    # 底側の接地球面の半径 (mm)
    rb: float = 30.0
    # 球面領域が底からどこまで続くか（極角, deg）
    cap_angle_deg: float = 75.0
    # 上端の半径 (mm)。0 は鋭い先端（造形性はプリンタ次第）
    rt: float = 2.0
    # 余裕量: 接地点の曲率半径より重心が eps だけ「下」にある (mm)
    eps: float = 0.5
    # 狙いの delta = 球中心z - 重心z = rb - z_com (mm)
    delta_target: float = 8.0
    # 検証する傾き角度範囲 (deg)
    tilt_deg: float = 60.0

    # メッシュ分割
    n_theta: int = 512
    # 断面サンプリング（回転体側面の「横バンド」を抑えるため適応細分化）
    # - profile_tol: 断面を直線近似したときの半径誤差許容 (mm)
    # - max_dz: 1区間の最大 z 間隔 (mm)（粗い分割の取りこぼし防止）
    profile_tol: float = 0.02
    max_dz: float = 0.8
    # backend/app/smoothing.py を使う場合の密化倍率（大きいほど滑らかだが重い）
    smoothing_dense_factor: int = 16


class ProfileSmoothing(str, Enum):
    NONE = "none"
    BSPLINE = "bspline"
    PCHIP = "pchip"
    GAUSSIAN = "gaussian"


def sphere_r(rb: float, z: float) -> float:
    # 球の中心は (0, rb)、最下点は z=0。
    # r^2 + (z - rb)^2 = rb^2  =>  r = sqrt(2rb z - z^2)
    v = 2.0 * rb * z - z * z
    return math.sqrt(max(v, 0.0))


def sphere_dr_dz(rb: float, z: float) -> float:
    r = sphere_r(rb, z)
    if r <= 1e-12:
        return 0.0
    # r^2 = 2rb z - z^2 から  2 r dr/dz = 2rb - 2z
    return (rb - z) / r


def sphere_d2r_dz2(rb: float, z: float) -> float:
    """
    球面 r(z)=sqrt(2rb z - z^2) の 2階微分。

    dr/dz = (rb - z) / r
    d2r/dz2 = -1/r - (rb - z)^2 / r^3
    """
    r = sphere_r(rb, z)
    if r <= 1e-12:
        return 0.0
    a = rb - z
    return -1.0 / r - (a * a) / (r * r * r)


def quintic_r(
    z: float,
    z0: float,
    r0: float,
    dr0: float,
    d2r0: float,
    z1: float,
    r1: float,
    dr1: float,
    d2r1: float,
) -> float:
    """
    5次多項式で r(z) を補間する（C2連続）。

    端点 (z0, z1) で r, dr/dz, d2r/dz2 を一致させる。
    実装は t=(z-z0)/L の多項式:
      r(t)=a0 + a1 t + a2 t^2 + a3 t^3 + a4 t^4 + a5 t^5
    を解いて係数を求める（L=z1-z0）。
    """
    if z <= z0:
        return r0
    if z >= z1:
        return r1
    L = z1 - z0
    if abs(L) <= 1e-12:
        return r0

    # t の基準での微分条件に変換
    # dr/dt = L * dr/dz,  d2r/dt2 = L^2 * d2r/dz2
    v0 = dr0 * L
    a0 = r0
    a1 = v0
    a2 = 0.5 * d2r0 * L * L

    t1 = 1.0
    v1 = dr1 * L
    acc1 = d2r1 * L * L

    # 未知数 a3,a4,a5 の線形方程式
    # r(1): a0+a1+a2+a3+a4+a5 = r1
    # r'(1): a1+2a2+3a3+4a4+5a5 = v1
    # r''(1): 2a2+6a3+12a4+20a5 = acc1
    b0 = r1 - (a0 + a1 + a2)
    b1 = v1 - (a1 + 2.0 * a2)
    b2 = acc1 - (2.0 * a2)

    # 解は手計算で固定（3x3）
    # [1  1  1 ][a3]=[b0]
    # [3  4  5 ][a4]=[b1]
    # [6 12 20 ][a5]=[b2]
    # これを消去して求める
    a5 = (b2 - 6.0 * b1 + 12.0 * b0) / 2.0
    a4 = b1 - 3.0 * b0 - 2.0 * a5
    a3 = b0 - a4 - a5

    t = (z - z0) / L
    return a0 + a1 * t + a2 * t**2 + a3 * t**3 + a4 * t**4 + a5 * t**5


def build_profile(p: Params, height: float) -> List[Tuple[float, float]]:
    """
    回転体断面の点列 [(r,z), ...] を返す（z=0 から z=height まで）。
    """
    cap_angle = math.radians(p.cap_angle_deg)
    z_cap_end = p.rb * (1.0 - math.cos(cap_angle))
    r_cap_end = p.rb * math.sin(cap_angle)

    # 接続点で球面の r, r', r'' を取る（C2連続につなぐ）
    dr0 = sphere_dr_dz(p.rb, z_cap_end)
    d2r0 = sphere_d2r_dz2(p.rb, z_cap_end)

    # 上端は「形状的に滑らか」にしたいので r', r'' を 0 に寄せる
    dr1 = 0.0
    d2r1 = 0.0

    def subdivide_by_error(
        z0: float,
        z1: float,
        r_at: Callable[[float], float],
        out: List[Tuple[float, float]],
        *,
        tol: float,
        max_dz: float,
        depth: int = 0,
    ) -> None:
        """
        z0→z1 の区間を、直線近似の誤差が tol 以下になるまで再帰分割して点列へ追加する。
        out には (r(z0),z0) が既に入っている前提で、(r(z1),z1) を末尾に追加する。
        """
        r0 = r_at(z0)
        r1 = r_at(z1)
        zm = 0.5 * (z0 + z1)
        rm = r_at(zm)
        # 端点線形補間との差（= この区間を円錐台で近似したときの断面誤差）
        r_lin = 0.5 * (r0 + r1)
        err = abs(rm - r_lin)

        if (z1 - z0) > max_dz:
            need_split = True
        else:
            need_split = err > tol

        # 念のため再帰深さに上限（無限分割防止）
        if need_split and depth < 40:
            subdivide_by_error(z0, zm, r_at, out, tol=tol, max_dz=max_dz, depth=depth + 1)
            subdivide_by_error(zm, z1, r_at, out, tol=tol, max_dz=max_dz, depth=depth + 1)
            return

        out.append((max(r1, 0.0), z1))

    pts: List[Tuple[float, float]] = []

    # 底側の球面（適応分割）
    pts.append((sphere_r(p.rb, 0.0), 0.0))
    subdivide_by_error(0.0, z_cap_end, lambda z: sphere_r(p.rb, z), pts, tol=p.profile_tol, max_dz=p.max_dz)

    # 上側のテーパ（5次補間, C2連続・適応分割）
    if height > z_cap_end + 1e-6:
        def r_taper(z: float) -> float:
            return quintic_r(z, z_cap_end, r_cap_end, dr0, d2r0, height, p.rt, dr1, d2r1)

        # subdivide は「始点が out に入っている前提」なので、球面末尾(=z_cap_end)から続ける
        subdivide_by_error(z_cap_end, height, r_taper, pts, tol=p.profile_tol, max_dz=p.max_dz)

    # 単調性の確保（非負 & 接続点より上で不自然な膨らみが出たら抑える）
    # 補間のオーバーシュートが出た場合は、接続点より上を「非増加」にクランプする
    for i in range(1, len(pts)):
        if pts[i][1] > z_cap_end and pts[i][0] > pts[i - 1][0]:
            pts[i] = (pts[i - 1][0], pts[i][1])

    return pts


def _try_smooth_with_backend(
    z_nodes: Sequence[float],
    r_nodes: Sequence[float],
    *,
    height: float,
    method: ProfileSmoothing,
    dense_factor: int,
) -> Optional[Tuple[List[float], List[float]]]:
    """
    backend/app/smoothing.py の実装を流用して (z,r) を密サンプル化する。

    注意:
    - smoothing.smooth_profile() は末端半径を 0 に固定する仕様なので、
      ここでは内部関数（_bspline/_pchip/_gaussian）を呼び、端点は
      r_nodes[0], r_nodes[-1] を維持する。
    - NumPy/SciPy が無い環境では None を返してフォールバックする。
    """
    if method == ProfileSmoothing.NONE:
        return None

    try:
        import numpy as np  # type: ignore
        from backend.app import smoothing as sm  # type: ignore
    except Exception:
        return None

    z_nodes_np = np.asarray(z_nodes, dtype=float)
    r_nodes_np = np.asarray(r_nodes, dtype=float)

    n_nodes = len(z_nodes_np)
    if n_nodes < 2:
        return None

    dense_factor = int(max(2, dense_factor))
    n_dense = (n_nodes - 1) * dense_factor + 1
    z_dense = np.linspace(0.0, float(height), n_dense)

    if method == ProfileSmoothing.BSPLINE:
        # z が等間隔という前提で radii を Bスプライン評価
        r_dense = sm._bspline(r_nodes_np, len(z_dense))
    elif method == ProfileSmoothing.PCHIP:
        r_dense = sm._pchip(z_nodes_np, r_nodes_np, z_dense)
    elif method == ProfileSmoothing.GAUSSIAN:
        r_dense = sm._gaussian(z_nodes_np, r_nodes_np, z_dense)
    else:
        return None

    # 端点固定 + 負値クリップ（数値誤差対策）
    r_dense[0] = float(r_nodes_np[0])
    r_dense[-1] = float(r_nodes_np[-1])
    np.maximum(r_dense, 0.0, out=r_dense)
    return (z_dense.tolist(), r_dense.tolist())


def smooth_profile_points(
    profile: Sequence[Tuple[float, float]],
    *,
    height: float,
    method: ProfileSmoothing,
    dense_factor: int,
    n_nodes: int = 33,
) -> Sequence[Tuple[float, float]]:
    """
    断面点列を「制御点」へ落としてから backend/app/smoothing.py で滑らか化する。

    - profile は任意のサンプル列（単調増→単調減の単峰を想定）
    - いったん z を等間隔 n_nodes 点にし、r を線形補間して制御点とする
    """
    if method == ProfileSmoothing.NONE:
        return profile

    # 等間隔ノードを作って r を補間（profile は z 昇順のはず）
    n_nodes = int(max(9, n_nodes))
    z_nodes = [height * i / (n_nodes - 1) for i in range(n_nodes)]

    zs = [z for _, z in profile]
    rs = [r for r, _ in profile]

    def interp_r(zq: float) -> float:
        # 端はそのまま
        if zq <= zs[0]:
            return rs[0]
        if zq >= zs[-1]:
            return rs[-1]
        # 線形探索（n_nodes が小さいので十分）
        for i in range(len(zs) - 1):
            z0, z1 = zs[i], zs[i + 1]
            if z0 <= zq <= z1:
                t = (zq - z0) / (z1 - z0) if z1 > z0 else 0.0
                return rs[i] * (1.0 - t) + rs[i + 1] * t
        return rs[-1]

    r_nodes = [interp_r(z) for z in z_nodes]

    smoothed = _try_smooth_with_backend(
        z_nodes,
        r_nodes,
        height=height,
        method=method,
        dense_factor=dense_factor,
    )
    if smoothed is None:
        # 使えない場合は元の profile を返す（依存関係なしで動くことを優先）
        return profile

    z_dense, r_dense = smoothed
    return [(float(r), float(z)) for z, r in zip(z_dense, r_dense)]


def integrate_volume_and_com_z(profile: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """
    z軸回りの回転体（中実）の体積と重心 z を数値積分で求める。

      V = pi ∫ r(z)^2 dz
      z_com = (pi/V) ∫ z r(z)^2 dz

    与えられた (r,z) サンプル上で台形則を使う。
    戻り値は (V_mm3, z_com_mm)。
    """
    if len(profile) < 2:
        raise ValueError("profile too short")

    v_int = 0.0
    z_int = 0.0
    for (r0, z0), (r1, z1) in zip(profile[:-1], profile[1:]):
        dz = z1 - z0
        a0 = r0 * r0
        a1 = r1 * r1
        v_int += 0.5 * (a0 + a1) * dz
        z_int += 0.5 * (z0 * a0 + z1 * a1) * dz

    V = math.pi * v_int
    if V <= 0:
        raise ValueError("non-positive volume")
    z_com = (math.pi * z_int) / V
    return V, z_com


def tune_height_for_delta(
    p: Params,
    *,
    smoothing_method: ProfileSmoothing,
) -> Tuple[float, float, List[Tuple[float, float]]]:
    """
    delta が delta_target に近づくように、上部高さ（height）を二分探索で調整する。

      delta = rb - z_com  （球中心は z=rb）
    """
    cap_angle = math.radians(p.cap_angle_deg)
    z_cap_end = p.rb * (1.0 - math.cos(cap_angle))

    # 探索範囲：接続点の少し上 ～ ほどほどの高さ
    h_lo = z_cap_end + 0.5
    h_hi = p.rb * 2.2

    def delta_for_height(h: float) -> Tuple[float, float, List[Tuple[float, float]]]:
        prof = build_profile(p, h)
        prof = list(
            smooth_profile_points(
                prof,
                height=h,
                method=smoothing_method,
                dense_factor=p.smoothing_dense_factor,
            )
        )
        _, zc = integrate_volume_and_com_z(prof)
        return (p.rb - zc), zc, prof

    d_lo, zc_lo, prof_lo = delta_for_height(h_lo)
    d_hi, zc_hi, prof_hi = delta_for_height(h_hi)

    # もし目標を挟めていなければ上限を少し伸ばす（稀だが安全策）
    tries = 0
    while not (d_lo >= p.delta_target >= d_hi) and tries < 12:
        h_hi *= 1.25
        d_hi, zc_hi, prof_hi = delta_for_height(h_hi)
        tries += 1

    # 目標は delta_target。一般に height を上げるほど delta は小さくなる。
    if not (d_lo >= p.delta_target >= d_hi):
        # 挟めない場合は近い方を採用
        if abs(d_lo - p.delta_target) < abs(d_hi - p.delta_target):
            return h_lo, zc_lo, prof_lo
        return h_hi, zc_hi, prof_hi

    # 二分探索
    best = (h_lo, zc_lo, prof_lo, abs(d_lo - p.delta_target))
    for _ in range(60):
        h_mid = 0.5 * (h_lo + h_hi)
        d_mid, zc_mid, prof_mid = delta_for_height(h_mid)
        err = abs(d_mid - p.delta_target)
        if err < best[3]:
            best = (h_mid, zc_mid, prof_mid, err)
        if d_mid >= p.delta_target:
            h_lo, d_lo = h_mid, d_mid
        else:
            h_hi, d_hi = h_mid, d_mid
        if (h_hi - h_lo) < 1e-3:
            break

    h_best, zc_best, prof_best, _ = best
    return h_best, zc_best, prof_best


def validate_constraint(p: Params, z_com: float) -> Tuple[bool, float]:
    """
    条件検証:
      theta in [-tilt_deg, tilt_deg] で
      dot(COM - contact, inward_normal) < curvature_radius(contact) - eps

    接地が球面上にあるなら curvature_radius == rb で、
      dot = rb - delta*cos(|theta|)

    戻り値: (ok, worst_margin_mm)
      worst_margin = (rb - eps) - dot  （これが常に正ならOK）
    """
    delta = p.rb - z_com
    worst_margin = float("inf")
    ok = True
    for i in range(241):
        theta = -p.tilt_deg + (2.0 * p.tilt_deg) * i / 240.0
        c = math.cos(math.radians(abs(theta)))
        dot = p.rb - delta * c
        margin = (p.rb - p.eps) - dot
        worst_margin = min(worst_margin, margin)
        if margin <= 0:
            ok = False
    return ok, worst_margin


def rotate_y(v: Vec3, angle_rad: float) -> Vec3:
    x, y, z = v
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return (c * x + s * z, y, -s * x + c * z)


def write_ascii_stl(path: str, triangles: Iterable[Tuple[Vec3, Vec3, Vec3]], solid_name: str = "roly_poly") -> None:
    def normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
        ax, ay, az = a
        bx, by, bz = b
        cx, cy, cz = c
        ux, uy, uz = (bx - ax, by - ay, bz - az)
        vx, vy, vz = (cx - ax, cy - ay, cz - az)
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln <= 1e-18:
            return (0.0, 0.0, 0.0)
        return (nx / ln, ny / ln, nz / ln)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"solid {solid_name}\n")
        for a, b, c in triangles:
            nx, ny, nz = normal(a, b, c)
            f.write(f"  facet normal {nx:.8e} {ny:.8e} {nz:.8e}\n")
            f.write("    outer loop\n")
            f.write(f"      vertex {a[0]:.8e} {a[1]:.8e} {a[2]:.8e}\n")
            f.write(f"      vertex {b[0]:.8e} {b[1]:.8e} {b[2]:.8e}\n")
            f.write(f"      vertex {c[0]:.8e} {c[1]:.8e} {c[2]:.8e}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write(f"endsolid {solid_name}\n")


def mesh_revolve(profile: Sequence[Tuple[float, float]], n_theta: int) -> List[Tuple[Vec3, Vec3, Vec3]]:
    """
    断面 (r,z) を z軸回りに回転して三角形メッシュ化する。
    座標系は mm、z が鉛直。
    """
    # 各 z 断面のリング頂点を事前計算
    rings: List[List[Vec3]] = []
    for r, z in profile:
        ring: List[Vec3] = []
        for j in range(n_theta):
            ang = 2.0 * math.pi * j / n_theta
            x = r * math.cos(ang)
            y = r * math.sin(ang)
            ring.append((x, y, z))
        rings.append(ring)

    tris: List[Tuple[Vec3, Vec3, Vec3]] = []
    # 側面
    for i in range(len(profile) - 1):
        r0, _ = profile[i]
        r1, _ = profile[i + 1]
        for j in range(n_theta):
            jn = (j + 1) % n_theta
            a = rings[i][j]
            b = rings[i + 1][j]
            c = rings[i + 1][jn]
            d = rings[i][jn]
            # 回転軸近傍の退化四角形はスキップ
            if r0 <= 1e-9 and r1 <= 1e-9:
                continue
            if r0 <= 1e-9:
                tris.append((b, c, a))
            elif r1 <= 1e-9:
                tris.append((b, a, d))
            else:
                tris.append((a, b, c))
                tris.append((a, c, d))

    # 必要なら上面をキャップする
    r_top, z_top = profile[-1]
    if r_top > 1e-9:
        center = (0.0, 0.0, z_top)
        top_ring = rings[-1]
        # 扇形分割（上面の法線が +z 側を向くように並べる）
        for j in range(n_theta):
            jn = (j + 1) % n_theta
            a = top_ring[j]
            b = top_ring[jn]
            tris.append((a, b, center))

    return tris


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate an axisymmetric roly-poly STL (solid, uniform density).")
    ap.add_argument("--out", default="roly_poly.stl", help="Output STL path (ASCII).")
    ap.add_argument("--rb", type=float, default=Params.rb, help="Bottom sphere radius (mm).")
    ap.add_argument("--cap-angle", type=float, default=Params.cap_angle_deg, help="Sphere cap angle from bottom (deg).")
    ap.add_argument("--rt", type=float, default=Params.rt, help="Top radius (mm).")
    ap.add_argument("--eps", type=float, default=Params.eps, help="Margin below curvature radius (mm).")
    ap.add_argument("--delta", type=float, default=Params.delta_target, help="Target delta = rb - z_com (mm).")
    ap.add_argument("--tilt", type=float, default=Params.tilt_deg, help="Validate tilt range [-tilt, +tilt] (deg).")
    ap.add_argument("--n-theta", type=int, default=Params.n_theta, help="Angular tessellation.")
    ap.add_argument(
        "--smooth",
        choices=[m.value for m in ProfileSmoothing],
        default=ProfileSmoothing.BSPLINE.value,
        help="断面プロファイルを backend/app/smoothing.py で滑らか化（利用不可なら自動フォールバック）",
    )
    ap.add_argument(
        "--smooth-factor",
        type=int,
        default=Params.smoothing_dense_factor,
        help="滑らか化の密サンプル倍率（大きいほど滑らか・重い）",
    )
    args = ap.parse_args()

    p = Params(
        rb=args.rb,
        cap_angle_deg=args.cap_angle,
        rt=args.rt,
        eps=args.eps,
        delta_target=args.delta,
        tilt_deg=args.tilt,
        n_theta=max(32, args.n_theta),
        smoothing_dense_factor=max(2, args.smooth_factor),
    )

    smoothing_method = ProfileSmoothing(args.smooth)
    height, z_com, profile = tune_height_for_delta(p, smoothing_method=smoothing_method)
    V, z_com = integrate_volume_and_com_z(profile)

    ok, worst_margin = validate_constraint(p, z_com)

    tris = mesh_revolve(profile, p.n_theta)
    write_ascii_stl(args.out, tris, solid_name="roly_poly")

    print("=== roly-poly STL generated ===")
    print(f"out           : {args.out}")
    print(f"rb            : {p.rb:.3f} mm (curvature radius at contact on sphere)")
    print(f"cap_angle     : {p.cap_angle_deg:.2f} deg")
    print(f"rt            : {p.rt:.3f} mm")
    print(f"height        : {height:.3f} mm")
    print(f"smoothing     : {args.smooth} (factor={p.smoothing_dense_factor})")
    print(f"profile points: {len(profile)}")
    print(f"volume        : {V/1000.0:.3f} cm^3")
    print(f"z_com         : {z_com:.3f} mm (from bottom tip)")
    print(f"delta=rb-z_com: {p.rb - z_com:.3f} mm  (target {p.delta_target:.3f})")
    print(f"tilt check    : +/- {p.tilt_deg:.1f} deg")
    print(f"constraint ok : {ok}")
    print(f"worst margin  : {worst_margin:.4f} mm (must be > 0)")
    if not ok:
        raise SystemExit("Constraint NOT satisfied: increase --delta or decrease --eps / change geometry.")


if __name__ == "__main__":
    main()

