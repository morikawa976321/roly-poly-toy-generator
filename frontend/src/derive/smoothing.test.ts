import { describe, expect, it } from "vitest";
import type { Gene } from "../types";
import { smoothProfile, geneZNodes, DENSE_FACTOR } from "./smoothing";

// backend/app/smoothing.py (smooth_profile) と意図的に "同等挙動" を
// 目指している実装。片方の修正がもう片方に反映されず静かに乖離する
// のを避けるため、両実装で守るべき不変条件を固定する。

function makeGene(
  radii: number[],
  height = 50,
  z_warp: number | null = 2.0,
): Gene {
  return {
    version: 2,
    N: radii.length,
    height,
    bottom_radius: 0.0,
    radii,
    z_warp,
  };
}

function typicalV2Radii(n: number): number[] {
  // 極 → ピーク → 上端テーパ の単峰プロファイル
  const radii: number[] = [0.0];
  for (let i = 1; i < n - 1; i++) {
    const u = i / (n - 1);
    // 単峰: 0.5 近傍でピーク
    const r = 18.0 * Math.sin(Math.PI * u);
    radii.push(Math.max(0.0, r));
  }
  radii.push(2.0);
  return radii;
}

describe("derive/smoothing invariants", () => {
  it("fixes endpoints exactly to the input radii", () => {
    const radii = typicalV2Radii(12);
    const gene = makeGene(radii, 60);
    const { r } = smoothProfile(gene);
    expect(r[0]).toBe(radii[0]);
    expect(r[r.length - 1]).toBe(radii[radii.length - 1]);
  });

  it("keeps every sampled radius non-negative", () => {
    const radii = typicalV2Radii(12);
    const gene = makeGene(radii, 60);
    const { r } = smoothProfile(gene);
    for (const v of r) {
      expect(v).toBeGreaterThanOrEqual(0);
    }
  });

  it("produces monotonic z starting at 0 and ending at height", () => {
    const radii = typicalV2Radii(12);
    const height = 60;
    const gene = makeGene(radii, height);
    const { z, r } = smoothProfile(gene);
    expect(z.length).toBe(r.length);
    expect(z.length).toBe((12 - 1) * DENSE_FACTOR + 1);
    expect(z[0]).toBe(0);
    expect(z[z.length - 1]).toBeCloseTo(height, 10);
    for (let i = 1; i < z.length; i++) {
      expect(z[i]).toBeGreaterThanOrEqual(z[i - 1]);
    }
  });

  it("z_warp=2.0 samples z more densely near the bottom than uniform", () => {
    // 同じ radii/height を使い、z_warp だけ変える。
    // warp=2 は底（z=0）付近で密、上で疎になる。よって列の中央付近の
    // z の値は uniform のそれより小さい（= 底寄り）になるはず。
    const radii = typicalV2Radii(10);
    const height = 50;
    const gLin = makeGene(radii, height, 1.0);
    const gWarp = makeGene(radii, height, 2.0);
    const { z: zLin } = smoothProfile(gLin);
    const { z: zWarp } = smoothProfile(gWarp);

    expect(zLin.length).toBe(zWarp.length);
    const midIdx = Math.floor(zLin.length / 2);
    expect(zWarp[midIdx]).toBeLessThan(zLin[midIdx]);
    // 底近傍は warp の方が密（= 同じ index の z が小さい）
    const quarterIdx = Math.floor(zLin.length / 4);
    expect(zWarp[quarterIdx]).toBeLessThan(zLin[quarterIdx]);
  });

  it("z_warp=null is equivalent to z_warp=1.0 (uniform)", () => {
    const radii = [0.0, 4.0, 8.0, 4.0, 0.0];
    const gNull = makeGene(radii, 40, null);
    const gOne = makeGene(radii, 40, 1.0);
    const { z: zN, r: rN } = smoothProfile(gNull);
    const { z: zO, r: rO } = smoothProfile(gOne);
    expect(zN.length).toBe(zO.length);
    for (let i = 0; i < zN.length; i++) {
      expect(zN[i]).toBeCloseTo(zO[i], 10);
      expect(rN[i]).toBeCloseTo(rO[i], 10);
    }
  });

  it("geneZNodes positions control points according to z_warp", () => {
    const radii = typicalV2Radii(6);
    const height = 60;
    // warp=2: z_i = height * (i/(N-1))^2
    const g = makeGene(radii, height, 2.0);
    const zs = geneZNodes(g);
    expect(zs.length).toBe(6);
    expect(zs[0]).toBe(0);
    expect(zs[zs.length - 1]).toBeCloseTo(height, 10);
    for (let i = 0; i < zs.length; i++) {
      const u = i / (zs.length - 1);
      expect(zs[i]).toBeCloseTo(height * u * u, 10);
    }
  });
});
