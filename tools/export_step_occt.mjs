/**
 * (z, r) プロファイルから opencascade.js で STEP を書き出す（CLI, Node ESM）。
 *
 * 役割: ブラウザ外（Node）での STEP 検証・バッチ出力。
 * 働き: export_step_variants.py から profiles JSON を受け取り OCCT で回転体を構築して .step を書く。
 *   使い方: node tools/export_step_occt.mjs <profiles.json> <methodKey> <out.step>
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WASM_JS = pathToFileURL(
  resolve(REPO_ROOT, "frontend/node_modules/opencascade.js/dist/opencascade.wasm.js"),
).href;
const WASM_BIN = resolve(
  REPO_ROOT,
  "frontend/node_modules/opencascade.js/dist/opencascade.wasm.wasm",
);

const STEP_PROFILE_MAX_POINTS = 96;

function ocCtor(oc, base, prefer = []) {
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

function subsampleProfileUniformZ(z, r, iStart, iEnd, maxPoints = STEP_PROFILE_MAX_POINTS) {
  if (iEnd <= iStart) return { z: [], r: [] };
  const nSeg = iEnd - iStart;
  if (nSeg + 1 <= maxPoints) {
    const zz = [];
    const rr = [];
    for (let i = iStart; i <= iEnd; i++) {
      zz.push(z[i]);
      rr.push(r[i]);
    }
    return { z: zz, r: rr };
  }
  const z0 = z[iStart];
  const z1 = z[iEnd];
  const target = Math.max(4, maxPoints);
  const zz = [];
  const rr = [];
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

function makeHPointArray(oc, z, r, t) {
  const n = z.length;
  const HArrayCtor = ocCtor(oc, "TColgp_HArray1OfPnt", [2, 1]);
  if (!HArrayCtor) throw new Error("TColgp_HArray1OfPnt not available");
  const arr = t(new HArrayCtor(1, n));
  const setValue =
    typeof arr.SetValue === "function"
      ? (idx, p) => arr.SetValue(idx, p)
      : (idx, p) => arr.setValue(idx, p);
  for (let i = 0; i < n; i++) {
    setValue(i + 1, t(new oc.gp_Pnt_3(r[i], 0, z[i])));
  }
  return arr;
}

function makeProfileSplineEdge(oc, z, r, t) {
  if (z.length < 2 || z.length !== r.length) return null;
  try {
    const hPoints = makeHPointArray(oc, z, r, t);
    const InterpCtor = ocCtor(oc, "GeomAPI_Interpolate", [1, 2]);
    if (!InterpCtor) return null;
    const interp = t(new InterpCtor(hPoints, false, 1e-3));
    if (typeof interp.Perform === "function") interp.Perform();
    else if (typeof interp.perform === "function") interp.perform();
    if (typeof interp.IsDone === "function" && !interp.IsDone()) return null;
    const curve =
      typeof interp.Curve === "function"
        ? interp.Curve()
        : typeof interp.curve === "function"
          ? interp.curve()
          : null;
    if (!curve) return null;
    for (const idx of [24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8]) {
      const EdgeCtor = oc[`BRepBuilderAPI_MakeEdge_${idx}`];
      if (typeof EdgeCtor !== "function") continue;
      try {
        const mk = t(new EdgeCtor(curve));
        if (typeof mk.IsDone === "function" && !mk.IsDone()) continue;
        return mk.Edge();
      } catch {
        try {
          const mk = t(new EdgeCtor(curve, 0, 1));
          if (typeof mk.IsDone === "function" && !mk.IsDone()) continue;
          return mk.Edge();
        } catch {
          /* next */
        }
      }
    }
    return null;
  } catch {
    return null;
  }
}

