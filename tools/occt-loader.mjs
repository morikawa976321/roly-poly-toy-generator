/** opencascade.wasm.js が ESM で __dirname を参照するため、読み込み時に注入する */
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
