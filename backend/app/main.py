"""FastAPI アプリのエントリポイント。"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import IDLE_SHUTDOWN_SECONDS, frontend_dist_dir, load_environment


def create_app(
    *,
    static_dir: Path | None = None,
    idle_shutdown_seconds: int = IDLE_SHUTDOWN_SECONDS,
) -> FastAPI:
    # import 時の副作用を避けるため、起動境界で明示的に .env を読む。
    load_environment()

    app = FastAPI(title="roly-poly-toy-generator", version="0.0.1")
    app.state.last_access_monotonic = time.monotonic()
    app.state.idle_shutdown_seconds = idle_shutdown_seconds
    app.state.request_shutdown = None
    app.state.idle_task = None

    # 開発用 CORS: フロントエンド（Vite）は :5173 で動いて :8000 のバックエンドを叩く。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def touch_last_access(request: Request, call_next):  # type: ignore[no-untyped-def]
        app.state.last_access_monotonic = time.monotonic()
        return await call_next(request)

    async def idle_shutdown_loop() -> None:
        while True:
            await asyncio.sleep(30)
            shutdown: Callable[[], None] | None = app.state.request_shutdown
            if shutdown is None:
                continue
            elapsed = time.monotonic() - float(app.state.last_access_monotonic)
            if elapsed >= int(app.state.idle_shutdown_seconds):
                shutdown()
                return

    @app.on_event("startup")
    async def start_idle_shutdown_loop() -> None:
        app.state.idle_task = asyncio.create_task(idle_shutdown_loop())

    @app.on_event("shutdown")
    async def stop_idle_shutdown_loop() -> None:
        task: asyncio.Task | None = app.state.idle_task
        if task is not None:
            task.cancel()

    # ルータ import は環境初期化後に行う（ストレージ等が env を参照するため）。
    from .api import router as api_router

    app.include_router(api_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    dist = static_dir or frontend_dist_dir()
    index_html = dist / "index.html"
    assets_dir = dist / "assets"
    if index_html.is_file():
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        def spa_root() -> FileResponse:
            return FileResponse(index_html)

        @app.get("/{path:path}")
        def spa_fallback(path: str) -> FileResponse:
            candidate = dist / path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_html)

    return app


app = create_app()