function buildSolidFromProfile(oc, z, r, t) {
  const eps = 1e-6;
  let iStart = 0;
  while (iStart < z.length && r[iStart] <= eps) iStart++;
  let iEnd = z.length - 1;
  while (iEnd >= 0 && r[iEnd] <= eps) iEnd--;
  if (iStart > iEnd) throw new Error("Profile has no non-zero radius");

  const wireMaker = t(new oc.BRepBuilderAPI_MakeWire_1());

  {
    const pAxis = t(new oc.gp_Pnt_3(0, 0, z[iStart]));
    const pFirst = t(new oc.gp_Pnt_3(r[iStart], 0, z[iStart]));
    wireMaker.Add_1(t(new oc.BRepBuilderAPI_MakeEdge_3(pAxis, pFirst)).Edge());
  }

  const { z: zSub, r: rSub } = subsampleProfileUniformZ(z, r, iStart, iEnd);
  const profileEdge = makeProfileSplineEdge(oc, zSub, rSub, t);
  if (profileEdge) {
    wireMaker.Add_1(profileEdge);
  } else {
    for (let i = iStart; i < iEnd; i++) {
      const p0 = t(new oc.gp_Pnt_3(r[i], 0, z[i]));
      const p1 = t(new oc.gp_Pnt_3(r[i + 1], 0, z[i + 1]));
      wireMaker.Add_1(t(new oc.BRepBuilderAPI_MakeEdge_3(p0, p1)).Edge());
    }
  }

  {
    const pLast = t(new oc.gp_Pnt_3(r[iEnd], 0, z[iEnd]));
    const pAxis = t(new oc.gp_Pnt_3(0, 0, z[iEnd]));
    wireMaker.Add_1(t(new oc.BRepBuilderAPI_MakeEdge_3(pLast, pAxis)).Edge());
  }

  if (Math.abs(z[iEnd] - z[iStart]) > eps) {
    const pTop = t(new oc.gp_Pnt_3(0, 0, z[iEnd]));
    const pBot = t(new oc.gp_Pnt_3(0, 0, z[iStart]));
    wireMaker.Add_1(t(new oc.BRepBuilderAPI_MakeEdge_3(pTop, pBot)).Edge());
  }

  const wire = wireMaker.Wire();
  const MakeFaceCtor = oc.BRepBuilderAPI_MakeFace_15 ?? oc.BRepBuilderAPI_MakeFace_1;
  const face = t(new MakeFaceCtor(wire, true)).Face();

  const origin = t(new oc.gp_Pnt_3(0, 0, 0));
  const dir = t(new oc.gp_Dir_4(0, 0, 1));
  const axis = t(new oc.gp_Ax1_2(origin, dir));
  return t(new oc.BRepPrimAPI_MakeRevol_1(face, axis, 2 * Math.PI, true)).Shape();
}

function writeStepFile(oc, solid, outPath, t) {
  const WriterCtor = oc.STEPControl_Writer_1 ?? oc.STEPControl_Writer;
  const writer = t(new WriterCtor());
  const asIs = oc.STEPControl_StepModelType?.STEPControl_AsIs ?? oc.STEPControl_AsIs ?? 0;
  const retDone = oc.IFSelect_ReturnStatus?.IFSelect_RetDone ?? oc.IFSelect_RetDone ?? 1;

  const transferStatus = writer.Transfer(solid, asIs, true);
  if (transferStatus !== retDone) {
    throw new Error(`STEP Transfer failed (status=${transferStatus})`);
  }

  const beforeFiles = oc.FS.readdir("/");
  const writeStatus = writer.Write("out.step");
  if (writeStatus !== retDone) {
    throw new Error(`STEP Write failed (status=${writeStatus})`);
  }

  const afterFiles = oc.FS.readdir("/");
  const beforeSet = new Set(beforeFiles);
  let writtenFile = afterFiles.find((f) => !beforeSet.has(f));
  if (!writtenFile && afterFiles.includes("H𢂋")) writtenFile = "H𢂋";
  if (!writtenFile) {
    throw new Error(`STEP not found in FS. Root: ${afterFiles.join(", ")}`);
  }

  const data = oc.FS.readFile("/" + writtenFile, { encoding: "binary" });
  oc.FS.unlink("/" + writtenFile);
  writeFileSync(outPath, Buffer.from(data));
}

async function getOC() {
  const glue = await import(WASM_JS);
  const init = glue.default ?? glue;
  const wasmBinary = readFileSync(WASM_BIN);
  return init({
    wasmBinary,
    locateFile: (p) => (p.endsWith(".wasm") ? WASM_BIN : p),
  });
}

async function main() {
  const [profilesPath, methodKey, outPath] = process.argv.slice(2);
  if (!profilesPath || !methodKey || !outPath) {
    console.error(
      "Usage: node tools/export_step_occt.mjs <profiles.json> <methodKey> <out.step>",
    );
    process.exit(1);
  }

  const all = JSON.parse(readFileSync(profilesPath, "utf8"));
  const entry = all[methodKey];
  if (!entry) {
    throw new Error(
      `Unknown method key: ${methodKey}. Keys: ${Object.keys(all).join(", ")}`,
    );
  }

  const { z, r } = entry;
  const oc = await getOC();
  const temps = [];
  const t = (obj) => {
    temps.push(obj);
    return obj;
  };

  try {
    const solid = buildSolidFromProfile(oc, z, r, t);
    writeStepFile(oc, solid, resolve(outPath), t);
    console.log(`Wrote ${outPath} (${methodKey}, ${z.length} profile points)`);
  } finally {
    for (const obj of temps) {
      if (obj && typeof obj.delete === "function") {
        try {
          obj.delete();
        } catch {
          /* ignore */
        }
      }
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
