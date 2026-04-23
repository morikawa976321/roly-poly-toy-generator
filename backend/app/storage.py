"""デザインの永続化レイヤ（Supabase Postgres）。

- メタデータ（gene / metrics / feasibility / created_at）は Supabase の `public.designs` に格納する。
- 大きい派生物（thumb.svg / 3D メッシュ / STL）はフロント側で gene から生成する。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, List, Optional, Tuple

from supabase import Client, create_client

from .config import supabase_service_role_key, supabase_url
from .models import DesignSummary, Gene, Metrics


TABLE = "designs"
logger = logging.getLogger(__name__)


def _is_unique_violation(exc: Exception) -> bool:
    """Postgres の unique_violation (SQLSTATE 23505) 相当かを雑に判定する。

    Supabase/PostgREST の Python クライアントが返す例外型/属性はバージョンで揺れるため、
    ここでは「見つけやすいヒント」を複合して判定する（安全側: 判定できなければ握らない）。
    """

    code = getattr(exc, "code", None)
    if code == "23505":
        return True

    # 例: details / message / error dict などに 23505 が含まれるケース
    for attr in ("details", "message", "error", "args"):
        try:
            val = getattr(exc, attr, None)
            if val is None:
                continue
            if "23505" in str(val):
                return True
        except Exception:
            continue

    s = str(exc).lower()
    return ("duplicate key value" in s) or ("unique constraint" in s)


@lru_cache(maxsize=1)
def _client() -> Client:
    url = supabase_url()
    key = supabase_service_role_key()
    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set")
    return create_client(url, key)


def _row_to_metrics(row: dict[str, Any]) -> Metrics:
    return Metrics(
        volume=float(row["volume"]),
        height=float(row["height"]),
        max_width=float(row["max_width"]),
        centroid_z=float(row["centroid_z"]),
        z_cog_suggested=row.get("z_cog_suggested", None),
        bottom_curvature_radius=row.get("bottom_curvature_radius", None),
        z_cog_max=row.get("z_cog_max", None),
    )


def exists(design_id: str) -> bool:
    res = (
        _client()
        .table(TABLE)
        .select("design_id")
        .eq("design_id", design_id)
        .limit(1)
        .execute()
    )
    return bool(getattr(res, "data", None))


def upsert_design(
    design_id: str,
    gene: Gene,
    metrics: Metrics,
) -> DesignSummary:
    payload = {
        "design_id": design_id,
        "gene": gene.model_dump(mode="json"),
        "volume": float(metrics.volume),
        "height": float(metrics.height),
        "max_width": float(metrics.max_width),
        "centroid_z": float(metrics.centroid_z),
        "z_cog_suggested": metrics.z_cog_suggested,
        "bottom_curvature_radius": metrics.bottom_curvature_radius,
        "z_cog_max": metrics.z_cog_max,
    }

    # 既存IDは上書きしない（Supabase/PostgREST 側の unique 制約により insert が失敗したら無視する）。
    try:
        _client().table(TABLE).insert(payload).execute()
    except Exception as e:
        # 期待される失敗: 既に同じ design_id が存在する（unique_violation）
        if _is_unique_violation(e):
            pass
        else:
            logger.exception("Failed to insert design_id=%s into %s", design_id, TABLE)
            raise

    found = get_design(design_id)
    if not found:
        raise RuntimeError("Failed to insert design")
    gene2, metrics2, created_at = found
    return DesignSummary(design_id=design_id, gene=gene2, metrics=metrics2, created_at=created_at)


def list_designs(limit: int = 100, offset: int = 0) -> Tuple[List[DesignSummary], int]:
    to_ = offset + limit - 1
    res = (
        _client()
        .table(TABLE)
        .select(
            "design_id, gene, volume, height, max_width, centroid_z, z_cog_suggested, bottom_curvature_radius, z_cog_max, created_at",
            count="exact",
        )
        .order("created_at", desc=True)
        .order("design_id", desc=True)
        .range(offset, to_)
        .execute()
    )
    total = int(getattr(res, "count", 0) or 0)
    rows = getattr(res, "data", None) or []
    out: List[DesignSummary] = []
    for r in rows:
        out.append(
            DesignSummary(
                design_id=r["design_id"],
                gene=Gene.model_validate(r["gene"]),
                metrics=_row_to_metrics(r),
                created_at=r["created_at"],
            )
        )
    return out, total


def list_designs_with_genes(
    limit: int = 100, offset: int = 0
) -> Tuple[List[Tuple[str, Gene, str]], int]:
    """gene 付きで designs を列挙する（フロントで派生物生成したい用途）。"""
    to_ = offset + limit - 1
    res = (
        _client()
        .table(TABLE)
        .select("design_id, gene, created_at", count="exact")
        .order("created_at", desc=True)
        .order("design_id", desc=True)
        .range(offset, to_)
        .execute()
    )
    total = int(getattr(res, "count", 0) or 0)
    rows = getattr(res, "data", None) or []
    out: List[Tuple[str, Gene, str]] = []
    for r in rows:
        gene = Gene.model_validate(r["gene"])
        out.append((r["design_id"], gene, r["created_at"]))
    return out, total


def get_design(design_id: str) -> Optional[Tuple[Gene, Metrics, str]]:
    res = (
        _client()
        .table(TABLE)
        .select(
            "gene, volume, height, max_width, centroid_z, z_cog_suggested, bottom_curvature_radius, z_cog_max, created_at"
        )
        .eq("design_id", design_id)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    row = rows[0]
    gene = Gene.model_validate(row["gene"])
    metrics = _row_to_metrics(row)
    return gene, metrics, row["created_at"]


def delete_all_designs() -> int:
    """全デザインを DB から削除する。"""
    count_res = _client().table(TABLE).select("design_id", count="exact").execute()
    count = int(getattr(count_res, "count", 0) or 0)
    # PostgREST はフィルタ無し DELETE を許さないことがあるため、常に true な条件を付ける
    _client().table(TABLE).delete().neq("design_id", "").execute()
    return count
