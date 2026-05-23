/**
 * frontend derive の STEP モジュールを deploy 向けに同期。
 *
 * 役割: deploy/src/derive のソース更新（sync-core npm script）。
 * 働き: stepExporter / stepProfile をコピーし import を @core に差し替え、Auto-synced ヘッダを付与する。
 * stepOcctLoader は deploy 同梱せず @core/derive へ解決する。
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDerive = path.resolve(__dirname, "../../frontend/src/derive");
const outDir = path.resolve(__dirname, "../src/derive");

const header =
  "/** Auto-synced from frontend/src/derive — npm run sync-core */\n\n";

function rewriteCoreImports(content) {
  return content
    .replace(
      'import type { Gene } from "../types";',
      'import type { Gene } from "@core/types";',
    )
    .replace(
      'from "./profileExtension"',
      'from "@core/derive/profileExtension"',
    )
    .replace('from "./meshPlaneCut"', 'from "@core/derive/meshPlaneCut"')
    .replace('from "./mesh"', 'from "@core/derive/mesh"')
    .replace(
      'from "./stepOcctLoader"',
      'from "@core/derive/stepOcctLoader"',
    );
}

fs.mkdirSync(outDir, { recursive: true });

for (const name of ["stepExporter.ts", "stepProfile.ts"]) {
  const srcPath = path.join(frontendDerive, name);
  const outPath = path.join(outDir, name);
  let content = fs.readFileSync(srcPath, "utf8");
  if (name === "stepExporter.ts") {
    content = rewriteCoreImports(content);
  }
  fs.writeFileSync(outPath, header + content);
  console.log(`Synced ${outPath}`);
}
