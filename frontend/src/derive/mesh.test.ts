import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { Gene } from "../types";
import { cappedGeometryFromGene } from "./mesh";

function assertWatertightIndexedGeometry(geom: THREE.BufferGeometry) {
  const index = geom.getIndex();
  expect(index, "geometry must be indexed").not.toBeNull();
  if (!index) return;

  const arr = index.array as unknown as ArrayLike<number>;
  expect(arr.length % 3, "index length must be multiple of 3").toBe(0);

  const edgeCount = new Map<string, number>();
  const addEdge = (a: number, b: number) => {
    const i = Math.min(a, b);
    const j = Math.max(a, b);
    const k = `${i},${j}`;
    edgeCount.set(k, (edgeCount.get(k) ?? 0) + 1);
  };

  for (let t = 0; t < arr.length; t += 3) {
    const a = Number(arr[t]);
    const b = Number(arr[t + 1]);
    const c = Number(arr[t + 2]);
    // degenerate triangles are not allowed in watertight meshes
    expect(a).not.toBe(b);
    expect(b).not.toBe(c);
    expect(c).not.toBe(a);

    addEdge(a, b);
    addEdge(b, c);
    addEdge(c, a);
  }

  for (const [edge, cnt] of edgeCount.entries()) {
    expect(cnt, `edge ${edge} must be shared by exactly 2 faces`).toBe(2);
  }
}

function makeGene(radii: number[], height = 50, z_warp: number | null = 2.0): Gene {
  return {
    version: 2,
    N: radii.length,
    height,
    bottom_radius: 0.0,
    radii,
    z_warp,
  };
}

describe("derive/mesh", () => {
  it(
    "produces a watertight revolve mesh for typical v2 genes",
    () => {
      // Keep geometry small so the edge-count check stays fast.
      const N = 12;
      const flatBody = [0.0, ...Array.from({ length: N - 2 }, () => 10.0), 4.0];
      const tapered = [
        0.0,
        ...Array.from({ length: N - 2 }, (_, i) => 18.0 - 12.0 * (i / (N - 3))),
        2.0,
      ];

      for (const radii of [flatBody, tapered]) {
        const gene = makeGene(radii, 60);
        const geom = cappedGeometryFromGene(gene, 32);
        assertWatertightIndexedGeometry(geom);
      }
    },
    20_000,
  );

  it(
    "handles rt=0 tip without leaving boundaries",
    () => {
      const N = 12;
      const radii = [0.0, ...Array.from({ length: N - 2 }, () => 10.0), 0.0];
      const gene = makeGene(radii, 50);
      const geom = cappedGeometryFromGene(gene, 32);
      assertWatertightIndexedGeometry(geom);
    },
    20_000,
  );
});

