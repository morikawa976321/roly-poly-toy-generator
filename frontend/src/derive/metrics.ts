import type { Gene, Metrics } from "../types";
import {
  cappedGeometryFromGene,
  revolutionGeometryFromGene,
} from "./mesh";
import { metricsFromGeometryWithFeas } from "./meshMetrics";
import { cutWouldChangeMesh, geneTopCutParams } from "./meshPlaneCut";
import { feasibilityFromProfile } from "./physics";
import { effectiveProfile } from "./profileExtension";

export function computeMetricsFromProfile(z: number[], r: number[]): Metrics {
  const volParts: number[] = [];
  const zCentroidParts: number[] = [];
  const eps = 1e-12;

  for (let i = 0; i < z.length - 1; i++) {
    const dz = z[i + 1] - z[i];
    const a = r[i];
    const b = r[i + 1];
    const k = a * a + a * b + b * b;
    const volI = (Math.PI / 3) * dz * k;
    const zLocal =
      (dz * (a * a + 2 * a * b + 3 * b * b)) / (4 * Math.max(k, eps));
    volParts.push(volI);
    zCentroidParts.push((z[i] + zLocal) * volI);
  }

  const volume = volParts.reduce((s, v) => s + v, 0);
  const centroidZ =
    volume > 0 ? zCentroidParts.reduce((s, v) => s + v, 0) / volume : 0;
  let maxR = 0;
  for (const v of r) maxR = Math.max(maxR, v);

  return {
    volume,
    height: z[z.length - 1],
    max_width: 2 * maxR,
    centroid_z: centroidZ,
    bottom_curvature_radius: null,
    z_cog_max: null,
  };
}

export function computeMetrics(gene: Gene): Metrics {
  const { z, r } = effectiveProfile(gene);
  const feas = feasibilityFromProfile(z, r);
  const feasExtras = {
    bottom_curvature_radius: feas.rho_m_bottom,
    z_cog_max: feas.z_cog_max > 0 ? feas.z_cog_max : null,
  };

  const rev = revolutionGeometryFromGene(gene, 96);
  const { zCut, tanA } = geneTopCutParams(gene);
  if (cutWouldChangeMesh(rev, zCut, tanA)) {
    const cut = cappedGeometryFromGene(gene, 96);
    return metricsFromGeometryWithFeas(cut, feasExtras);
  }

  const base = computeMetricsFromProfile(z, r);
  return { ...base, ...feasExtras };
}

export function geneWithModifications(
  gene: Gene,
  topExtensionMm: number,
  topCutHeightMm: number,
  topCutAngleDeg: number,
): Gene {
  return {
    ...gene,
    top_extension_mm: topExtensionMm,
    top_cut_height_mm: topCutHeightMm,
    top_cut_angle_deg: topCutAngleDeg,
  };
}
