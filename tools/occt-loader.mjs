/**
 * Node 用 opencascade.js ローダフック。
 *
 * 役割: export_step_occt.mjs 実行時の WASM モジュール読み込み補助。
 * 働き: occt-register 経由で register され、opencascade.wasm.js に __dirname を注入する。
 */
import { fileURLToPath } from "node:url";

export async function load(url, context, nextLoad) {
  const result = await nextLoad(url, context, nextLoad);
  if (!url.includes("opencascade.wasm.js")) {
    return result;
  }
  const ocDir = fileURLToPath(new URL(".", url));
  return {
    format: result.format,
    source: `const __dirname = ${JSON.stringify(ocDir)};\n${result.source}`,
    shortCircuit: true,
  };
}
