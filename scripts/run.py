"""Migrate, start FastAPI, and serve the local workspace login on localhost:5173."""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from frontend_server import serve

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def available(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(f"Port {port} is already in use. Stop the earlier app and retry.")


def main():
    if Path(sys.executable).resolve() != PYTHON.resolve():
        os.execv(str(PYTHON), [str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
    if not PYTHON.exists():
        raise SystemExit("Run python scripts/setup.py first.")
    if not (ROOT / "backend" / ".env").exists():
        raise SystemExit("backend/.env is missing. Run setup first.")
    available(8000)
    available(5173)
    subprocess.run(
        [str(PYTHON), "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=ROOT / "backend",
        check=True,
    )
    server = subprocess.Popen(
        [
            str(PYTHON),
            "-m",
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--no-access-log",
        ],
        cwd=ROOT / "backend",
    )
    try:
        for _ in range(80):
            if server.poll() is not None:
                raise SystemExit("Backend stopped. Check the error above and backend/.env.")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1) as r:
                    if r.status == 200:
                        break
            except OSError:
                time.sleep(0.25)
        else:
            raise SystemExit(
                "Backend did not become healthy. Check DATABASE_URL and its connection."
            )
        print(
            "\nCare Intake: http://localhost:5173\n"
            "Create your workspace account on first use, then sign in to continue.\n"
            "API docs (after sign-in): http://localhost:5173/docs\nPress Ctrl+C to stop.\n",
            flush=True,
        )
        serve()
    finally:
        server.terminate()
        try:
            server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCare Intake stopped.")
    except subprocess.CalledProcessError:
        raise SystemExit(
            "Migration failed. Confirm your PostgreSQL connection, or use --sqlite when first running setup."
        )
