"""pytest 共通設定。

このリポジトリはパッケージ化していない（`tool.uv.package = false`）ので、
``backend.app.xxx`` を import するためにリポジトリルートを ``sys.path`` の
先頭に入れる必要がある。pytest 起動時に自動で読み込まれる conftest でこれを行う。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
