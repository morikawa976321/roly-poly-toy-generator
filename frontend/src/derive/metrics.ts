import type { Gene, Metrics } from "../types";
import { smoothProfile } from "./smoothing";

// backend/app/geometry.py::compute_metrics の TS ポート
export function computeMetricsFromGene(gene: Gene): Metrics {
  const { z, r } = smoothProfile(gene);
  const n = z.length;

  let volume = 0;
  let moment = 0;
  let maxR = 0;

  for (let i = 0; i < n - 1; i++) {
    const z0 = z[i];
    const z1 = z[i + 1];
    const dz = z1 - z0;
    const a = r[i];
    const b = r[i + 1];
    if (a > maxR) maxR = a;
    if (b > maxR) maxR = b;

    const k = a * a + a * b + b * b; // >=0
    const volI = (Math.PI / 3) * dz * k;
    const denom = Math.max(k, 1e-12);
    const zCLocal = dz * (a * a + 2 * a * b + 3 * b * b) / (4 * denom);
    const zCGlobal = z0 + zCLocal;

    volume += volI;
    moment += volI * zCGlobal;
  }

  const centroidZ = volume > 0 ? moment / volume : 0;
  return {
    volume,
    height: Number(gene.height),
    max_width: 2 * maxR,
    centroid_z: centroidZ,
    // feasibility は DB 由来を表示するため、ここでは計算しない
    z_cog_suggested: null,
    bottom_curvature_radius: null,
    z_cog_max: null,
  };
}

