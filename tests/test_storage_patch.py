from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import storage
from backend.app.metrics import compute_metrics
from backend.app.models import Gene, Metrics


def _make_gene(**overrides) -> Gene:
    data = dict(
        version=2,
        N=5,
        height=30.0,
        bottom_radius=0.0,
        radii=[0.0, 5.0, 10.0, 5.0, 2.0],
        z_warp=2.0,
        top_extension_mm=0.0,
        top_cut_height_mm=0.0,
        top_cut_angle_deg=0.0,
    )
    data.update(overrides)
    return Gene(**data)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    db_path = data_dir / "app.db"
    monkeypatch.setattr(storage, "local_data_dir", lambda: data_dir)
    monkeypatch.setattr(storage, "sqlite_db_path", lambda: db_path)
    storage.init_db.cache_clear()
    yield
    storage.init_db.cache_clear()


def test_update_design_preserves_created_at() -> None:
    gene = _make_gene()
    metrics = compute_metrics(gene)
    first = storage.upsert_design("id-1", gene, metrics)
    updated_gene = gene.model_copy(
        update={
            "top_extension_mm": 1.0,
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
    assert g.top_extension_mm == 1.0
    assert m.height > metrics.height
