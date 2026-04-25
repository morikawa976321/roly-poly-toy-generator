"""`backend/app/storage.py` の例外ハンドリング境界のテスト。

実 DB には繋がず、`_client()` を monkeypatch でフェイクに差し替えて
`upsert_design` の分岐（unique_violation を握る / それ以外は再送出）と
`_is_unique_violation` のヒューリスティックだけを検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.app import storage
from backend.app.models import Gene, Metrics


# ----------------------------- helpers -----------------------------------


def _make_gene() -> Gene:
    return Gene(
        version=2,
        N=5,
        height=30.0,
        bottom_radius=0.0,
        radii=[0.0, 5.0, 10.0, 5.0, 0.0],
        z_warp=2.0,
    )


def _make_metrics() -> Metrics:
    return Metrics(
        volume=100.0,
        height=30.0,
        max_width=20.0,
        centroid_z=10.0,
    )


# --------------------- _is_unique_violation -----------------------------


def test_is_unique_violation_detects_code_23505_attribute() -> None:
    class E(Exception):
        code = "23505"

    assert storage._is_unique_violation(E()) is True


def test_is_unique_violation_detects_23505_in_args() -> None:
    e = Exception("boom", {"error": "violates", "pg_code": "23505"})
    assert storage._is_unique_violation(e) is True


def test_is_unique_violation_detects_23505_in_details_attribute() -> None:
    class E(Exception):
        details = "SQLSTATE 23505: duplicate"

    assert storage._is_unique_violation(E()) is True


def test_is_unique_violation_detects_duplicate_key_value_message() -> None:
    e = RuntimeError(
        'duplicate key value violates unique constraint "designs_pkey"'
    )
    assert storage._is_unique_violation(e) is True


def test_is_unique_violation_detects_unique_constraint_message() -> None:
    e = RuntimeError("ERROR: new row violates UNIQUE constraint on design_id")
    assert storage._is_unique_violation(e) is True


def test_is_unique_violation_false_for_unrelated_errors() -> None:
    assert storage._is_unique_violation(RuntimeError("connection refused")) is False
    assert storage._is_unique_violation(ValueError("bad payload")) is False


# --------------------------- upsert_design ------------------------------


def _patch_fake_client_raising(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> MagicMock:
    """`_client().table(TABLE).insert(...).execute()` が `exc` を投げる
    フェイクに差し替える。"""
    fake_table = MagicMock()
    fake_table.insert.return_value.execute.side_effect = exc
    fake_client = MagicMock()
    fake_client.table.return_value = fake_table
    monkeypatch.setattr(storage, "_client", lambda: fake_client)
    return fake_client


def test_upsert_design_swallows_unique_violation_and_returns_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unique_violation は「既存行が居た」と解釈し、
    後続の get_design で拾った既存行を返す。"""

    class UniqueViolation(Exception):
        code = "23505"

    _patch_fake_client_raising(monkeypatch, UniqueViolation())

    gene = _make_gene()
    metrics = _make_metrics()
    created_at = "2026-04-24T12:00:00+00:00"

    def fake_get_design(design_id: str):
        # 既に DB にある行を返すフェイク
        return (gene, metrics, created_at)

    monkeypatch.setattr(storage, "get_design", fake_get_design)

    summary = storage.upsert_design("dup-id", gene, metrics)

    assert summary.design_id == "dup-id"
    assert summary.created_at == created_at
    assert summary.gene.model_dump() == gene.model_dump()


def test_upsert_design_reraises_non_unique_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fake_client_raising(monkeypatch, RuntimeError("connection refused"))

    # unique 以外の失敗時は get_design に到達せず raise される
    called = {"get_design": 0}

    def fake_get_design(_id: str):
        called["get_design"] += 1
        return None

    monkeypatch.setattr(storage, "get_design", fake_get_design)

    with pytest.raises(RuntimeError, match="connection refused"):
        storage.upsert_design("x", _make_gene(), _make_metrics())

    assert called["get_design"] == 0


def test_upsert_design_raises_when_row_disappears_after_unique_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unique_violation を握った後、get_design が None を返した場合は、
    整合性が壊れているので RuntimeError を投げる。"""

    class UniqueViolation(Exception):
        code = "23505"

    _patch_fake_client_raising(monkeypatch, UniqueViolation())
    monkeypatch.setattr(storage, "get_design", lambda _id: None)

    with pytest.raises(RuntimeError, match="Failed to insert design"):
        storage.upsert_design("ghost", _make_gene(), _make_metrics())
