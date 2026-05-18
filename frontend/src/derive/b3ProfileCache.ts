/**
 * B3 再フィット済みプロファイル (z,r) のメモリキャッシュ。
 *
 * 役割: effectiveGeneKey 単位で Pyodide 計算結果を共有・購読可能にする。
 * 働き: GalleryPage / DetailPage が subscribe し、ensureB3Profile が set する。effectiveGeneKey でキャッシュを分離。
 */
import type { Gene } from "../types";

export type ProfileSample = { z: number[]; r: number[] };

/** 形状のみ（effectiveGeneKey のベース） */
function baseGeneKey(gene: Gene): string {
  return JSON.stringify({
    version: gene.version,
    N: gene.N,
    height: gene.height,
    bottom_radius: gene.bottom_radius,
    radii: gene.radii,
    z_warp: gene.z_warp ?? null,
  });
}

/**
 * メッシュ用 effective プロファイルのキャッシュキー。
 * プロファイルは「ガウシアン + 延長 → B3 再フィット」まで。カットは mesh の clip のみ。
 */
export function effectiveGeneKey(gene: Gene): string {
  return JSON.stringify({
    ...JSON.parse(baseGeneKey(gene)),
    top_extension_mm: Number(gene.top_extension_mm ?? 0),
  });
}

const cache = new Map<string, ProfileSample>();
let version = 0;
const listeners = new Set<() => void>();

function bump(): void {
  version += 1;
  for (const fn of listeners) fn();
}

export function getEffectiveProfile(gene: Gene): ProfileSample | null {
  return cache.get(effectiveGeneKey(gene)) ?? null;
}

export function setEffectiveProfile(gene: Gene, profile: ProfileSample): void {
  cache.set(effectiveGeneKey(gene), profile);
  bump();
}

export function getB3ProfileCacheVersion(): number {
  return version;
}

export function subscribeB3ProfileCache(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

