"""
回転体メッシュの 3D 平面カット。

役割: 上部傾斜カット・平面クリップの三角メッシュ幾何。
働き: フロント ``meshPlaneCut.ts`` と同等。``feasibility_metrics`` / ``metrics`` がカット後形状を得る際に呼ぶ。
"""

from __future__ import annotations



import math

from typing import Dict, List, Set, Tuple



import numpy as np



_EPS = 1e-6

_PLANE_EPS = 1e-3





def _tan_angle(angle_deg: float) -> float:

    if abs(angle_deg) < 1e-12:

        return 0.0

    rad = math.radians(angle_deg)

    return math.tan(rad)





def _signed(v: np.ndarray, z_cut: float, tan_a: float) -> float:

    return float(v[2] - z_cut - v[0] * tan_a)





def cut_would_change(

    verts: np.ndarray,

    z_cut: float,

    tan_a: float,

) -> bool:

    z_min = float(np.min(verts[:, 2]))

    z_max = float(np.max(verts[:, 2]))

    any_above = any(_signed(v, z_cut, tan_a) > _EPS for v in verts)

    if not any_above:

        return False

    if abs(tan_a) < 1e-12:

        if z_cut >= z_max - _EPS:

            return False

        if z_cut <= z_min + _EPS:

            return False

    return True





def _lerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:

    return a + t * (b - a)





def _snap_to_plane(p: np.ndarray, z_cut: float, tan_a: float) -> np.ndarray:

    d = _signed(p, z_cut, tan_a)

    if abs(d) <= 1e-12:

        return p

    denom = 1.0 + tan_a * tan_a

    return np.array(

        [p[0] + (d * tan_a) / denom, p[1], p[2] - d / denom],

        dtype=float,

    )





def _clip_poly(poly: list[np.ndarray], z_cut: float, tan_a: float) -> list[np.ndarray]:

    if not poly:

        return []

    out: list[np.ndarray] = []

    n = len(poly)

    for i in range(n):

        cur = poly[i]

        prev = poly[(i - 1) % n]

        cur_in = _signed(cur, z_cut, tan_a) <= _EPS

        prev_in = _signed(prev, z_cut, tan_a) <= _EPS

        if cur_in:

            if not prev_in:

                sp = _signed(prev, z_cut, tan_a)

                sc = _signed(cur, z_cut, tan_a)

                out.append(_snap_to_plane(_lerp(prev, cur, sp / (sp - sc)), z_cut, tan_a))

            out.append(cur)

        elif prev_in:

            sp = _signed(prev, z_cut, tan_a)

            sc = _signed(cur, z_cut, tan_a)

            out.append(_snap_to_plane(_lerp(prev, cur, sp / (sp - sc)), z_cut, tan_a))

    return out





def _cap_key(v: np.ndarray) -> str:

    return f"{round(v[0]*1e4)}:{round(v[1]*1e4)}:{round(v[2]*1e4)}"





def _on_plane(v: np.ndarray, z_cut: float, tan_a: float) -> bool:

    return abs(_signed(v, z_cut, tan_a)) <= _PLANE_EPS





def _cut_plane_frame(z_cut: float, tan_a: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:

    n = np.array([-tan_a, 0.0, 1.0], dtype=float)

    n /= max(np.linalg.norm(n), 1e-12)

    aux = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])

    u = np.cross(n, aux)

    u /= max(np.linalg.norm(u), 1e-12)

    v = np.cross(n, u)

    origin = np.array([0.0, 0.0, z_cut], dtype=float)

    return origin, u, v, n





def _project2d(p: np.ndarray, origin: np.ndarray, u: np.ndarray, v: np.ndarray) -> Tuple[float, float]:

    d = p - origin

    return float(np.dot(d, u)), float(np.dot(d, v))





def _edge_id(ka: str, kb: str) -> str:

    return f"{ka}|{kb}" if ka < kb else f"{kb}|{ka}"





