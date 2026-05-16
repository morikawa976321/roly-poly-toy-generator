import type { Gene, Metrics } from "../types";
import {
  cutProfileSilhouette,
  cutWouldChangeProfile,
  geneTopCutParams,
} from "./meshPlaneCut";
import { effectiveProfile } from "./profileExtension";

/** 傾斜カット上面: x 軸上を z = z_cut + x·tan で結ぶ */
function topCutEdgePoints(
  xStart: number,
  xEnd: number,
  zCut: number,
  tanA: number,
  height: number,
): Array<[number, number]> {
  if (Math.abs(xStart - xEnd) < 1e-9) return [];
  const n = Math.max(2, Math.min(48, Math.ceil(Math.abs(xStart - xEnd))));
  const pts: Array<[number, number]> = [];
  for (let i = 1; i < n; i++) {
    const x = xStart + ((xEnd - xStart) * i) / n;
    pts.push([x, height - (zCut + x * tanA)]);
  }
  return pts;
}

// backend/app/thumbnail.py::render_thumbnail_svg の TS ポート
export function thumbnailSvg(gene: Gene, metrics: Metrics): string {
  const { z, r } = effectiveProfile(gene);
  const { zCut, tanA } = geneTopCutParams(gene);
  const angleDeg = Number(gene.top_cut_angle_deg ?? 0);
  const { zRight, rRight, zLeft, rLeft } = cutWouldChangeProfile(z, r, zCut, tanA)
    ? cutProfileSilhouette(z, r, zCut, angleDeg)
    : { zRight: z, rRight: r, zLeft: z, rLeft: r };

  let maxR = 0;
  let zMax = -Infinity;
  let zMin = Infinity;
  for (let i = 0; i < zRight.length; i++) {
    maxR = Math.max(maxR, rRight[i]);
    zMax = Math.max(zMax, zRight[i]);
    zMin = Math.min(zMin, zRight[i]);
  }
  for (let i = 0; i < zLeft.length; i++) {
    maxR = Math.max(maxR, rLeft[i]);
    zMax = Math.max(zMax, zLeft[i]);
    zMin = Math.min(zMin, zLeft[i]);
  }
  if (!Number.isFinite(zMax)) {
    zMax = z[z.length - 1];
    zMin = z[0];
  }
  const height = zMax;

  const pts: Array<[number, number]> = [];
  for (let i = 0; i < zRight.length; i++) {
    pts.push([rRight[i], height - zRight[i]]);
  }
  if (cutWouldChangeProfile(z, r, zCut, tanA) && zRight.length > 0 && zLeft.length > 0) {
    const xRight = rRight[rRight.length - 1];
    const xLeft = -rLeft[rLeft.length - 1];
    pts.push(...topCutEdgePoints(xRight, xLeft, zCut, tanA, height));
  }
  for (let i = zLeft.length - 1; i >= 0; i--) {
    pts.push([-rLeft[i], height - zLeft[i]]);
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
