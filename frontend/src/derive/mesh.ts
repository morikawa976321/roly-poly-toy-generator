import type { Gene } from "../types";
import * as THREE from "three";
import { effectiveProfile } from "./profileExtension";
import { clipGeneMesh } from "./meshPlaneCut";

function revolveWatertightGeometry(
  zLine: number[],
  rLine: number[],
  radialSegments: number,
  eps = 1e-6,
): THREE.BufferGeometry {
  if (zLine.length !== rLine.length || zLine.length < 2) {
    throw new Error("profile must have same-length z and r with >= 2 points");
  }
  if (radialSegments < 3) {
    throw new Error("radialSegments must be >= 3");
  }

  const theta: number[] = [];
  for (let i = 0; i < radialSegments; i++) {
    theta.push((2 * Math.PI * i) / radialSegments);
  }

  const vertices: number[] = [];
  const ringIndex: number[] = [];
  const axisIndex: Array<number | null> = [];

  for (let i = 0; i < zLine.length; i++) {
    const zi = zLine[i];
    const ri = Math.abs(rLine[i]) <= eps ? 0 : rLine[i];
    if (ri <= eps) {
      axisIndex.push(vertices.length / 3);
      ringIndex.push(-1);
      vertices.push(0, 0, zi);
      continue;
    }
    axisIndex.push(null);
    ringIndex.push(vertices.length / 3);
    for (const t of theta) {
      vertices.push(ri * Math.cos(t), ri * Math.sin(t), zi);
    }
  }

  const indices: number[] = [];
  const ringVert = (i: number, j: number): number => {
    const base = ringIndex[i];
    if (base < 0) throw new Error("ringVert called for axis point");
    return base + (j % radialSegments);
  };

  // 側面
  for (let i = 0; i < zLine.length - 1; i++) {
    const ra = rLine[i];
    const rb = rLine[i + 1];
    const aAxis = axisIndex[i];
    const bAxis = axisIndex[i + 1];

    for (let j = 0; j < radialSegments; j++) {
      const jn = (j + 1) % radialSegments;
      if (ra <= eps && rb <= eps) continue;

      if (ra <= eps) {
        if (aAxis == null) throw new Error("axis index is missing");
        const b0 = ringVert(i + 1, j);
        const b1 = ringVert(i + 1, jn);
        indices.push(b1, b0, aAxis);
      } else if (rb <= eps) {
        if (bAxis == null) throw new Error("axis index is missing");
        const a0 = ringVert(i, j);
        const a1 = ringVert(i, jn);
        indices.push(a0, a1, bAxis);
      } else {
        const a0 = ringVert(i, j);
        const a1 = ringVert(i, jn);
        const b0 = ringVert(i + 1, j);
        const b1 = ringVert(i + 1, jn);
        indices.push(a0, b1, b0);
        indices.push(a0, a1, b1);
      }
    }
  }

  // 天面キャップ
  if (rLine[rLine.length - 1] > eps) {
    const topCenter = vertices.length / 3;
    vertices.push(0, 0, zLine[zLine.length - 1]);
    const topI = zLine.length - 1;
    for (let j = 0; j < radialSegments; j++) {
      const jn = (j + 1) % radialSegments;
      const a = ringVert(topI, j);
      const b = ringVert(topI, jn);
      indices.push(topCenter, a, b);
    }
  }

  // 底面キャップ
  if (rLine[0] > eps) {
    const botCenter = vertices.length / 3;
    vertices.push(0, 0, zLine[0]);
    for (let j = 0; j < radialSegments; j++) {
      const jn = (j + 1) % radialSegments;
      const a = ringVert(0, j);
      const b = ringVert(0, jn);
      indices.push(b, a, botCenter);
    }
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  geom.setIndex(indices);
  geom.computeVertexNormals();
  return geom;
}

export function latheGeometryFromGene(
  gene: Gene,
  radialSegments = 128,
): THREE.BufferGeometry {
  return cappedGeometryFromGene(gene, radialSegments);
}

export function revolutionGeometryFromGene(
  gene: Gene,
  radialSegments = 128,
): THREE.BufferGeometry {
  const { z, r } = effectiveProfile(gene);
  return revolveWatertightGeometry(z, r, radialSegments, 1e-6);
}

export function cappedGeometryFromGene(
  gene: Gene,
  radialSegments = 128,
): THREE.BufferGeometry {
  const geom = revolutionGeometryFromGene(gene, radialSegments);
  return clipGeneMesh(geom, gene);
}

