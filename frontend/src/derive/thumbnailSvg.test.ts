/**
 * thumbnailSvg の単体テスト。
 *
 * 役割: 傾斜上面カットが断面 SVG に反映されることの回帰テスト。
 * 働き: vitest が SVG polygon 点列と cutProfileSilhouette の一致を検証する。
 */
import { describe, expect, it } from "vitest";
import geneJson from "../../../docs/designs/6d7afe17fed27c7c/gene.json";
import type { Gene } from "../types";
import { computeMetrics, geneWithModifications } from "./metrics";
import { cutProfileSilhouette } from "./meshPlaneCut";
import { effectiveProfile } from "./profileExtension";
import { thumbnailSvg } from "./thumbnailSvg";

function polygonPointsFromSvg(svg: string): Array<[number, number]> {
  const m = svg.match(/<polygon points="([^"]+)"/);
  expect(m).toBeTruthy();
  return m![1].split(" ").map((pair) => {
    const [x, y] = pair.split(",").map(Number);
    return [x, y] as [number, number];
  });
}

describe("thumbnailSvg", () => {
  it("shows full body with angled top cut in cross-section", () => {
    const gene = geneWithModifications(
      geneJson as Gene,
      30,
      100,
      35,
    );
    const metrics = computeMetrics(gene);
    const svg = thumbnailSvg(gene, metrics);
    const pts = polygonPointsFromSvg(svg);

    const ys = pts.map((p) => p[1]);
    expect(pts.length).toBeGreaterThan(100);
    expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThan(50);

    const { z, r } = effectiveProfile(gene);
    const uncutTopZ = z[z.length - 1];
    expect(uncutTopZ).toBeGreaterThan(110);
    const { zRight } = cutProfileSilhouette(z, r, 100, 35);
    expect(zRight[0]).toBeCloseTo(0, 3);
    expect(zRight[zRight.length - 1]).toBeLessThan(uncutTopZ - 5);

    expect(Math.min(...ys)).toBeLessThan(5);
  });
});
