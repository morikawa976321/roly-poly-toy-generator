"""
上部延長とメッシュ用 effective プロファイル。

役割: gene のベース形状に上部延長を付与した密 (z, r) を提供。
働き: smooth + 5次延長のあと B3 再フィットで 1 本化。``metrics`` / メッシュ・STEP 下流が ``effective_profile`` を参照する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

import numpy as np

from .shape import _eval_quintic, _quintic_coeffs
from .smoothing import b3_refit_profile, mild_smooth_profile, smooth_profile

if TYPE_CHECKING:
    from .models import Gene
else:
    Gene = object  # type: ignore

_EXTENSION_SAMPLES = 96
_JUNCTION_FIT_WINDOW = 24
_JUNCTION_FIT_MIN = 8
_R_EPS = 1e-9
_Z_EPS = 1e-9


def base_gene(gene: Gene) -> Gene:
    """延長量を 0 にしたベース gene（radii / height は不変）。"""
    data = gene.model_dump()
    data["top_extension_mm"] = 0.0
    return type(gene).model_validate(data)


def _junction_state(z: np.ndarray, r: np.ndarray) -> Tuple[float, float, float, float]:
    """上端での H, 接合半径, dr/dz, d²r/dz²。

    smooth_profile は r[-1] を gene 制御点へハード固定するため、
    最終 1 点だけ半径が滑らか曲線から外れる。延長時は最終点を除く
    尾部に 2 次式を当て、z=H での半径・傾き・曲率を接合条件とする。
    """
    n = len(z)
    H = float(z[-1])
    k = min(_JUNCTION_FIT_WINDOW, n - 2)
    if k < _JUNCTION_FIT_MIN:
        r_junc = float(r[-1])
        dz = float(z[-1] - z[-2]) if n >= 2 else 1.0
        dr = (float(r[-1]) - float(r[-2])) / dz if dz > _Z_EPS else 0.0
        d2r = 0.0
    else:
        z_fit = z[-k - 1 : -1]
        r_fit = r[-k - 1 : -1]
        p = np.polyfit(z_fit, r_fit, 2)
        r_junc = float(np.polyval(p, H))
        dr = float(np.polyval(np.polyder(p), H))
        d2r = float(2.0 * p[0])
    if dr > -1e-9:
        dr = -1e-6
    return H, r_junc, dr, d2r


def _base_with_smooth_top(z0: np.ndarray, r0: np.ndarray) -> np.ndarray:
    """延長用にベース上端のハード固定段差を除去した半径列。"""
    _, r_junc, _, _ = _junction_state(z0, r0)
    r_base = np.array(r0, dtype=float, copy=True)
    r_base[-1] = r_junc
    return r_base


def _quintic_extension_valid(
    H: float,
    r_junc: float,
    dr: float,
    d2r: float,
    L: float,
    n_check: int = 64,
) -> bool:
    if L <= _Z_EPS or r_junc <= _R_EPS:
        return False
    coeffs = _quintic_coeffs(r_junc, dr, d2r, 0.0, 0.0, 0.0, L)
    z = np.linspace(H, H + L, n_check, dtype=float)
    r = _eval_quintic(z, H, H + L, coeffs)
    if float(np.min(r)) < -0.05:
        return False
    return bool(np.all(np.diff(r) <= 1e-5))


def _extension_segment(
    H: float,
    r_junc: float,
    dr: float,
    d2r: float,
    delta: float,
    L_span: float,
    n_samples: int = _EXTENSION_SAMPLES,
) -> Tuple[np.ndarray, np.ndarray]:
    """区間 (H, H+delta] を、長さ L_span の 5 次外挿（先端 r=0, C²）上でサンプル。"""
    if delta <= _Z_EPS or r_junc <= _R_EPS or L_span <= _Z_EPS:
        return np.array([], dtype=float), np.array([], dtype=float)

    coeffs = _quintic_coeffs(r_junc, dr, d2r, 0.0, 0.0, 0.0, L_span)
    z_seg = np.linspace(H, H + delta, n_samples + 1, dtype=float)[1:]
    r_seg = _eval_quintic(z_seg, H, H + L_span, coeffs)
    np.maximum(r_seg, 0.0, out=r_seg)
    for i in range(1, len(r_seg)):
        if r_seg[i] > r_seg[i - 1]:
            r_seg[i] = r_seg[i - 1]
    return z_seg, r_seg


def _profile_valid(z: np.ndarray, r: np.ndarray, peak_idx: int) -> bool:
    if np.any(r < -_R_EPS):
        return False
    tail = r[peak_idx:]
    if len(tail) < 2:
        return True
    return bool(np.all(np.diff(tail) <= 1e-4))


def _compute_delta_max(
    z0: np.ndarray,
    r0: np.ndarray,
    tol: float = 0.05,
) -> float:
    H, r_junc, dr, d2r = _junction_state(z0, r0)
    if r_junc <= _R_EPS:
        return 0.0

    lo, hi = 1.0, max(2.0, r_junc * 4.0, float(z0[-1]) * 0.5)
    while hi < 500.0 and _quintic_extension_valid(H, r_junc, dr, d2r, hi):
        hi *= 2.0

    best = 0.0
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        if _quintic_extension_valid(H, r_junc, dr, d2r, mid):
            z_seg, r_seg = _extension_segment(H, r_junc, dr, d2r, mid, mid)
            if len(r_seg) and float(r_seg[-1]) <= tol + 1e-3:
                best = mid
                lo = mid
            else:
                hi = mid
        else:
            hi = mid
    return float(best)


def _extension_junction_source(gene: Gene) -> Tuple[np.ndarray, np.ndarray]:
    """延長の接続条件は旧 smooth_profile から取る（5 次外挿はそちら向けに調整済み）。"""
    return smooth_profile(base_gene(gene))


def _build_extended(
    z0: np.ndarray,
    r0: np.ndarray,
    delta: float,
    delta_max: float,
    junction_z: np.ndarray | None = None,
    junction_r: np.ndarray | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    jz = junction_z if junction_z is not None else z0
    jr = junction_r if junction_r is not None else r0
    H, r_junc, dr, d2r = _junction_state(jz, jr)
    r_base = np.array(r0, dtype=float, copy=True)
    r_base[-1] = r_junc
    L_span = max(delta, delta_max)
    z_seg, r_seg = _extension_segment(H, r_junc, dr, d2r, delta, L_span)
    if len(z_seg) == 0:
        return z0, r0
    z_out = np.concatenate([z0, z_seg])
    r_out = np.concatenate([r_base, r_seg])
    peak_idx = int(np.argmax(r_out))
    if not _profile_valid(z_out, r_out, peak_idx):
        raise ValueError("extended profile violates monotonicity or r>=0")
    return z_out, r_out


def profile_with_extension(
    gene: Gene,
    z0: np.ndarray,
    r0: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """ガウシアン等の基底 (z,r) に上部延長を付与（レガシー経路）。"""
    ext = float(getattr(gene, "top_extension_mm", 0.0) or 0.0)
    if ext <= _Z_EPS:
        return z0, r0
    jz, jr = _extension_junction_source(gene)
    d_max = _compute_delta_max(jz, jr)
    if ext > d_max + 1e-6:
        ext = d_max
    return _build_extended(z0, r0, ext, d_max, junction_z=jz, junction_r=jr)


def legacy_mesh_profile(gene: Gene) -> Tuple[np.ndarray, np.ndarray]:
    """メッシュ用レガシー母線: smooth_profile（基底）+ 現行延長。"""
    z0, r0 = smooth_profile(base_gene(gene))
    return profile_with_extension(gene, z0, r0)


def effective_profile(gene: Gene) -> Tuple[np.ndarray, np.ndarray]:
    """レガシー (z,r) を密サンプルのまま B3 再フィットした 1 本のプロファイル。"""
    z_legacy, r_legacy = legacy_mesh_profile(gene)
    return b3_refit_profile(z_legacy, r_legacy, n_control=int(gene.N))


_profile_with_extension = profile_with_extension


def feasibility_profile(gene: Gene) -> Tuple[np.ndarray, np.ndarray]:
    """feasibility / z_cog_max 用の (z, r)。メッシュ用 ``effective_profile`` より軽い平滑化。"""
    z0, r0 = mild_smooth_profile(base_gene(gene))
    return _profile_with_extension(gene, z0, r0)


def max_top_extension_mm(gene: Gene, tol: float = 0.05) -> float:
    jz, jr = _extension_junction_source(gene)
    return _compute_delta_max(jz, jr, tol=tol)
