import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { Gene } from "../types";
import { cappedGeometryFromGene } from "./mesh";
import { geneTopCutParams, signedCutDist } from "./meshPlaneCut";

function posKey(
  pos: THREE.BufferAttribute | THREE.InterleavedBufferAttribute,
  idx: number,
): string {
  return `${Math.round(pos.getX(idx) * 1e4)}:${Math.round(pos.getY(idx) * 1e4)}:${Math.round(pos.getZ(idx) * 1e4)}`;
}

function assertWatertightIndexedGeometry(geom: THREE.BufferGeometry) {
  const index = geom.getIndex();
  const pos = geom.getAttribute("position");
  expect(index, "geometry must be indexed").not.toBeNull();
  expect(pos).toBeTruthy();
  if (!index || !pos) return;

  const arr = index.array as unknown as ArrayLike<number>;
  expect(arr.length % 3, "index length must be multiple of 3").toBe(0);

  const edgeCount = new Map<string, number>();
  const addEdge = (a: number, b: number) => {
    const ka = posKey(pos, a);
    const kb = posKey(pos, b);
    const k = ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
    edgeCount.set(k, (edgeCount.get(k) ?? 0) + 1);
  };

  for (let t = 0; t < arr.length; t += 3) {
    const a = Number(arr[t]);
    const b = Number(arr[t + 1]);
    const c = Number(arr[t + 2]);
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
    top_extension_mm: 0,
    top_cut_height_mm: 0,
    top_cut_angle_deg: 0,
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

  it(
    "keeps watertight mesh after horizontal top cut with cap",
    () => {
      const N = 12;
      const radii = [
        0.0,
        ...Array.from({ length: N - 2 }, (_, i) => 18.0 - 12.0 * (i / (N - 3))),
        2.0,
      ];
      const gene = makeGene(radii, 60);
      gene.top_cut_height_mm = 45;
      const geom = cappedGeometryFromGene(gene, 32);
      assertWatertightIndexedGeometry(geom);
    },
    20_000,
  );

  function assertCapFacesOutward(
    geom: THREE.BufferGeometry,
    zCut: number,
    tanA: number,
  ) {
    const pos = geom.getAttribute("position")!;
    const index = geom.getIndex()!;
    const nx = -tanA;
    const nz = 1;
    const nLen = Math.hypot(nx, nz);
    let outward = 0;
    let inward = 0;
    for (let i = 0; i < index.count; i += 3) {
      const ia = index.getX(i);
      const ib = index.getX(i + 1);
      const ic = index.getX(i + 2);
      const verts = [ia, ib, ic].map((idx) => ({
        x: pos.getX(idx),
        y: pos.getY(idx),
        z: pos.getZ(idx),
      }));
      if (
        !verts.every((v) => Math.abs(signedCutDist(v, zCut, tanA)) < 1e-2)
      ) {
        continue;
      }
      const ax = verts[0].x;
      const ay = verts[0].y;
      const az = verts[0].z;
      const bx = verts[1].x;
      const by = verts[1].y;
      const bz = verts[1].z;
      const cx = verts[2].x;
      const cy = verts[2].y;
      const cz = verts[2].z;
      const ux = bx - ax;
      const uy = by - ay;
      const uz = bz - az;
      const vx = cx - ax;
      const vy = cy - ay;
      const vz = cz - az;
      const fnx = uy * vz - uz * vy;
      const fny = uz * vx - ux * vz;
      const fnz = ux * vy - uy * vx;
      const fnLen = Math.hypot(fnx, fny, fnz);
      if (fnLen < 1e-9) continue;
      const align = Math.abs((fnx * nx + fny * 0 + fnz * nz) / (fnLen * nLen));
      if (align < 0.9) continue;
      const dot = (fnx * nx + fnz * nz) / (fnLen * nLen);
      if (dot > 0) outward++;
      else inward++;
    }
    expect(outward).toBeGreaterThan(0);
    expect(inward).toBe(0);
  }

  it("fills cut face with cap triangles on the cut plane", () => {
    const N = 16;
    const radii = [
      0.0,
      ...Array.from({ length: N - 2 }, (_, i) => 18.0 - 12.0 * (i / (N - 3))),
      2.0,
    ];
    const gene = makeGene(radii, 60);
    gene.top_cut_height_mm = 48;
    gene.top_cut_angle_deg = 20;
    const geom = cappedGeometryFromGene(gene, 48);
    const { zCut, tanA } = geneTopCutParams(gene);
    const pos = geom.getAttribute("position")!;
    const index = geom.getIndex()!;
    let capTriCount = 0;
    for (let i = 0; i < index.count; i += 3) {
      const verts = [0, 1, 2].map((k) => ({
        x: pos.getX(index.getX(i + k)),
        y: pos.getY(index.getX(i + k)),
        z: pos.getZ(index.getX(i + k)),
      }));
      const onPlane = verts.every(
        (v) => Math.abs(signedCutDist(v, zCut, tanA)) < 1e-2,
      );
      if (onPlane) capTriCount++;
    }
    expect(capTriCount).toBeGreaterThan(0);
    assertCapFacesOutward(geom, zCut, tanA);
  });

  it("orients angled cap faces outward for steep cuts", () => {
    const N = 16;
    const radii = [
      0.0,
      ...Array.from({ length: N - 2 }, (_, i) => 18.0 - 12.0 * (i / (N - 3))),
      2.0,
    ];
    const gene = makeGene(radii, 60);
    gene.top_cut_height_mm = 48;
    gene.top_cut_angle_deg = 35;
    const geom = cappedGeometryFromGene(gene, 64);
    const { zCut, tanA } = geneTopCutParams(gene);
    assertCapFacesOutward(geom, zCut, tanA);
  });

  it(
    "keeps watertight mesh after angled top cut with cap",
    () => {
      const N = 12;
      const radii = [
        0.0,
        ...Array.from({ length: N - 2 }, (_, i) => 18.0 - 12.0 * (i / (N - 3))),
        2.0,
      ];
      const gene = makeGene(radii, 60);
      gene.top_cut_height_mm = 50;
      gene.top_cut_angle_deg = 15;
      const geom = cappedGeometryFromGene(gene, 32);
      assertWatertightIndexedGeometry(geom);
    },
    20_000,
  );
});

