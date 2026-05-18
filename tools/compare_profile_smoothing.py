#!/usr/bin/env python3
"""プロファイル平滑化と本番 effective の子午面断面を PNG に出力する。

  1. current … 線形密化 + インデックス空間ガウシアン σ=24（延長の基準）
  5. B3      … 64 制御点 smoothing spline (s 指定) → 密サンプル（延長なし本体）
  7. B5      … PCHIP → z 等間隔 96 点 → smoothing spline → 密サンプル
  P. prod    … effective_profile（レガシー+延長 → B3 再フィット、本番）

使い方 (リポジトリルート):

  python tools/compare_profile_smoothing.py
  python tools/compare_profile_smoothing.py --extension-mm 5
  python tools/compare_profile_smoothing.py --out tools/output/compare.png
  python tools/compare_profile_smoothing.py --from-db --db data/app.db
  python tools/compare_profile_smoothing.py --seed 5

既定モデル: design_id ``6d7afe17fed27c7c``（``docs/designs/.../gene.json``）

依存: numpy, matplotlib, scipy
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Tuple

import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import PchipInterpolator, UnivariateSpline

# backend を import 可能にする
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.app.gene import sample_gene_with_feasibility  # noqa: E402
from backend.app.models import Gene  # noqa: E402
from backend.app.profile_extension import (  # noqa: E402
    effective_profile,
    legacy_mesh_profile,
)
from backend.app.shape import build_parametric_profile, sample_shape_params  # noqa: E402
from backend.app.smoothing import (  # noqa: E402
    B3_SPLINE_S,
    DENSE_FACTOR,
    _dense_z,
    _effective_z_warp,
    gene_z_nodes,
    smooth_profile,
)

REFERENCE_DESIGN_ID = "6d7afe17fed27c7c"
REFERENCE_GENE_JSON = (
    _REPO_ROOT / "docs" / "designs" / REFERENCE_DESIGN_ID / "gene.json"
)

# --- チューニング ---
B5_SUBSAMPLE = 96
B5_SPLINE_S = 0.5
DEFAULT_EXTENSION_MM = 5.0

# 一覧図の描画（高解像度・細線で浪打ちを見やすく）
FIGSIZE_INCH = (32.0, 8.0)
SAVE_DPI = 400
LINE_SCALE = 0.6
LW_PROFILE = 1.4 * LINE_SCALE
LW_PARAMETRIC_REF = 0.8 * LINE_SCALE
MS_NODES = 3.0 * LINE_SCALE


@dataclass(frozen=True)
class MethodSpec:
    key: str
    title: str
    subtitle: str


METHODS: tuple[MethodSpec, ...] = (
    MethodSpec("current", "1. current", f"index Gaussian sigma={DENSE_FACTOR}"),
    MethodSpec("b3", "5. B3", f"smoothing spline s={B3_SPLINE_S:g} on nodes"),
    MethodSpec(
        "b5",
        "7. B5",
        f"PCHIP -> {B5_SUBSAMPLE} pts -> spline s={B5_SPLINE_S:g}",
    ),
    MethodSpec(
        "prod",
        "P. production",
        "legacy+ext → B3 refit (effective_profile)",
    ),
)


ProfileFn = Callable[[Gene], Tuple[np.ndarray, np.ndarray]]


def _control_points(gene: Gene) -> Tuple[np.ndarray, np.ndarray]:
    z_nodes = gene_z_nodes(gene)
    r_nodes = np.asarray(gene.radii, dtype=float)
    return z_nodes, r_nodes


def _dense_z_for(gene: Gene) -> np.ndarray:
    w = _effective_z_warp(getattr(gene, "z_warp", None))
    return _dense_z(float(gene.height), int(gene.N), DENSE_FACTOR, z_warp=w)


def _fix_endpoints(r: np.ndarray, r_nodes: np.ndarray) -> np.ndarray:
    out = np.asarray(r, dtype=float).copy()
    if out.size:
        out[0] = float(r_nodes[0])
        out[-1] = float(r_nodes[-1])
    np.maximum(out, 0.0, out=out)
    return out


def profile_current(gene: Gene) -> Tuple[np.ndarray, np.ndarray]:
    return smooth_profile(gene)


def profile_b3(gene: Gene) -> Tuple[np.ndarray, np.ndarray]:
    z_nodes, r_nodes = _control_points(gene)
    z_dense = _dense_z_for(gene)
    spl = UnivariateSpline(z_nodes, r_nodes, s=float(B3_SPLINE_S), k=3)
    r = np.asarray(spl(z_dense), dtype=float)
    return z_dense, _fix_endpoints(r, r_nodes)


def profile_b5(gene: Gene) -> Tuple[np.ndarray, np.ndarray]:
    z_nodes, r_nodes = _control_points(gene)
    z_dense = _dense_z_for(gene)
    pchip = PchipInterpolator(z_nodes, r_nodes, extrapolate=False)
    r_dense_pchip = np.asarray(pchip(z_dense), dtype=float)

    z0, z1 = float(z_nodes[0]), float(z_nodes[-1])
    z_sub = np.linspace(z0, z1, int(B5_SUBSAMPLE))
    r_sub = np.asarray(pchip(z_sub), dtype=float)
    spl = UnivariateSpline(z_sub, r_sub, s=float(B5_SPLINE_S), k=3)
    r = np.asarray(spl(z_dense), dtype=float)
    _ = r_dense_pchip  # noqa: F841
    return z_dense, _fix_endpoints(r, r_nodes)


def make_profile_fns(extension_mm: float) -> dict[str, ProfileFn]:
    def profile_prod(gene: Gene) -> Tuple[np.ndarray, np.ndarray]:
        g = gene.model_copy(update={"top_extension_mm": float(extension_mm)})
        return effective_profile(g)

    return {
        "current": profile_current,
        "b3": profile_b3,
        "b5": profile_b5,
        "prod": profile_prod,
    }


def parametric_reference_for_seed(gene: Gene, seed: int) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    params = sample_shape_params(rng)
    return build_parametric_profile(params, float(gene.height), n_dense=513)


def load_gene_from_json(gene_json: Path) -> Gene:
    if not gene_json.is_file():
        raise SystemExit(f"gene.json not found: {gene_json}")
    return Gene.model_validate(json.loads(gene_json.read_text(encoding="utf-8")))


def load_gene_from_db(db_path: Path, design_id: str) -> Gene:
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT gene_json FROM designs WHERE design_id = ?",
            (design_id,),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        raise SystemExit(f"design_id not found: {design_id}")
    return Gene.model_validate(json.loads(row[0]))


def load_gene(
    *,
    gene_json: Path,
    design_id: str,
    from_db: bool,
    db_path: Path,
    seed: int | None,
) -> Gene:
    if seed is not None:
        gene, _feas = sample_gene_with_feasibility(seed=seed)
        return gene
    if from_db:
        return load_gene_from_db(db_path, design_id)
    return load_gene_from_json(gene_json)


def plot_comparison(
    gene: Gene,
    out_path: Path,
    *,
    design_id: str,
    extension_mm: float,
    seed: int | None = None,
    show_parametric: bool = True,
) -> None:
    z_nodes, r_nodes = _control_points(gene)
    profile_fns = make_profile_fns(extension_mm)
    ref = (
        parametric_reference_for_seed(gene, seed)
        if show_parametric and seed is not None
        else None
    )

    profiles: dict[str, Tuple[np.ndarray, np.ndarray]] = {
        spec.key: profile_fns[spec.key](gene) for spec in METHODS
    }

    r_max = float(np.max(r_nodes))
    z_max = float(np.max(z_nodes))
    for z, r in profiles.values():
        r_max = max(r_max, float(np.max(r)))
        z_max = max(z_max, float(np.max(z)))
    if ref is not None:
        z_ref, r_ref = ref
        r_max = max(r_max, float(np.max(r_ref)))
        z_max = max(z_max, float(np.max(z_ref)))
    pad = 1.03
    xlim = (0.0, r_max * pad)
    ylim = (0.0, z_max * pad)

    fig, axes = plt.subplots(1, len(METHODS), figsize=FIGSIZE_INCH, constrained_layout=True)
    if len(METHODS) == 1:
        axes = [axes]

    def style_ax(ax: plt.Axes) -> None:
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("r (mm)")
        ax.set_ylabel("z (mm)")
        ax.grid(True, alpha=0.25)

    for ax, spec in zip(axes, METHODS):
        z, r = profiles[spec.key]
        ax.plot(r, z, color="#2563eb", linewidth=LW_PROFILE, label="profile")
        ax.plot(
            r_nodes,
            z_nodes,
            "o",
            color="#94a3b8",
            markersize=MS_NODES,
            alpha=0.7,
            label="64 nodes",
        )
        if ref is not None:
            z_ref, r_ref = ref
            ax.plot(
                r_ref,
                z_ref,
                color="#16a34a",
                linewidth=LW_PARAMETRIC_REF,
                alpha=0.45,
                label="parametric ref",
            )
        if spec.key == "prod":
            g_ext = gene.model_copy(update={"top_extension_mm": extension_mm})
            z_legacy, r_legacy = legacy_mesh_profile(g_ext)
            # 延長区間だけ重ねる（レガシー延長形状の一致確認）
            H = float(z_nodes[-1])
            mask = z_legacy > H + 1e-6
            if np.any(mask):
                ax.plot(
                    r_legacy[mask],
                    z_legacy[mask],
                    color="#dc2626",
                    linewidth=LW_PROFILE * 0.9,
                    linestyle="--",
                    alpha=0.85,
                    label=f"legacy ext ({extension_mm:g} mm)",
                )
        ax.set_title(f"{spec.title}\n{spec.subtitle}", fontsize=10)
        style_ax(ax)
        if spec.key == "prod":
            ax.legend(fontsize=6, loc="best")

    title = (
        f"Profile smoothing — design_id={design_id}, "
        f"N={gene.N}, height={gene.height:.1f} mm, "
        f"z_warp={getattr(gene, 'z_warp', None)}, "
        f"top_extension_mm={extension_mm:g} (prod/overlay)"
    )
    fig.suptitle(title, fontsize=12, fontweight="bold")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=SAVE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--design-id",
        type=str,
        default=REFERENCE_DESIGN_ID,
        help=f"design id label / SQLite key (default: {REFERENCE_DESIGN_ID})",
    )
    parser.add_argument(
        "--gene-json",
        type=Path,
        default=REFERENCE_GENE_JSON,
        help="gene JSON path (default: docs/designs/<design-id>/gene.json)",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="load gene from SQLite instead of --gene-json",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_REPO_ROOT / "data" / "app.db",
        help="SQLite path when using --from-db",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="ignore design-id; sample a random feasible gene with this seed",
    )
    parser.add_argument(
        "--extension-mm",
        type=float,
        default=DEFAULT_EXTENSION_MM,
        help=f"top_extension_mm for P. production column (default: {DEFAULT_EXTENSION_MM})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_REPO_ROOT
        / "tools"
        / "output"
        / f"profile_smoothing_compare_{REFERENCE_DESIGN_ID}.png",
    )
    parser.add_argument(
        "--parametric-ref",
        action="store_true",
        help="overlay jitter-free parametric curve (only with --seed)",
    )
    args = parser.parse_args()

    gene_json = args.gene_json
    if not args.from_db and args.seed is None and args.design_id != REFERENCE_DESIGN_ID:
        gene_json = _REPO_ROOT / "docs" / "designs" / args.design_id / "gene.json"

    gene = load_gene(
        gene_json=gene_json,
        design_id=args.design_id,
        from_db=args.from_db,
        db_path=args.db,
        seed=args.seed,
    )
    plot_comparison(
        gene,
        args.out,
        design_id=args.design_id,
        extension_mm=float(args.extension_mm),
        seed=args.seed,
        show_parametric=bool(args.parametric_ref and args.seed is not None),
    )


if __name__ == "__main__":
    main()
