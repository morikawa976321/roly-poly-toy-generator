"""FastAPI アプリのエントリポイント。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router as api_router
from .storage import init_db


def create_app() -> FastAPI:
    app = FastAPI(title="roly-poly-toy-generator", version="0.0.1")

    # 開発用 CORS: フロントエンド（Vite）は :5173 で動いて :8000 のバックエンドを叩く。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    init_db()
    app.include_router(api_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
