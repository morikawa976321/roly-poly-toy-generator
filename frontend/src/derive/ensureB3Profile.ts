/**
 * レガシー母線 + B3 再フィットのオンデマンド確保。
 *
 * 役割: 表示・メッシュ前に effective プロファイルをキャッシュへ投入する。
 * 働き: legacyMeshProfile → b3RefitProfileAsync の inflight 重複排除。initB3Pyodide を re-export。
 */
import type { Gene } from "../types";
import {
  effectiveGeneKey,
  getEffectiveProfile,
  setEffectiveProfile,
} from "./b3ProfileCache";
import { b3RefitProfileAsync, b3RefitSForGene } from "./b3Pyodide";
import { legacyMeshProfile } from "./profileExtension";

const inflight = new Map<string, Promise<void>>();

export { initB3Pyodide } from "./b3Pyodide";

/** レガシー母線 + B3 再フィットをキャッシュ（previewGene 単位） */
export async function ensureEffectiveProfile(gene: Gene): Promise<void> {
  const key = effectiveGeneKey(gene);
  if (getEffectiveProfile(gene)) return;
  let p = inflight.get(key);
  if (!p) {
    p = (async () => {
      const legacy = legacyMeshProfile(gene);
      const s = b3RefitSForGene(legacy.z.length, gene);
      const profile = await b3RefitProfileAsync(legacy.z, legacy.r, s);
      setEffectiveProfile(gene, profile);
    })().finally(() => inflight.delete(key));
    inflight.set(key, p);
  }
  await p;
}

/** @deprecated ensureEffectiveProfile を使用 */
export async function ensureB3BaseProfile(gene: Gene): Promise<void> {
  return ensureEffectiveProfile(gene);
}
