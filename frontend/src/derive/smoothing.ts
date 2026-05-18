/**
 * プロファイル平滑化（SciPy 非依存・backend 同等）。
 *
 * 役割: gene の (z,r) ノード列のガウシアン平滑と B3 定数定義。
 * 働き: profileExtension・b3Pyodide・feasibility が smoothProfile / geneZNodes を使用。backend/app/smoothing.py と意図的に同等挙動。
 */
import type { Gene } from "../types";

export const DENSE_FACTOR = 24;
/** 手法 5 (B3): 64 制御点 smoothing spline — compare_profile_smoothing と同じ */
const B3_SPLINE_S = 0.8;
/** 密サンプル再フィット用（backend ``b3_refit_s`` と同じスケール） */
const B3_REFIT_S_PER_NODE = B3_SPLINE_S;

export function b3RefitS(nSamples: number, nControl: number): number {
  const n = Math.max(Math.trunc(nSamples), 1);
  const nc = Math.max(Math.trunc(nControl), 1);
  return (B3_REFIT_S_PER_NODE * n) / nc;
}
const FEASIBILITY_PROFILE_N = 281;
const FEASIBILITY_SMOOTH_SIGMA = 8;

function effectiveZWarp(zWarp: unknown): number {
  if (zWarp === null || zWarp === undefined) return 1.0;
  const w = Number(zWarp);
  if (!Number.isFinite(w) || w <= 0) return 1.0;
  return w;
}

export function geneZNodes(gene: Gene): number[] {
  const n = Math.trunc(gene.N);
  const height = Number(gene.height);
  const w = effectiveZWarp(gene.z_warp);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const u = n <= 1 ? 0 : i / (n - 1);
    out.push(height * u ** w);
  }
  return out;
}

function denseZ(
  height: number,
  nNodes: number,
  factor: number,
  zWarp = 1.0,
): number[] {
  const n = (nNodes - 1) * factor + 1;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const u = n <= 1 ? 0 : i / (n - 1);
    out.push(height * u ** zWarp);
  }
  return out;
}

function gaussianKernel(sigma: number): { radius: number; k: number[] } {
  const radius = Math.trunc(Math.max(3, Math.round(4.0 * sigma)));
  const k: number[] = [];
  let s = 0;
  for (let i = -radius; i <= radius; i++) {
    const v = Math.exp(-0.5 * (i / sigma) ** 2);
    k.push(v);
    s += v;
  }
  for (let i = 0; i < k.length; i++) k[i] /= s;
  return { radius, k };
}

function gaussianFilter1dNearest(x: number[], sigma: number): number[] {
  if (!Number.isFinite(sigma) || sigma <= 0) return x.slice();
  const { radius, k } = gaussianKernel(sigma);
  const n = x.length;
  const out: number[] = new Array(n);
  for (let i = 0; i < n; i++) {
    let acc = 0;
    for (let j = -radius; j <= radius; j++) {
      const idx = Math.min(n - 1, Math.max(0, i + j));
      acc += x[idx] * k[j + radius];
    }
    out[i] = acc;
  }
  return out;
}

function interp1(zq: number[], z: number[], r: number[]): number[] {
  // z は単調増加である前提（gene の定義より）
  const n = z.length;
  const out: number[] = [];
  let j = 0;
  for (const zz of zq) {
    while (j + 1 < n && z[j + 1] < zz) j++;
    if (zz <= z[0]) {
      out.push(r[0]);
      continue;
    }
    if (zz >= z[n - 1]) {
      out.push(r[n - 1]);
      continue;
    }
    const z0 = z[j];
    const z1 = z[j + 1];
    const t = z1 === z0 ? 0 : (zz - z0) / (z1 - z0);
    out.push(r[j] * (1 - t) + r[j + 1] * t);
  }
  return out;
}

export function smoothProfile(
  gene: Gene,
): { z: number[]; r: number[] } {
  const n = Math.trunc(gene.N);
  const height = Number(gene.height);
  const w = effectiveZWarp(gene.z_warp);

  const zNodes = geneZNodes(gene);
  const rNodes = gene.radii.map((v) => Number(v));

  const zDense = denseZ(height, n, DENSE_FACTOR, w);
  const rLin = interp1(zDense, zNodes, rNodes);

  // backend と同じく sigma は DENSE_FACTOR（= だいたい 1 ノード分）
  const rDense = gaussianFilter1dNearest(rLin, DENSE_FACTOR);

  // 端点固定 + 非負クリップ
  if (rDense.length > 0) {
    rDense[0] = rNodes[0];
    rDense[rDense.length - 1] = rNodes[rNodes.length - 1];
  }
  for (let i = 0; i < rDense.length; i++) {
    if (rDense[i] < 0) rDense[i] = 0;
  }
  return { z: zDense, r: rDense };
}

export function mildSmoothProfile(gene: Gene): { z: number[]; r: number[] } {
  const zNodes = geneZNodes(gene);
  const rNodes = gene.radii.map((v) => Number(v));
  const height = Number(gene.height);
  const n = FEASIBILITY_PROFILE_N;
  const zDense: number[] = [];
  for (let i = 0; i < n; i++) {
    zDense.push(height * (n <= 1 ? 0 : i / (n - 1)));
  }
  const rLin = interp1(zDense, zNodes, rNodes);
  const rDense =
    FEASIBILITY_SMOOTH_SIGMA > 0
      ? gaussianFilter1dNearest(rLin, FEASIBILITY_SMOOTH_SIGMA)
      : rLin.slice();
  if (rDense.length > 0) {
    rDense[0] = rNodes[0];
    rDense[rDense.length - 1] = rNodes[rNodes.length - 1];
  }
  for (let i = 0; i < rDense.length; i++) {
    if (rDense[i] < 0) rDense[i] = 0;
  }
  return { z: zDense, r: rDense };
}

