from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from app.bot.setup import bot, dp

router = APIRouter()


@router.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    data: dict[str, Any] = await request.json()
    await dp.feed_raw_update(bot, data)
    return Response(status_code=200)
