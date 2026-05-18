"""pytest 共通設定。

役割: テスト実行環境の import パス初期化と共有 fixture。
働き: pytest 起動時に conftest として自動読み込み。非パッケージ化リポジトリのため
リポジトリルートを sys.path 先頭に入れ backend.app を import 可能にする。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from backend.app import storage

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def docs_gene():
    """``docs/designs/6d7afe17fed27c7c/gene.json`` の参照 gene（延長・カット検証用）。"""
    from backend.app.models import Gene

    path = REPO_ROOT / "docs" / "designs" / "6d7afe17fed27c7c" / "gene.json"
    if not path.is_file():
        pytest.skip("docs design gene missing")
    return Gene.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """storage テスト用の一時 SQLite（``local_data_dir`` / ``sqlite_db_path`` を差し替え）。"""
    data_dir = tmp_path / "data"
    db_path = data_dir / "app.db"
    monkeypatch.setattr(storage, "local_data_dir", lambda: data_dir)
    monkeypatch.setattr(storage, "sqlite_db_path", lambda: db_path)
    storage.init_db.cache_clear()
    yield
    storage.init_db.cache_clear()
