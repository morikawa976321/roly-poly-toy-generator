/**
 * frontend/src/derive/stepExporter.ts を deploy 用に同期（import を @core に差し替え）
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcPath = path.resolve(
  __dirname,
  "../../frontend/src/derive/stepExporter.ts",
);
const outDir = path.resolve(__dirname, "../src/derive");
const outPath = path.join(outDir, "stepExporter.ts");

let content = fs.readFileSync(srcPath, "utf8");
content = content
  .replace(
    'import type { Gene } from "../types";',
    'import type { Gene } from "@core/types";',
  )
  .replace(
    'from "./profileExtension"',
    'from "@core/derive/profileExtension"',
  )
  .replace('from "./meshPlaneCut"', 'from "@core/derive/meshPlaneCut"')
  .replace('from "./mesh"', 'from "@core/derive/mesh"');

const header =
  "/** Auto-synced from frontend/src/derive/stepExporter.ts — npm run sync-core */\n\n";

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(outPath, header + content);
console.log(`Synced ${outPath}`);
