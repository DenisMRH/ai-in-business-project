from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.webhook import router as webhook_router
from app.bot.setup import bot
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.WEBHOOK_PUBLIC_URL:
        await bot.set_webhook(
            url=settings.WEBHOOK_PUBLIC_URL,
            drop_pending_updates=True,
        )
    yield
    await bot.session.close()


app = FastAPI(
    title="CalorAI API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "calorai", "vllm_base_url": settings.VLLM_BASE_URL}
