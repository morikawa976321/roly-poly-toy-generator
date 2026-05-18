/**
 * 傾斜上面カット（平面クリップ）の幾何処理。
 *
 * 役割: z <= z_cut + x·tan(θ) 側を残すメッシュ・プロファイル操作。
 * 働き: mesh・feasibilityMetrics・thumbnailSvg・stepExporter が clip / silhouette / geneTopCutParams を利用。
 */
import type { Gene } from "../types";
import * as THREE from "three";
import { ShapeUtils } from "three";

const EPS = 1e-6;
const PLANE_EPS = 1e-3;

export type Vec3 = { x: number; y: number; z: number };

export function topCutTanAngle(angleDeg: number): number {
  if (Math.abs(angleDeg) < 1e-12) return 0;
  const rad = (angleDeg * Math.PI) / 180;
  if (Math.abs(Math.abs(rad) - Math.PI / 2) < 1e-6) {
    throw new Error("top_cut_angle_deg must be within (-89, 89)");
  }
  return Math.tan(rad);
}

/** 残す側: z <= z_cut + x·tan(θ) */
export function signedCutDist(v: Vec3, zCut: number, tanA: number): number {
  return v.z - zCut - v.x * tanA;
}

export function geneTopCutParams(gene: Gene): { zCut: number; tanA: number } {
  return {
    zCut: Number(gene.top_cut_height_mm ?? 0),
    tanA: topCutTanAngle(Number(gene.top_cut_angle_deg ?? 0)),
  };
}

/** 断面図 (+r / −r) 用: x = ±r で z <= z_cut + x·tan(θ) */
export function signedProfileCutDist(
  z: number,
  r: number,
  zCut: number,
  tanA: number,
  side: "right" | "left",
): number {
  const x = side === "right" ? r : -r;
  return z - zCut - x * tanA;
}

export function cutWouldChangeProfile(
  z: number[],
  r: number[],
  zCut: number,
  tanA: number,
): boolean {
  if (z.length === 0) return false;
  let zMin = Infinity;
  let zMax = -Infinity;
  let anyAbove = false;
  for (let i = 0; i < z.length; i++) {
    zMin = Math.min(zMin, z[i]);
    zMax = Math.max(zMax, z[i]);
    if (signedProfileCutDist(z[i], r[i], zCut, tanA, "right") > EPS) {
      anyAbove = true;
    }
    if (signedProfileCutDist(z[i], r[i], zCut, tanA, "left") > EPS) {
      anyAbove = true;
    }
  }
  if (!anyAbove) return false;
  if (Math.abs(tanA) < 1e-12) {
    if (zCut >= zMax - EPS) return false;
    if (zCut <= zMin + EPS) return false;
  }
  return true;
}

function profileOnCutPlane(
  r: number,
  zCut: number,
  tanA: number,
  side: "right" | "left",
): number {
  const x = side === "right" ? r : -r;
  return zCut + x * tanA;
}

/** 母線 (z,r) を開曲線として半断面ごとにカット */
export function clipOpenProfileHalf(
  z: number[],
  r: number[],
  zCut: number,
  tanA: number,
  side: "right" | "left",
): { z: number[]; r: number[] } {
  if (z.length === 0) return { z: [], r: [] };
  const outZ: number[] = [];
  const outR: number[] = [];
  const dist = (zi: number, ri: number) =>
    signedProfileCutDist(zi, ri, zCut, tanA, side);

  const add = (ri: number, zi: number) => {
    outR.push(ri);
    outZ.push(zi);
  };

  const addOnCut = (ri: number) => {
    outR.push(ri);
    outZ.push(profileOnCutPlane(ri, zCut, tanA, side));
  };

  let prevZ = z[0];
  let prevR = r[0];
  let prevIn = dist(prevZ, prevR) <= EPS;
  if (prevIn) add(prevR, prevZ);

  for (let i = 1; i < z.length; i++) {
    const curZ = z[i];
    const curR = r[i];
    const curIn = dist(curZ, curR) <= EPS;
    if (curIn) {
      if (!prevIn) {
        const sp = dist(prevZ, prevR);
        const sc = dist(curZ, curR);
        const t = sp / (sp - sc);
        const ri = prevR + t * (curR - prevR);
        addOnCut(ri);
      }
      add(curR, curZ);
    } else if (prevIn) {
      const sp = dist(prevZ, prevR);
      const sc = dist(curZ, curR);
      const t = sp / (sp - sc);
      const ri = prevR + t * (curR - prevR);
      addOnCut(ri);
    }
    prevZ = curZ;
    prevR = curR;
    prevIn = curIn;
  }

  return { z: outZ, r: outR };
}

