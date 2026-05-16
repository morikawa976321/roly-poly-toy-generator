import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { DesignDetail } from "../types";
import { getDesign, patchDesign } from "../api";
import MetricsPanel from "../components/MetricsPanel";
import ModelViewer from "../components/ModelViewer";
import { geneWithModifications, computeMetrics } from "../derive/metrics";
import { maxTopExtensionMm } from "../derive/profileExtension";
import { thumbnailDataUrl } from "../derive/thumbnailSvg";
import { exportGeneToStepBlob } from "../derive/stepExporter";

const PREVIEW_DEBOUNCE_MS = 400;

type PreviewParams = {
  extensionMm: number;
  cutHeightMm: number;
  cutAngleDeg: number;
};

export default function DetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const [data, setData] = useState<DesignDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftExtensionMm, setDraftExtensionMm] = useState(0);
  const [draftCutHeightMm, setDraftCutHeightMm] = useState(0);
  const [draftCutAngleDeg, setDraftCutAngleDeg] = useState(0);
  const [debouncedPreview, setDebouncedPreview] = useState<PreviewParams>({
    extensionMm: 0,
    cutHeightMm: 0,
    cutAngleDeg: 0,
  });
  const [saving, setSaving] = useState(false);
  const [stepLoading, setStepLoading] = useState(false);
  const stepBlobUrlRef = useRef<string | null>(null);
  const initExtensionForDesignRef = useRef<string | null>(null);

  useEffect(() => {
    if (!data) return;
    const useMaxDefault = initExtensionForDesignRef.current !== data.design_id;
    initExtensionForDesignRef.current = data.design_id;
    const params: PreviewParams = {
      extensionMm: useMaxDefault
        ? maxTopExtensionMm(data.gene)
        : Number(data.gene.top_extension_mm ?? 0),
      cutHeightMm: Number(data.gene.top_cut_height_mm ?? 0),
      cutAngleDeg: Number(data.gene.top_cut_angle_deg ?? 0),
    };
    setDraftExtensionMm(params.extensionMm);
    setDraftCutHeightMm(params.cutHeightMm);
    setDraftCutAngleDeg(params.cutAngleDeg);
    setDebouncedPreview(params);
  }, [data]);

  useEffect(() => {
    if (!data) return;
    const timer = window.setTimeout(() => {
      setDebouncedPreview({
        extensionMm: draftExtensionMm,
        cutHeightMm: draftCutHeightMm,
        cutAngleDeg: draftCutAngleDeg,
      });
    }, PREVIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [data, draftExtensionMm, draftCutHeightMm, draftCutAngleDeg]);

  const previewGene = useMemo(() => {
    if (!data) return null;
    return geneWithModifications(
      data.gene,
      debouncedPreview.extensionMm,
      debouncedPreview.cutHeightMm,
      debouncedPreview.cutAngleDeg,
    );
  }, [data, debouncedPreview]);

  const maxExtensionMm = useMemo(() => {
    if (!data) return 0;
    return maxTopExtensionMm(data.gene);
  }, [data]);

  const profileTopMm = useMemo(() => {
    if (!previewGene) return 0;
    const m = computeMetrics({
      ...previewGene,
      top_cut_height_mm: 0,
      top_cut_angle_deg: 0,
    });
    return m.height;
  }, [previewGene]);

  const liveMetrics = useMemo(() => {
    if (!previewGene) return null;
    return computeMetrics(previewGene);
  }, [previewGene]);

  const detailThumbUrl = useMemo(() => {
    if (!previewGene || !liveMetrics) return "";
    return thumbnailDataUrl(previewGene, liveMetrics);
  }, [previewGene, liveMetrics]);

  useEffect(() => {
    if (stepBlobUrlRef.current) {
      URL.revokeObjectURL(stepBlobUrlRef.current);
      stepBlobUrlRef.current = null;
    }
  }, [data]);

  const handleStepDownload = useCallback(async () => {
    if (!data || !previewGene) return;
    setStepLoading(true);
    try {
      const blob = await exportGeneToStepBlob(previewGene);
      const url = URL.createObjectURL(blob);
      if (stepBlobUrlRef.current) URL.revokeObjectURL(stepBlobUrlRef.current);
      stepBlobUrlRef.current = url;
      const a = document.createElement("a");
      a.href = url;
      a.download = `${data.design_id}.step`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (e) {
      setError(
        `STEP export failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    } finally {
      setStepLoading(false);
    }
  }, [data, previewGene]);

  const handleSave = useCallback(async () => {
    if (!data) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await patchDesign(data.design_id, {
        top_extension_mm: draftExtensionMm,
        top_cut_height_mm: draftCutHeightMm,
        top_cut_angle_deg: draftCutAngleDeg,
      });
      setData(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [data, draftExtensionMm, draftCutHeightMm, draftCutAngleDeg]);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    getDesign(id)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const savedExtension = data ? Number(data.gene.top_extension_mm ?? 0) : 0;
  const savedCutHeight = data ? Number(data.gene.top_cut_height_mm ?? 0) : 0;
  const savedCutAngle = data ? Number(data.gene.top_cut_angle_deg ?? 0) : 0;
  const dirty =
    data != null &&
    (Math.abs(draftExtensionMm - savedExtension) > 1e-6 ||
      Math.abs(draftCutHeightMm - savedCutHeight) > 1e-6 ||
      Math.abs(draftCutAngleDeg - savedCutAngle) > 1e-6);

  return (
    <div>
      <div className="mb-4">
        <Link to="/" className="text-sm text-slate-600 hover:underline">
          &larr; Back to gallery
        </Link>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {!data || !previewGene || !liveMetrics ? (
        <div className="text-sm text-slate-500">Loading...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <div className="flex items-center justify-end gap-2 mb-2">
              <button
                type="button"
                onClick={handleStepDownload}
                disabled={stepLoading}
                className="inline-flex items-center rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 disabled:cursor-wait"
              >
                {stepLoading ? "STEP生成中…" : "STEP出力"}
              </button>
            </div>
            <ModelViewer
              gene={previewGene}
              centroidZ={liveMetrics.centroid_z}
              height={liveMetrics.height}
            />
          </div>
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-white p-3 space-y-3">
              <div className="text-xs text-slate-500">上部加工</div>
              <label className="block text-sm text-slate-700">
                上部延長量 (mm)
                <input
                  type="number"
                  min={0}
                  max={maxExtensionMm}
                  step={0.1}
                  value={draftExtensionMm}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    if (!Number.isFinite(v)) return;
                    setDraftExtensionMm(Math.min(maxExtensionMm, Math.max(0, v)));
                  }}
                  className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                />
              </label>
              <p className="text-xs text-slate-500">
                最大 {maxExtensionMm.toFixed(1)} mm（上端が尖るまで）
              </p>
              <label className="block text-sm text-slate-700">
                カット平面の高さ (mm)
                <input
                  type="number"
                  min={0}
                  max={Math.max(profileTopMm, liveMetrics.height)}
                  step={0.1}
                  value={draftCutHeightMm}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    if (!Number.isFinite(v)) return;
                    setDraftCutHeightMm(Math.max(0, v));
                  }}
                  className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                />
              </label>
              <p className="text-xs text-slate-500">
                z 軸上の交点。延長のみの上端 ≈ {profileTopMm.toFixed(1)} mm
              </p>
              <label className="block text-sm text-slate-700">
                カット平面の傾き (°)
                <input
                  type="number"
                  min={-89}
                  max={89}
                  step={0.1}
                  value={draftCutAngleDeg}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    if (!Number.isFinite(v)) return;
                    setDraftCutAngleDeg(Math.min(89, Math.max(-89, v)));
                  }}
                  className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                />
              </label>
              <p className="text-xs text-slate-500">
                0° = 水平。正の値で外側（縁）ほど残す高さが高くなります。
              </p>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving || !dirty}
                className={`w-full rounded-md px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed ${
                  dirty ? "bg-blue-600 hover:bg-blue-500" : "bg-slate-400"
                }`}
              >
                {saving ? "保存中…" : "保存"}
              </button>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="text-xs text-slate-500 mb-2">Cross-section</div>
              <img
                key={`${data.design_id}:${liveMetrics.z_cog_max ?? "na"}:${debouncedPreview.extensionMm}:${debouncedPreview.cutHeightMm}:${debouncedPreview.cutAngleDeg}`}
                src={detailThumbUrl}
                alt={data.design_id}
                className="w-full"
              />
            </div>
            <MetricsPanel
              metrics={liveMetrics}
              designId={data.design_id}
              createdAt={data.created_at}
            />
          </div>
        </div>
      )}
    </div>
  );
}
