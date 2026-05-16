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
