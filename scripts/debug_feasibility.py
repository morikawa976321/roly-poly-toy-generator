"""Temp: feasibility 診断。

- (A) 生のパラメトリック密プロファイル上で rho/feasibility を計算
- (B) radii→BSpline 経由で再評価した場合の比較
- (C) いくつかの seed で sample_gene の成功率を統計
"""

from __future__ import annotations

import numpy as np

from backend.app.gene import sample_gene
from backend.app.physics import feasibility_from_profile, rolypoly_feasibility
from backend.app.shape import sample_shape_params, tune_height_for_delta


def diagnose(seed: int) -> None:
    rng = np.random.default_rng(seed)
    params = sample_shape_params(rng)
    height, _zc, z_dense, r_dense = tune_height_for_delta(params)
    print(f"--- seed={seed} ---")
    print(
        f"params rb={params.rb:.2f} cap={params.cap_angle_deg:.1f} "
        f"rt={params.rt:.2f} delta={params.delta_target:.2f} height={height:.2f}"
    )

    # (A) 生密プロファイル
    rp = np.gradient(r_dense, z_dense)
    rpp = np.gradient(rp, z_dense)
    rho = (1 + rp * rp) ** 1.5 / np.maximum(np.abs(rpp), 1e-12)
    peak_idx = int(np.argmax(r_dense))
    print("(A) raw parametric profile derivatives:")
    for i in range(0, peak_idx + 1, max(1, peak_idx // 10)):
        print(
            f"    z={z_dense[i]:6.2f} r={r_dense[i]:6.2f} r'={rp[i]:7.3f} "
            f"r''={rpp[i]:+.5f} rho={rho[i]:7.2f}"
        )

    f_raw = feasibility_from_profile(z_dense, r_dense, smooth_derivatives=False)
    print(
        f"    -> feasible={f_raw.is_feasible} z_cog_max={f_raw.z_cog_max:.3f} "
        f"limiting_z={f_raw.limiting_z:.3f} rho_bottom={f_raw.rho_m_bottom:.2f} "
        f"worst={f_raw.worst_margin:.3f}"
    )

    # (B) radii 経由の roundtrip
    try:
        g = sample_gene(seed=seed)
        f_rt = rolypoly_feasibility(g)
        print(
            f"(B) via radii+GAUSSIAN roundtrip: feasible={f_rt.is_feasible} "
            f"z_cog_max={f_rt.z_cog_max:.3f} rho_bottom={f_rt.rho_m_bottom:.2f} "
            f"worst={f_rt.worst_margin:.3f}"
        )
    except RuntimeError as e:
        print(f"(B) sample_gene failed: {e}")


def success_rate(n: int = 100) -> None:
    ok = 0
    fails: list[int] = []
    for seed in range(n):
        try:
            sample_gene(seed=seed)
            ok += 1
        except RuntimeError:
            fails.append(seed)
    print(f"success rate: {ok}/{n}")
    if fails:
        print(f"failed seeds: {fails[:10]}{'...' if len(fails) > 10 else ''}")


if __name__ == "__main__":
    for s in [42, 7, 100, 2026]:
        diagnose(s)
        print()
    success_rate(50)
