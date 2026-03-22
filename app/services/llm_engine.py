from __future__ import annotations

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings

VLLM_CHAT_MODEL = "Qwen/Qwen2.5-72B-Instruct"

_SYSTEM_PROMPT = """Ты извлекаешь продукты питания из текста пользователя.
Верни ТОЛЬКО один JSON-объект без markdown и пояснений, строго такого вида:
{"items": [{"name": "<строка>", "weight_grams": <целое число грамм>}, ...]}
Если продуктов нет, верни {"items": []}."""


class MealItemSchema(BaseModel):
    name: str
    weight_grams: int


class MealExtraction(BaseModel):
    items: list[MealItemSchema]


async def extract_food(text: str) -> MealExtraction:
    client = AsyncOpenAI(
        base_url=settings.VLLM_BASE_URL,
        api_key="dummy",
    )
    completion = await client.chat.completions.create(
        model=VLLM_CHAT_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    raw = completion.choices[0].message.content or "{}"
    return MealExtraction.model_validate_json(raw)
