"""デザインの永続化レイヤ（ローカル SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterator, List, Optional, Tuple

from .config import local_data_dir, sqlite_db_path
from .models import DesignSummary, Gene, Metrics


TABLE = "designs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@lru_cache(maxsize=1)
def init_db() -> None:
    """SQLite DB とスキーマを初期化する。"""

    local_data_dir().mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(sqlite_db_path()) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                design_id TEXT PRIMARY KEY,
                gene_json TEXT NOT NULL,
                volume REAL NOT NULL,
                height REAL NOT NULL,
                max_width REAL NOT NULL,
                centroid_z REAL NOT NULL,
                z_cog_suggested REAL,
                bottom_curvature_radius REAL,
                z_cog_max REAL,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            f"""
            CREATE INDEX IF NOT EXISTS designs_created_at_idx
            ON {TABLE} (created_at DESC, design_id DESC)
            """
        )


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    init_db()
    con = sqlite3.connect(sqlite_db_path())
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _row_to_metrics(row: dict[str, Any]) -> Metrics:
    return Metrics(
        volume=float(row["volume"]),
        height=float(row["height"]),
        max_width=float(row["max_width"]),
        centroid_z=float(row["centroid_z"]),
        bottom_curvature_radius=row.get("bottom_curvature_radius", None),
        z_cog_max=row.get("z_cog_max", None),
    )


def exists(design_id: str) -> bool:
    with _connect() as con:
        row = con.execute(
            f"SELECT 1 FROM {TABLE} WHERE design_id = ? LIMIT 1",
            (design_id,),
        ).fetchone()
    return row is not None


def upsert_design(
    design_id: str,
    gene: Gene,
    metrics: Metrics,
) -> DesignSummary:
    payload = (
        design_id,
        json.dumps(gene.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")),
        float(metrics.volume),
        float(metrics.height),
        float(metrics.max_width),
        float(metrics.centroid_z),
        None,
        metrics.bottom_curvature_radius,
        metrics.z_cog_max,
        _now_iso(),
    )

    # 既存IDは上書きしない。SQLite の INSERT OR IGNORE で冪等にする。
    with _connect() as con:
        con.execute(
            f"""
            INSERT OR IGNORE INTO {TABLE}
              (design_id, gene_json, volume, height, max_width, centroid_z,
               z_cog_suggested, bottom_curvature_radius, z_cog_max, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )

    found = get_design(design_id)
    if not found:
        raise RuntimeError("Failed to insert design")
    gene2, metrics2, created_at = found
    return DesignSummary(design_id=design_id, gene=gene2, metrics=metrics2, created_at=created_at)


def list_designs(limit: int = 100, offset: int = 0) -> Tuple[List[DesignSummary], int]:
    with _connect() as con:
        total = int(con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0])
        rows = con.execute(
            f"""
            SELECT design_id, gene_json, volume, height, max_width, centroid_z,
                   z_cog_suggested, bottom_curvature_radius, z_cog_max, created_at
            FROM {TABLE}
            ORDER BY created_at DESC, design_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    out: List[DesignSummary] = []
    for r in rows:
        out.append(
            DesignSummary(
                design_id=r["design_id"],
                gene=Gene.model_validate(json.loads(r["gene_json"])),
                metrics=_row_to_metrics(dict(r)),
                created_at=r["created_at"],
            )
        )
    return out, total


def list_designs_with_genes(
    limit: int = 100, offset: int = 0
) -> Tuple[List[Tuple[str, Gene, str]], int]:
    """gene 付きで designs を列挙する（フロントで派生物生成したい用途）。"""
    with _connect() as con:
        total = int(con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0])
        rows = con.execute(
            f"""
            SELECT design_id, gene_json, created_at
            FROM {TABLE}
            ORDER BY created_at DESC, design_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    out: List[Tuple[str, Gene, str]] = []
    for r in rows:
        gene = Gene.model_validate(json.loads(r["gene_json"]))
        out.append((r["design_id"], gene, r["created_at"]))
    return out, total


def get_design(design_id: str) -> Optional[Tuple[Gene, Metrics, str]]:
    with _connect() as con:
        row = con.execute(
            f"""
            SELECT gene_json, volume, height, max_width, centroid_z,
                   z_cog_suggested, bottom_curvature_radius, z_cog_max, created_at
            FROM {TABLE}
            WHERE design_id = ?
            LIMIT 1
            """,
            (design_id,),
        ).fetchone()
    if row is None:
        return None
    gene = Gene.model_validate(json.loads(row["gene_json"]))
    metrics = _row_to_metrics(dict(row))
    return gene, metrics, row["created_at"]


def delete_all_designs() -> int:
    """全デザインを DB から削除する。"""
    with _connect() as con:
        count = int(con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0])
        con.execute(f"DELETE FROM {TABLE}")
    return count


def update_design(
    design_id: str,
    gene: Gene,
    metrics: Metrics,
) -> Optional[DesignSummary]:
    """既存デザインの gene / metrics を上書きする（design_id / created_at は不変）。"""
    with _connect() as con:
        row = con.execute(
            f"SELECT created_at FROM {TABLE} WHERE design_id = ? LIMIT 1",
            (design_id,),
        ).fetchone()
        if row is None:
            return None
        created_at = row["created_at"]
        con.execute(
            f"""
            UPDATE {TABLE}
            SET gene_json = ?,
                volume = ?,
                height = ?,
                max_width = ?,
                centroid_z = ?,
                bottom_curvature_radius = ?,
                z_cog_max = ?
            WHERE design_id = ?
            """,
            (
                json.dumps(gene.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")),
                float(metrics.volume),
                float(metrics.height),
                float(metrics.max_width),
                float(metrics.centroid_z),
                metrics.bottom_curvature_radius,
                metrics.z_cog_max,
                design_id,
            ),
        )
    return DesignSummary(
        design_id=design_id,
        gene=gene,
        metrics=metrics,
        created_at=created_at,
    )
