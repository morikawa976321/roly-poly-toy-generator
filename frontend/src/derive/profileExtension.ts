import type { Gene } from "../types";
import { smoothProfile } from "./smoothing";

const EXTENSION_SAMPLES = 96;
const JUNCTION_FIT_WINDOW = 24;
const JUNCTION_FIT_MIN = 8;
const R_EPS = 1e-9;
const Z_EPS = 1e-9;

export function baseGene(gene: Gene): Gene {
  return { ...gene, top_extension_mm: 0 };
}

function quinticCoeffs(
  r0: number,
  dr0: number,
  d2r0: number,
  r1: number,
  dr1: number,
  d2r1: number,
  L: number,
): [number, number, number, number, number, number] {
  const a0 = r0;
  const a1 = dr0 * L;
  const a2 = 0.5 * d2r0 * L * L;
  const v1 = dr1 * L;
  const acc1 = d2r1 * L * L;
  const b0 = r1 - (a0 + a1 + a2);
  const b1 = v1 - (a1 + 2 * a2);
  const b2 = acc1 - 2 * a2;
  const a5 = (b2 - 6 * b1 + 12 * b0) / 2;
  const a4 = b1 - 3 * b0 - 2 * a5;
  const a3 = b0 - a4 - a5;
  return [a0, a1, a2, a3, a4, a5];
}

function evalQuintic(
  z: number[],
  z0: number,
  z1: number,
  coeffs: [number, number, number, number, number, number],
): number[] {
  const [a0, a1, a2, a3, a4, a5] = coeffs;
  const L = z1 - z0;
  return z.map((zz) => {
    const t = L > 1e-12 ? Math.min(1, Math.max(0, (zz - z0) / L)) : 0;
    return a0 + a1 * t + a2 * t ** 2 + a3 * t ** 3 + a4 * t ** 4 + a5 * t ** 5;
  });
}

function junctionState(z: number[], r: number[]): {
  H: number;
  rJunc: number;
  dr: number;
  d2r: number;
} {
  const n = z.length;
  const H = z[n - 1];
  const k = Math.min(JUNCTION_FIT_WINDOW, n - 2);
  let rJunc: number;
  let dr: number;
  let d2r: number;
  if (k < JUNCTION_FIT_MIN) {
    rJunc = r[n - 1];
    const dz = n >= 2 ? z[n - 1] - z[n - 2] : 1;
    dr = dz > Z_EPS ? (r[n - 1] - r[n - 2]) / dz : 0;
    d2r = 0;
  } else {
    const zFit = z.slice(-k - 1, -1);
    const rFit = r.slice(-k - 1, -1);
    const p = polyfit2(zFit, rFit);
    rJunc = polyval(p, H);
    dr = polyval(polyder(p), H);
    d2r = 2 * p[0];
  }
  if (dr > -1e-9) dr = -1e-6;
  return { H, rJunc, dr, d2r };
}

function baseWithSmoothTop(z: number[], r: number[]): number[] {
  const { rJunc } = junctionState(z, r);
  const out = [...r];
  out[out.length - 1] = rJunc;
  return out;
}

function polyfit2(z: number[], r: number[]): [number, number, number] {
  // r = a z^2 + b z + c  — 正規方程式（3点以上）
  let s0 = 0;
  let s1 = 0;
  let s2 = 0;
  let s3 = 0;
  let s4 = 0;
  let t0 = 0;
  let t1 = 0;
  let t2 = 0;
  for (let i = 0; i < z.length; i++) {
    const zi = z[i];
    const ri = r[i];
    const z2 = zi * zi;
    const z3 = z2 * zi;
    const z4 = z3 * zi;
    s0 += 1;
    s1 += zi;
    s2 += z2;
    s3 += z3;
    s4 += z4;
    t0 += ri;
    t1 += ri * zi;
    t2 += ri * z2;
  }
  // Solve 3x3 — 簡易ガウス消去
  const A = [
    [s4, s3, s2],
    [s3, s2, s1],
    [s2, s1, s0],
  ];
  const b = [t2, t1, t0];
  return solve3(A, b) as [number, number, number];
}

function solve3(A: number[][], b: number[]): number[] {
  const m = A.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < 3; col++) {
    let pivot = col;
    for (let row = col + 1; row < 3; row++) {
      if (Math.abs(m[row][col]) > Math.abs(m[pivot][col])) pivot = row;
    }
    [m[col], m[pivot]] = [m[pivot], m[col]];
    const div = m[col][col] || 1e-12;
    for (let row = col; row < 4; row++) m[col][row] /= div;
    for (let row = 0; row < 3; row++) {
      if (row === col) continue;
      const f = m[row][col];
      for (let c = col; c < 4; c++) m[row][c] -= f * m[col][c];
    }
  }
  return [m[0][3], m[1][3], m[2][3]];
}

