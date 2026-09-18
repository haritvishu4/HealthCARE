"""Create a private environment and install dependencies. Does not overwrite existing secrets."""

import argparse
import base64
import os
import secrets
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "backend" / ".env"
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite", action="store_true", help="Use SQLite for a local development trial only."
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Generate configuration only; useful with Docker.",
    )
    parser.add_argument("--dev", action="store_true", help="Also install the test dependencies.")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required. Python 3.12 is recommended.")
    if not ENV.exists():
        content = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
        content = content.replace(
            "FIELD_ENCRYPTION_KEY=\n",
            "FIELD_ENCRYPTION_KEY="
            + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
            + "\n",
        )
        content = content.replace(
            "DEV_AUTH_TOKEN=\n", "DEV_AUTH_TOKEN=" + secrets.token_urlsafe(48) + "\n"
        )
        if args.sqlite:
            path = (ROOT / "backend" / "care-local.db").as_posix()
            content = content.replace(
                "postgresql+psycopg://care:change-me@localhost:5432/care", "sqlite:///" + path
            )
        ENV.write_text(content, encoding="utf-8")
        try:
            ENV.chmod(0o600)
        except OSError:
            pass
        print("Created backend/.env with private random local credentials.")
    else:
        print("Preserved existing backend/.env. Database choice and secrets were not changed.")
    if not args.skip_install:
        if not PYTHON.exists():
            print("Creating .venv...")
            venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
        requirement = "requirements-dev.txt" if args.dev else "requirements.txt"
        subprocess.run(
            [str(PYTHON), "-m", "pip", "install", "-r", str(ROOT / "backend" / requirement)],
            check=True,
        )
    print("Next: edit backend/.env and set SARVAM_API_KEY and GEMINI_API_KEY.")
    print("Set OCR_API_KEY if you will upload scans/images. Text PDFs work without it.")
    print("Configure DATABASE_URL, then run: python scripts/run.py")
    print("On first visit, create your local workspace account in the browser.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit(
            "Dependency installation failed. Check your internet connection and Python version, then retry setup."
        )
