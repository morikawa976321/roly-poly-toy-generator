"""API 層（`backend/app/api.py` + `backend/app/main.py`）の回帰テスト。

役割: FastAPI エンドポイントの契約・バリデーション検証。
働き: TestClient で HTTP を叩き storage は monkeypatch でモックする。
API 側のバリデーション/分岐/ループガードだけを検証する。
"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app

from tests.factories import make_gene, make_metrics


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


# ------------------------------- /health ---------------------------------


def test_health_returns_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# -------------------------- GET /api/designs/{id} -----------------------


def test_get_design_returns_404_when_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("backend.app.api.get_design", lambda _id: None)
    r = client.get("/api/designs/does-not-exist")
    assert r.status_code == 404
    assert "not found" in str(r.json().get("detail", "")).lower()


def test_get_design_response_matches_design_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    gene = make_gene()
    metrics = make_metrics()
    created_at = "2026-04-24T12:00:00+00:00"

    def fake_get_design(design_id: str):
        return (gene, metrics, created_at)

    monkeypatch.setattr("backend.app.api.get_design", fake_get_design)

    r = client.get("/api/designs/abc123")
    assert r.status_code == 200
    body = r.json()

    # DesignDetail スキーマと整合
    assert set(body.keys()) >= {"design_id", "gene", "metrics", "created_at"}
    assert body["design_id"] == "abc123"
    assert body["gene"] == gene.model_dump(mode="json")
    assert body["metrics"]["volume"] == metrics.volume
    assert "z_cog_suggested" not in body["metrics"]
    assert body["created_at"] == created_at


def test_patch_design_updates_extension(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.app.profile_extension import max_top_extension_mm

    gene = make_gene(top_extension_mm=0.0)
    metrics = make_metrics()
    created_at = "2026-04-24T12:00:00+00:00"
    stored = {"gene": gene, "metrics": metrics}

    def fake_get_design(design_id: str):
        if design_id != "abc123":
            return None
        return (stored["gene"], stored["metrics"], created_at)

    def fake_update(design_id: str, g, m):
        stored["gene"] = g
        stored["metrics"] = m
        from backend.app.models import DesignSummary

        return DesignSummary(
            design_id=design_id, gene=g, metrics=m, created_at=created_at
        )

    monkeypatch.setattr("backend.app.api.get_design", fake_get_design)
    monkeypatch.setattr("backend.app.api.update_design", fake_update)

    from backend.app.gene import sample_gene

    rich_gene = sample_gene(seed=42)
    rich_gene = rich_gene.model_copy(update={"top_extension_mm": 0.0})
    stored["gene"] = rich_gene
    stored["metrics"] = make_metrics(height=float(rich_gene.height))

    d_max = max_top_extension_mm(rich_gene)
    assert d_max > 0.5
    ext = min(1.0, d_max)
    r = client.patch(
        "/api/designs/abc123",
        json={
            "top_extension_mm": ext,
            "top_cut_height_mm": 0.0,
            "top_cut_angle_deg": 0.0,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["gene"]["top_extension_mm"] == ext
    assert body["metrics"]["height"] > float(rich_gene.height)


# ------------------------ POST /api/designs/generate --------------------


def test_generate_rejects_too_many_parent_ids(client: TestClient) -> None:
    """parent_ids が 4 を超えた場合はリクエスト時点で拒否される。

    実装上は Pydantic の max_length=4 バリデーションが先に働くため 422、
    そこを通り抜けても api.py の明示チェックで 400 になる。どちらでも
    「4 超を受け付けない」という契約は満たす。
    """
    r = client.post(
        "/api/designs/generate",
        json={"n": 1, "parent_ids": ["a", "b", "c", "d", "e"]},
    )
    assert r.status_code in (400, 422)


def test_generate_returns_400_with_missing_parents(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    present_gene = make_gene()
    present_metrics = make_metrics()

    def fake_get_design(pid: str):
        if pid == "present":
            return (present_gene, present_metrics, "2026-04-24T12:00:00+00:00")
        return None

    monkeypatch.setattr("backend.app.api.get_design", fake_get_design)

    r = client.post(
        "/api/designs/generate",
        json={"n": 1, "parent_ids": ["present", "missing-1", "missing-2"]},
    )
    assert r.status_code == 400

    detail = r.json()["detail"]
    # detail は {"message": "...", "missing": [...]} の構造
    assert isinstance(detail, dict)
    assert "missing" in detail
    assert set(detail["missing"]) == {"missing-1", "missing-2"}


def test_generate_terminates_when_ids_always_collide(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`exists()` が常に True を返す（= 常に ID 衝突）状況でも、
    endpoint は max_attempts ガードで有限時間で終了しなければならない。

    無限ループ回帰防止のガードテスト（`max_attempts = n * 4`）。
    """

    call_count = {"exists": 0, "upsert": 0}

    def fake_exists(_design_id: str) -> bool:
        call_count["exists"] += 1
        return True

    def fake_upsert(*_args, **_kwargs):  # noqa: ANN002, ANN003
        # 常に衝突するので呼ばれてはいけない
        call_count["upsert"] += 1
        raise AssertionError("upsert_design must not be called when ids always collide")

    monkeypatch.setattr("backend.app.api.exists", fake_exists)
    monkeypatch.setattr("backend.app.api.upsert_design", fake_upsert)

    r = client.post("/api/designs/generate", json={"n": 2})
    assert r.status_code == 200
    assert r.json() == {"designs": []}
    # max_attempts = n * 4 = 8 回以下しか exists() を呼ばない
    assert call_count["exists"] <= 8
    assert call_count["upsert"] == 0
