"""`backend/app/storage.py` のローカル SQLite 永続化テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import storage
from backend.app.models import Gene, Metrics


# ----------------------------- helpers -----------------------------------


def _make_gene(**overrides) -> Gene:
    data = dict(
        version=2,
        N=5,
        height=30.0,
        bottom_radius=0.0,
        radii=[0.0, 5.0, 10.0, 5.0, 0.0],
        z_warp=2.0,
    )
    data.update(overrides)
    return Gene(**data)


def _make_metrics(**overrides) -> Metrics:
    data = dict(
        volume=100.0,
        height=30.0,
        max_width=20.0,
        centroid_z=10.0,
    )
    data.update(overrides)
    return Metrics(**data)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    db_path = data_dir / "app.db"
    monkeypatch.setattr(storage, "local_data_dir", lambda: data_dir)
    monkeypatch.setattr(storage, "sqlite_db_path", lambda: db_path)
    storage.init_db.cache_clear()
    yield
    storage.init_db.cache_clear()


def test_upsert_design_inserts_and_gets_row() -> None:
    gene = _make_gene()
    metrics = _make_metrics()

    summary = storage.upsert_design("id-1", gene, metrics)
    found = storage.get_design("id-1")

    assert summary.design_id == "id-1"
    assert found is not None
    found_gene, found_metrics, created_at = found
    assert found_gene.model_dump() == gene.model_dump()
    assert found_metrics.volume == metrics.volume
    assert created_at.endswith("Z")


def test_upsert_design_does_not_overwrite_existing_row() -> None:
    gene = _make_gene()
    metrics = _make_metrics(volume=100.0)
    updated = _make_metrics(volume=999.0)

    first = storage.upsert_design("same-id", gene, metrics)
    second = storage.upsert_design("same-id", gene, updated)

    assert second.created_at == first.created_at
    assert second.metrics.volume == 100.0


def test_list_designs_and_delete_all() -> None:
    storage.upsert_design("a", _make_gene(height=30.0), _make_metrics(height=30.0))
    storage.upsert_design("b", _make_gene(height=40.0), _make_metrics(height=40.0))

    items, total = storage.list_designs(limit=10, offset=0)

    assert total == 2
    assert {item.design_id for item in items} == {"a", "b"}
    assert storage.delete_all_designs() == 2
    assert storage.list_designs(limit=10, offset=0) == ([], 0)
