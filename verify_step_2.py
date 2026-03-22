"""
Проверка шага 2: импорт моделей и размерность вектора Product.embedding (1024).
Запуск из корня проекта: python verify_step_2.py

Требуются переменные DATABASE_URL и TELEGRAM_BOT_TOKEN для загрузки настроек;
если не заданы, подставляются безопасные заглушки (без подключения к БД).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://calorai:calorai@localhost:5432/calorai",
)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "verify-step-2-placeholder")


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main() -> int:
    _ensure_utf8_stdio()

    from pgvector.sqlalchemy import Vector

    from app.models import Product

    col = Product.__table__.c.embedding
    if not isinstance(col.type, Vector):
        print(
            f"Ожидался pgvector.sqlalchemy.Vector, получено {type(col.type)!r}",
            file=sys.stderr,
        )
        return 1

    dim = getattr(col.type, "dim", None)
    if dim != 1024:
        print(
            f"Ожидалась размерность Vector 1024, получено {dim!r}",
            file=sys.stderr,
        )
        return 1

    print("Проверка пройдена: Product.embedding — Vector(1024).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
