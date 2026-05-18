/** Auto-synced from frontend/src/derive — npm run sync-core */

/**
 * STEP AP214 エクスポート（OpenCascade.js WASM）。
 *
 * 役割: effective プロファイルから回転体ソリッドを構築し STEP バイナリを生成。
 * 働き: DetailPage のダウンロードから lazy-load された opencascade.js で BRep 構築・top cut 適用。初回のみ WASM（~65MB）をロードし以降キャッシュ。
 */

import type { Gene } from "@core/types";
import { effectiveProfile } from "@core/derive/profileExtension";
import {
  cutWouldChangeMesh,
  geneTopCutParams,
  signedCutDist,
  topCutTanAngle,
} from "@core/derive/meshPlaneCut";
import { revolutionGeometryFromGene } from "@core/derive/mesh";
import {
  makeProfileSplineEdge,
  subsampleProfileUniformZ,
} from "./stepProfile.ts";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let ocPromise: Promise<any> | null = null;

/** カット平面 z = zCut + u·tanA 上の大きな矩形フェース（MakeFace_2 の UV 版は 1.1.1 で非対応） */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function makeCutPlaneFace(
  oc: any,
  zCut: number,
  tanA: number,
  halfSize: number,
  t: <T>(obj: T) => T,
): any {
  const L = halfSize;
  const wireMaker = t(new oc.BRepBuilderAPI_MakeWire_1());
  const corners: [number, number][] = [
    [-L, -L],
    [L, -L],
    [L, L],
    [-L, L],
  ];
  const pnt = (u: number, v: number) =>
    t(new oc.gp_Pnt_3(u, v, zCut + tanA * u));

  for (let i = 0; i < 4; i++) {
    const [u0, v0] = corners[i];
    const [u1, v1] = corners[(i + 1) % 4];
    const edgeMaker = t(new oc.BRepBuilderAPI_MakeEdge_3(pnt(u0, v0), pnt(u1, v1)));
    wireMaker.Add_1(edgeMaker.Edge());
  }

  const MakeFaceCtor =
    oc.BRepBuilderAPI_MakeFace_15 ?? oc.BRepBuilderAPI_MakeFace_1;
  const faceMaker = t(new MakeFaceCtor(wireMaker.Wire(), true));
  return faceMaker.Face();
}

/** Face から半空間ソリッドを作る（MakeHalfSpace_2 は Shell 専用なので使わない） */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function makeHalfSpaceSolid(
  oc: any,
  face: any,
  refPt: any,
  t: <T>(obj: T) => T,
): any {
  if (oc.BRepPrimAPI_MakeHalfSpace_1) {
    const mkHalf = t(new oc.BRepPrimAPI_MakeHalfSpace_1(face, refPt));
    if (typeof mkHalf.IsDone === "function" && !mkHalf.IsDone()) {
      throw new Error("MakeHalfSpace failed for cut plane");
    }
    return typeof mkHalf.Solid === "function" ? mkHalf.Solid() : mkHalf.Shape();
  }

  if (oc.BRepPrimAPI_MakeHalfSpace_2) {
    const shellMaker = t(new oc.BRepBuilderAPI_MakeShell_1());
    const add = shellMaker.Add_1 ?? shellMaker.Add;
    if (typeof add !== "function") {
      throw new Error("BRepBuilderAPI_MakeShell.Add not available");
    }
    add.call(shellMaker, face);
    const shell = shellMaker.Shell();
    const mkHalf = t(new oc.BRepPrimAPI_MakeHalfSpace_2(shell, refPt));
    if (typeof mkHalf.IsDone === "function" && !mkHalf.IsDone()) {
      throw new Error("MakeHalfSpace failed for cut plane");
    }
    return typeof mkHalf.Solid === "function" ? mkHalf.Solid() : mkHalf.Shape();
  }

  throw new Error("opencascade.js: MakeHalfSpace API not available");
}

