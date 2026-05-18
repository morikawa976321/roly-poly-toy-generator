/**
 * 設計メトリクスの表示パネル。
 *
 * 役割: 詳細画面での数値一覧 UI。
 * 働き: DetailPage から metrics / design_id / created_at を受け取り体積・寸法・重心等を表形式で表示する。
 */
import type { Metrics } from "../types";

type Props = { metrics: Metrics; designId: string; createdAt: string };

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1 border-b border-slate-100 last:border-b-0">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

export default function MetricsPanel({ metrics, designId, createdAt }: Props) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
      <Row label="design_id" value={designId} />
      <Row label="volume (mm³)" value={metrics.volume.toFixed(2)} />
      <Row label="height (mm)" value={metrics.height.toFixed(3)} />
      <Row label="max width (mm)" value={metrics.max_width.toFixed(3)} />
      <Row label="centroid_z (mm)" value={metrics.centroid_z.toFixed(3)} />
      <Row
        label="bottom_curvature_radius (mm)"
        value={
          metrics.bottom_curvature_radius == null
            ? "na"
            : metrics.bottom_curvature_radius.toFixed(3)
        }
      />
      <Row
        label="z_cog_max (mm)"
        value={metrics.z_cog_max == null ? "na" : metrics.z_cog_max.toFixed(3)}
      />
      <Row label="created_at" value={createdAt} />
    </div>
  );
}
