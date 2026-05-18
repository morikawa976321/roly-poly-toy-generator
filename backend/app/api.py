"""
プレプロトタイプ用 HTTP API ルータ。

役割: デザイン生成・一覧・詳細・更新・全削除の REST エンドポイント。
働き: FastAPI ``APIRouter``。``gene`` / ``metrics`` / ``storage`` を呼び出し JSON を返す（generate はバックグラウンド upsert）。
"""

from __future__ import annotations

from typing import List

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from .config import BATCH_SIZE
from .gene import breed_gene_with_feasibility, sample_gene_with_feasibility
from .identify import design_id_for
from .metrics import compute_metrics
from .models import (
    DesignDetail,
    DesignSummary,
    DeleteAllResponse,
    GenerateRequest,
    GenerateResponse,
    ListResponse,
    PatchDesignRequest,
)
from .profile_extension import max_top_extension_mm
from .storage import (
    delete_all_designs,
    exists,
    get_design,
    list_designs,
    update_design,
    upsert_design,
)


router = APIRouter(prefix="/api")


async def _shutdown_after_response(request: Request) -> None:
    await asyncio.sleep(0.1)
    shutdown = getattr(request.app.state, "request_shutdown", None)
    if shutdown is not None:
        shutdown()


@router.post("/app/exit")
def exit_app(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """ローカル配布版の終了ボタンから呼ばれる終了API。"""

    background_tasks.add_task(_shutdown_after_response, request)
    return {"status": "shutting_down"}


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
        # 安全弁: 生成関数のバグ等で不成立が混入しても保存しない。
        if not feasibility.is_feasible:
            continue
        did = design_id_for(gene)
        if exists(did):
            continue
        metrics = compute_metrics(gene, feasibility=feasibility)
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


@router.patch("/designs/{design_id}", response_model=DesignDetail)
def patch_design_endpoint(
    design_id: str,
    payload: PatchDesignRequest,
) -> DesignDetail:
    found = get_design(design_id)
    if not found:
        raise HTTPException(status_code=404, detail="Design not found")
    gene, _metrics, created_at = found
    d_max = max_top_extension_mm(gene)
    ext = float(payload.top_extension_mm)
    if ext > d_max + 1e-6:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "top_extension_mm exceeds maximum",
                "max_top_extension_mm": d_max,
            },
        )
    updated_gene = gene.model_copy(
        update={
            "top_extension_mm": ext,
            "top_cut_height_mm": float(payload.top_cut_height_mm),
            "top_cut_angle_deg": float(payload.top_cut_angle_deg),
        }
    )
    updated_metrics = compute_metrics(updated_gene)
    summary = update_design(design_id, updated_gene, updated_metrics)
    if summary is None:
        raise HTTPException(status_code=404, detail="Design not found")
    return DesignDetail(
        design_id=design_id,
        gene=summary.gene,
        metrics=summary.metrics,
        created_at=created_at,
    )


@router.delete("/designs", response_model=DeleteAllResponse)
def delete_all_designs_endpoint() -> DeleteAllResponse:
    deleted = delete_all_designs()
    return DeleteAllResponse(deleted=deleted)
