import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { DesignDetail } from "../types";
import { getDesign, modelUrl, stlUrl, thumbUrl } from "../api";
import MetricsPanel from "../components/MetricsPanel";
import ModelViewer from "../components/ModelViewer";
import { useSmoothing } from "../smoothing";

export default function DetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const { smoothing } = useSmoothing();
  const [data, setData] = useState<DesignDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const detailThumbUrl = useMemo(() => {
    if (!data) return "";
    const base = thumbUrl(data.design_id, smoothing);
    const sep = base.includes("?") ? "&" : "?";
    // 詳細ビューはキャッシュを掴みやすいので、切替時に必ず再取得させる。
    return `${base}${sep}view=detail&s=${smoothing}&zmax=${data.metrics.z_cog_max ?? "na"}`;
  }, [data, smoothing]);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    getDesign(id, smoothing)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [id, smoothing]);

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
            <div className="flex items-center justify-end mb-2">
              <a
                href={stlUrl(data.design_id, smoothing)}
                download={`${data.design_id}.stl`}
                className="inline-flex items-center rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
              >
                STL出力
              </a>
            </div>
            <ModelViewer
              modelUrl={modelUrl(data.design_id, smoothing)}
              centroidZ={data.metrics.centroid_z}
              height={data.metrics.height}
            />
          </div>
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="text-xs text-slate-500 mb-2">Cross-section</div>
              <img
                key={`${data.design_id}:${smoothing}:${data.metrics.z_cog_max ?? "na"}`}
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
