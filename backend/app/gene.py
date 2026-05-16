"""gene のランダム生成（v2: 球キャップ+5次テーパのパラメトリック族）。

v2 gene は [0, height] を等分した z 軸上に ``N_NODES`` 個の制御点 radii を持つ
プロファイルで、以下を満たす:

    r[0] = 0        （底は球キャップの最下点 = 極点）
    r[N-1] = rt     （上端。テーパ終端。rt=0 で尖らせることも可）
    単峰                 （途中で一度だけ最大）

生成手順:
    1. ``sample_shape_params()`` で (rb, cap_angle, rt, delta_target) を引く
    2. ``tune_height_for_delta()`` で height を選ぶ（案C: 細長さ/成立性/δ目標を同時に評価）
       → 密プロファイル (z_dense, r_dense) が得られる
    3. ``profile_to_radii()`` で N_NODES 点に等間隔ダウンサンプル
    4. 小さなランダム摂動（単峰性維持）を乗せて個体差を出す
    5. ``rolypoly_feasibility(gene, theta_max_deg=TILT_MAX_DEG)`` で θ_max=75°
       の自己復元条件を確認。不合格なら再サンプル（最大 ``FEASIBILITY_MAX_RETRY`` 回）。

v1 の折れ線ランダム生成関数は廃止した（既存 v1 gene は ``version`` フィールドで
区別され、読み取りは引き続き可能）。
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

from .config import (
    FEASIBILITY_MAX_RETRY,
    GENE_VERSION,
    JITTER_AMP,
    N_NODES,
    TILT_MAX_DEG,
)
from .models import Gene
from .physics import Feasibility, feasibility_from_profile, rolypoly_feasibility
from .shape import (
    profile_to_radii,
    sample_shape_params,
    tune_height_for_delta,
)


def _apply_radial_jitter(
    radii: List[float], rng: np.random.Generator, amp: float
) -> List[float]:
    """radii の各中間ノードに微小なランダム摂動を乗せる。

    制約:
    - 端点 radii[0], radii[-1] は変更しない
    - 単峰性（登り区間で狭義単調増、下り区間で狭義単調減）を崩さない:
      各ノードの許容幅を「前後の隣接ノードとの差の半分」に制限する
    """
    n = len(radii)
    if n < 3 or amp <= 0.0:
        return radii

    r = np.asarray(radii, dtype=float)
    peak_idx = int(np.argmax(r))
    peak_r = float(r[peak_idx])

    base_amp = amp * peak_r
    noise = (rng.random(n) - 0.5) * 2.0 * base_amp  # U(-amp*peak, +amp*peak)

    out = r.copy()
    # 端点は動かさない。ピーク位置も安定性のため動かさない方が安全。
    for i in range(1, n - 1):
        if i == peak_idx:
            continue
        # 単峰性を壊さない上下限
        left = out[i - 1]
        right = out[i + 1]
        if i < peak_idx:
            # 登り中: left < out[i] < right 相当
            lower = left + 1e-6
            upper = right - 1e-6
        elif i > peak_idx:
            # 下り中: left > out[i] > right 相当
            lower = right + 1e-6
            upper = left - 1e-6
        else:
            continue
        if upper <= lower:
            continue  # 挟める余地なし
        half = 0.5 * (upper - lower)
        delta = max(min(noise[i], half), -half)
        new_val = 0.5 * (lower + upper) + delta * 0.5
        out[i] = min(max(new_val, lower), upper)

    out[0] = r[0]
    out[-1] = r[-1]
    return [float(v) for v in out]


def _repair_unimodal(
    radii: Sequence[float],
    peak_idx: int,
    *,
    r0: float = 0.0,
    r_end: Optional[float] = None,
    eps: float = 0.0,
) -> List[float]:
    """radii を「単峰（ほぼ狭義）」になるように修復する。

    ここでの単峰は以下を満たすように近似的に投影する:
    - radii[0] は r0 に固定
    - radii[-1] は r_end（指定時）に固定（指定なしなら入力値を保持）
    - 0..peak_idx は非減少（実装上は eps によりほぼ狭義）
    - peak_idx..end は非増加（同上）

    注: 厳密な isotonic regression ではないが、生成系の修復として十分に安定で、
    下流の smoothing/mesh 生成で破綻しにくい形に戻すことが目的。
    """
    r = np.asarray(list(radii), dtype=float)
    n = int(r.size)
    if n < 3:
        return [float(v) for v in r]

    peak = int(np.clip(peak_idx, 1, n - 2))

    r[0] = float(r0)
    if r_end is not None:
        r[-1] = float(max(0.0, r_end))
    else:
        r[-1] = float(max(0.0, r[-1]))

    # まず全体を非負に。
    np.maximum(r, 0.0, out=r)

    # peak 値を決めて以降のクランプ上限として使う。
    peak_r = float(np.max(r))
    r[peak] = max(r[peak], peak_r)
    peak_r = float(r[peak])

    # 左側: 非減少（ほぼ狭義）かつ peak を超えない。
    # ここは必要な場合のみ増やす（親の特徴をできるだけ保つ）。
    for i in range(1, peak + 1):
        lo = r[i - 1] + eps
        r[i] = min(max(r[i], lo), peak_r)

    # 右側: 非増加（ほぼ狭義）。こちらは「増やす」より「減らす」方が
    # feasibility を壊しにくいので、前ノード以下にクランプしていく。
    for i in range(peak + 1, n):
        hi = r[i - 1] - eps
        r[i] = min(r[i], hi)
        if r[i] < 0.0:
            r[i] = 0.0

    # 端点再固定（ループ中に触れていないが保険）
    r[0] = float(r0)
    if r_end is not None:
        r[-1] = float(max(0.0, r_end))
    return [float(v) for v in r]


def breed_gene_with_feasibility(
    parents: Sequence[Gene],
    *,
    seed: Optional[int] = None,
    max_retry: int = FEASIBILITY_MAX_RETRY,
) -> Tuple[Gene, Feasibility]:
    """親 gene 群（1〜4）を「次世代生成に影響」させつつ、生成は確実に成立させる。

    現行の物理成立性判定は **パラメトリック密プロファイル** に対して行うのが最も安定
    だが、親からの交叉で得た radii だけから同等の密プロファイルを復元するのは難しい。
    そのためここでは:

    1) まず `sample_gene_with_feasibility()` で必ず成立する個体を生成（基底個体）
    2) 親の radii/height の統計（平均形状）で基底個体を軽く“モーフ”し、親の特徴を混ぜる
    3) 子 gene に対して feasibility を再評価し、成立する個体のみ返す

    という方針で「親が影響するGA的生成」を実現する。
    """
    if not parents:
        raise ValueError("parents must be non-empty")

    rng = np.random.default_rng(seed)
    ps = list(parents)

    # 親の平均形状（radii/height）を作る。N は揃っている前提（現行v2）。
    parent_r = np.mean([np.asarray(p.radii, dtype=float) for p in ps], axis=0)
    parent_h = float(np.mean([float(p.height) for p in ps]))

    last_feas: Optional[Feasibility] = None
    for _attempt in range(max_retry):
        base_seed = int(rng.integers(0, np.iinfo(np.int64).max))
        gene, _feas_base = sample_gene_with_feasibility(seed=base_seed, max_retry=max_retry)

        # 子に混ぜる割合（小さめにして feasibility を壊しにくくする）
        mix = float(rng.uniform(0.2, 0.4))

        child_r = np.asarray(gene.radii, dtype=float)
        parent_r_scaled = parent_r
        # 親のスケールを合わせる（ピーク半径を揃える）。親のピークが0ならスキップ。
        pr_peak = float(np.max(parent_r_scaled))
        cr_peak = float(np.max(child_r))
        if pr_peak > 1e-9 and cr_peak > 1e-9:
            parent_r_scaled = parent_r_scaled * (cr_peak / pr_peak)

        blended = (1.0 - mix) * child_r + mix * parent_r_scaled
        peak = int(np.argmax(blended))
        blended_list = _repair_unimodal(blended.tolist(), peak, r0=0.0, r_end=None, eps=0.0)
        # 最後にごく小さな jitter（見た目の個体差）。random生成より弱め。
        blended_list = _apply_radial_jitter(blended_list, rng, amp=float(JITTER_AMP * 0.35))

        # height も少しだけ親に寄せる
        h_mix = float(rng.uniform(0.05, 0.18))
        child_h = (1.0 - h_mix) * float(gene.height) + h_mix * parent_h

        child = gene.model_copy(
            update={
                "height": float(child_h),
                "radii": blended_list,
                "bottom_radius": 0.0,
                "z_warp": 2.0,
            }
        )

        feas_child = rolypoly_feasibility(child)
        last_feas = feas_child
        if feas_child.is_feasible:
            return child, feas_child

    raise RuntimeError(
        f"Failed to breed a feasible gene after {max_retry} retries "
        f"(last: {last_feas})"
    )


def sample_gene_with_feasibility(
    seed: Optional[int] = None,
    max_retry: int = FEASIBILITY_MAX_RETRY,
) -> Tuple[Gene, Feasibility]:
    """feasibility を満たす v2 gene と、生成時に計算した feasibility を返す。

    feasibility は **摂動前の密パラメトリックプロファイル**（281 点）上で
    評価する。これは低解像度の再評価より精度が高い。

    摂動（jitter）は保存形（radii）にだけ影響し、物理的な形はほぼ変わらないため、
    ここで計算した feasibility を保存しても実用上問題ない。
    """
    rng = np.random.default_rng(seed)

    last_err: Optional[str] = None
    for _attempt in range(max_retry):
        params = sample_shape_params(rng)
        height, _z_com, z_dense, r_dense = tune_height_for_delta(params)

        # feasibility はパラメトリックな密プロファイル（281 点）上で直接判定する。
        # radii に落としてから smoothing 経由で再評価すると 低解像度 + 数値微分の
        # 合成による偽ノイズで False Negative になりやすい。
        feas = feasibility_from_profile(
            z_dense, r_dense, theta_max_deg=TILT_MAX_DEG, smooth_derivatives=False
        )
        if not feas.is_feasible:
            last_err = (
                f"z_cog_max={feas.z_cog_max:.3f} worst_margin={feas.worst_margin:.3f}"
            )
            continue

        # v2 の radii は z_warp=2.0（= z_i = height·(i/(N-1))²）で配置する。
        # z=0 付近にノードが密に集まり、球キャップ極の √z 型特異点（傾き無限大）
        # を忠実に再現できる。等間隔配置だと最初の区間で Δz≈2mm となり、折れ線
        # 補間では底が「尖った円錐」のように見えてしまう。
        z_warp_v2 = 2.0
        radii = profile_to_radii(
            z_dense, r_dense, N_NODES, height=height, z_warp=z_warp_v2
        )
        radii = _apply_radial_jitter(radii, rng, amp=JITTER_AMP)

        gene = Gene(
            version=GENE_VERSION,
            N=N_NODES,
            height=float(height),
            bottom_radius=0.0,  # v2 は底も r=0（球キャップ極点）
            radii=radii,
            z_warp=z_warp_v2,
            top_extension_mm=0.0,
            top_cut_height_mm=0.0,
            top_cut_angle_deg=0.0,
        )
        return gene, feas

    raise RuntimeError(
        f"Failed to sample a feasible gene after {max_retry} retries "
        f"(last: {last_err})"
    )


def sample_gene(
    seed: Optional[int] = None,
    max_retry: int = FEASIBILITY_MAX_RETRY,
) -> Gene:
    """feasibility を満たす v2 gene を返す（feasibility 情報は破棄）。

    API から Feasibility も必要な場合は ``sample_gene_with_feasibility`` を使う。
    """
    gene, _ = sample_gene_with_feasibility(seed=seed, max_retry=max_retry)
    return gene
