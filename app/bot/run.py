from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.bot.setup import bot, dp
from app.db.base import Base, engine
from app.models import Meal, MealItem, Product, User  # noqa: F401
from app.services.ml_globals import preload_models


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)


async def main() -> None:
    try:
        await init_database()
        await preload_models()
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
