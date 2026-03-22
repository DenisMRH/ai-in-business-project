"""
Verify step 1: folder structure, docker-compose.yml, requirements.txt.
Run from project root: python verify_step_1.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REQUIRED_DIRS = [
    ROOT / "app",
    ROOT / "app" / "api",
    ROOT / "app" / "bot",
    ROOT / "app" / "core",
    ROOT / "app" / "db",
    ROOT / "app" / "models",
    ROOT / "app" / "services",
]

REQUIREMENTS_PACKAGES = [
    "fastapi",
    "uvicorn",
    "pydantic-settings",
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "pgvector",
    "aiogram",
    "openai",
]

DOCKER_COMPOSE_MARKERS = [
    "pgvector/pgvector:pg15",
    "healthcheck",
    "pg_isready",
]


def main() -> int:
    errors: list[str] = []

    for d in REQUIRED_DIRS:
        if not d.is_dir():
            errors.append(f"Missing directory: {d.relative_to(ROOT)}")

    req_path = ROOT / "requirements.txt"
    if not req_path.is_file():
        errors.append("Missing file: requirements.txt")
    else:
        text = req_path.read_text(encoding="utf-8")
        for pkg in REQUIREMENTS_PACKAGES:
            if pkg not in text:
                errors.append(f"requirements.txt missing package line containing: {pkg}")
        if "==" not in text:
            errors.append("requirements.txt should pin versions (use ==)")

    compose_path = ROOT / "docker-compose.yml"
    if not compose_path.is_file():
        errors.append("Missing file: docker-compose.yml")
    else:
        compose = compose_path.read_text(encoding="utf-8")
        for marker in DOCKER_COMPOSE_MARKERS:
            if marker not in compose:
                errors.append(f"docker-compose.yml missing expected content: {marker}")

    config_path = ROOT / "app" / "core" / "config.py"
    if not config_path.is_file():
        errors.append("Missing file: app/core/config.py")
    else:
        cfg = config_path.read_text(encoding="utf-8")
        for name in ("DATABASE_URL", "OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"):
            if name not in cfg:
                errors.append(f"app/core/config.py missing: {name}")

    main_path = ROOT / "app" / "main.py"
    if not main_path.is_file():
        errors.append("Missing file: app/main.py")
    else:
        main_src = main_path.read_text(encoding="utf-8")
        if "/health" not in main_src and '"/health"' not in main_src and "'/health'" not in main_src:
            errors.append("app/main.py should define GET /health")
        if "FastAPI" not in main_src:
            errors.append("app/main.py should use FastAPI")

    if errors:
        print("FAIL - verification errors:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("OK - step 1 verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
