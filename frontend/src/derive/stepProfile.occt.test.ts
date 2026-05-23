/**
 * opencascade.js 1.1.1 上の STEP スプラインエッジ生成の回帰テスト。
 *
 * 役割: ポリライン回転フォールバック再発の防止。
 * 働き: makeProfileSplineEdge が Handle_Geom_Curve_2 + MakeEdge_24 で成功することを検証。
 */
import { describe, it, expect } from "vitest";
import { loadOpenCascade } from "./stepOcctLoader";
import { makeProfileSplineEdge } from "./stepProfile";

describe("opencascade.js STEP profile edge", () => {
  it(
    "builds a single B-spline edge (not polyline fallback)",
    async () => {
      const oc = await loadOpenCascade();
      const z: number[] = [];
      const r: number[] = [];
      for (let i = 0; i < 64; i++) {
        const u = i / 63;
        z.push(40 * u);
        r.push(15 * Math.sin(Math.PI * u) ** 1.2 + 0.5);
      }

      const temps: unknown[] = [];
      const t = <T>(v: T): T => {
        temps.push(v);
        return v;
      };
      const edge = makeProfileSplineEdge(oc, z, r, t);
      expect(edge).not.toBeNull();
    },
    120_000,
  );
});
