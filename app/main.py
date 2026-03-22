from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(
    title="CalorAI API",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "calorai", "vllm_base_url": settings.VLLM_BASE_URL}
