from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from aiogram import F, Router
from aiogram.types import Message

from app.bot.users import get_or_create_user
from app.db.base import async_session_maker
from app.models.meal import Meal
from app.models.meal_item import MealItem
from app.services.llm_engine import extract_food
from app.services.rag_service import calculate_meal
from app.services.stt_engine import transcribe_audio

router = Router()


def _format_meal_report(
    text: str,
    totals: dict[str, float],
    items_rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = [
        "<b>Распознанный текст</b>",
        f"<code>{text}</code>",
        "",
        "<b>Итого за приём пищи</b>",
        f"🔥 Ккал: <b>{totals['total_kcal']:.1f}</b>",
        f"🥩 Белки: <b>{totals['total_protein']:.1f}</b> г",
        f"🧈 Жиры: <b>{totals['total_fat']:.1f}</b> г",
        f"🍞 Углеводы: <b>{totals['total_carb']:.1f}</b> г",
        "",
        "<b>По продуктам</b>",
    ]
    for row in items_rows:
        lines.append(
            f"• {row['name']} — {row['weight_grams']} г → "
            f"{row['portion_kcal']:.0f} ккал"
        )
    return "\n".join(lines)


@router.message(F.voice)
async def handle_voice(message: Message) -> None:
    if message.from_user is None or message.voice is None:
        return

    await message.answer("⏳ Обрабатываю на GPU...")

    fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)
    try:
        await message.bot.download(message.voice, destination=ogg_path)

        text = await transcribe_audio(ogg_path)
        meal_data = await extract_food(text)

        async with async_session_maker() as session:
            user = await get_or_create_user(session, message.from_user.id)
            totals, items_rows = await calculate_meal(session, meal_data)

            meal = Meal(
                user_id=user.id,
                meal_time=datetime.now(timezone.utc),
                raw_text=text,
                total_kcal=totals["total_kcal"],
                total_protein=totals["total_protein"],
                total_fat=totals["total_fat"],
                total_carb=totals["total_carb"],
            )
            session.add(meal)
            await session.flush()

            for row in items_rows:
                session.add(
                    MealItem(
                        meal_id=meal.id,
                        product_id=row["product_id"],
                        weight_grams=float(row["weight_grams"]),
                        calculated_kcal=row["portion_kcal"],
                    )
                )

            await session.commit()

        report = _format_meal_report(text, totals, items_rows)
        await message.answer(report)
    finally:
        try:
            os.unlink(ogg_path)
        except OSError:
            pass
