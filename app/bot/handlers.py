from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from sqlalchemy import func, select

from app.bot.users import get_or_create_user
from app.db.base import async_session_maker
from app.models.meal import Meal
from app.models.meal_item import MealItem
from app.services.llm_engine import QwenUnavailableError, extract_food
from app.services.rag_service import calculate_meal
from app.services.stt_engine import transcribe_audio

router = Router()
logger = logging.getLogger(__name__)

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статистика за день"), KeyboardButton(text="📅 За неделю")],
        [KeyboardButton(text="🍎 Помощь")],
    ],
    resize_keyboard=True,
)


def _escape_md(text: str) -> str:
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", text)


def _format_meal_report(
    text: str,
    totals: dict[str, float],
    items_rows: list[dict[str, Any]],
) -> str:
    escaped_text = _escape_md(text)
    lines: list[str] = [
        "*Распознанный текст*",
        f"`{escaped_text}`",
        "",
        "*Итого за прием пищи*",
        "```",
        f"Kкал: {totals['total_kcal']:.1f}",
        f"Белки: {totals['total_protein']:.1f} г",
        f"Жиры: {totals['total_fat']:.1f} г",
        f"Углеводы: {totals['total_carb']:.1f} г",
        "```",
        "",
        "*По продуктам*",
    ]
    for row in items_rows:
        name = _escape_md(str(row["name"]))
        lines.append(
            f"• {name} \\- {row['weight_grams']:.0f} г → {row['portion_kcal']:.0f} ккал"
        )
    return "\n".join(lines)


def _format_stats_card(
    title: str,
    total_kcal: float,
    total_protein: float,
    total_fat: float,
    total_carb: float,
) -> str:
    safe_title = _escape_md(title)
    return (
        f"*{safe_title}*\n"
        "```"
        f"\nKкал: {total_kcal:.1f}"
        f"\nБелки: {total_protein:.1f} г"
        f"\nЖиры: {total_fat:.1f} г"
        f"\nУглеводы: {total_carb:.1f} г"
        "\n```"
    )


async def _get_stats(user_id: int, days: int) -> tuple[float, float, float, float]:
    now = datetime.now(timezone.utc)
    if days <= 1:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=days)

    async with async_session_maker() as session:
        stmt = select(
            func.coalesce(func.sum(Meal.total_kcal), 0.0),
            func.coalesce(func.sum(Meal.total_protein), 0.0),
            func.coalesce(func.sum(Meal.total_fat), 0.0),
            func.coalesce(func.sum(Meal.total_carb), 0.0),
        ).where(Meal.user_id == user_id, Meal.meal_time >= start)
        result = await session.execute(stmt)
        totals = result.one()
        return float(totals[0]), float(totals[1]), float(totals[2]), float(totals[3])


@router.message(Command("start"))
async def handle_start(message: Message) -> None:
    await message.answer(
        "*Добро пожаловать в CalorAI\\!* "
        "Отправьте голосовое сообщение с приемом пищи.",
        reply_markup=MAIN_MENU_KEYBOARD,
    )


@router.message(F.text == "🍎 Помощь")
async def handle_help(message: Message) -> None:
    await message.answer(
        "*Как пользоваться*\n"
        "1\\. Отправьте голосом что вы съели\n"
        "2\\. Бот распознает речь и посчитает КБЖУ\n"
        "3\\. Используйте кнопки статистики внизу",
        reply_markup=MAIN_MENU_KEYBOARD,
    )


@router.message(F.text == "📊 Статистика за день")
async def handle_stats_day(message: Message) -> None:
    if message.from_user is None:
        return
    try:
        kcal, protein, fat, carb = await _get_stats(message.from_user.id, days=1)
        await message.answer(
            _format_stats_card("Статистика за день", kcal, protein, fat, carb),
            reply_markup=MAIN_MENU_KEYBOARD,
        )
    except Exception:
        logger.exception("Failed to build day stats for user_id=%s", message.from_user.id)
        await message.answer("Не удалось получить статистику\\. Попробуйте позже\\.")


@router.message(F.text == "📅 За неделю")
async def handle_stats_week(message: Message) -> None:
    if message.from_user is None:
        return
    try:
        kcal, protein, fat, carb = await _get_stats(message.from_user.id, days=7)
        await message.answer(
            _format_stats_card("Статистика за неделю", kcal, protein, fat, carb),
            reply_markup=MAIN_MENU_KEYBOARD,
        )
    except Exception:
        logger.exception("Failed to build week stats for user_id=%s", message.from_user.id)
        await message.answer("Не удалось получить статистику\\. Попробуйте позже\\.")


@router.message(F.voice)
async def handle_voice(message: Message) -> None:
    if message.from_user is None or message.voice is None:
        return

    status_message = await message.answer(
        "🎤 Распознаю речь\\.\\.\\.",
        reply_markup=MAIN_MENU_KEYBOARD,
    )

    fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)
    try:
        await message.bot.download(message.voice, destination=ogg_path)

        text = await transcribe_audio(ogg_path)
        await status_message.edit_text("🤖 Анализирую состав\\.\\.\\.")
        meal_items = await extract_food(text)

        async with async_session_maker() as session:
            user = await get_or_create_user(session, message.from_user.id)
            totals, items_rows = await calculate_meal(session, meal_items)

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

        await status_message.edit_text("✅ Готово\\!")
        report = _format_meal_report(text, totals, items_rows)
        await message.answer(report, reply_markup=MAIN_MENU_KEYBOARD)
    except QwenUnavailableError as exc:
        logger.exception(
            "Qwen unavailable while processing voice. user_id=%s",
            message.from_user.id,
        )
        await status_message.edit_text(_escape_md(str(exc)))
    except Exception:
        logging.exception("CRITICAL ERROR DURING VOICE PROCESSING:")
        await message.answer(
            "Произошла ошибка при обработке сообщения\\. Подробности в логах\\.",
            reply_markup=MAIN_MENU_KEYBOARD,
        )
    finally:
        try:
            os.unlink(ogg_path)
        except OSError:
            pass
