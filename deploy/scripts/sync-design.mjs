/**
 * リファレンスデザインを deploy 用 JSON に同期。
 *
 * 役割: Vercel 静的ビューアへの埋め込みデータ生成。
 * 働き: docs/designs/6d7afe17fed27c7c/dump.json を deploy/src/design.json に書き出す。
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dumpPath = path.resolve(
  __dirname,
  "../../docs/designs/6d7afe17fed27c7c/dump.json",
);
const outPath = path.resolve(__dirname, "../src/design.json");

const dump = JSON.parse(fs.readFileSync(dumpPath, "utf8"));
const gene = {
  ...dump.gene,
  top_extension_mm: dump.gene.top_extension_mm ?? 0,
  top_cut_height_mm: dump.gene.top_cut_height_mm ?? 0,
  top_cut_angle_deg: dump.gene.top_cut_angle_deg ?? 0,
};
const design = {
  design_id: dump.design_id,
  gene,
};
fs.writeFileSync(outPath, `${JSON.stringify(design, null, 2)}\n`);
console.log(`Wrote ${outPath}`);
