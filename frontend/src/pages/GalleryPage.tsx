import { useCallback, useEffect, useState } from "react";
import type { DesignSummary } from "../types";
import { deleteAllDesigns, generateDesigns, listDesigns } from "../api";
import DesignCard from "../components/DesignCard";

export default function GalleryPage() {
  const [designs, setDesigns] = useState<DesignSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [deletingAll, setDeletingAll] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listDesigns(200, 0);
      setDesigns(res.designs);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const toggleSelect = (designId: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(designId)) return prev.filter((id) => id !== designId);
      if (prev.length >= 4) return prev;
      return [...prev, designId];
    });
  };

  const onGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      await generateDesigns(12, selectedIds);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  };

  const onDeleteAllConfirmed = async () => {
    setDeletingAll(true);
    setError(null);
    try {
      await deleteAllDesigns();
      setConfirmOpen(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingAll(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-slate-600">
          {loading ? "Loading..." : `${designs.length} designs`}
        </div>
        <div className="flex items-center gap-2">
          {selectedIds.length > 0 && (
            <button
              type="button"
              onClick={() => setSelectedIds([])}
              disabled={generating || deletingAll}
              className="inline-flex items-center rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              選択解除（{selectedIds.length}）
            </button>
          )}
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            disabled={designs.length === 0 || loading || generating || deletingAll}
            className="inline-flex items-center rounded-md border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            一括削除
          </button>
          <button
            type="button"
            onClick={onGenerate}
            disabled={generating || deletingAll}
            className="inline-flex items-center rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {generating
              ? "生成中..."
              : selectedIds.length > 0
                ? `選択（${selectedIds.length}）から12個生成`
                : "12個追加生成"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {designs.length === 0 && !loading ? (
        <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
          まだデザインがありません。<span className="font-medium">12個追加生成</span>をクリックして開始してください。
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {designs.map((d) => (
            <DesignCard
              key={d.design_id}
              design={d}
              selected={selectedIds.includes(d.design_id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </div>
      )}

      {confirmOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/30"
            onClick={() => !deletingAll && setConfirmOpen(false)}
            aria-label="Close"
          />
          <div className="relative w-full max-w-md rounded-lg border border-slate-200 bg-white shadow-lg">
            <div className="p-4">
              <div className="text-base font-semibold text-slate-900">
                すべて削除しますか？
              </div>
              <div className="mt-2 text-sm text-slate-600">
                {designs.length}件のデザイン（保存済みサムネイル・モデルを含む）を完全に削除します。
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-slate-200 p-3">
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                disabled={deletingAll}
                className="inline-flex items-center rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                キャンセル
              </button>
              <button
                type="button"
                onClick={onDeleteAllConfirmed}
                disabled={deletingAll}
                className="inline-flex items-center rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deletingAll ? "削除中..." : "削除する"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
