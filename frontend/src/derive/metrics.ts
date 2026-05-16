import type { Gene, Metrics } from "../types";
import { cappedGeometryFromGene } from "./mesh";
import { metricsFromGeometryWithFeas } from "./meshMetrics";
import { feasibilityExtrasForGene } from "./feasibilityMetrics";

/**
 * gene の最終形状（延長・カット込み）からメトリクスを算出する。
 * 体積 / 高さ / 幅 / 重心は常にカット後メッシュから求め、3D ビューと一致させる。
 * z_cog_max / bottom_curvature_radius は feasibility 用プロファイルから求める。
 */
export function computeMetrics(gene: Gene): Metrics {
  const feasExtras = feasibilityExtrasForGene(gene);
  const geom = cappedGeometryFromGene(gene, 96);
  return metricsFromGeometryWithFeas(geom, feasExtras);
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

/** プロファイル積分（テスト・デバッグ用）。本番の computeMetrics はメッシュ経路を使う。 */
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
