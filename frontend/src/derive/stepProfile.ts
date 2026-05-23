/**
 * STEP エクスポート用 B-spline プロファイルエッジ。
 *
 * 役割: (z,r) 点列の間引きと OpenCascade スプラインエッジ生成。
 * 働き: stepExporter が subsampleProfileUniformZ / makeProfileSplineEdge で母線を OCCT に渡す。
 * 制約: opencascade.js 1.1.1 は GeomAPI_Interpolate 非同梱。PointsToBSpline_2 + Handle_Geom_Curve_2 + MakeEdge_24 が必須。
 */

/** スプライン近似に渡す最大点数 */
const STEP_PROFILE_MAX_POINTS = 64;

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
    return dedupeProfileZ(zz, rr);
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
  return dedupeProfileZ(zz, rr);
}

export type MeridianProfileForStep = {
  z: number[];
  r: number[];
  /** 閉ワイヤー用の底軸 z（gene v2 では z[0]） */
  zAxisBottom: number;
  /** 閉ワイヤー用の上端軸 z */
  zAxisTop: number;
  /** 上端が軸上（r≈0）ならスプラインが極まで届く */
  topOnAxis: boolean;
};

/**
 * STEP 用子午線点列。底極 (r=0,z[0]) を含め、(A) の径方向スタブを廃止する。
 * PointsToBSpline の始端オーバーシュート＋回転で底部にでっぱりが出るのを防ぐ。
 */
export function buildMeridianProfileForStep(
  z: number[],
  r: number[],
  eps = 1e-6,
): MeridianProfileForStep {
  let iStart = 0;
  while (iStart < z.length && r[iStart] <= eps) iStart++;
  let iEnd = z.length - 1;
  while (iEnd >= 0 && r[iEnd] <= eps) iEnd--;

  const zAxisBottom = z[0];
  const zAxisTop = z[z.length - 1];
  const topOnAxis = r[z.length - 1] <= eps;

  const zz: number[] = [zAxisBottom];
  const rr: number[] = [0];

  if (iStart <= iEnd) {
    const bodyMax = Math.max(4, STEP_PROFILE_MAX_POINTS - (topOnAxis ? 2 : 1));
    const body = subsampleProfileUniformZ(z, r, iStart, iEnd, bodyMax);
    for (let i = 0; i < body.z.length; i++) {
      const zi = body.z[i];
      const ri = body.r[i];
      if (zi <= zAxisBottom + 1e-9 && ri <= eps) continue;
      if (topOnAxis && zi >= zAxisTop - 1e-9 && ri <= eps) continue;
      zz.push(zi);
      rr.push(ri);
    }
  }

  if (topOnAxis) {
    zz.push(zAxisTop);
    rr.push(0);
  }

  const deduped = dedupeProfileZ(zz, rr);
  return {
    ...deduped,
    zAxisBottom,
    zAxisTop: topOnAxis ? zAxisTop : z[iEnd],
    topOnAxis,
  };
}

function dedupeProfileZ(
  z: number[],
  r: number[],
): { z: number[]; r: number[] } {
  const zz: number[] = [];
  const rr: number[] = [];
  for (let i = 0; i < z.length; i++) {
    if (zz.length > 0 && Math.abs(z[i] - zz[zz.length - 1]) <= 1e-9) continue;
    zz.push(z[i]);
    rr.push(r[i]);
  }
  return { z: zz, r: rr };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Oc = any;

/** opencascade.js 1.1.1: 無引数 ctor + Resize(1, n, false) */
export function buildPointArray(
  oc: Oc,
  z: number[],
  r: number[],
  t: <T>(obj: T) => T,
): unknown {
  const n = z.length;
  const ArrayCtor =
    oc.TColgp_Array1OfPnt_1 ??
    oc.TColgp_Array1OfPnt_2 ??
    oc.TColgp_Array1OfPnt;
  if (typeof ArrayCtor !== "function") {
    throw new Error("opencascade.js: TColgp_Array1OfPnt not available");
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const arr = t(new (ArrayCtor as any)());
  const resize = (arr as { Resize: (lo: number, hi: number, copy: boolean) => void })
    .Resize;
  resize.call(arr, 1, n, false);

  const setValue =
    typeof arr.SetValue === "function"
      ? (i: number, p: unknown) => arr.SetValue(i, p)
      : (i: number, p: unknown) => arr.setValue(i, p);

  for (let i = 0; i < n; i++) {
    setValue(i + 1, t(new oc.gp_Pnt_3(r[i], 0, z[i])));
  }
  return arr;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function bareGeomCurve(curveHandle: any): any {
  if (curveHandle && typeof curveHandle.get === "function") {
    return curveHandle.get();
  }
  return curveHandle;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function makeGeomCurveFromPoints(
  oc: Oc,
  z: number[],
  r: number[],
  t: <T>(obj: T) => T,
): any | null {
  const pts = buildPointArray(oc, z, r, t);
  const geomAbs = oc.GeomAbs_Shape?.GeomAbs_C2 ?? oc.GeomAbs_C2 ?? 2;
  const P2B = oc.GeomAPI_PointsToBSpline_2;
  if (typeof P2B !== "function") return null;

  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    // 端点乖離を抑えて底部オーバーシュート（でっぱり）を減らす
    const p2b = t(new (P2B as any)(pts, 3, 8, geomAbs, 1e-6));
    if (typeof p2b.Curve !== "function") return null;
    return p2b.Curve();
  } catch {
    return null;
  }
}

/**
 * Handle_Geom_BSplineCurve → Handle_Geom_Curve → TopoDS_Edge。
 * opencascade.js 1.1.1 では MakeEdge_24(Handle_Geom_Curve) のみが有効（実測）。
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function makeEdgeFromGeomCurve(
  oc: Oc,
  curveHandle: any,
  t: <T>(obj: T) => T,
): any | null {
  const bare = bareGeomCurve(curveHandle);
  const HandleCtor = oc.Handle_Geom_Curve_2 ?? oc.Handle_Geom_Curve_1;
  const EdgeCtor = oc.BRepBuilderAPI_MakeEdge_24 ?? oc.BRepBuilderAPI_MakeEdge_23;
  if (typeof HandleCtor !== "function" || typeof EdgeCtor !== "function") {
    return null;
  }

  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const hCurve = t(new (HandleCtor as any)(bare));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mk = t(new (EdgeCtor as any)(hCurve));
    if (typeof mk.IsDone === "function" && !mk.IsDone()) return null;
    return mk.Edge();
  } catch {
    return null;
  }
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
    const curveHandle = makeGeomCurveFromPoints(oc, z, r, t);
    if (!curveHandle) return null;
    return makeEdgeFromGeomCurve(oc, curveHandle, t);
  } catch {
    return null;
  }
}
