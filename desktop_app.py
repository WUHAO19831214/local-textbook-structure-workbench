from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

import uvicorn


APP_TITLE = "本地教材结构化工作台"


def main() -> int:
    root_dir = _resource_path(Path("."))
    backend_dir = root_dir / "backend"
    frontend_dist = root_dir / "frontend" / "dist"

    if not (frontend_dist / "index.html").exists():
        print("未找到前端构建产物：frontend/dist/index.html")
        print("请先运行：cd frontend && npm install && npm run build")
        return 1

    os.environ.setdefault("TEXTBOOK_FRONTEND_DIST", str(frontend_dist))
    sys.path.insert(0, str(backend_dir))

    from app.main import app

    port = _find_free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="on",
        )
    )
    server_thread = threading.Thread(target=server.run, name="fastapi-server", daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}"
    if not _wait_until_ready(f"{url}/api/health"):
        print("本地后端启动失败。")
        server.should_exit = True
        return 1

    try:
        import webview
    except ImportError:
        print("未安装 pywebview。请运行：python3 -m pip install -r desktop/requirements.txt")
        server.should_exit = True
        return 1

    window = webview.create_window(
        APP_TITLE,
        url,
        width=1440,
        height=920,
        min_size=(1100, 720),
        text_select=True,
    )
    webview.start()
    server.should_exit = True
    server_thread.join(timeout=5)
    return 0 if window else 1


def _resource_path(relative_path: Path) -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return (base_dir / relative_path).resolve()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(url: str, timeout_seconds: float = 12) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.2)
    return False


if __name__ == "__main__":
    raise SystemExit(main())
