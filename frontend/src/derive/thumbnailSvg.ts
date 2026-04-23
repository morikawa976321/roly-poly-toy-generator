import type { Gene, Metrics } from "../types";
import { smoothProfile } from "./smoothing";

// backend/app/thumbnail.py::render_thumbnail_svg の TS ポート
export function thumbnailSvg(gene: Gene, metrics: Metrics): string {
  const { z, r } = smoothProfile(gene);
  const height = Number(gene.height);
  let maxR = 0;
  for (const v of r) maxR = Math.max(maxR, v);

  // 右側を下→上、左側（符号反転）を上→下で閉じる
  const xs: number[] = [];
  const zs: number[] = [];
  for (let i = 0; i < r.length; i++) {
    xs.push(r[i]);
    zs.push(z[i]);
  }
  for (let i = r.length - 1; i >= 0; i--) {
    xs.push(-r[i]);
    zs.push(z[i]);
  }

  // svg座標: y = height - z
  const pts: Array<[number, number]> = [];
  for (let i = 0; i < xs.length; i++) {
    pts.push([xs[i], height - zs[i]]);
  }

  const pad = Math.max(2.0, 0.05 * Math.max(height, maxR * 2.0));
  const viewX = -maxR - pad;
  const viewY = -pad;
  const viewW = 2.0 * maxR + 2.0 * pad;
  const viewH = height + 2.0 * pad;

  const pointsAttr = pts.map(([x, y]) => `${x.toFixed(3)},${y.toFixed(3)}`).join(" ");

  const cx = 0.0;
  const cy = height - Number(metrics.centroid_z);
  const crossSize = Math.max(1.0, 0.03 * Math.max(height, maxR * 2.0));

  const zCogMax = metrics.z_cog_max;
  const cyReq =
    zCogMax !== null && zCogMax !== undefined && Number.isFinite(Number(zCogMax))
      ? height - Number(zCogMax)
      : null;

  const strokeWPoly = Math.max(0.3, crossSize * 0.15);
  const strokeWGrid = Math.max(0.2, crossSize * 0.08);
  const dashA = (crossSize * 0.6).toFixed(3);
  const dashB = (crossSize * 0.4).toFixed(3);
  const crossW = Math.max(0.3, crossSize * 0.2);

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewX.toFixed(3)} ${viewY.toFixed(3)} ${viewW.toFixed(3)} ${viewH.toFixed(3)}" preserveAspectRatio="xMidYMid meet">
  <g>
    <polygon points="${pointsAttr}" fill="#cbd5e1" stroke="#334155" stroke-width="${strokeWPoly.toFixed(3)}" stroke-linejoin="round" />
    <line x1="${(-maxR - pad * 0.5).toFixed(3)}" y1="${cy.toFixed(3)}" x2="${(maxR + pad * 0.5).toFixed(3)}" y2="${cy.toFixed(3)}" stroke="#94a3b8" stroke-width="${strokeWGrid.toFixed(3)}" stroke-dasharray="${dashA},${dashB}" />
    ${
      cyReq === null
        ? ""
        : `<g stroke="#3b82f6" stroke-width="${crossW.toFixed(3)}" stroke-linecap="round"><line x1="${(cx - crossSize).toFixed(3)}" y1="${cyReq.toFixed(3)}" x2="${(cx + crossSize).toFixed(3)}" y2="${cyReq.toFixed(3)}" /><line x1="${cx.toFixed(3)}" y1="${(cyReq - crossSize).toFixed(3)}" x2="${cx.toFixed(3)}" y2="${(cyReq + crossSize).toFixed(3)}" /></g>`
    }
    <g stroke="#ef4444" stroke-width="${crossW.toFixed(3)}" stroke-linecap="round">
      <line x1="${(cx - crossSize).toFixed(3)}" y1="${cy.toFixed(3)}" x2="${(cx + crossSize).toFixed(3)}" y2="${cy.toFixed(3)}" />
      <line x1="${cx.toFixed(3)}" y1="${(cy - crossSize).toFixed(3)}" x2="${cx.toFixed(3)}" y2="${(cy + crossSize).toFixed(3)}" />
    </g>
  </g>
</svg>`;
}

export function thumbnailDataUrl(gene: Gene, metrics: Metrics): string {
  const svg = thumbnailSvg(gene, metrics);
  const encoded = encodeURIComponent(svg)
    .replace(/'/g, "%27")
    .replace(/\"/g, "%22");
  return `data:image/svg+xml;charset=utf-8,${encoded}`;
}

