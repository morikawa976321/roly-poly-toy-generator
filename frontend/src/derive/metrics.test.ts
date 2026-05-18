/**
 * computeMetrics / geneWithModifications の単体テスト。
 *
 * 役割: メトリクス計算が延長・カットで変化することの回帰テスト。
 * 働き: vitest が fixture gene.json で volume・centroid・z_cog_max を検証する。
 */
import { describe, expect, it } from "vitest";
import geneJson from "../../../docs/designs/6d7afe17fed27c7c/gene.json";
import type { Gene } from "../types";
import { computeMetrics, geneWithModifications } from "./metrics";
import { maxTopExtensionMm } from "./profileExtension";

describe("computeMetrics", () => {
  it("updates volume and centroid when extension or cut changes", () => {
    const gene = geneJson as Gene;
    const ext = maxTopExtensionMm(gene);

    const base = computeMetrics(gene);
    const extended = computeMetrics(geneWithModifications(gene, ext, 0, 0));
    const cut = computeMetrics(geneWithModifications(gene, ext, 50, 35));

    expect(extended.volume).not.toBeCloseTo(base.volume, -2);
    expect(extended.centroid_z).not.toBeCloseTo(base.centroid_z, 1);
    expect(cut.volume).toBeLessThan(extended.volume);
    expect(cut.centroid_z).not.toBeCloseTo(extended.centroid_z, 1);
    expect(cut.z_cog_max).not.toBeNull();
    expect(base.z_cog_max).not.toBeNull();
  });
});
