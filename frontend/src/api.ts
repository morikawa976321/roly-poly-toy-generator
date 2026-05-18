/**
 * バックエンド REST API クライアント。
 *
 * 役割: /api/* への fetch ラッパと型付きレスポンス。
 * 働き: GalleryPage・DetailPage などから list/get/patch/generate/delete/exit を呼ぶ。エラー時は HTTP ステータス付き Error を投げる。
 */
import type {
  DesignDetail,
  GenerateResponse,
  ListResponse,
} from "./types";

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
): Promise<ListResponse> {
  return jsonFetch<ListResponse>(
    `/api/designs?limit=${limit}&offset=${offset}`,
  );
}

export function getDesign(
  designId: string,
): Promise<DesignDetail> {
  return jsonFetch<DesignDetail>(
    `/api/designs/${designId}`,
  );
}

type PatchDesignPayload = {
  top_extension_mm: number;
  top_cut_height_mm: number;
  top_cut_angle_deg: number;
};

export function patchDesign(
  designId: string,
  payload: PatchDesignPayload,
): Promise<DesignDetail> {
  return jsonFetch<DesignDetail>(`/api/designs/${designId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
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

export function exitApp(): Promise<{ status: string }> {
  return jsonFetch<{ status: string }>(`/api/app/exit`, { method: "POST" });
}
