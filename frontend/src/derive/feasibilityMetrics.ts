/**
 * feasibility 用メトリクス（z_cog_max・底面曲率半径）。
 *
 * 役割: カット有無に応じた feasibility プロファイルから付加 Metrics を算出。
 * 働き: computeMetrics が feasibilityExtrasForGene を併用。mesh シルエットと physics を橋渡し。
 */
import type { Gene, Metrics } from "../types";
import { revolutionGeometryFromProfile } from "./mesh";
import { silhouetteFromGeometry } from "./meshMetrics";
import {
  clipGeometryBelowCutPlane,
  clipOpenProfileHalf,
  cutProfileSilhouette,
  cutWouldChangeMesh,
  geneTopCutParams,
  topCutTanAngle,
} from "./meshPlaneCut";
import { feasibilityFromProfile, type Feasibility } from "./physics";
import { feasibilityProfile } from "./profileExtension";

const CUT_EPS = 1e-6;

function hasActiveTopCut(gene: Gene): boolean {
  const { zCut, tanA } = geneTopCutParams(gene);
  return zCut > CUT_EPS || Math.abs(tanA) > CUT_EPS;
}

function meshSilhouetteMeridian(
  z: number[],
  r: number[],
  zCut: number,
  angleDeg: number,
): { z: number[]; r: number[] } {
  const rev = revolutionGeometryFromProfile(z, r, 96);
  const tanA = topCutTanAngle(angleDeg);
  if (!cutWouldChangeMesh(rev, zCut, tanA)) {
    return { z, r };
  }
  const cut = clipGeometryBelowCutPlane(rev, zCut, angleDeg);
  return silhouetteFromGeometry(cut);
}

function* iterFeasibilityMeridians(
  gene: Gene,
): Generator<{ z: number[]; r: number[] }> {
  const { z, r } = feasibilityProfile(gene);
  if (!hasActiveTopCut(gene)) {
    yield { z, r };
    return;
  }

  const { zCut, tanA } = geneTopCutParams(gene);
  const angleDeg = Number(gene.top_cut_angle_deg ?? 0);
  const sil = cutProfileSilhouette(z, r, zCut, angleDeg);
  yield { z: sil.zRight, r: sil.rRight };
  yield { z: sil.zLeft, r: sil.rLeft };

  if (zCut > CUT_EPS && Math.abs(tanA) > CUT_EPS) {
    yield clipOpenProfileHalf(z, r, zCut, 0, "right");
  }

  const meshSil = meshSilhouetteMeridian(z, r, zCut, angleDeg);
  if (meshSil.z.length >= 8) {
    yield meshSil;
  }
}

function bestFeasibility(
  meridians: Iterable<{ z: number[]; r: number[] }>,
): Feasibility | null {
  let best: Feasibility | null = null;
  for (const { z: zm, r: rm } of meridians) {
    if (zm.length < 8) continue;
    const feas = feasibilityFromProfile(
      zm,
      rm,
      undefined,
      undefined,
      undefined,
      true,
    );
    if (feas.z_cog_max <= 0) continue;
    if (!best || feas.z_cog_max < best.z_cog_max) best = feas;
  }
  return best;
}

export function feasibilityExtrasForGene(
  gene: Gene,
  generationFeas?: Feasibility,
): Pick<Metrics, "bottom_curvature_radius" | "z_cog_max"> {
  if (!hasActiveTopCut(gene)) {
    if (generationFeas && generationFeas.z_cog_max > 0) {
      return {
        bottom_curvature_radius:
          generationFeas.rho_m_bottom > 0 ? generationFeas.rho_m_bottom : null,
        z_cog_max: generationFeas.z_cog_max,
      };
    }
    const { z, r } = feasibilityProfile(gene);
    const feas = feasibilityFromProfile(
      z,
      r,
      undefined,
      undefined,
      undefined,
      true,
    );
    return {
      bottom_curvature_radius:
        feas.rho_m_bottom > 0 ? feas.rho_m_bottom : null,
      z_cog_max: feas.z_cog_max > 0 ? feas.z_cog_max : null,
    };
  }

  const best = bestFeasibility(iterFeasibilityMeridians(gene));
  if (!best) {
    return { bottom_curvature_radius: null, z_cog_max: null };
  }
  return {
    bottom_curvature_radius: best.rho_m_bottom > 0 ? best.rho_m_bottom : null,
    z_cog_max: best.z_cog_max,
  };
}
