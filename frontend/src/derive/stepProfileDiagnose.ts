/**
 * STEP 用 B-spline エッジ生成の段階診断（opencascade.js 1.1.1 向け）。
 *
 * 役割: ポリライン回転フォールバックの失敗段階を特定する。
 * 働き: buildPointArray / diagnoseProfileSplineEdge が API 制約を検証する。
 */

import { buildPointArray as buildPointArrayImpl } from "./stepProfile";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Oc = any;

export type SplineDiagStage =
  | "input"
  | "tcolgp_array"
  | "points_to_bspline"
  | "interpolate"
  | "geom_curve"
  | "make_edge"
  | "done";

export type SplineDiagResult = {
  ok: boolean;
  failedAt: SplineDiagStage;
  pointCount: number;
  available: {
    TColgp_Array1OfPnt: string | null;
    TColgp_HArray1OfPnt: string | null;
    GeomAPI_PointsToBSpline: string | null;
    GeomAPI_Interpolate: string | null;
    BRepBuilderAPI_MakeEdge: string[];
    Geom_BSplineCurve: string | null;
  };
  errors: Partial<Record<SplineDiagStage | "tcolgp_harray", string>>;
  edgeBuilt: boolean;
  curveSource: "points_to_bspline" | "interpolate" | null;
  makeEdgeOverload: number | null;
  arrayStrategy: string | null;
};

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

function ctorName(oc: Oc, base: string, prefer: number[] = []): string | null {
  const c = ocCtor(oc, base, prefer);
  if (!c) return null;
  for (let i = 1; i <= 32; i++) {
    if (oc[`${base}_${i}`] === c) return `${base}_${i}`;
  }
  if (oc[base] === c) return base;
  return base;
}

function listMakeEdgeCtors(oc: Oc): string[] {
  const out: string[] = [];
  for (let i = 1; i <= 32; i++) {
    if (typeof oc[`BRepBuilderAPI_MakeEdge_${i}`] === "function") {
      out.push(`BRepBuilderAPI_MakeEdge_${i}`);
    }
  }
  if (typeof oc.BRepBuilderAPI_MakeEdge === "function") {
    out.push("BRepBuilderAPI_MakeEdge");
  }
  return out;
}

function errMsg(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function readCurve(api: any): any | null {
  if (!api) return null;
  if (typeof api.Curve === "function") return api.Curve();
  if (typeof api.curve === "function") return api.curve();
  return null;
}

/** 診断用ラッパ（stepProfile.buildPointArray を再利用） */
export function buildPointArray(
  oc: Oc,
  z: number[],
  r: number[],
  t: <T>(obj: T) => T = (x) => x,
): { arr: unknown; strategy: string } | null {
  try {
    const arr = buildPointArrayImpl(oc, z, r, t);
    return { arr, strategy: "Array1OfPnt() + Resize(1,n,false)" };
  } catch {
    return null;
  }
}

/** opencascade.js 上でスプラインエッジ構築を段階診断する */
export function diagnoseProfileSplineEdge(
  oc: Oc,
  z: number[],
  r: number[],
  t: <T>(obj: T) => T = (x) => x,
): SplineDiagResult {
  const result: SplineDiagResult = {
    ok: false,
    failedAt: "input",
    pointCount: z.length,
    available: {
      TColgp_Array1OfPnt: ctorName(oc, "TColgp_Array1OfPnt", [1, 2]),
      TColgp_HArray1OfPnt: ctorName(oc, "TColgp_HArray1OfPnt", [2, 1]),
      GeomAPI_PointsToBSpline: ctorName(oc, "GeomAPI_PointsToBSpline", [1, 2, 3]),
      GeomAPI_Interpolate: ctorName(oc, "GeomAPI_Interpolate", [1, 2]),
      BRepBuilderAPI_MakeEdge: listMakeEdgeCtors(oc),
      Geom_BSplineCurve: ctorName(oc, "Geom_BSplineCurve", [1, 2, 3, 4]),
    },
    errors: {},
    edgeBuilt: false,
    curveSource: null,
    makeEdgeOverload: null,
    arrayStrategy: null,
  };

  if (z.length < 2 || z.length !== r.length) {
    result.errors.input = "need >=2 points with matching z,r";
    return result;
  }

  let arr: unknown;
  try {
    const built = buildPointArray(oc, z, r, t);
    if (!built) {
      result.failedAt = "tcolgp_array";
      result.errors.tcolgp_array = "all TColgp array construction strategies failed";
      return result;
    }
    arr = built.arr;
    result.arrayStrategy = built.strategy;
  } catch (e) {
    result.failedAt = "tcolgp_array";
    result.errors.tcolgp_array = errMsg(e);
    return result;
  }

  let curve: unknown = null;
  const geomAbs = oc.GeomAbs_Shape?.GeomAbs_C2 ?? oc.GeomAbs_C2 ?? 2;
  const attempts: { label: string; idx: number; args: unknown[] }[] = [];
  for (let idx = 1; idx <= 5; idx++) {
    if (typeof oc[`GeomAPI_PointsToBSpline_${idx}`] !== "function") continue;
    attempts.push({
      label: `_${idx}(pts)`,
      idx,
      args: [arr],
    });
    attempts.push({
      label: `_${idx}(pts,3,8,C2,tol)`,
      idx,
      args: [arr, 3, 8, geomAbs, 1e-3],
    });
  }
  if (attempts.length === 0) {
    result.failedAt = "points_to_bspline";
    result.errors.points_to_bspline = "GeomAPI_PointsToBSpline missing";
    return result;
  }
  for (const { label, idx, args } of attempts) {
    try {
      const P2BCtor = oc[`GeomAPI_PointsToBSpline_${idx}`];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const p2b = t(new (P2BCtor as any)(...args));
      curve = readCurve(p2b);
      if (curve) {
        result.curveSource = "points_to_bspline";
        break;
      }
      result.errors.points_to_bspline = `Curve() null for ${label}`;
    } catch (e) {
      result.errors.points_to_bspline = `${label}: ${errMsg(e)}`;
    }
  }

  if (!curve) {
    result.failedAt = "points_to_bspline";
    result.errors.interpolate =
      "GeomAPI_Interpolate excluded from opencascade.js 1.1.1 (embind/autobind.py blacklist)";
    return result;
  }

  const HandleCtor = oc.Handle_Geom_Curve_2;
  const EdgeCtor = oc.BRepBuilderAPI_MakeEdge_24;
  if (typeof HandleCtor !== "function" || typeof EdgeCtor !== "function") {
    result.failedAt = "make_edge";
    result.errors.make_edge =
      "Handle_Geom_Curve_2 or BRepBuilderAPI_MakeEdge_24 missing";
    return result;
  }

  try {
    const bare =
      curve && typeof (curve as { get?: () => unknown }).get === "function"
        ? (curve as { get: () => unknown }).get()
        : curve;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const hCurve = t(new (HandleCtor as any)(bare));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mk = t(new (EdgeCtor as any)(hCurve));
    if (typeof mk.IsDone === "function" && !mk.IsDone()) {
      result.failedAt = "make_edge";
      result.errors.make_edge = "MakeEdge_24 IsDone false";
      return result;
    }
    mk.Edge();
    result.edgeBuilt = true;
    result.makeEdgeOverload = 24;
    result.ok = true;
    result.failedAt = "done";
    return result;
  } catch (e) {
    result.failedAt = "make_edge";
    result.errors.make_edge = errMsg(e);
    return result;
  }
}
