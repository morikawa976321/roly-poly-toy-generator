"""storage.update_design の部分更新テスト。

役割: PATCH 相当の DB 更新パスの検証。
働き: update_design が created_at を保持し、gene/metrics の変更が永続化されることを確認する。
"""

from __future__ import annotations

import pytest

from backend.app import storage
from backend.app.metrics import compute_metrics
from backend.app.profile_extension import max_top_extension_mm

pytestmark = pytest.mark.usefixtures("isolated_db")


def test_update_design_preserves_created_at(docs_gene) -> None:
    gene = docs_gene
    metrics = compute_metrics(gene)
    ext = min(1.0, max_top_extension_mm(gene))
    first = storage.upsert_design("id-1", gene, metrics)
    updated_gene = gene.model_copy(
        update={
            "top_extension_mm": ext,
            "top_cut_height_mm": 0.0,
            "top_cut_angle_deg": 0.0,
        }
    )
    updated_metrics = compute_metrics(updated_gene)
    second = storage.update_design("id-1", updated_gene, updated_metrics)
    assert second is not None
    assert second.created_at == first.created_at
    found = storage.get_design("id-1")
    assert found is not None
    g, m, _ = found
    assert g.top_extension_mm == ext
    assert m.height > metrics.height
