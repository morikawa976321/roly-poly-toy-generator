import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Gene } from "@core/types";
import ModelViewer from "@core/components/ModelViewer";
import { geneWithModifications, computeMetrics } from "@core/derive/metrics";
import { maxTopExtensionMm } from "@core/derive/profileExtension";
import { thumbnailDataUrl } from "@core/derive/thumbnailSvg";
import { exportGeneToStepBlob } from "./derive/stepExporter";
import designData from "./design.json";

type DeployDesign = { design_id: string; gene: Gene };

const PREVIEW_DEBOUNCE_MS = 400;

type PreviewParams = {
  extensionMm: number;
  cutHeightMm: number;
  cutAngleDeg: number;
};

function Panel({
  title,
  children,
  className = "",
  fill = false,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  fill?: boolean;
}) {
  return (
    <section
      className={`flex flex-col rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden ${fill ? "h-full min-h-0" : ""} ${className}`}
    >
      <header className="shrink-0 border-b border-slate-100 bg-slate-50/80 px-4 py-2.5">
        <h2 className="text-sm font-medium text-slate-700">{title}</h2>
      </header>
      <div
        className={
          fill
            ? "flex-1 min-h-0 p-2 flex flex-col"
            : "flex-1 min-h-0 p-4"
        }
      >
        {children}
      </div>
    </section>
  );
}

export default function App() {
  const data = designData as DeployDesign;
  const [error, setError] = useState<string | null>(null);
  const [draftExtensionMm, setDraftExtensionMm] = useState(0);
  const [draftCutHeightMm, setDraftCutHeightMm] = useState(0);
  const [draftCutAngleDeg, setDraftCutAngleDeg] = useState(0);
  const [debouncedPreview, setDebouncedPreview] = useState<PreviewParams>({
    extensionMm: 0,
    cutHeightMm: 0,
    cutAngleDeg: 0,
  });
  const [stepLoading, setStepLoading] = useState(false);
  const stepBlobUrlRef = useRef<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    const params: PreviewParams = {
      extensionMm: maxTopExtensionMm(data.gene),
      cutHeightMm: Number(data.gene.top_cut_height_mm ?? 0),
      cutAngleDeg: Number(data.gene.top_cut_angle_deg ?? 0),
    };
    setDraftExtensionMm(params.extensionMm);
    setDraftCutHeightMm(params.cutHeightMm);
    setDraftCutAngleDeg(params.cutAngleDeg);
    setDebouncedPreview(params);
    setInitialized(true);
  }, [data]);

  useEffect(() => {
    if (!initialized) return;
    const timer = window.setTimeout(() => {
      setDebouncedPreview({
        extensionMm: draftExtensionMm,
        cutHeightMm: draftCutHeightMm,
        cutAngleDeg: draftCutAngleDeg,
      });
    }, PREVIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [initialized, draftExtensionMm, draftCutHeightMm, draftCutAngleDeg]);

  const previewGene = useMemo(() => {
    return geneWithModifications(
      data.gene,
      debouncedPreview.extensionMm,
      debouncedPreview.cutHeightMm,
      debouncedPreview.cutAngleDeg,
    );
  }, [data, debouncedPreview]);

  const maxExtensionMm = useMemo(() => maxTopExtensionMm(data.gene), [data]);

  const profileTopMm = useMemo(() => {
    const m = computeMetrics({
      ...previewGene,
      top_cut_height_mm: 0,
      top_cut_angle_deg: 0,
    });
    return m.height;
  }, [previewGene]);

  const liveMetrics = useMemo(() => computeMetrics(previewGene), [previewGene]);

  const detailThumbUrl = useMemo(
    () => thumbnailDataUrl(previewGene, liveMetrics),
    [previewGene, liveMetrics],
  );

  const handleStepDownload = useCallback(async () => {
    setStepLoading(true);
    setError(null);
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
  }, [data.design_id, previewGene]);

  useEffect(() => {
    return () => {
      if (stepBlobUrlRef.current) URL.revokeObjectURL(stepBlobUrlRef.current);
    };
  }, []);

  if (!initialized) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-slate-500">
        Loading...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 flex flex-col">
      <header className="shrink-0 border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              Roly-Poly Design Viewer
            </h1>
            <p className="text-xs text-slate-500 mt-0.5 font-mono">
              {data.design_id}
            </p>
          </div>
          <button
            type="button"
            onClick={handleStepDownload}
            disabled={stepLoading}
            className="shrink-0 inline-flex items-center rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 disabled:cursor-wait"
          >
            {stepLoading ? "STEP生成中…" : "STEP出力"}
          </button>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-[1600px] px-4 sm:px-6 py-5 min-h-0">
        {error && (
          <div className="mb-4 rounded-lg border border-red-300 bg-red-50 px-4 py-2.5 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(300px,360px)_1fr] gap-5 h-[calc(100vh-5.5rem)] min-h-[640px]">
          <aside className="flex flex-col gap-5 min-h-0 order-2 lg:order-1">
            <Panel title="上部加工" className="shrink-0">
              <div className="space-y-4 -m-1">
                <label className="block text-sm text-slate-700">
                  <span className="font-medium">上部延長量</span>
                  <span className="text-slate-400 ml-1">(mm)</span>
                  <input
                    type="number"
                    min={0}
                    max={maxExtensionMm}
                    step={0.1}
                    value={draftExtensionMm}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      if (!Number.isFinite(v)) return;
                      setDraftExtensionMm(
                        Math.min(maxExtensionMm, Math.max(0, v)),
                      );
                    }}
                    className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200"
                  />
                </label>
                <p className="text-xs text-slate-500 -mt-2">
                  最大 {maxExtensionMm.toFixed(1)} mm（上端が尖るまで）
                </p>

                <label className="block text-sm text-slate-700">
                  <span className="font-medium">カット平面の高さ</span>
                  <span className="text-slate-400 ml-1">(mm)</span>
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
                    className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200"
                  />
                </label>
                <p className="text-xs text-slate-500 -mt-2">
                  z 軸上の交点。延長のみの上端 ≈ {profileTopMm.toFixed(1)} mm
                </p>

                <label className="block text-sm text-slate-700">
                  <span className="font-medium">カット平面の傾き</span>
                  <span className="text-slate-400 ml-1">(°)</span>
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
                    className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200"
                  />
                </label>
                <p className="text-xs text-slate-500 -mt-2">
                  0° = 水平。正の値で外側（縁）ほど残す高さが高くなります。
                </p>
              </div>
            </Panel>

            <Panel title="平面図" className="flex-1 min-h-[240px]">
              <div className="h-full min-h-[200px] flex items-center justify-center bg-slate-50 rounded-lg border border-slate-100 p-2 -m-1">
                <img
                  key={`${data.design_id}:${liveMetrics.z_cog_max ?? "na"}:${debouncedPreview.extensionMm}:${debouncedPreview.cutHeightMm}:${debouncedPreview.cutAngleDeg}`}
                  src={detailThumbUrl}
                  alt="断面図"
                  className="max-h-full max-w-full w-auto object-contain"
                />
              </div>
            </Panel>
          </aside>

          <Panel
            title="3Dプレビュー"
            fill
            className="min-h-[min(72vh,820px)] lg:min-h-0 lg:h-full order-1 lg:order-2"
          >
            <ModelViewer
              gene={previewGene}
              centroidZ={liveMetrics.centroid_z}
              height={liveMetrics.height}
              className="flex-1 w-full min-h-0 h-full rounded-lg border border-slate-100 bg-slate-50 overflow-hidden"
            />
          </Panel>
        </div>
      </main>
    </div>
  );
}
