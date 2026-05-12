import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { DesignDetail } from "../types";
import { getDesign } from "../api";
import MetricsPanel from "../components/MetricsPanel";
import ModelViewer from "../components/ModelViewer";
import { thumbnailDataUrl } from "../derive/thumbnailSvg";
import { cappedGeometryFromGene } from "../derive/mesh";
import { exportGeometryToStlBlob } from "../derive/stlExporter";
import { exportGeneToStepBlob } from "../derive/stepExporter";

export default function DetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const [data, setData] = useState<DesignDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stepLoading, setStepLoading] = useState(false);
  const stepBlobUrlRef = useRef<string | null>(null);
  const detailThumbUrl = useMemo(() => {
    if (!data) return "";
    return thumbnailDataUrl(data.gene, data.metrics);
  }, [data]);

  const stlBlobUrl = useMemo(() => {
    if (!data) return "";
    const geom = cappedGeometryFromGene(data.gene, 128);
    const blob = exportGeometryToStlBlob(geom);
    return URL.createObjectURL(blob);
  }, [data]);

  useEffect(() => {
    return () => {
      if (stlBlobUrl) URL.revokeObjectURL(stlBlobUrl);
    };
  }, [stlBlobUrl]);

  // data が変わったら前回の STEP Blob を破棄
  useEffect(() => {
    if (stepBlobUrlRef.current) {
      URL.revokeObjectURL(stepBlobUrlRef.current);
      stepBlobUrlRef.current = null;
    }
  }, [data]);

  const handleStepDownload = useCallback(async () => {
    if (!data) return;
    setStepLoading(true);
    try {
      const blob = await exportGeneToStepBlob(data.gene);
      const url = URL.createObjectURL(blob);
      // 前回分があれば破棄
      if (stepBlobUrlRef.current) URL.revokeObjectURL(stepBlobUrlRef.current);
      stepBlobUrlRef.current = url;
      // プログラムからダウンロードをトリガー
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
  }, [data]);

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

      {!data ? (
        <div className="text-sm text-slate-500">Loading...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <div className="flex items-center justify-end gap-2 mb-2">
              <a
                href={stlBlobUrl}
                download={`${data.design_id}.stl`}
                className="inline-flex items-center rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
              >
                STL出力
              </a>
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
              gene={data.gene}
              centroidZ={data.metrics.centroid_z}
              height={data.metrics.height}
            />
          </div>
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="text-xs text-slate-500 mb-2">Cross-section</div>
              <img
                key={`${data.design_id}:${data.metrics.z_cog_max ?? "na"}`}
                src={detailThumbUrl}
                alt={data.design_id}
                className="w-full"
              />
            </div>
            <MetricsPanel
              metrics={data.metrics}
              designId={data.design_id}
              createdAt={data.created_at}
            />
          </div>
        </div>
      )}
    </div>
  );
}