export function cutProfileSilhouette(
  z: number[],
  r: number[],
  zCut: number,
  angleDeg: number,
): { zRight: number[]; rRight: number[]; zLeft: number[]; rLeft: number[] } {
  const tanA = topCutTanAngle(angleDeg);
  if (!cutWouldChangeProfile(z, r, zCut, tanA)) {
    return { zRight: z, rRight: r, zLeft: z, rLeft: r };
  }
  const right = clipOpenProfileHalf(z, r, zCut, tanA, "right");
  const left = clipOpenProfileHalf(z, r, zCut, tanA, "left");
  return {
    zRight: right.z,
    rRight: right.r,
    zLeft: left.z,
    rLeft: left.r,
  };
}

export function cutWouldChangeMesh(
  geom: THREE.BufferGeometry,
  zCut: number,
  tanA: number,
): boolean {
  const pos = geom.getAttribute("position");
  if (!pos) return false;
  let zMin = Infinity;
  let zMax = -Infinity;
  let anyAbove = false;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const z = pos.getZ(i);
    zMin = Math.min(zMin, z);
    zMax = Math.max(zMax, z);
    if (signedCutDist({ x, y: pos.getY(i), z }, zCut, tanA) > EPS) {
      anyAbove = true;
    }
  }
  if (!anyAbove) return false;
  if (Math.abs(tanA) < 1e-12) {
    if (zCut >= zMax - EPS) return false;
    if (zCut <= zMin + EPS) return false;
  }
  return true;
}

function lerpV(a: Vec3, b: Vec3, t: number): Vec3 {
  return {
    x: a.x + t * (b.x - a.x),
    y: a.y + t * (b.y - a.y),
    z: a.z + t * (b.z - a.z),
  };
}

function clipPolyBelowPlane(poly: Vec3[], zCut: number, tanA: number): Vec3[] {
  if (poly.length === 0) return [];
  const out: Vec3[] = [];
  for (let i = 0; i < poly.length; i++) {
    const cur = poly[i];
    const prev = poly[(i + poly.length - 1) % poly.length];
    const curIn = signedCutDist(cur, zCut, tanA) <= EPS;
    const prevIn = signedCutDist(prev, zCut, tanA) <= EPS;
    if (curIn) {
      if (!prevIn) {
        const sp = signedCutDist(prev, zCut, tanA);
        const sc = signedCutDist(cur, zCut, tanA);
        const t = sp / (sp - sc);
        out.push(snapToCutPlane(lerpV(prev, cur, t), zCut, tanA));
      }
      out.push(cur);
    } else if (prevIn) {
      const sp = signedCutDist(prev, zCut, tanA);
      const sc = signedCutDist(cur, zCut, tanA);
      const t = sp / (sp - sc);
      out.push(snapToCutPlane(lerpV(prev, cur, t), zCut, tanA));
    }
  }
  return out;
}

function triangulateFan(poly: Vec3[]): Array<[Vec3, Vec3, Vec3]> {
  if (poly.length < 3) return [];
  const tris: Array<[Vec3, Vec3, Vec3]> = [];
  for (let i = 1; i < poly.length - 1; i++) {
    tris.push([poly[0], poly[i], poly[i + 1]]);
  }
  return tris;
}

export function quantKey(v: Vec3): string {
  return `${Math.round(v.x * 1e4)}:${Math.round(v.y * 1e4)}:${Math.round(v.z * 1e4)}`;
}

/** 切断平面 n=(-tanA,0,1) 上へ射影 */
export function snapToCutPlane(p: Vec3, zCut: number, tanA: number): Vec3 {
  const d = signedCutDist(p, zCut, tanA);
  if (Math.abs(d) <= 1e-12) return p;
  const denom = 1 + tanA * tanA;
  return {
    x: p.x + (d * tanA) / denom,
    y: p.y,
    z: p.z - d / denom,
  };
}

function onCutPlane(v: Vec3, zCut: number, tanA: number): boolean {
  return Math.abs(signedCutDist(v, zCut, tanA)) <= PLANE_EPS;
}

type CutPlaneFrame = {
  origin: Vec3;
  u: Vec3;
  v: Vec3;
  n: Vec3;
};