/** Boolean Common（1.1.1: _3=2形状） */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function booleanCommonSolid(
  oc: any,
  solid: any,
  tool: any,
  t: <T>(obj: T) => T,
): any {
  const runBuild = (op: any) => {
    if (typeof op.Build === "function") op.Build();
  };

  const finish = (op: any) => {
    runBuild(op);
    if (typeof op.IsDone === "function" && !op.IsDone()) {
      throw new Error("BRepAlgoAPI_Common failed for plane cut");
    }
    return op.Shape();
  };

  if (oc.BRepAlgoAPI_Common_3) {
    return finish(t(new oc.BRepAlgoAPI_Common_3(solid, tool)));
  }

  if (oc.BRepAlgoAPI_Common_1) {
    const common = t(new oc.BRepAlgoAPI_Common_1());
    if (
      typeof common.SetArguments === "function" &&
      typeof common.SetTools === "function"
    ) {
      common.SetArguments(solid);
      common.SetTools(tool);
    } else if (
      typeof common.AddArgument === "function" &&
      typeof common.AddTool === "function"
    ) {
      common.AddArgument(solid);
      common.AddTool(tool);
    } else {
      throw new Error(
        "opencascade.js: BRepAlgoAPI_Common SetArguments/SetTools not available",
      );
    }
    return finish(common);
  }

  throw new Error("opencascade.js: BRepAlgoAPI_Common API not available");
}

/** 残す側（signedCutDist <= 0）上の参照点 */
function keptSideRefPoint(
  zCut: number,
  tanA: number,
): { x: number; y: number; z: number } {
  const candidates: Array<{ x: number; z: number }> = [
    { x: 0, z: zCut - 10 },
    { x: 0, z: 0 },
    { x: 0, z: Math.max(0, zCut * 0.5) },
    { x: -200, z: zCut },
    { x: 200, z: zCut },
  ];
  for (const { x, z } of candidates) {
    if (signedCutDist({ x, y: 0, z }, zCut, tanA) < -0.1) {
      return { x, y: 0, z };
    }
  }
  throw new Error("Could not locate reference point on kept side of cut plane");
}

/**
 * 回転体ソリッドを z <= z_cut + x·tan(θ) の半空間に切り詰める。
 * MakeHalfSpace の参照点は残す側。Cut ではなく Common で交差する
 * （Cut + 残す側 ref は削る側が残り上側だけになる）。
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function applyStepPlaneCut(
  oc: any,
  solid: any,
  zCut: number,
  angleDeg: number,
  t: <T>(obj: T) => T,
): any {
  const tanA = topCutTanAngle(angleDeg);
  const face = makeCutPlaneFace(oc, zCut, tanA, 500, t);

  const ref = keptSideRefPoint(zCut, tanA);
  const refPt = t(new oc.gp_Pnt_3(ref.x, ref.y, ref.z));
  const halfSolid = makeHalfSpaceSolid(oc, face, refPt, t);

  return booleanCommonSolid(oc, solid, halfSolid, t);
}

/**
 * opencascade.js の WASM インスタンスを lazy-load する。
 * 初回のみロード（~65 MB）、以降はキャッシュを返す。
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getOC(): Promise<any> {
  if (!ocPromise) {
    ocPromise = (async () => {
      // Vite が WASM バイナリを静的アセット URL として扱えるよう ?url で import
      const [glueModule, wasmModule] = await Promise.all([
        import("opencascade.js/dist/opencascade.wasm.js"),
        // @ts-expect-error Vite ?url import
        import("opencascade.js/dist/opencascade.wasm.wasm?url"),
      ]);
      const initOC = glueModule.default ?? glueModule;
      return initOC({
        locateFile: (path: string) => {
          if (path.endsWith(".wasm")) return wasmModule.default;
          return path;
        },
      });
    })();
  }
  return ocPromise;
}

/**
 * Gene から STEP ファイルの Blob を生成する。
 *
 * 1. effectiveProfile(gene) — B3 smoothing spline — で (z, r) を取得
 * 2. r > 0 の区間を BRepBuilderAPI_MakeEdge でエッジ化
 * 3. Z 軸上の閉路（r=0 の端点同士をつなぐ）を加えてワイヤー→フェースを構築
 * 4. BRepPrimAPI_MakeRevol で 360° 回転してソリッド化
 * 5. STEPControl_Writer で STEP Blob に出力
 */
