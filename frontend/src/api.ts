import type {
  DesignDetail,
  GenerateResponse,
  ListResponse,
} from "./types";
import type { SmoothingMethod } from "./smoothing";
import { withSmoothingQuery } from "./smoothing";

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return (await res.json()) as T;
}

export function listDesigns(
  limit = 200,
  offset = 0,
  smoothing: SmoothingMethod = "bspline",
): Promise<ListResponse> {
  return jsonFetch<ListResponse>(
    withSmoothingQuery(
      `/api/designs?limit=${limit}&offset=${offset}`,
      smoothing,
    ),
  );
}

export function getDesign(
  designId: string,
  smoothing: SmoothingMethod = "bspline",
): Promise<DesignDetail> {
  return jsonFetch<DesignDetail>(
    withSmoothingQuery(`/api/designs/${designId}`, smoothing),
  );
}

export function generateDesigns(
  n?: number,
  parentIds?: string[],
): Promise<GenerateResponse> {
  return jsonFetch<GenerateResponse>(`/api/designs/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...(n ? { n } : {}),
      ...(parentIds && parentIds.length > 0 ? { parent_ids: parentIds } : {}),
    }),
  });
}

export function deleteAllDesigns(): Promise<{ deleted: number }> {
  return jsonFetch<{ deleted: number }>(`/api/designs`, { method: "DELETE" });
}

export function thumbUrl(
  designId: string,
  smoothing: SmoothingMethod = "bspline",
): string {
  return withSmoothingQuery(`/api/designs/${designId}/thumb.svg`, smoothing);
}

export function modelUrl(
  designId: string,
  smoothing: SmoothingMethod = "bspline",
): string {
  return withSmoothingQuery(`/api/designs/${designId}/model.glb`, smoothing);
}

export function stlUrl(
  designId: string,
  smoothing: SmoothingMethod = "bspline",
): string {
  return withSmoothingQuery(`/api/designs/${designId}/model.stl`, smoothing);
}