function cutPlaneFrame(zCut: number, tanA: number): CutPlaneFrame {
  const nx = -tanA;
  const ny = 0;
  const nz = 1;
  const nLen = Math.hypot(nx, ny, nz) || 1;
  const n = { x: nx / nLen, y: ny / nLen, z: nz / nLen };
  const aux =
    Math.abs(n.z) < 0.9 ? { x: 0, y: 0, z: 1 } : { x: 1, y: 0, z: 0 };
  const ux = n.y * aux.z - n.z * aux.y;
  const uy = n.z * aux.x - n.x * aux.z;
  const uz = n.x * aux.y - n.y * aux.x;
  const uLen = Math.hypot(ux, uy, uz) || 1;
  const u = { x: ux / uLen, y: uy / uLen, z: uz / uLen };
  // v = n × u so that u × v = +n (outward from the kept solid)
  const vx = n.y * u.z - n.z * u.y;
  const vy = n.z * u.x - n.x * u.z;
  const vz = n.x * u.y - n.y * u.x;
  const origin = { x: 0, y: 0, z: zCut };
  return { origin, u, v: { x: vx, y: vy, z: vz }, n };
}

function project2d(p: Vec3, frame: CutPlaneFrame): THREE.Vector2 {
  const dx = p.x - frame.origin.x;
  const dy = p.y - frame.origin.y;
  const dz = p.z - frame.origin.z;
  return new THREE.Vector2(
    dx * frame.u.x + dy * frame.u.y + dz * frame.u.z,
    dx * frame.v.x + dy * frame.v.y + dz * frame.v.z,
  );
}

function edgeId(ka: string, kb: string): string {
  return ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
}

function collectBoundaryLoopsOnPlane(
  bodyTris: Array<[Vec3, Vec3, Vec3]>,
  zCut: number,
  tanA: number,
): Vec3[][] {
  const verts = new Map<string, Vec3>();
  const edgeCount = new Map<string, number>();

  const registerEdge = (a: Vec3, b: Vec3) => {
    const ka = quantKey(a);
    const kb = quantKey(b);
    if (ka === kb) return;
    verts.set(ka, a);
    verts.set(kb, b);
    const ek = edgeId(ka, kb);
    edgeCount.set(ek, (edgeCount.get(ek) ?? 0) + 1);
  };

  for (const [a, b, c] of bodyTris) {
    registerEdge(a, b);
    registerEdge(b, c);
    registerEdge(c, a);
  }

  const planeEdges: Array<[string, string]> = [];
  for (const [ek, count] of edgeCount) {
    if (count !== 1) continue;
    const [ka, kb] = ek.split("|");
    const a = verts.get(ka)!;
    const b = verts.get(kb)!;
    if (!onCutPlane(a, zCut, tanA) || !onCutPlane(b, zCut, tanA)) continue;
    planeEdges.push([ka, kb]);
  }

  const adj = new Map<string, Set<string>>();
  const link = (ka: string, kb: string) => {
    if (!adj.has(ka)) adj.set(ka, new Set());
    if (!adj.has(kb)) adj.set(kb, new Set());
    adj.get(ka)!.add(kb);
    adj.get(kb)!.add(ka);
  };
  for (const [ka, kb] of planeEdges) link(ka, kb);

  const used = new Set<string>();
  const loops: Vec3[][] = [];

  for (const [ka, kb] of planeEdges) {
    const startEk = edgeId(ka, kb);
    if (used.has(startEk)) continue;
    used.add(startEk);

    const loopKeys = [ka, kb];
    let prev = ka;
    let cur = kb;

    while (true) {
      const neighbors = [...(adj.get(cur) ?? [])].filter((n) => n !== prev);
      let next: string | null = null;
      for (const cand of neighbors) {
        const nek = edgeId(cur, cand);
        if (!used.has(nek)) {
          next = cand;
          used.add(nek);
          break;
        }
      }
      if (!next) break;
      if (next === loopKeys[0]) break;
      loopKeys.push(next);
      prev = cur;
      cur = next;
    }

    if (loopKeys.length >= 3) {
      loops.push(loopKeys.map((k) => snapToCutPlane(verts.get(k)!, zCut, tanA)));
    }
  }

  return loops;
}

function orderLoopCCW(loop: Vec3[], frame: CutPlaneFrame): Vec3[] {
  if (loop.length < 3) return loop;
  const pts2d = loop.map((p) => project2d(p, frame));
  let area = 0;
  for (let i = 0; i < pts2d.length; i++) {
    const a = pts2d[i];
    const b = pts2d[(i + 1) % pts2d.length];
    area += a.x * b.y - b.x * a.y;
  }
  const ordered = area >= 0 ? loop : [...loop].reverse();
  return ordered;
}

