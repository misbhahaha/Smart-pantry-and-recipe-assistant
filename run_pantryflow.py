#!/usr/bin/env python3
"""Start the Smart Pantry API, wait until it is healthy, then open Streamlit.

Run from the project root (same folder as this file):

    python run_pantryflow.py

This avoids "cannot reach backend" when only Streamlit was started.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parent
BACKEND_DIR = REPO / "backend"
if sys.platform == "win32":
    _venv_python = REPO / ".venv" / "Scripts" / "python.exe"
else:
    _venv_python = REPO / ".venv" / "bin" / "python"


def _bootstrap_venv() -> None:
    """Always run under the project .venv so dependencies and paths match."""
    if not _venv_python.is_file():
        print(
            "Missing virtual environment. From this folder run:\n"
            "  python3 -m venv .venv\n"
            "  .venv/bin/pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if Path(sys.executable).resolve() != _venv_python.resolve():
        os.execv(str(_venv_python), [str(_venv_python), *sys.argv])


_bootstrap_venv()
VENV_PY = _venv_python

API_PORT = int(os.environ.get("API_PORT", "8000"))
API_HOST = os.environ.get("API_HEALTH_HOST", "127.0.0.1").strip() or "127.0.0.1"
# Fixed Streamlit port so PUBLIC_APP_URL can default to a stable local link.
STREAMLIT_PORT = int(os.environ.get("STREAMLIT_PORT", "8501"))


def _configured_base_url() -> str:
    return os.environ.get("BACKEND_URL", f"http://{API_HOST}:{API_PORT}").strip().rstrip("/")


def _local_loopback_base() -> str:
    return f"http://127.0.0.1:{API_PORT}"


def _wait_health(base_url: str, timeout: float) -> bool:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=1.5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def _tcp_port_accepting_connections(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _listening_process_cmdline(port: int) -> str | None:
    """Best-effort command line for the process listening on a TCP port (macOS/Linux)."""
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    pid: str | None = None
    for line in out.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = line[1:]
            break
    if not pid:
        return None
    try:
        return subprocess.check_output(["ps", "-p", pid, "-o", "args="], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _pick_streamlit_port(preferred: int) -> int:
    if not _tcp_port_accepting_connections("127.0.0.1", preferred):
        return preferred
    cmd = _listening_process_cmdline(preferred) or ""
    if "PROJECT" in cmd or "/PantryFlow" in cmd.replace("\\", "/"):
        print(
            f"Port {preferred} is held by an old session from before the project rename:\n  {cmd}\n"
            f"Stop it, then run again:\n  kill $(lsof -t -iTCP:{preferred} -sTCP:LISTEN)",
            file=sys.stderr,
        )
    for port in range(preferred + 1, 8516):
        if not _tcp_port_accepting_connections("127.0.0.1", port):
            print(f"Port {preferred} is busy — opening Streamlit on {port} instead.", file=sys.stderr)
            return port
    print(
        f"No free port between {preferred} and 8515. Stop old Streamlit/Python processes:\n"
        f"  lsof -nP -iTCP:{preferred}-8515 -sTCP:LISTEN",
        file=sys.stderr,
    )
    return preferred


def _open_browser_later(url: str, delay: float = 2.5) -> None:
    def _go() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_go, daemon=True).start()


def _launcher_env() -> dict[str, str]:
    """Environment for API + UI child processes."""
    env = os.environ.copy()
    # Faster, more reliable local startup (recipe data still loads from DB/catalog).
    env.setdefault("AUTO_THEMEALDB_ENRICH", "0")
    env.setdefault("AUTO_KASHMIRI_THEMEALDB", "0")
    env.setdefault("AUTO_DISH_IMAGE_BACKFILL", "1")
    env.setdefault("AUTO_THEMEALDB_IMAGE_SEARCH", "1")
    env.setdefault("AUTO_THEMEALDB_IMAGE_SEARCH_CAP", "80")
    return env


def main() -> int:
    backend_proc: subprocess.Popen | None = None
    base_url = _configured_base_url()
    try:
        if _wait_health(base_url, timeout=2.0):
            print("API already reachable at", base_url, "; starting Streamlit only.", file=sys.stderr)
        elif base_url.rstrip("/") != _local_loopback_base().rstrip("/") and _wait_health(
            _local_loopback_base(), timeout=2.0
        ):
            print(
                "API is healthy at",
                _local_loopback_base(),
                "but BACKEND_URL / default pointed to",
                base_url,
                "— using the local server for Streamlit.",
                file=sys.stderr,
            )
            base_url = _local_loopback_base()
        else:
            if _tcp_port_accepting_connections("127.0.0.1", API_PORT):
                print(
                    f"Port {API_PORT} on 127.0.0.1 is already in use, but no Smart Pantry API responded at "
                    f"{base_url}/health or {_local_loopback_base()}/health.\n"
                    "Stop the process that holds the port (see README) or use another port, e.g.:\n"
                    f"  lsof -nP -iTCP:{API_PORT} -sTCP:LISTEN\n"
                    f"  API_PORT=8001 {sys.argv[0] if sys.argv else 'python run_pantryflow.py'}",
                    file=sys.stderr,
                )
                return 1
            cors = os.environ.get("CORS_ORIGINS", "").strip()
            if not cors:
                parts: list[str] = []
                for p in range(8501, 8516):
                    parts.append(f"http://127.0.0.1:{p}")
                    parts.append(f"http://localhost:{p}")
                for p in (8081, 8082, 19000, 19001, 19002, 19006):
                    parts.append(f"http://127.0.0.1:{p}")
                    parts.append(f"http://localhost:{p}")
                cors = ",".join(parts)
            env = _launcher_env()
            env["CORS_ORIGINS"] = cors
            cmd = [str(VENV_PY), "-m", "uvicorn", "app.main:app"]
            if os.environ.get("PANTRYFLOW_RELOAD", "").strip().lower() in ("1", "true", "yes"):
                cmd.append("--reload")
            cmd.extend(["--host", "0.0.0.0", "--port", str(API_PORT)])
            backend_proc = subprocess.Popen(cmd, cwd=str(BACKEND_DIR), env=env)
            if not _wait_health(_local_loopback_base(), timeout=90.0):
                print("Timed out waiting for the API to start. Check port conflicts and logs.", file=sys.stderr)
                if backend_proc.poll() is None:
                    backend_proc.terminate()
                return 1
            if not _wait_health(base_url, timeout=2.0):
                base_url = _local_loopback_base()

        ui_env = _launcher_env()
        ui_env["BACKEND_URL"] = base_url
        streamlit_port = _pick_streamlit_port(STREAMLIT_PORT)
        app_url = (ui_env.get("PUBLIC_APP_URL") or "").strip() or f"http://127.0.0.1:{streamlit_port}"
        if streamlit_port != STREAMLIT_PORT and app_url.rstrip("/").endswith(f":{STREAMLIT_PORT}"):
            app_url = f"http://127.0.0.1:{streamlit_port}"
        ui_env["PUBLIC_APP_URL"] = app_url
        print(f"Open in your browser: {app_url}", file=sys.stderr)
        print("(Keep this terminal open while you use the app.)", file=sys.stderr)
        _open_browser_later(app_url)
        ui = subprocess.run(
            [
                str(VENV_PY),
                "-m",
                "streamlit",
                "run",
                str(REPO / "frontend" / "streamlit" / "Home.py"),
                "--server.headless",
                "true",
                "--server.address",
                (os.environ.get("STREAMLIT_SERVER_ADDRESS", "0.0.0.0").strip() or "0.0.0.0"),
                "--server.port",
                str(streamlit_port),
            ],
            cwd=str(REPO),
            env=ui_env,
        )
        return ui.returncode
    finally:
        if backend_proc is not None and backend_proc.poll() is None:
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                backend_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main() or 0)
