"""プレプロトタイプ用の HTTP API。

エンドポイント:
    POST /api/designs/generate  -> N 個のデザインを生成し、サマリを返す
    GET  /api/designs           -> 一覧（新しい順、ページング対応）
    GET  /api/designs/{id}      -> 詳細（gene・metrics）
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query

from .config import BATCH_SIZE
from .gene import breed_gene_with_feasibility, sample_gene_with_feasibility
from .geometry import compute_metrics
from .identify import design_id_for
from .models import (
    DesignDetail,
    DesignSummary,
    DeleteAllResponse,
    GenerateRequest,
    GenerateResponse,
    ListResponse,
)
from .storage import (
    delete_all_designs,
    exists,
    get_design,
    list_designs,
    upsert_design,
)


router = APIRouter(prefix="/api")


@router.post("/designs/generate", response_model=GenerateResponse)
def generate_designs(payload: GenerateRequest | None = None) -> GenerateResponse:
    n = (payload.n if payload and payload.n else BATCH_SIZE)
    parent_ids = (payload.parent_ids if payload and payload.parent_ids else None)
    created: List[DesignSummary] = []

    parents = None
    if parent_ids:
        if len(parent_ids) > 4:
            raise HTTPException(status_code=400, detail="Too many parents (max 4)")
        missing: List[str] = []
        genes = []
        for pid in parent_ids:
            found = get_design(pid)
            if not found:
                missing.append(pid)
                continue
            gene, _metrics, _created_at = found
            genes.append(gene)
        if missing:
            raise HTTPException(
                status_code=400,
                detail={"message": "Parent design(s) not found", "missing": missing},
            )
        parents = genes

    attempts = 0
    max_attempts = n * 4  # まれに design_id が衝突したときに無限ループしないためのガード
    while len(created) < n and attempts < max_attempts:
        attempts += 1
        if parents:
            gene, feasibility = breed_gene_with_feasibility(parents)
        else:
            gene, feasibility = sample_gene_with_feasibility()
        did = design_id_for(gene)
        if exists(did):
            continue
        metrics = compute_metrics(gene)
        # 生成時に計算した feasibility（密パラメトリックプロファイル上の正確な値）
        # を metrics に詰めて保存する。radii 経由で後から再計算するより精度が高い。
        metrics = metrics.model_copy(update={
            "z_cog_suggested": feasibility.suggested_z_cog,
            "bottom_curvature_radius": feasibility.rho_m_bottom,
            "z_cog_max": feasibility.z_cog_max,
        })
        summary = upsert_design(did, gene, metrics)
        created.append(summary)

    return GenerateResponse(designs=created)


@router.get("/designs", response_model=ListResponse)
def list_designs_endpoint(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ListResponse:
    items, total = list_designs(limit=limit, offset=offset)
    return ListResponse(designs=items, total=total)


@router.get("/designs/{design_id}", response_model=DesignDetail)
def get_design_endpoint(
    design_id: str,
) -> DesignDetail:
    found = get_design(design_id)
    if not found:
        raise HTTPException(status_code=404, detail="Design not found")
    gene, metrics, created_at = found
    return DesignDetail(
        design_id=design_id,
        gene=gene,
        metrics=metrics,
        created_at=created_at,
    )


@router.delete("/designs", response_model=DeleteAllResponse)
def delete_all_designs_endpoint() -> DeleteAllResponse:
    deleted = delete_all_designs()
    return DeleteAllResponse(deleted=deleted)
