/**
 * ブラウザ上 SciPy B3 スプライン（Pyodide）。
 *
 * 役割: WASM Pyodide + numpy/scipy で UnivariateSpline を実行する非同期層。
 * 働き: ensureB3Profile から b3RefitProfileAsync を呼び、密 (z,r) を B3 平滑化・再フィットする。初回 loadPackage で scipy を読み込む。
 */
import type { Gene } from "../types";
import { B3_SPLINE_S, DENSE_FACTOR, b3RefitS, geneZNodes } from "./smoothing";

type PyodideApi = {
  loadPackage: (names: string | string[]) => Promise<unknown>;
  runPythonAsync: (code: string) => Promise<unknown>;
  globals: { get: (name: string) => { toJs: (opts?: object) => unknown } };
};

let pyodidePromise: Promise<PyodideApi> | null = null;

function effectiveZWarp(zWarp: unknown): number {
  if (zWarp === null || zWarp === undefined) return 1.0;
  const w = Number(zWarp);
  if (!Number.isFinite(w) || w <= 0) return 1.0;
  return w;
}

function denseZ(height: number, nNodes: number, factor: number, zWarp = 1.0): number[] {
  const n = (nNodes - 1) * factor + 1;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const u = n <= 1 ? 0 : i / (n - 1);
    out.push(height * u ** zWarp);
  }
  return out;
}

async function loadPyodide(): Promise<PyodideApi> {
  if (pyodidePromise) return pyodidePromise;
  pyodidePromise = (async () => {
    const { loadPyodide } = await import("pyodide");
    const pyodide = (await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/",
    })) as unknown as PyodideApi;
    await pyodide.loadPackage(["numpy", "scipy"]);
    await pyodide.runPythonAsync(`
import numpy as np
from scipy.interpolate import UnivariateSpline

def b3_profile(z_nodes, r_nodes, z_dense, s):
    spl = UnivariateSpline(z_nodes, r_nodes, s=float(s), k=3)
    r = np.asarray(spl(z_dense), dtype=float)
    r[0] = float(r_nodes[0])
    r[-1] = float(r_nodes[-1])
    np.maximum(r, 0.0, out=r)
    peak = int(np.argmax(r))
    for i in range(peak + 1, len(r)):
        if r[i] > r[i - 1]:
            r[i] = r[i - 1]
    return r.tolist()
`);
    return pyodide;
  })();
  return pyodidePromise;
}

export function initB3Pyodide(): Promise<void> {
  return loadPyodide().then(() => undefined);
}

export function isB3PyodideReady(): boolean {
  return pyodidePromise !== null;
}

/** 64 制御点 → 密格子 B3（compare の profile_b3 相当） */
export async function b3SmoothProfileAsync(
  gene: Gene,
): Promise<{ z: number[]; r: number[] }> {
  const pyodide = await loadPyodide();
  const n = Math.trunc(gene.N);
  const height = Number(gene.height);
  const w = effectiveZWarp(gene.z_warp);
  const zNodes = geneZNodes(gene);
  const rNodes = gene.radii.map((v) => Number(v));
  const zDense = denseZ(height, n, DENSE_FACTOR, w);

  await pyodide.runPythonAsync(`
import json
_z_nodes = json.loads(${JSON.stringify(JSON.stringify(zNodes))})
_r_nodes = json.loads(${JSON.stringify(JSON.stringify(rNodes))})
_z_dense = json.loads(${JSON.stringify(JSON.stringify(zDense))})
_s = ${B3_SPLINE_S}
`);
  await pyodide.runPythonAsync(`_r_dense = b3_profile(_z_nodes, _r_nodes, _z_dense, _s)`);
  const rDense = pyodide.globals.get("_r_dense").toJs() as number[];
  return { z: zDense, r: rDense };
}

/** レガシー密 (z,r) 列を同じ z 格子で B3 再フィット */
export async function b3RefitProfileAsync(
  z: number[],
  r: number[],
  s: number,
): Promise<{ z: number[]; r: number[] }> {
  const pyodide = await loadPyodide();
  await pyodide.runPythonAsync(`
import json
_z = json.loads(${JSON.stringify(JSON.stringify(z))})
_r = json.loads(${JSON.stringify(JSON.stringify(r))})
_s = ${s}
`);
  await pyodide.runPythonAsync(`_r_out = b3_profile(_z, _r, _z, _s)`);
  const rOut = pyodide.globals.get("_r_out").toJs() as number[];
  return { z, r: rOut };
}

export function b3RefitSForGene(zLen: number, gene: Gene): number {
  return b3RefitS(zLen, gene.N);
}
