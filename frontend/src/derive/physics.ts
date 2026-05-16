/** backend/app/physics.py の TS ポート（feasibility 判定）。 */

const TILT_MAX_DEG = 75.0;
const EPS_MM = 0.5;
const RHO_M_CAP_MM = 200.0;
const HEAD_SKIP_FRACTION = 0.03;

export type Feasibility = {
  is_feasible: boolean;
  z_cog_max: number;
  limiting_z: number;
  rho_m_bottom: number;
  worst_margin: number;
};

function gaussianFilter1dNearest(x: number[], sigma: number): number[] {
  if (!Number.isFinite(sigma) || sigma <= 0) return x.slice();
  const radius = Math.trunc(Math.max(3, Math.round(4.0 * sigma)));
  const k: number[] = [];
  let s = 0;
  for (let i = -radius; i <= radius; i++) {
    const v = Math.exp(-0.5 * (i / sigma) ** 2);
    k.push(v);
    s += v;
  }
  for (let i = 0; i < k.length; i++) k[i] /= s;
  const n = x.length;
  const out: number[] = new Array(n);
  for (let i = 0; i < n; i++) {
    let acc = 0;
    for (let j = -radius; j <= radius; j++) {
      const idx = Math.min(n - 1, Math.max(0, i + j));
      acc += x[idx] * k[j + radius];
    }
    out[i] = acc;
  }
  return out;
}

function gradient(y: number[], x: number[]): number[] {
  const n = y.length;
  const out = new Array<number>(n);
  if (n < 2) return out;
  out[0] = (y[1] - y[0]) / (x[1] - x[0]);
  out[n - 1] = (y[n - 1] - y[n - 2]) / (x[n - 1] - x[n - 2]);
  for (let i = 1; i < n - 1; i++) {
    out[i] = (y[i + 1] - y[i - 1]) / (x[i + 1] - x[i - 1]);
  }
  return out;
}

export function feasibilityFromProfile(
  zIn: number[],
  rIn: number[],
  thetaMaxDeg = TILT_MAX_DEG,
  epsMm = EPS_MM,
  safetyMargin = 0.85,
  smoothDerivatives = false,
): Feasibility {
  const z = zIn.slice();
  const r = rIn.slice();
  const n = z.length;
  const fail = (rho = 0): Feasibility => ({
    is_feasible: false,
    z_cog_max: 0,
    limiting_z: 0,
    rho_m_bottom: rho,
    worst_margin: Number.NEGATIVE_INFINITY,
  });
  if (n < 8) return fail();

  let peakIdx = 0;
  for (let i = 1; i < r.length; i++) {
    if (r[i] > r[peakIdx]) peakIdx = i;
  }
  if (peakIdx < 3) return fail();

  const zAsc = z.slice(0, peakIdx + 1);
  const rAsc = r.slice(0, peakIdx + 1);
  let rp = gradient(rAsc, zAsc);
  let rpp = gradient(rp, zAsc);
  if (smoothDerivatives) {
    const sigma = Math.max(1, zAsc.length / 60);
    rp = gaussianFilter1dNearest(rp, sigma);
    rpp = gaussianFilter1dNearest(rpp, sigma);
  }
  const headSkip = Math.max(3, Math.trunc(HEAD_SKIP_FRACTION * zAsc.length));

  const cotThmax = 1 / Math.tan((thetaMaxDeg * Math.PI) / 180);
  const rhoM: number[] = [];
  const rhoEffArr: number[] = [];
  const zCogUpper: number[] = [];
  const marginPer: number[] = [];
  const valid: boolean[] = [];

  for (let i = 0; i < zAsc.length; i++) {
    const rppAbs = Math.max(Math.abs(rpp[i]), 1e-12);
    const rho = (1 + rp[i] ** 2) ** 1.5 / rppAbs;
    rhoM.push(rho);
    const rhoEff = rho - epsMm;
    rhoEffArr.push(rhoEff);
    const sqrtTerm = Math.sqrt(1 + rp[i] * rp[i]);
    const numer = rhoEff * sqrtTerm - rAsc[i];
    zCogUpper.push(zAsc[i] + numer / (rp[i] > 1e-9 ? rp[i] : NaN));
    marginPer.push(
      rhoEff - (rAsc[i] + rp[i] * (0 - zAsc[i])) / sqrtTerm,
    );
    valid.push(
      i >= headSkip &&
      rp[i] >= cotThmax &&
      rp[i] > 1e-6 &&
      Number.isFinite(rhoEff) &&
      rhoEff > 0 &&
      rho < RHO_M_CAP_MM,
    );
  }

  let zCogMaxRaw = Number.POSITIVE_INFINITY;
  let limitingZ = 0;
  let worstMargin = Number.POSITIVE_INFINITY;
  let anyValid = false;
  for (let i = 0; i < zAsc.length; i++) {
    if (!valid[i]) continue;
    anyValid = true;
    if (zCogUpper[i] < zCogMaxRaw) {
      zCogMaxRaw = zCogUpper[i];
      limitingZ = zAsc[i];
    }
    worstMargin = Math.min(worstMargin, marginPer[i]);
  }

  if (!anyValid) {
    const pos = rhoM.filter((v) => v > 0);
    pos.sort((a, b) => a - b);
    const med = pos.length ? pos[Math.floor(pos.length / 2)] : 0;
    return fail(med);
  }

  const headLo = Math.max(headSkip, Math.floor(peakIdx / 20));
  const headHi = Math.max(headLo + 2, Math.floor(peakIdx / 8));
  const headSlice = rhoM.slice(headLo, headHi).filter((v) => v > 0);
  headSlice.sort((a, b) => a - b);
  const rhoBottom =
    headSlice.length > 0
      ? headSlice[Math.floor(headSlice.length / 2)]
      : rhoM[headSkip] ?? 0;

  const isFeasible = zCogMaxRaw > 0 && worstMargin > 0;
  const zCogMax = Math.max(0, zCogMaxRaw) * safetyMargin;
  return {
    is_feasible: isFeasible,
    z_cog_max: zCogMax,
    limiting_z: limitingZ,
    rho_m_bottom: rhoBottom,
    worst_margin: worstMargin,
  };
}
