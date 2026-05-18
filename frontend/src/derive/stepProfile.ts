/**
 * STEP エクスポート用 B-spline プロファイルエッジ。
 *
 * 役割: (z,r) 点列の間引きと OpenCascade スプラインエッジ生成。
 * 働き: stepExporter が subsampleProfileUniformZ / makeProfileSplineEdge で母線を OCCT に渡す。
 */

/** スプライン近似に渡す最大点数（多すぎると補間が不安定） */
const STEP_PROFILE_MAX_POINTS = 96;

/** z 等間隔に間引き（端点は必ず含める） */
export function subsampleProfileUniformZ(
  z: number[],
  r: number[],
  iStart: number,
  iEnd: number,
  maxPoints: number = STEP_PROFILE_MAX_POINTS,
): { z: number[]; r: number[] } {
  if (iEnd <= iStart) {
    return { z: [], r: [] };
  }
  const nSeg = iEnd - iStart;
  if (nSeg + 1 <= maxPoints) {
    const zz: number[] = [];
    const rr: number[] = [];
    for (let i = iStart; i <= iEnd; i++) {
      zz.push(z[i]);
      rr.push(r[i]);
    }
    return { z: zz, r: rr };
  }

  const z0 = z[iStart];
  const z1 = z[iEnd];
  const target = Math.max(4, maxPoints);
  const zz: number[] = [];
  const rr: number[] = [];
  let j = iStart;

  for (let k = 0; k < target; k++) {
    const t = k / (target - 1);
    const zq = z0 + t * (z1 - z0);
    while (j + 1 < iEnd && z[j + 1] < zq) j++;
    const zA = z[j];
    const zB = z[j + 1];
    const rA = r[j];
    const rB = r[j + 1];
    const u = zB === zA ? 0 : (zq - zA) / (zB - zA);
    zz.push(zq);
    rr.push(rA * (1 - u) + rB * u);
  }

  zz[0] = z[iStart];
  rr[0] = r[iStart];
  zz[zz.length - 1] = z[iEnd];
  rr[rr.length - 1] = r[iEnd];
  return { z: zz, r: rr };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Oc = any;

function ocCtor(
  oc: Oc,
  base: string,
  prefer: number[] = [],
): ((...args: unknown[]) => unknown) | null {
  for (const i of prefer) {
    const c = oc[`${base}_${i}`];
    if (typeof c === "function") return c;
  }
  for (let i = 1; i <= 32; i++) {
    const c = oc[`${base}_${i}`];
    if (typeof c === "function") return c;
  }
  return typeof oc[base] === "function" ? oc[base] : null;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function makeHPointArray(
  oc: Oc,
  z: number[],
  r: number[],
  t: <T>(obj: T) => T,
): any {
  const n = z.length;
  const HArrayCtor = ocCtor(oc, "TColgp_HArray1OfPnt", [2, 1]);
  if (!HArrayCtor) {
    throw new Error("opencascade.js: TColgp_HArray1OfPnt not available");
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const arr = t(new (HArrayCtor as any)(1, n));
  const setValue =
    typeof arr.SetValue === "function"
      ? (idx: number, p: unknown) => arr.SetValue(idx, p)
      : (idx: number, p: unknown) => arr.setValue(idx, p);

  for (let i = 0; i < n; i++) {
    setValue(i + 1, t(new oc.gp_Pnt_3(r[i], 0, z[i])));
  }
  return arr;
}

/**
 * (r,0,z) 点列からプロファイル用 B-spline Edge を 1 本生成する。
 * 失敗時は null（呼び出し側で直線フォールバック）。
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function makeProfileSplineEdge(
  oc: Oc,
  z: number[],
  r: number[],
  t: <T>(obj: T) => T,
): any | null {
  if (z.length < 2 || z.length !== r.length) return null;

  try {
    const hPoints = makeHPointArray(oc, z, r, t);

    const InterpCtor = ocCtor(oc, "GeomAPI_Interpolate", [1, 2]);
    if (!InterpCtor) return null;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const interp = t(new (InterpCtor as any)(hPoints, false, 1e-3));
    if (typeof interp.Perform === "function") {
      interp.Perform();
    } else if (typeof interp.perform === "function") {
      interp.perform();
    }

    if (typeof interp.IsDone === "function" && !interp.IsDone()) {
      return null;
    }

    const curve =
      typeof interp.Curve === "function"
        ? interp.Curve()
        : typeof interp.curve === "function"
          ? interp.curve()
          : null;
    if (!curve) return null;

    const makeEdgeCtors = [
      24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8,
    ];
    for (const idx of makeEdgeCtors) {
      const EdgeCtor = oc[`BRepBuilderAPI_MakeEdge_${idx}`];
      if (typeof EdgeCtor !== "function") continue;
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const mk = t(new (EdgeCtor as any)(curve));
        if (typeof mk.IsDone === "function" && !mk.IsDone()) continue;
        return mk.Edge();
      } catch {
        try {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const mk = t(new (EdgeCtor as any)(curve, 0, 1));
          if (typeof mk.IsDone === "function" && !mk.IsDone()) continue;
          return mk.Edge();
        } catch {
          // next overload
        }
      }
    }

    return null;
  } catch {
    return null;
  }
}
