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
