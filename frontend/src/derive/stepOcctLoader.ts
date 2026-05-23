/**
 * opencascade.js WASM の共有ローダ。
 *
 * 役割: STEP エクスポートと診断テストで同一の init 手順を使う。
 * 働き: ブラウザは Vite ?url。vitest のみ動的 import で wasmBinary 直読み（node:fs はバンドルしない）。
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let ocPromise: Promise<any> | null = null;

const isNode =
  typeof process !== "undefined" &&
  typeof process.versions?.node === "string";

async function initInNode(
  initOC: (opts: { wasmBinary: Uint8Array }) => Promise<unknown>,
): Promise<unknown> {
  const { fileURLToPath } = await import("node:url");
  const { dirname, join } = await import("node:path");
  const { readFileSync } = await import("node:fs");
  const here = dirname(fileURLToPath(import.meta.url));
  const wasmPath = join(
    here,
    "../../node_modules/opencascade.js/dist/opencascade.wasm.wasm",
  );
  const wasmBinary = readFileSync(wasmPath);
  return initOC({ wasmBinary });
}

async function initInBrowser(
  initOC: (opts: {
    locateFile: (path: string) => string;
  }) => Promise<unknown>,
): Promise<unknown> {
  const wasmModule = await import(
    // @ts-expect-error Vite ?url import
    "opencascade.js/dist/opencascade.wasm.wasm?url"
  );
  return initOC({
    locateFile: (path: string) => {
      if (path.endsWith(".wasm")) return wasmModule.default;
      return path;
    },
  });
}

/** opencascade.js 1.1.1 インスタンス（stepExporter / 診断で共有） */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function loadOpenCascade(): Promise<any> {
  if (!ocPromise) {
    ocPromise = (async () => {
      const glueModule = await import("opencascade.js/dist/opencascade.wasm.js");
      const initOC = glueModule.default ?? glueModule;
      if (isNode) {
        return initInNode(initOC);
      }
      return initInBrowser(initOC);
    })();
  }
  return ocPromise;
}