export async function exportGeneToStepBlob(gene: Gene): Promise<Blob> {
  const oc = await getOC();

  const { z, r } = effectiveProfile(gene);

  // ---------- プロファイル点列を収集 ----------
  // r=0 近傍（軸上）の点はスキップし、r > eps の区間のみ使用。
  // 閉じたワイヤーにするため、Z 軸上の上端・下端を明示的に追加する。
  const eps = 1e-6;

  // r > eps のインデックス範囲を求める
  let iStart = 0;
  while (iStart < z.length && r[iStart] <= eps) iStart++;
  let iEnd = z.length - 1;
  while (iEnd >= 0 && r[iEnd] <= eps) iEnd--;

  if (iStart > iEnd) {
    throw new Error("Profile has no non-zero radius — cannot build solid");
  }

  // ---------- 一時オブジェクトを追跡して後で delete ----------
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const temps: any[] = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const t = <T>(obj: T): T => {
    temps.push(obj);
    return obj;
  };

  try {
    // ---------- ワイヤー構築 ----------
    const wireMaker = t(new oc.BRepBuilderAPI_MakeWire_1());

    // (A) 底の軸点 → プロファイル始点
    {
      const pAxis = t(new oc.gp_Pnt_3(0, 0, z[iStart]));
      const pFirst = t(new oc.gp_Pnt_3(r[iStart], 0, z[iStart]));
      const edgeMaker = t(new oc.BRepBuilderAPI_MakeEdge_3(pAxis, pFirst));
      wireMaker.Add_1(edgeMaker.Edge());
    }

    // (B) プロファイル曲線 — B-spline 1 本（失敗時は直線セグメントにフォールバック）
    const { z: zSub, r: rSub } = subsampleProfileUniformZ(z, r, iStart, iEnd);
    const profileEdge = makeProfileSplineEdge(oc, zSub, rSub, t);
    if (profileEdge) {
      wireMaker.Add_1(profileEdge);
    } else {
      for (let i = iStart; i < iEnd; i++) {
        const p0 = t(new oc.gp_Pnt_3(r[i], 0, z[i]));
        const p1 = t(new oc.gp_Pnt_3(r[i + 1], 0, z[i + 1]));
        const edgeMaker = t(new oc.BRepBuilderAPI_MakeEdge_3(p0, p1));
        wireMaker.Add_1(edgeMaker.Edge());
      }
    }

    // (C) プロファイル終点 → 上端の軸点
    {
      const pLast = t(new oc.gp_Pnt_3(r[iEnd], 0, z[iEnd]));
      const pAxis = t(new oc.gp_Pnt_3(0, 0, z[iEnd]));
      const edgeMaker = t(new oc.BRepBuilderAPI_MakeEdge_3(pLast, pAxis));
      wireMaker.Add_1(edgeMaker.Edge());
    }

    // (D) 軸上閉路: 上端軸点 → 底軸点
    if (Math.abs(z[iEnd] - z[iStart]) > eps) {
      const pTop = t(new oc.gp_Pnt_3(0, 0, z[iEnd]));
      const pBot = t(new oc.gp_Pnt_3(0, 0, z[iStart]));
      const edgeMaker = t(new oc.BRepBuilderAPI_MakeEdge_3(pTop, pBot));
      wireMaker.Add_1(edgeMaker.Edge());
    }

    const wire = wireMaker.Wire();

    // ---------- ワイヤー → フェース ----------
    const faceMaker = t(new oc.BRepBuilderAPI_MakeFace_15(wire, true));
    const face = faceMaker.Face();

    // ---------- Z 軸周り 360° 回転 → ソリッド ----------
    const origin = t(new oc.gp_Pnt_3(0, 0, 0));
    const dir = t(new oc.gp_Dir_4(0, 0, 1));
    const axis = t(new oc.gp_Ax1_2(origin, dir));
    const revolMaker = t(
      new oc.BRepPrimAPI_MakeRevol_1(face, axis, 2 * Math.PI, true),
    );
    let solid = revolMaker.Shape();

    const { zCut, tanA } = geneTopCutParams(gene);
    const angleDeg = (Math.atan(tanA) * 180) / Math.PI;
    const revGeom = revolutionGeometryFromGene(gene, 64);
    if (cutWouldChangeMesh(revGeom, zCut, tanA)) {
      solid = applyStepPlaneCut(oc, solid, zCut, angleDeg, t);
    }

    // ---------- STEP 出力 ----------
    // opencascade.js のバージョンによりコンストラクタ名のサフィックスが異なる
    const WriterCtor =
      oc.STEPControl_Writer_1 ?? oc.STEPControl_Writer;
    const writer = t(new WriterCtor());

    // StepModelType enum の取得（バージョンによる差異を吸収）
    const asIs =
      oc.STEPControl_StepModelType?.STEPControl_AsIs ??
      oc.STEPControl_AsIs ??
      0; // fallback: AsIs = 0

    // Transfer — Message_ProgressRange を取らない 2 引数版を使用
    // シグネチャ: Transfer(shape, mode) — opencascade.js 1.x 系で利用可能
    const transferStatus = writer.Transfer(solid, asIs, true);

    // IFSelect_ReturnStatus の取得（バージョン差異を吸収）
    const retDone =
      oc.IFSelect_ReturnStatus?.IFSelect_RetDone ??
      oc.IFSelect_RetDone ??
      1; // fallback: RetDone = 1

    if (transferStatus !== retDone) {
      throw new Error(`STEP Transfer failed (status=${transferStatus})`);
    }

    // Emscripten 仮想FS に書き出す
    // ※ opencascade.js 1.x は C++ 側で文字列エンコーディングが壊れるケースが
    //    あるため、Write 前後の FS ルートを diff して新規ファイルを特定する。
    const beforeFiles: string[] = oc.FS.readdir("/");

    const filename = "output.step";
    const writeStatus = writer.Write(filename);
    if (writeStatus !== retDone) {
      throw new Error(`STEP Write failed (status=${writeStatus})`);
    }

    const afterFiles: string[] = oc.FS.readdir("/");
    const beforeSet = new Set(beforeFiles);
    const newFiles = afterFiles.filter((f: string) => !beforeSet.has(f));

    let writtenFile = newFiles[0];

    if (newFiles.length === 0) {
      // Sometimes the mangled filename is constant and overwrites the previous one.
      // If no new file was created, check if the known mangled name exists.
      if (afterFiles.includes("H𢂋")) {
        writtenFile = "H𢂋";
      } else {
        throw new Error(
          `STEP file not found in virtual FS after Write. ` +
            `Root contents: ${afterFiles.join(", ")}`,
        );
      }
    }

    // Emscripten 仮想FS からファイルを読み出す
    const fileData: Uint8Array = oc.FS.readFile(
      "/" + writtenFile,
      { encoding: "binary" },
    );
    oc.FS.unlink("/" + writtenFile);

    return new Blob([fileData.slice().buffer], {
      type: "application/step",
    });
  } finally {
    // OpenCascade WASM ヒープのリーク防止
    for (const obj of temps) {
      if (obj && typeof obj.delete === "function") {
        try {
          obj.delete();
        } catch {
          // already deleted — ignore
        }
      }
    }
  }
}
