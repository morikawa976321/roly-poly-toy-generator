/**
 * API スキーマ由来の共有型（再 export）。
 *
 * 役割: OpenAPI 生成型をアプリ全体の単一 import 先にする。
 * 働き: generated/api-schema の components["schemas"] を Gene / Metrics / DesignDetail 等として再 export。既存 import パス互換のための薄い層。
 */
import type { components } from "./generated/api-schema";

type Schemas = components["schemas"];

export type Gene = Schemas["Gene"];
export type Metrics = Schemas["Metrics"];
export type DesignSummary = Schemas["DesignSummary"];
export type DesignDetail = Schemas["DesignDetail"];
export type ListResponse = Schemas["ListResponse"];
export type GenerateResponse = Schemas["GenerateResponse"];
export type PatchDesignRequest = Schemas["PatchDesignRequest"];
