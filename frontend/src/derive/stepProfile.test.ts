/**
 * STEP プロファイル間引きの単体テスト。
 *
 * 役割: subsampleProfileUniformZ / buildMeridianProfileForStep の検証。
 * 働き: STEP スプライン入力のリグレッション防止。
 */
import { describe, it, expect } from "vitest";
import {
  buildMeridianProfileForStep,
  subsampleProfileUniformZ,
} from "./stepProfile";

describe("subsampleProfileUniformZ", () => {
  it("caps output at 64 points for long profiles", () => {
    const n = 1500;
    const z = Array.from({ length: n }, (_, i) => i);
    const r = z.map((zi) => 10 + Math.sin(zi * 0.1));
    const { z: zs, r: rs } = subsampleProfileUniformZ(z, r, 0, n - 1);
    expect(zs.length).toBe(64);
    expect(rs.length).toBe(64);
    expect(zs[0]).toBe(z[0]);
    expect(zs[zs.length - 1]).toBe(z[n - 1]);
  });
});

describe("buildMeridianProfileForStep", () => {
  it("starts at south pole r=0 on z[0] without radial stub points", () => {
    const z = [0, 0.01, 0.05, 1, 10, 20, 30];
    const r = [0, 0, 0.001, 0.5, 10, 8, 0];
    const m = buildMeridianProfileForStep(z, r);
    expect(m.z[0]).toBe(0);
    expect(m.r[0]).toBe(0);
    expect(m.zAxisBottom).toBe(0);
    expect(m.topOnAxis).toBe(true);
    expect(m.r[m.r.length - 1]).toBe(0);
    // 底極の直後に r>0 の点があり、iStart 相当の径方向ゼロ長点は含まない
    const secondR = m.r.find((ri, i) => i > 0 && ri > 1e-4);
    expect(secondR).toBeGreaterThan(0);
  });
});
