import { Link } from "react-router-dom";
import type { DesignSummary } from "../types";
import { thumbnailDataUrl } from "../derive/thumbnailSvg";

type Props = {
  design: DesignSummary;
  selected?: boolean;
  onToggleSelect?: (designId: string) => void;
};

export default function DesignCard({ design, selected, onToggleSelect }: Props) {
  const { design_id, gene, metrics } = design;
  return (
    <Link
      to={`/designs/${design_id}`}
      className={[
        "group block rounded-lg border bg-white overflow-hidden hover:shadow-sm transition relative",
        selected ? "border-slate-900 ring-2 ring-slate-900/20" : "border-slate-200 hover:border-slate-400",
      ].join(" ")}
    >
      {onToggleSelect && (
        <button
          type="button"
          aria-pressed={!!selected}
          aria-label={selected ? "選択解除" : "選択"}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onToggleSelect(design_id);
          }}
          className={[
            "absolute left-2 top-2 z-10 inline-flex items-center justify-center rounded-md border px-2 py-1 text-xs font-medium shadow-sm",
            selected
              ? "border-slate-900 bg-slate-900 text-white"
              : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
          ].join(" ")}
        >
          {selected ? "選択中" : "選択"}
        </button>
      )}
      <div className="aspect-square bg-slate-100 flex items-center justify-center">
        <img
          src={thumbnailDataUrl(gene, metrics)}
          alt={design_id}
          className="max-h-full max-w-full p-2"
        />
      </div>
      <div className="px-3 py-2 text-xs text-slate-600 border-t border-slate-200">
        <div className="font-mono truncate">{design_id}</div>
        <div className="flex justify-between mt-1">
          <span>H {metrics.height.toFixed(1)}</span>
          <span>W {metrics.max_width.toFixed(1)}</span>
          <span>V {Math.round(metrics.volume).toLocaleString()}</span>
        </div>
      </div>
    </Link>
  );
}