function capTriOrientation(
  a: Vec3,
  b: Vec3,
  c: Vec3,
  n: Vec3,
): number {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const abz = b.z - a.z;
  const acx = c.x - a.x;
  const acy = c.y - a.y;
  const acz = c.z - a.z;
  const fnx = aby * acz - abz * acy;
  const fny = abz * acx - abx * acz;
  const fnz = abx * acy - aby * acx;
  return fnx * n.x + fny * n.y + fnz * n.z;
}

function triangulateCapLoops(
  loops: Vec3[][],
  frame: CutPlaneFrame,
): Array<[Vec3, Vec3, Vec3]> {
  const tris: Array<[Vec3, Vec3, Vec3]> = [];
  for (const loop of loops) {
    const ordered = orderLoopCCW(loop, frame);
    if (ordered.length < 3) continue;
    const contour = ordered.map((p) => project2d(p, frame));
    const faces = ShapeUtils.triangulateShape(contour, []);
    for (const [i0, i1, i2] of faces) {
      const a = ordered[i0];
      const b = ordered[i1];
      const c = ordered[i2];
      if (capTriOrientation(a, b, c, frame.n) < 0) {
        tris.push([a, c, b]);
      } else {
        tris.push([a, b, c]);
      }
    }
  }
  return tris;
}

/**
 * 回転体メッシュをカット平面より下だけ残し、切断面をキャップする。
 */
export function clipGeometryBelowCutPlane(
  geom: THREE.BufferGeometry,
  zCut: number,
  angleDeg: number,
): THREE.BufferGeometry {
  const tanA = topCutTanAngle(angleDeg);
  if (!cutWouldChangeMesh(geom, zCut, tanA)) {
    return geom;
  }

  const posAttr = geom.getAttribute("position");
  const index = geom.getIndex();
  if (!posAttr || !index) return geom;

  const getV = (idx: number): Vec3 => ({
    x: posAttr.getX(idx),
    y: posAttr.getY(idx),
    z: posAttr.getZ(idx),
  });

  const bodyTris: Array<[Vec3, Vec3, Vec3]> = [];

  for (let i = 0; i < index.count; i += 3) {
    const ia = index.getX(i);
    const ib = index.getX(i + 1);
    const ic = index.getX(i + 2);
    const tri = [getV(ia), getV(ib), getV(ic)];
    const clipped = clipPolyBelowPlane(tri, zCut, tanA);
    if (clipped.length < 3) continue;
    for (const t of triangulateFan(clipped)) {
      bodyTris.push(t);
    }
  }

  const frame = cutPlaneFrame(zCut, tanA);
  const capLoops = collectBoundaryLoopsOnPlane(bodyTris, zCut, tanA);
  const capTris = triangulateCapLoops(capLoops, frame);

  if (bodyTris.length === 0) {
    return new THREE.BufferGeometry();
  }

  const bodyMap = new Map<string, number>();
  const capMap = new Map<string, number>();
  const positions: number[] = [];
  const indices: number[] = [];

  const addVertex = (v: Vec3): number => {
    const idx = positions.length / 3;
    positions.push(v.x, v.y, v.z);
    return idx;
  };

  const bodyIndex = (v: Vec3): number => {
    const k = quantKey(v);
    const existing = bodyMap.get(k);
    if (existing !== undefined) return existing;
    const idx = addVertex(v);
    bodyMap.set(k, idx);
    return idx;
  };

  const capIndex = (v: Vec3): number => {
    const snapped = snapToCutPlane(v, zCut, tanA);
    const k = quantKey(snapped);
    const existing = capMap.get(k);
    if (existing !== undefined) return existing;
    const idx = addVertex(snapped);
    capMap.set(k, idx);
    return idx;
  };

  for (const [a, b, c] of bodyTris) {
    indices.push(bodyIndex(a), bodyIndex(b), bodyIndex(c));
  }
  for (const [a, b, c] of capTris) {
    indices.push(capIndex(a), capIndex(b), capIndex(c));
  }

  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  out.setIndex(indices);
  out.computeVertexNormals();
  return out;
}

export function clipGeneMesh(
  geom: THREE.BufferGeometry,
  gene: Gene,
): THREE.BufferGeometry {
  const { zCut, tanA } = geneTopCutParams(gene);
  return clipGeometryBelowCutPlane(geom, zCut, (Math.atan(tanA) * 180) / Math.PI);
}
