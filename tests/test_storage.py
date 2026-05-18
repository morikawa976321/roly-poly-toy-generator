"""`backend/app/storage.py` のローカル SQLite 永続化テスト。

役割: storage レイヤの CRUD 契約検証。
働き: 一時 DB fixture で upsert/list/delete の決定性と既存行の上書き防止を確認する。
"""

from __future__ import annotations

import pytest

from backend.app import storage

from tests.factories import make_gene, make_metrics

pytestmark = pytest.mark.usefixtures("isolated_db")


def test_upsert_design_inserts_and_gets_row() -> None:
    gene = make_gene()
    metrics = make_metrics()

    summary = storage.upsert_design("id-1", gene, metrics)
    found = storage.get_design("id-1")

    assert summary.design_id == "id-1"
    assert found is not None
    found_gene, found_metrics, created_at = found
    assert found_gene.model_dump() == gene.model_dump()
    assert found_metrics.volume == metrics.volume
    assert created_at.endswith("Z")


def test_upsert_design_does_not_overwrite_existing_row() -> None:
    gene = make_gene()
    metrics = make_metrics(volume=100.0)
    updated = make_metrics(volume=999.0)

    first = storage.upsert_design("same-id", gene, metrics)
    second = storage.upsert_design("same-id", gene, updated)

    assert second.created_at == first.created_at
    assert second.metrics.volume == 100.0


def test_list_designs_and_delete_all() -> None:
    storage.upsert_design("a", make_gene(height=30.0), make_metrics(height=30.0))
    storage.upsert_design("b", make_gene(height=40.0), make_metrics(height=40.0))

    items, total = storage.list_designs(limit=10, offset=0)

    assert total == 2
    assert {item.design_id for item in items} == {"a", "b"}
    assert storage.delete_all_designs() == 2
    assert storage.list_designs(limit=10, offset=0) == ([], 0)
