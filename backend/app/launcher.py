"""Windows 配布版のローカルアプリ起動エントリポイント。"""

from __future__ import annotations

import socket
import threading
import webbrowser
from tkinter import messagebox

import uvicorn

from backend.app.config import IDLE_SHUTDOWN_SECONDS, frontend_dist_dir
from backend.app.main import create_app


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    port = _pick_free_port()
    app = create_app(
        static_dir=frontend_dist_dir(),
        idle_shutdown_seconds=IDLE_SHUTDOWN_SECONDS,
    )
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)

    def request_shutdown() -> None:
        server.should_exit = True

    app.state.request_shutdown = request_shutdown

    url = f"http://127.0.0.1:{port}/"
    # サーバ起動直後にブラウザを開く。少し待つことで初回接続失敗を避ける。
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    server.run()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        messagebox.showerror("Roly-Poly Toy Generator", f"アプリの起動に失敗しました。\n\n{exc}")
        raise
