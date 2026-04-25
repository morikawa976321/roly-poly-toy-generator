// OpenAPI を単一ソースにし、型は生成物から参照する。
// 既存 import の互換のため、このファイルは再export専用にしている。
import type { components } from "./generated/api-schema";

type Schemas = components["schemas"];

export type Gene = Schemas["Gene"];
export type Metrics = Schemas["Metrics"];
export type DesignSummary = Schemas["DesignSummary"];
export type DesignDetail = Schemas["DesignDetail"];
export type ListResponse = Schemas["ListResponse"];
export type GenerateResponse = Schemas["GenerateResponse"];
