"""FastAPI アプリのエントリポイント。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import load_environment


def create_app() -> FastAPI:
    # import 時の副作用を避けるため、起動境界で明示的に .env を読む。
    load_environment()

    app = FastAPI(title="roly-poly-toy-generator", version="0.0.1")

    # 開発用 CORS: フロントエンド（Vite）は :5173 で動いて :8000 のバックエンドを叩く。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ルータ import は環境初期化後に行う（ストレージ等が env を参照するため）。
    from .api import router as api_router

    app.include_router(api_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
