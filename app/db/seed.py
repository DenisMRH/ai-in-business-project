"""
Асинхронное заполнение БД базовыми продуктами с эмбеддингами (intfloat/multilingual-e5-large).

Запуск из корня репозитория:

  set PYTHONPATH=.
  python -m app.db.seed

Переменная окружения DATABASE_URL обязательна (как у приложения).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_maker, engine
from app.models.product import Product
from app.services.embeddings import get_embedding

# Базовые продукты: КБЖУ на 100 г (приблизительные справочные значения)
SEED_PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "Яйцо куриное варёное",
        "kcal_per_100g": 155.0,
        "protein_per_100g": 12.9,
        "fat_per_100g": 11.1,
        "carb_per_100g": 0.8,
    },
    {
        "name": "Куриная грудка отварная",
        "kcal_per_100g": 165.0,
        "protein_per_100g": 31.0,
        "fat_per_100g": 3.6,
        "carb_per_100g": 0.0,
    },
    {
        "name": "Гречка отварная",
        "kcal_per_100g": 132.0,
        "protein_per_100g": 4.5,
        "fat_per_100g": 2.3,
        "carb_per_100g": 24.0,
    },
    {
        "name": "Кофе капучино",
        "kcal_per_100g": 45.0,
        "protein_per_100g": 2.2,
        "fat_per_100g": 2.4,
        "carb_per_100g": 4.5,
    },
    {
        "name": "Яблоко свежее",
        "kcal_per_100g": 52.0,
        "protein_per_100g": 0.3,
        "fat_per_100g": 0.2,
        "carb_per_100g": 14.0,
    },
    {
        "name": "Хлеб пшеничный",
        "kcal_per_100g": 265.0,
        "protein_per_100g": 9.0,
        "fat_per_100g": 3.2,
        "carb_per_100g": 49.0,
    },
    {
        "name": "Творог 5%",
        "kcal_per_100g": 121.0,
        "protein_per_100g": 17.0,
        "fat_per_100g": 5.0,
        "carb_per_100g": 3.0,
    },
    {
        "name": "Банан",
        "kcal_per_100g": 89.0,
        "protein_per_100g": 1.1,
        "fat_per_100g": 0.3,
        "carb_per_100g": 23.0,
    },
    {
        "name": "Оливковое масло",
        "kcal_per_100g": 884.0,
        "protein_per_100g": 0.0,
        "fat_per_100g": 100.0,
        "carb_per_100g": 0.0,
    },
    {
        "name": "Молоко 2.5%",
        "kcal_per_100g": 52.0,
        "protein_per_100g": 2.9,
        "fat_per_100g": 2.5,
        "carb_per_100g": 4.8,
    },
]


async def _upsert_product(
    session: AsyncSession,
    row: dict[str, Any],
    embedding: list[float],
) -> None:
    name = row["name"]
    stmt = select(Product).where(Product.name == name)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.embedding = embedding
        existing.kcal_per_100g = row["kcal_per_100g"]
        existing.protein_per_100g = row["protein_per_100g"]
        existing.fat_per_100g = row["fat_per_100g"]
        existing.carb_per_100g = row["carb_per_100g"]
        return
    session.add(
        Product(
            name=name,
            embedding=embedding,
            kcal_per_100g=row["kcal_per_100g"],
            protein_per_100g=row["protein_per_100g"],
            fat_per_100g=row["fat_per_100g"],
            carb_per_100g=row["carb_per_100g"],
        )
    )


async def seed_products() -> None:
    async with async_session_maker() as session:
        for row in SEED_PRODUCTS:
            embedding = await get_embedding(row["name"])
            await _upsert_product(session, row, embedding)
            print(f"OK: {row['name']}", flush=True)
        await session.commit()
    await engine.dispose()


def main() -> None:
    asyncio.run(seed_products())


if __name__ == "__main__":
    main()
