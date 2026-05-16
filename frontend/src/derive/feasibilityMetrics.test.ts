import { describe, expect, it } from "vitest";
import geneJson from "../../../docs/designs/6d7afe17fed27c7c/gene.json";
import type { Gene } from "../types";
import { feasibilityExtrasForGene } from "./feasibilityMetrics";
import { geneWithModifications } from "./metrics";
import { feasibilityProfile } from "./profileExtension";

describe("feasibilityExtrasForGene", () => {
  it("lowers z_cog_max when an angled cut removes upper material", () => {
    const gene = geneJson as Gene;
    const uncut = feasibilityExtrasForGene(gene);
    expect(uncut.z_cog_max).not.toBeNull();

    const { z, r } = feasibilityProfile(gene);
    let peakIdx = 0;
    for (let i = 1; i < r.length; i++) {
      if (r[i] > r[peakIdx]) peakIdx = i;
    }
    const cutH = Math.max(5, 0.45 * z[peakIdx]);

    const cutGene = geneWithModifications(gene, 0, cutH, 25);
    const cut = feasibilityExtrasForGene(cutGene);
    expect(cut.z_cog_max).not.toBeNull();
    expect(cut.z_cog_max!).toBeLessThan(uncut.z_cog_max!);
  });

  it("updates z_cog_max as cut height moves through the belly (with extension)", () => {
    const gene = geneJson as Gene;
    const ext = 30;
    const values: number[] = [];
    for (const cutH of [25, 40, 55]) {
      const g = geneWithModifications(gene, ext, cutH, 35);
      const m = feasibilityExtrasForGene(g);
      expect(m.z_cog_max).not.toBeNull();
      values.push(m.z_cog_max!);
    }
    expect(new Set(values.map((v) => v.toFixed(3))).size).toBeGreaterThan(1);
  });
});
