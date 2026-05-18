/**
 * Node カスタムローダ登録のエントリ。
 *
 * 役割: export_step_occt.mjs 起動前の OCCT WASM 用フック登録。
 * 働き: node --import tools/occt-register.mjs で occt-loader.mjs を module loader に登録する。
 */
import { register } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
register(pathToFileURL(resolve(here, "occt-loader.mjs")).href);