function polyder(p: [number, number, number]): [number, number] {
  return [2 * p[0], p[1]];
}

function polyval(p: number[] | [number, number, number], x: number): number {
  if (p.length === 2) return p[0] * x + p[1];
  return p[0] * x * x + p[1] * x + p[2];
}

function quinticExtensionValid(
  H: number,
  rJunc: number,
  dr: number,
  d2r: number,
  L: number,
): boolean {
  if (L <= Z_EPS || rJunc <= R_EPS) return false;
  const coeffs = quinticCoeffs(rJunc, dr, d2r, 0, 0, 0, L);
  const n = 64;
  let prev = rJunc;
  for (let i = 0; i <= n; i++) {
    const zi = H + (L * i) / n;
    const ri = evalQuintic([zi], H, H + L, coeffs)[0];
    if (ri < -0.05) return false;
    if (i > 0 && ri > prev + 1e-5) return false;
    prev = ri;
  }
  return true;
}

function extensionSegment(
  H: number,
  rJunc: number,
  dr: number,
  d2r: number,
  delta: number,
  Lspan: number,
): { z: number[]; r: number[] } {
  if (delta <= Z_EPS || rJunc <= R_EPS || Lspan <= Z_EPS) {
    return { z: [], r: [] };
  }
  const coeffs = quinticCoeffs(rJunc, dr, d2r, 0, 0, 0, Lspan);
  const z: number[] = [];
  const r: number[] = [];
  for (let i = 1; i <= EXTENSION_SAMPLES; i++) {
    const zi = H + (delta * i) / EXTENSION_SAMPLES;
    z.push(zi);
    r.push(Math.max(0, evalQuintic([zi], H, H + Lspan, coeffs)[0]));
  }
  if (r.length > 0) {
    r[0] = rJunc;
    for (let i = 1; i < r.length; i++) {
      if (r[i] > r[i - 1]) r[i] = r[i - 1];
    }
  }
  return { z, r };
}

function profileValid(_z: number[], r: number[], peakIdx: number): boolean {
  if (r.some((v) => v < -R_EPS)) return false;
  const tail = r.slice(peakIdx);
  for (let i = 1; i < tail.length; i++) {
    if (tail[i] > tail[i - 1] + 1e-4) return false;
  }
  return true;
}

function computeDeltaMax(z0: number[], r0: number[], tol = 0.05): number {
  const { H, rJunc, dr, d2r } = junctionState(z0, r0);
  if (rJunc <= R_EPS) return 0;

  let lo = 0;
  let hi = Math.max(2, rJunc * 4, z0[z0.length - 1] * 0.5);
  while (hi < 500 && quinticExtensionValid(H, rJunc, dr, d2r, hi)) {
    hi *= 2;
  }

  let best = 0;
  for (let i = 0; i < 48; i++) {
    const mid = 0.5 * (lo + hi);
    if (quinticExtensionValid(H, rJunc, dr, d2r, mid)) {
      const { r } = extensionSegment(H, rJunc, dr, d2r, mid, mid);
      if (r.length && r[r.length - 1] <= tol + 1e-3) {
        best = mid;
        lo = mid;
      } else {
        hi = mid;
      }
    } else {
      hi = mid;
    }
  }
  return best;
}

function buildExtended(
  z0: number[],
  r0: number[],
  delta: number,
  deltaMax: number,
): { z: number[]; r: number[] } {
  const { H, rJunc, dr, d2r } = junctionState(z0, r0);
  const rBase = baseWithSmoothTop(z0, r0);
  const Lspan = Math.max(delta, deltaMax);
  const { z: zSeg, r: rSeg } = extensionSegment(H, rJunc, dr, d2r, delta, Lspan);
  if (zSeg.length === 0) return { z: z0, r: r0 };
  const z = [...z0, ...zSeg];
  const r = [...rBase, ...rSeg];
  const peakIdx = r.indexOf(Math.max(...r));
  if (!profileValid(z, r, peakIdx)) {
    throw new Error("extended profile invalid");
  }
  return { z, r };
}

export function effectiveProfile(gene: Gene): { z: number[]; r: number[] } {
  const ext = Number(gene.top_extension_mm ?? 0);
  let { z, r } = smoothProfile(baseGene(gene));
  if (Number.isFinite(ext) && ext > Z_EPS) {
    const dMax = computeDeltaMax(z, r);
    const clamped = Math.min(ext, dMax);
    ({ z, r } = buildExtended(z, r, clamped, dMax));
  }
  return { z, r };
}

export function maxTopExtensionMm(gene: Gene, tol = 0.05): number {
  const { z, r } = smoothProfile(baseGene(gene));
  return computeDeltaMax(z, r, tol);
}
