"""プレプロトタイプ用の HTTP API。

エンドポイント:
    POST /api/designs/generate  -> N 個のデザインを生成し、サマリを返す
    GET  /api/designs           -> 一覧（新しい順、ページング対応）
    GET  /api/designs/{id}      -> 詳細（gene・metrics・アセット URL）
    GET  /api/designs/{id}/thumb.svg
    GET  /api/designs/{id}/model.glb
    GET  /api/designs/{id}/model.stl

``smoothing`` クエリ（bspline|gaussian）で曲線生成ロジックを切り替えて比較できる。
代表（bspline）以外の指定時は、ディスクに <method> 付きキャッシュアセットを書き出し、
以降はキャッシュから返す。
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
from .smoothing import SmoothingMethod
from .storage import (
    delete_all_designs,
    exists,
    get_design,
    list_designs,
    list_designs_with_genes,
    model_path,
    stl_path,
    thumb_path,
    upsert_design,
)
from .thumbnail import render_thumbnail_svg


router = APIRouter(prefix="/api")


def _asset_urls(design_id: str, method: SmoothingMethod) -> tuple[str, str]:
    # 代表（BSPLINE）はクエリ無し。追加方式はクエリ付きで返し、フロント側でそのまま使えるようにする。
    suffix = "" if method == SmoothingMethod.BSPLINE else f"?smoothing={method.value}"
    return (
        f"/api/designs/{design_id}/thumb.svg{suffix}",
        f"/api/designs/{design_id}/model.glb{suffix}",
    )


def _ensure_thumb(design_id: str, method: SmoothingMethod) -> "FileResponse":
    path = thumb_path(design_id, method)
    if path.exists():
        # 代表（BSPLINE）は既存キャッシュをそのまま使う。
        if method == SmoothingMethod.BSPLINE:
            return FileResponse(path, media_type="image/svg+xml")

        # 以前の実装で作られた gaussian キャッシュは青十字が欠ける場合がある。
        # "#3b82f6"（青十字の色）が無いときは再生成して置き換える。
        try:
            cached = path.read_text(encoding="utf-8")
        except Exception:
            cached = ""
        if "#3b82f6" in cached:
            return FileResponse(path, media_type="image/svg+xml")

    found = get_design(design_id)
    if not found:
        raise HTTPException(status_code=404, detail="Design not found")
    gene, metrics_stored, _ = found
    # サムネは重心（centroid_z）が smoothing に依存するため再計算するが、
    # 青十字の基準である z_cog_max など feasibility 由来の値は smoothing 非依存なので引き継ぐ。
    metrics = compute_metrics(gene, method).model_copy(
        update={
            "z_cog_suggested": metrics_stored.z_cog_suggested,
            "bottom_curvature_radius": metrics_stored.bottom_curvature_radius,
            "z_cog_max": metrics_stored.z_cog_max,
        }
    )
    svg = render_thumbnail_svg(gene, metrics, method)
    path.write_text(svg, encoding="utf-8")
    return FileResponse(path, media_type="image/svg+xml")


def _ensure_model(design_id: str, method: SmoothingMethod) -> "FileResponse":
    path = model_path(design_id, method)
    if not path.exists():
        found = get_design(design_id)
        if not found:
            raise HTTPException(status_code=404, detail="Design not found")
        gene, _metrics_stored, _ = found
        mesh = build_revolve_mesh(gene, method)
        path.write_bytes(export_glb(mesh))
    return FileResponse(path, media_type="model/gltf-binary")


def _ensure_stl(design_id: str, method: SmoothingMethod) -> "FileResponse":
    path = stl_path(design_id, method)
    if not path.exists():
        found = get_design(design_id)
        if not found:
            raise HTTPException(status_code=404, detail="Design not found")
        gene, _metrics_stored, _ = found
        mesh = build_revolve_mesh(gene, method)
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
        # 保存時は常に代表（BSPLINE）ベースの metrics・アセットで代表とする
        # （ID や DB 上の体積などを滑らか化方式に依存させないため）。
        metrics = compute_metrics(gene, SmoothingMethod.BSPLINE)
        # 生成時に計算した feasibility（密パラメトリックプロファイル上の正確な値）
        # を metrics に詰めて保存する。radii 経由で後から再計算するより精度が高い。
        metrics = metrics.model_copy(update={
            "z_cog_suggested": feasibility.suggested_z_cog,
            "bottom_curvature_radius": feasibility.rho_m_bottom,
            "z_cog_max": feasibility.z_cog_max,
        })
        mesh = build_revolve_mesh(gene, SmoothingMethod.BSPLINE)
        glb = export_glb(mesh)
        svg = render_thumbnail_svg(gene, metrics, SmoothingMethod.BSPLINE)
        summary = upsert_design(did, gene, metrics, svg, glb)
        created.append(summary)

    return GenerateResponse(designs=created)


@router.get("/designs", response_model=ListResponse)
def list_designs_endpoint(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    smoothing: SmoothingMethod = Query(default=SmoothingMethod.BSPLINE),
) -> ListResponse:
    # 代表（BSPLINE）は DB に保存済みの集計列をそのまま返す（安いパス）。
    if smoothing == SmoothingMethod.BSPLINE:
        items, total = list_designs(limit=limit, offset=offset)
        return ListResponse(designs=items, total=total)

    # 非 LINEAR は、保存されている全 gene を取り出して metrics を再計算する。
    # compute_metrics は polynomial 評価 + 円錐台積和のみで数ミリ秒／件なので、
    # 数百件規模のギャラリーなら同期で十分速い。
    # feasibility 関連の値（z_cog_suggested, bottom_curvature_radius）は
    # smoothing 非依存の形状プロパティなので、代表（BSPLINE）時の DB 値も併読して引き継ぐ。
    rows, total = list_designs_with_genes(limit=limit, offset=offset)
    stored_items, _ = list_designs(limit=limit, offset=offset)
    stored_by_id = {s.design_id: s.metrics for s in stored_items}
    items: List[DesignSummary] = []
    for did, gene, created_at in rows:
        m = compute_metrics(gene, smoothing)
        stored = stored_by_id.get(did)
        if stored is not None:
            m = m.model_copy(update={
                "z_cog_suggested": stored.z_cog_suggested,
                "bottom_curvature_radius": stored.bottom_curvature_radius,
                "z_cog_max": stored.z_cog_max,
            })
        items.append(DesignSummary(design_id=did, metrics=m, created_at=created_at))
    return ListResponse(designs=items, total=total)


@router.get("/designs/{design_id}", response_model=DesignDetail)
def get_design_endpoint(
    design_id: str,
    smoothing: SmoothingMethod = Query(default=SmoothingMethod.BSPLINE),
) -> DesignDetail:
    found = get_design(design_id)
    if not found:
        raise HTTPException(status_code=404, detail="Design not found")
    gene, metrics_baseline, created_at = found
    # 代表以外のときは metrics を計算し直し、リアルタイムに差分を観察できるようにする。
    # feasibility 関連は smoothing 非依存なので DB 値を引き継ぐ。
    if smoothing == SmoothingMethod.BSPLINE:
        metrics = metrics_baseline
    else:
        metrics = compute_metrics(gene, smoothing).model_copy(update={
            "z_cog_suggested": metrics_baseline.z_cog_suggested,
            "bottom_curvature_radius": metrics_baseline.bottom_curvature_radius,
            "z_cog_max": metrics_baseline.z_cog_max,
        })
    thumb_url, model_url = _asset_urls(design_id, smoothing)
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
    smoothing: SmoothingMethod = Query(default=SmoothingMethod.BSPLINE),
) -> FileResponse:
    if not exists(design_id):
        raise HTTPException(status_code=404, detail="Design not found")
    return _ensure_thumb(design_id, smoothing)


@router.get("/designs/{design_id}/model.glb")
def get_model(
    design_id: str,
    smoothing: SmoothingMethod = Query(default=SmoothingMethod.BSPLINE),
) -> FileResponse:
    if not exists(design_id):
        raise HTTPException(status_code=404, detail="Design not found")
    return _ensure_model(design_id, smoothing)


@router.get("/designs/{design_id}/model.stl")
def get_stl(
    design_id: str,
    smoothing: SmoothingMethod = Query(default=SmoothingMethod.BSPLINE),
) -> FileResponse:
    if not exists(design_id):
        raise HTTPException(status_code=404, detail="Design not found")
    return _ensure_stl(design_id, smoothing)


@router.delete("/designs", response_model=DeleteAllResponse)
def delete_all_designs_endpoint() -> DeleteAllResponse:
    deleted = delete_all_designs()
    return DeleteAllResponse(deleted=deleted)
