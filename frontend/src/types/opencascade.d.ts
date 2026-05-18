/**
 * opencascade.js / WASM モジュールの型宣言。
 *
 * 役割: STEP エクスポート用 WASM パッケージの import 型補完。
 * 働き: stepExporter の dynamic import に対し initOpenCascade の戻り値型を緩く定義する。
 */
declare module "opencascade.js" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const initOpenCascade: (...args: any[]) => Promise<any>;
  export default initOpenCascade;
  export { initOpenCascade };
}

declare module "opencascade.js/dist/opencascade.wasm.js" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const initOpenCascade: (...args: any[]) => Promise<any>;
  export default initOpenCascade;
}
