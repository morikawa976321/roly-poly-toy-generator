"""プレプロトタイプ用の HTTP API。

エンドポイント:
    POST /api/designs/generate  -> N 個のデザインを生成し、サマリを返す
    GET  /api/designs           -> 一覧（新しい順、ページング対応）
    GET  /api/designs/{id}      -> 詳細（gene・metrics・アセット URL）
    GET  /api/designs/{id}/thumb.svg
    GET  /api/designs/{id}/model.glb
    GET  /api/designs/{id}/model.stl
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from .config import BATCH_SIZE
from .gene import breed_gene_with_feasibility, sample_gene_with_feasibility
from .geometry import build_revolve_mesh, compute_metrics, export_glb, export_stl
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
    model_path,
    stl_path,
    thumb_path,
    upsert_design,
)
from .thumbnail import render_thumbnail_svg


router = APIRouter(prefix="/api")


def _asset_urls(design_id: str) -> tuple[str, str]:
    return (
        f"/api/designs/{design_id}/thumb.svg",
        f"/api/designs/{design_id}/model.glb",
    )


def _ensure_thumb(design_id: str) -> "FileResponse":
    path = thumb_path(design_id)
    if path.exists():
        return FileResponse(path, media_type="image/svg+xml")

    found = get_design(design_id)
    if not found:
        raise HTTPException(status_code=404, detail="Design not found")
    gene, metrics_stored, _ = found
    # サムネは重心（centroid_z）が smoothing に依存するため再計算するが、
    # 青十字の基準である z_cog_max など feasibility 由来の値は smoothing 非依存なので引き継ぐ。
    metrics = compute_metrics(gene).model_copy(
        update={
            "z_cog_suggested": metrics_stored.z_cog_suggested,
            "bottom_curvature_radius": metrics_stored.bottom_curvature_radius,
            "z_cog_max": metrics_stored.z_cog_max,
        }
    )
    svg = render_thumbnail_svg(gene, metrics)
    path.write_text(svg, encoding="utf-8")
    return FileResponse(path, media_type="image/svg+xml")


def _ensure_model(design_id: str) -> "FileResponse":
    path = model_path(design_id)
    if not path.exists():
        found = get_design(design_id)
        if not found:
            raise HTTPException(status_code=404, detail="Design not found")
        gene, _metrics_stored, _ = found
        mesh = build_revolve_mesh(gene)
        path.write_bytes(export_glb(mesh))
    return FileResponse(path, media_type="model/gltf-binary")


def _ensure_stl(design_id: str) -> "FileResponse":
    path = stl_path(design_id)
    if not path.exists():
        found = get_design(design_id)
        if not found:
            raise HTTPException(status_code=404, detail="Design not found")
        gene, _metrics_stored, _ = found
        mesh = build_revolve_mesh(gene)
        path.write_bytes(export_stl(mesh))
    return FileResponse(path, media_type="model/stl")


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
        mesh = build_revolve_mesh(gene)
        glb = export_glb(mesh)
        svg = render_thumbnail_svg(gene, metrics)
        summary = upsert_design(did, gene, metrics, svg, glb)
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
    gene, metrics_baseline, created_at = found
    metrics = metrics_baseline
    thumb_url, model_url = _asset_urls(design_id)
    return DesignDetail(
        design_id=design_id,
        gene=gene,
        metrics=metrics,
        created_at=created_at,
        thumbnail_url=thumb_url,
        model_url=model_url,
    )


@router.get("/designs/{design_id}/thumb.svg")
def get_thumb(
    design_id: str,
) -> FileResponse:
    if not exists(design_id):
        raise HTTPException(status_code=404, detail="Design not found")
    return _ensure_thumb(design_id)


@router.get("/designs/{design_id}/model.glb")
def get_model(
    design_id: str,
) -> FileResponse:
    if not exists(design_id):
        raise HTTPException(status_code=404, detail="Design not found")
    return _ensure_model(design_id)


@router.get("/designs/{design_id}/model.stl")
def get_stl(
    design_id: str,
) -> FileResponse:
    if not exists(design_id):
        raise HTTPException(status_code=404, detail="Design not found")
    return _ensure_stl(design_id)


@router.delete("/designs", response_model=DeleteAllResponse)
def delete_all_designs_endpoint() -> DeleteAllResponse:
    deleted = delete_all_designs()
    return DeleteAllResponse(deleted=deleted)
