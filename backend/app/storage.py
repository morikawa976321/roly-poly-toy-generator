"""デザインの永続化レイヤ（SQLite + ファイルシステム）。

- メタデータは ``data/app.db``（単一の ``designs`` テーブル）に格納する。
- デザインごとのアセットは ``data/assets/{design_id}/`` 以下に置く:
    - ``thumb.svg``
    - ``model.glb``

DESIGN_DECISIONS.md の「ローカル前提・まずは最もシンプルに」方針に従い、
書き込みはすべて同期で行う。
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from .config import ASSETS_DIR, DATA_DIR, DB_PATH
from .models import DesignSummary, Gene, Metrics


SCHEMA = """
CREATE TABLE IF NOT EXISTS designs (
    design_id              TEXT PRIMARY KEY,
    gene_json              TEXT NOT NULL,
    volume                 REAL NOT NULL,
    height                 REAL NOT NULL,
    max_width              REAL NOT NULL,
    centroid_z             REAL NOT NULL,
    z_cog_suggested        REAL,
    bottom_curvature_radius REAL,
    z_cog_max              REAL,
    created_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_designs_created_at ON designs(created_at);
"""


def _ensure_v2_columns(conn: sqlite3.Connection) -> None:
    """古いスキーマ（v1 列のみ）のテーブルに v2 で追加した列を migrate する。

    ``ALTER TABLE ADD COLUMN`` は SQLite では冪等ではないので、
    ``PRAGMA table_info`` で存在チェックしてから追加する。
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(designs)").fetchall()}
    if "z_cog_suggested" not in cols:
        conn.execute("ALTER TABLE designs ADD COLUMN z_cog_suggested REAL")
    if "bottom_curvature_radius" not in cols:
        conn.execute("ALTER TABLE designs ADD COLUMN bottom_curvature_radius REAL")
    if "z_cog_max" not in cols:
        conn.execute("ALTER TABLE designs ADD COLUMN z_cog_max REAL")


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        _ensure_v2_columns(conn)
    # 旧方式のアセット（thumb_gaussian.svg 等）が残っていても、新仕様の単一名
    # （thumb.svg / model.glb / model.stl）に統一して扱えるように移行する。
    try:
        migrate_assets_to_gaussian()
    except Exception:
        # 移行はベストエフォート（生成物の再生成で復旧できるため）。
        pass


def migrate_assets_to_gaussian() -> None:
    """既存 `data/assets/*` を GAUSSIAN 単一キャッシュへ移行し、旧キャッシュを掃除する。

    旧仕様では以下が混在し得る:
    - 代表（旧）: `thumb.svg`, `model.glb`, `model.stl`
    - 追加方式: `thumb_<method>.svg`, `model_<method>.glb`, `model_<method>.stl`

    新仕様では method suffix を参照しないため、可能なら `*_gaussian.*` を正として
    単一名へ置換し、無い場合は DB の gene から GAUSSIAN で再生成する。
    """
    _ensure_dirs()
    if not ASSETS_DIR.exists():
        return

    # 遅延 import（重い依存/循環参照回避）
    from .geometry import build_revolve_mesh, compute_metrics, export_glb, export_stl
    from .thumbnail import render_thumbnail_svg

    for child in ASSETS_DIR.iterdir():
        if not child.is_dir():
            continue
        design_id = child.name
        found = get_design(design_id)
        if not found:
            continue
        gene, metrics_stored, _created_at = found

        # まず `*_gaussian.*` があれば単一名へ採用
        mapping = [
            ("thumb_gaussian.svg", "thumb.svg"),
            ("model_gaussian.glb", "model.glb"),
            ("model_gaussian.stl", "model.stl"),
        ]
        for src, dst in mapping:
            src_path = child / src
            dst_path = child / dst
            if src_path.exists():
                try:
                    dst_path.write_bytes(src_path.read_bytes())
                except Exception:
                    # text/svg の場合も bytes で統一して扱う
                    dst_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")

        # 無いものは GAUSSIAN で再生成（旧方式を残さない）
        thumb_p = child / "thumb.svg"
        model_p = child / "model.glb"
        stl_p = child / "model.stl"

        if not thumb_p.exists():
            metrics = compute_metrics(gene).model_copy(
                update={
                    "z_cog_suggested": metrics_stored.z_cog_suggested,
                    "bottom_curvature_radius": metrics_stored.bottom_curvature_radius,
                    "z_cog_max": metrics_stored.z_cog_max,
                }
            )
            svg = render_thumbnail_svg(gene, metrics)
            thumb_p.write_text(svg, encoding="utf-8")

        if not model_p.exists():
            mesh = build_revolve_mesh(gene)
            model_p.write_bytes(export_glb(mesh))

        if not stl_p.exists():
            mesh = build_revolve_mesh(gene)
            stl_p.write_bytes(export_stl(mesh))

        # 旧 suffix 付きキャッシュを削除（gaussian含む）
        for p in child.glob("thumb_*.svg"):
            try:
                p.unlink()
            except Exception:
                pass
        for p in child.glob("model_*.glb"):
            try:
                p.unlink()
            except Exception:
                pass
        for p in child.glob("model_*.stl"):
            try:
                p.unlink()
            except Exception:
                pass


def asset_dir(design_id: str) -> Path:
    p = ASSETS_DIR / design_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def thumb_path(
    design_id: str,
) -> Path:
    return asset_dir(design_id) / "thumb.svg"


def model_path(
    design_id: str,
) -> Path:
    return asset_dir(design_id) / "model.glb"


def stl_path(
    design_id: str,
) -> Path:
    return asset_dir(design_id) / "model.stl"


def exists(design_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM designs WHERE design_id = ?",
            (design_id,),
        ).fetchone()
        return row is not None


def upsert_design(
    design_id: str,
    gene: Gene,
    metrics: Metrics,
    svg_text: str,
    glb_bytes: bytes,
) -> DesignSummary:
    created_at = _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    gene_json = json.dumps(gene.model_dump(), sort_keys=True, ensure_ascii=False)

    with _connect() as conn:
        _ensure_v2_columns(conn)
        conn.execute(
            """
            INSERT INTO designs (
                design_id, gene_json, volume, height, max_width, centroid_z,
                z_cog_suggested, bottom_curvature_radius, z_cog_max, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(design_id) DO NOTHING
            """,
            (
                design_id,
                gene_json,
                metrics.volume,
                metrics.height,
                metrics.max_width,
                metrics.centroid_z,
                metrics.z_cog_suggested,
                metrics.bottom_curvature_radius,
                metrics.z_cog_max,
                created_at,
            ),
        )
        row = conn.execute(
            """
            SELECT design_id, volume, height, max_width, centroid_z,
                   z_cog_suggested, bottom_curvature_radius, z_cog_max, created_at
            FROM designs WHERE design_id = ?
            """,
            (design_id,),
        ).fetchone()

    thumb_path(design_id).write_text(svg_text, encoding="utf-8")
    model_path(design_id).write_bytes(glb_bytes)

    return DesignSummary(
        design_id=row["design_id"],
        metrics=Metrics(
            volume=row["volume"],
            height=row["height"],
            max_width=row["max_width"],
            centroid_z=row["centroid_z"],
            z_cog_suggested=row["z_cog_suggested"],
            bottom_curvature_radius=row["bottom_curvature_radius"],
            z_cog_max=row["z_cog_max"],
        ),
        created_at=row["created_at"],
    )


def list_designs(limit: int = 100, offset: int = 0) -> Tuple[List[DesignSummary], int]:
    with _connect() as conn:
        _ensure_v2_columns(conn)
        total_row = conn.execute("SELECT COUNT(*) AS c FROM designs").fetchone()
        total = int(total_row["c"]) if total_row else 0
        rows = conn.execute(
            """
            SELECT design_id, volume, height, max_width, centroid_z,
                   z_cog_suggested, bottom_curvature_radius, z_cog_max, created_at
            FROM designs
            ORDER BY created_at DESC, design_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    designs = [
        DesignSummary(
            design_id=r["design_id"],
            metrics=Metrics(
                volume=r["volume"],
                height=r["height"],
                max_width=r["max_width"],
                centroid_z=r["centroid_z"],
                z_cog_suggested=r["z_cog_suggested"],
                bottom_curvature_radius=r["bottom_curvature_radius"],
                z_cog_max=r["z_cog_max"],
            ),
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return designs, total


def list_designs_with_genes(
    limit: int = 100, offset: int = 0
) -> Tuple[List[Tuple[str, Gene, str]], int]:
    """gene 付きで designs を列挙する。

    返り値は ``(design_id, gene, created_at)`` のリストと件数。一覧の metrics を
    動的に再計算するためなどに使う（DB の集計列は使わない）。
    """
    with _connect() as conn:
        total_row = conn.execute("SELECT COUNT(*) AS c FROM designs").fetchone()
        total = int(total_row["c"]) if total_row else 0
        rows = conn.execute(
            """
            SELECT design_id, gene_json, created_at
            FROM designs
            ORDER BY created_at DESC, design_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    out: List[Tuple[str, Gene, str]] = []
    for r in rows:
        gene = Gene.model_validate_json(r["gene_json"])
        out.append((r["design_id"], gene, r["created_at"]))
    return out, total


def get_design(design_id: str) -> Optional[Tuple[Gene, Metrics, str]]:
    with _connect() as conn:
        _ensure_v2_columns(conn)
        row = conn.execute(
            """
            SELECT gene_json, volume, height, max_width, centroid_z,
                   z_cog_suggested, bottom_curvature_radius, z_cog_max, created_at
            FROM designs WHERE design_id = ?
            """,
            (design_id,),
        ).fetchone()
    if not row:
        return None
    gene = Gene.model_validate_json(row["gene_json"])
    metrics = Metrics(
        volume=row["volume"],
        height=row["height"],
        max_width=row["max_width"],
        centroid_z=row["centroid_z"],
        z_cog_suggested=row["z_cog_suggested"],
        bottom_curvature_radius=row["bottom_curvature_radius"],
        z_cog_max=row["z_cog_max"],
    )
    return gene, metrics, row["created_at"]


def delete_all_designs() -> int:
    """全デザインをDBとファイルシステムから削除する。"""
    _ensure_dirs()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM designs").fetchone()
        count = int(row["c"]) if row else 0
        conn.execute("DELETE FROM designs")

    # 生成物（thumb/model とその smoothing キャッシュ）もすべて消す
    if ASSETS_DIR.exists():
        for child in ASSETS_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except FileNotFoundError:
                    pass
    return count