def _collect_boundary_loops_on_plane(

    body_tris: list[list[np.ndarray]],

    z_cut: float,

    tan_a: float,

) -> list[list[np.ndarray]]:

    verts: Dict[str, np.ndarray] = {}

    edge_count: Dict[str, int] = {}



    def register_edge(a: np.ndarray, b: np.ndarray) -> None:

        ka = _cap_key(a)

        kb = _cap_key(b)

        if ka == kb:

            return

        verts[ka] = a

        verts[kb] = b

        ek = _edge_id(ka, kb)

        edge_count[ek] = edge_count.get(ek, 0) + 1



    for tri in body_tris:

        register_edge(tri[0], tri[1])

        register_edge(tri[1], tri[2])

        register_edge(tri[2], tri[0])



    plane_edges: list[tuple[str, str]] = []

    for ek, count in edge_count.items():

        if count != 1:

            continue

        ka, kb = ek.split("|")

        a = verts[ka]

        b = verts[kb]

        if not _on_plane(a, z_cut, tan_a) or not _on_plane(b, z_cut, tan_a):

            continue

        plane_edges.append((ka, kb))



    adj: Dict[str, Set[str]] = {}



    def link(ka: str, kb: str) -> None:

        adj.setdefault(ka, set()).add(kb)

        adj.setdefault(kb, set()).add(ka)



    for ka, kb in plane_edges:

        link(ka, kb)



    used: Set[str] = set()

    loops: list[list[np.ndarray]] = []



    for ka, kb in plane_edges:

        start_ek = _edge_id(ka, kb)

        if start_ek in used:

            continue

        used.add(start_ek)

        loop_keys = [ka, kb]

        prev, cur = ka, kb



        while True:

            neighbors = [n for n in adj.get(cur, set()) if n != prev]

            nxt = None

            for cand in neighbors:

                nek = _edge_id(cur, cand)

                if nek not in used:

                    nxt = cand

                    used.add(nek)

                    break

            if nxt is None:

                break

            if nxt == loop_keys[0]:

                break

            loop_keys.append(nxt)

            prev, cur = cur, nxt



        if len(loop_keys) >= 3:

            loops.append([_snap_to_plane(verts[k], z_cut, tan_a) for k in loop_keys])



    return loops





def _triangulate_cap_loops(

    loops: list[list[np.ndarray]],

    origin: np.ndarray,

    u: np.ndarray,

    v: np.ndarray,

) -> list[list[np.ndarray]]:

    """Ear-clip 相当: 凸/凹単純多角形を扇+分割で三角化（小さなループ向け）。"""

    tris: list[list[np.ndarray]] = []



    def signed_area(coords: list[tuple[float, float]]) -> float:

        area = 0.0

        n = len(coords)

        for i in range(n):

            x0, y0 = coords[i]

            x1, y1 = coords[(i + 1) % n]

            area += x0 * y1 - x1 * y0

        return area * 0.5



    def point_in_tri(

        p: tuple[float, float],

        a: tuple[float, float],

        b: tuple[float, float],

        c: tuple[float, float],

    ) -> bool:

        def cross2d(u: tuple[float, float], v: tuple[float, float], w: tuple[float, float]) -> float:

            return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])



        c1 = cross2d(a, b, p)

        c2 = cross2d(b, c, p)

        c3 = cross2d(c, a, p)

        eps = 1e-12

        has_neg = c1 < -eps or c2 < -eps or c3 < -eps

        has_pos = c1 > eps or c2 > eps or c3 > eps

        return not (has_neg and has_pos)



    for loop in loops:

        if len(loop) < 3:

            continue

        coords = [_project2d(p, origin, u, v) for p in loop]

        if signed_area(coords) < 0:

            loop = list(reversed(loop))

            coords = list(reversed(coords))



        idx = list(range(len(loop)))

        guard = 0

        while len(idx) > 3 and guard < 10000:

            guard += 1

            ear_found = False

            n = len(idx)

            for i in range(n):

                i0 = idx[(i - 1) % n]

                i1 = idx[i]

                i2 = idx[(i + 1) % n]

                a, b, c = coords[i0], coords[i1], coords[i2]

                cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

                if cross <= 1e-12:

                    continue

                if any(

                    point_in_tri(coords[j], a, b, c)

                    for j in idx

                    if j not in (i0, i1, i2)

                ):

                    continue

                tris.append([loop[i0], loop[i1], loop[i2]])

                del idx[i]

                ear_found = True

                break

            if not ear_found:

                break



        if len(idx) == 3:

            tris.append([loop[idx[0]], loop[idx[1]], loop[idx[2]]])



    return tris





