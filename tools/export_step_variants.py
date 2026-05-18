#!/usr/bin/env python3
"""手法 1 / 5 / 7 のプロファイルで STEP を tools/output/ に書き出す（アプリ本体と独立）。

役割: 平滑化バリアント別 STEP 出力のオフライン比較ツール。
働き: compare_profile_smoothing の PROFILE_FNS を使い Node opencascade 経由で STEP を生成する。
本番 export パイプラインとは独立。

  1. current … smooth_profile（現行ガウシアン）
  5. b3      … smoothing spline on 64 nodes
  7. b5      … PCHIP → 96 pts → smoothing spline

使い方 (リポジトリルート):

  python tools/export_step_variants.py

出力例:

  tools/output/6d7afe17fed27c7c_step_1_current.step
  tools/output/6d7afe17fed27c7c_step_5_b3.step
  tools/output/6d7afe17fed27c7c_step_7_b5.step

依存:
  - Python: numpy, scipy（compare_profile_smoothing と同じ）
  - Node.js + frontend の opencascade.js（``cd frontend && npm install`` 済み）
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.compare_profile_smoothing import (  # noqa: E402
    METHODS,
    PROFILE_FNS,
    REFERENCE_DESIGN_ID,
    REFERENCE_GENE_JSON,
    load_gene_from_json,
)

OUTPUT_DIR = _REPO_ROOT / "tools" / "output"
OCCT_SCRIPT = _REPO_ROOT / "tools" / "export_step_occt.mjs"
OCCT_REGISTER = _REPO_ROOT / "tools" / "occt-register.mjs"
FRONTEND_DIR = _REPO_ROOT / "frontend"


def _check_frontend_oc() -> None:
    wasm = FRONTEND_DIR / "node_modules" / "opencascade.js" / "dist" / "opencascade.wasm.wasm"
    if not wasm.is_file():
        raise SystemExit(
            "opencascade.js not found. Run: cd frontend && npm install"
        )


def _node_exe() -> str:
    node = shutil.which("node")
    if not node:
        raise SystemExit("node not found on PATH")
    return node


def main() -> None:
    _check_frontend_oc()
    gene = load_gene_from_json(REFERENCE_GENE_JSON)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    profiles: dict[str, dict] = {}
    for spec in METHODS:
        z, r = PROFILE_FNS[spec.key](gene)
        profiles[spec.key] = {
            "title": spec.title,
            "z": z.tolist(),
            "r": r.tolist(),
        }

    cache_path = OUTPUT_DIR / f"profiles_{REFERENCE_DESIGN_ID}.json"
    cache_path.write_text(json.dumps(profiles), encoding="utf-8")
    print(f"Wrote profile cache {cache_path}")

    file_suffix = {
        "current": "1_current",
        "b3": "5_b3",
        "b5": "7_b5",
    }

    for spec in METHODS:
        suffix = file_suffix[spec.key]
        out_step = OUTPUT_DIR / f"{REFERENCE_DESIGN_ID}_step_{suffix}.step"
        cmd = [
            _node_exe(),
            f"--import={OCCT_REGISTER.resolve().as_uri()}",
            str(OCCT_SCRIPT),
            str(cache_path),
            spec.key,
            str(out_step),
        ]
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, cwd=str(_REPO_ROOT))


if __name__ == "__main__":
    main()
