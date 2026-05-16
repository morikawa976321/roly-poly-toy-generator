import * as THREE from "three";
import type { Metrics } from "../types";

function cross(
  ax: number,
  ay: number,
  az: number,
  bx: number,
  by: number,
  bz: number,
): [number, number, number] {
  return [ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx];
}

function dot(ax: number, ay: number, az: number, bx: number, by: number, bz: number): number {
  return ax * bx + ay * by + az * bz;
}

/** 閉じた三角メッシュの体積・重心 z（原点基準の符号付き体積） */
function metricsFromGeometry(geom: THREE.BufferGeometry): {
  volume: number;
  centroidZ: number;
  height: number;
  maxR: number;
} {
  const pos = geom.getAttribute("position");
  if (!pos || pos.count < 3) {
    return { volume: 0, centroidZ: 0, height: 0, maxR: 0 };
  }

  let vol = 0;
  let cz = 0;
  let zMin = Infinity;
  let zMax = -Infinity;
  let maxR = 0;

  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    const z = pos.getZ(i);
    zMin = Math.min(zMin, z);
    zMax = Math.max(zMax, z);
    maxR = Math.max(maxR, Math.hypot(x, y));
  }

  const index = geom.getIndex();
  const accumulateTri = (i0: number, i1: number, i2: number) => {
    const ax = pos.getX(i0);
    const ay = pos.getY(i0);
    const az = pos.getZ(i0);
    const bx = pos.getX(i1);
    const by = pos.getY(i1);
    const bz = pos.getZ(i1);
    const cx = pos.getX(i2);
    const cy = pos.getY(i2);
    const cz0 = pos.getZ(i2);
    const [cxp, cyp, czp] = cross(bx, by, bz, cx, cy, cz0);
    const tet = dot(ax, ay, az, cxp, cyp, czp) / 6;
    vol += tet;
    const zTri = (az + bz + cz0) / 3;
    cz += tet * zTri;
  };

  if (index) {
    for (let i = 0; i < index.count; i += 3) {
      accumulateTri(index.getX(i), index.getX(i + 1), index.getX(i + 2));
    }
  } else {
    for (let i = 0; i < pos.count; i += 3) {
      accumulateTri(i, i + 1, i + 2);
    }
  }

  const volume = Math.abs(vol);
  const centroidZ = Math.abs(vol) > 1e-12 ? cz / vol : 0;

  return {
    volume,
    centroidZ,
    height: Number.isFinite(zMax) ? zMax : 0,
    maxR,
  };
}

export function silhouetteFromGeometry(geom: THREE.BufferGeometry): {
  z: number[];
  r: number[];
} {
  const pos = geom.getAttribute("position");
  if (!pos || pos.count === 0) return { z: [0], r: [0] };

  const byZ = new Map<number, number>();
  for (let i = 0; i < pos.count; i++) {
    const z = pos.getZ(i);
    const zq = Math.round(z * 400) / 400;
    const r = Math.hypot(pos.getX(i), pos.getY(i));
    byZ.set(zq, Math.max(byZ.get(zq) ?? 0, r));
  }
  const z = [...byZ.keys()].sort((a, b) => a - b);
  const r = z.map((zz) => byZ.get(zz) ?? 0);
  return { z, r };
}

export function metricsFromGeometryWithFeas(
  geom: THREE.BufferGeometry,
  feasExtras: Pick<Metrics, "bottom_curvature_radius" | "z_cog_max">,
): Metrics {
  const m = metricsFromGeometry(geom);
  return {
    volume: m.volume,
    height: m.height,
    max_width: 2 * m.maxR,
    centroid_z: m.centroidZ,
    ...feasExtras,
  };
}