def clip_mesh_below_plane(

    verts: np.ndarray,

    tris: np.ndarray,

    z_cut: float,

    angle_deg: float,

) -> Tuple[np.ndarray, np.ndarray]:

    tan_a = _tan_angle(angle_deg)

    if not cut_would_change(verts, z_cut, tan_a):

        return verts, tris



    body_tris: list[list[np.ndarray]] = []



    for tri in tris:

        poly = [verts[int(tri[0])], verts[int(tri[1])], verts[int(tri[2])]]

        clipped = _clip_poly(poly, z_cut, tan_a)

        if len(clipped) < 3:

            continue

        for k in range(1, len(clipped) - 1):

            body_tris.append([clipped[0], clipped[k], clipped[k + 1]])



    origin, u, v, _ = _cut_plane_frame(z_cut, tan_a)

    cap_loops = _collect_boundary_loops_on_plane(body_tris, z_cut, tan_a)

    cap_tris = _triangulate_cap_loops(cap_loops, origin, u, v)



    if not body_tris:

        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int)

    body_map: Dict[str, int] = {}

    cap_map: Dict[str, int] = {}

    positions: list[float] = []

    indices: list[int] = []



    def add_vertex(v: np.ndarray) -> int:

        idx = len(positions) // 3

        positions.extend([float(v[0]), float(v[1]), float(v[2])])

        return idx



    def body_index(v: np.ndarray) -> int:

        k = _cap_key(v)

        if k in body_map:

            return body_map[k]

        idx = add_vertex(v)

        body_map[k] = idx

        return idx



    def cap_index(v: np.ndarray) -> int:

        snapped = _snap_to_plane(v, z_cut, tan_a)

        k = _cap_key(snapped)

        if k in cap_map:

            return cap_map[k]

        idx = add_vertex(snapped)

        cap_map[k] = idx

        return idx



    for tri in body_tris:

        indices.extend(body_index(t) for t in tri)

    for tri in cap_tris:

        indices.extend(cap_index(t) for t in tri)



    flat = np.asarray(positions, dtype=float).reshape(-1, 3)

    tri_idx = np.asarray(indices, dtype=int).reshape(-1, 3)

    return flat, tri_idx





def mesh_volume(verts: np.ndarray, tris: np.ndarray | None = None) -> Tuple[float, float]:

    """符号付き四面体和から体積と重心 z。"""

    if len(verts) < 3:

        return 0.0, 0.0

    vol = 0.0

    cz = 0.0

    tri_list = tris if tris is not None and len(tris) > 0 else np.arange(len(verts)).reshape(-1, 3)

    for tri in tri_list:

        a = verts[int(tri[0])]

        b = verts[int(tri[1])]

        c = verts[int(tri[2])]

        cross = np.cross(b, c)

        tet = float(np.dot(a, cross)) / 6.0

        vol += tet

        z_tri = float((a[2] + b[2] + c[2]) / 3.0)

        cz += tet * z_tri

    volume = abs(vol)

    centroid_z = cz / vol if abs(vol) > 1e-12 else 0.0

    return volume, centroid_z


