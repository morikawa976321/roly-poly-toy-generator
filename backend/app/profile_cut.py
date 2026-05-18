"""
子午面プロファイルへの傾斜カット。

役割: (z, r) 半断面への平面カット幾何（右/左シルエット）。
働き: フロント ``meshPlaneCut.ts`` と同等。``feasibility_metrics`` がカット後プロファイルを組み立てる際に利用。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Literal, Tuple

import numpy as np

_EPS = 1e-6


def _tan_angle(angle_deg: float) -> float:
    if abs(angle_deg) < 1e-12:
        return 0.0
    return math.tan(math.radians(angle_deg))


def _signed_profile_cut_dist(
    z: float,
    r: float,
    z_cut: float,
    tan_a: float,
    side: Literal["right", "left"],
) -> float:
    x = r if side == "right" else -r
    return z - z_cut - x * tan_a


def _profile_on_cut_plane(
    r: float,
    z_cut: float,
    tan_a: float,
    side: Literal["right", "left"],
) -> float:
    x = r if side == "right" else -r
    return z_cut + x * tan_a


def cut_would_change_profile(
    z: np.ndarray,
    r: np.ndarray,
    z_cut: float,
    tan_a: float,
) -> bool:
    if len(z) == 0:
        return False
    z_min = float(np.min(z))
    z_max = float(np.max(z))
    any_above = False
    for zi, ri in zip(z, r):
        if _signed_profile_cut_dist(float(zi), float(ri), z_cut, tan_a, "right") > _EPS:
            any_above = True
        if _signed_profile_cut_dist(float(zi), float(ri), z_cut, tan_a, "left") > _EPS:
            any_above = True
    if not any_above:
        return False
    if abs(tan_a) < 1e-12:
        if z_cut >= z_max - _EPS:
            return False
        if z_cut <= z_min + _EPS:
            return False
    return True


def clip_open_profile_half(
    z: np.ndarray,
    r: np.ndarray,
    z_cut: float,
    tan_a: float,
    side: Literal["right", "left"],
) -> Tuple[np.ndarray, np.ndarray]:
    if len(z) == 0:
        return np.array([]), np.array([])
    out_z: List[float] = []
    out_r: List[float] = []

    def dist(zi: float, ri: float) -> float:
        return _signed_profile_cut_dist(zi, ri, z_cut, tan_a, side)

    def add(ri: float, zi: float) -> None:
        out_r.append(ri)
        out_z.append(zi)

    def add_on_cut(ri: float) -> None:
        out_r.append(ri)
        out_z.append(_profile_on_cut_plane(ri, z_cut, tan_a, side))

    prev_z = float(z[0])
    prev_r = float(r[0])
    prev_in = dist(prev_z, prev_r) <= _EPS
    if prev_in:
        add(prev_r, prev_z)

    for i in range(1, len(z)):
        cur_z = float(z[i])
        cur_r = float(r[i])
        cur_in = dist(cur_z, cur_r) <= _EPS
        if cur_in:
            if not prev_in:
                sp = dist(prev_z, prev_r)
                sc = dist(cur_z, cur_r)
                t = sp / (sp - sc)
                ri = prev_r + t * (cur_r - prev_r)
                add_on_cut(ri)
            add(cur_r, cur_z)
        elif prev_in:
            sp = dist(prev_z, prev_r)
            sc = dist(cur_z, cur_r)
            t = sp / (sp - sc)
            ri = prev_r + t * (cur_r - prev_r)
            add_on_cut(ri)
        prev_z, prev_r, prev_in = cur_z, cur_r, cur_in

    return np.asarray(out_z, dtype=float), np.asarray(out_r, dtype=float)


@dataclass(frozen=True)
class CutProfileSilhouette:
    z_right: np.ndarray
    r_right: np.ndarray
    z_left: np.ndarray
    r_left: np.ndarray


def cut_profile_silhouette(
    z: np.ndarray,
    r: np.ndarray,
    z_cut: float,
    angle_deg: float,
) -> CutProfileSilhouette:
    tan_a = _tan_angle(angle_deg)
    if not cut_would_change_profile(z, r, z_cut, tan_a):
        return CutProfileSilhouette(z, r, z, r)
    z_r, r_r = clip_open_profile_half(z, r, z_cut, tan_a, "right")
    z_l, r_l = clip_open_profile_half(z, r, z_cut, tan_a, "left")
    return CutProfileSilhouette(z_r, r_r, z_l, r_l)
