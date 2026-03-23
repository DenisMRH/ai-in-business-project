from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI
from openai import APIConnectionError, APITimeoutError, OpenAIError
from pydantic import BaseModel, Field, ValidationError

from app.core.config import config

VLLM_CHAT_MODEL = "Qwen/Qwen2.5-72B-Instruct"

_EXTRACT_SYSTEM_PROMPT = (
    "You extract food items from user text. "
    "Return only JSON with this schema: "
    '{"items":[{"name":"string","weight_grams": number}]}. '
    "If there are no foods, return {'items': []}."
)


class ExtractedMealItem(BaseModel):
    name: str
    weight_grams: float = Field(gt=0)


class MealExtractionResponse(BaseModel):
    items: list[ExtractedMealItem]


_NUTRITION_SYSTEM_PROMPT = (
    "Estimate macros per 100 grams for a food product. "
    "Return only JSON with numeric fields: "
    '{"kcal": number, "protein": number, "fat": number, "carb": number}.'
)


class NutritionPer100g(BaseModel):
    kcal: float
    protein: float
    fat: float
    carb: float


_client = AsyncOpenAI(base_url=config.VLLM_BASE_URL, api_key="dummy")
logger = logging.getLogger(__name__)


class QwenUnavailableError(RuntimeError):
    pass


def _extract_json_fragment(raw: str) -> str:
    match = re.search(r"\{[\s\S]*\}", raw)
    if match is None:
        raise ValueError("No JSON object found in model response.")
    return match.group(0)


def _normalize_json(raw: str) -> str:
    fragment = _extract_json_fragment(raw)
    parsed = json.loads(fragment)
    return json.dumps(parsed, ensure_ascii=False)


def _raise_qwen_overloaded(exc: Exception) -> None:
    logger.exception("vLLM/Qwen request failed.")
    raise QwenUnavailableError(
        "Нейросеть Qwen сейчас перегружена, попробуйте через минуту"
    ) from exc


async def extract_food(text: str) -> list[ExtractedMealItem]:
    try:
        completion = await _client.chat.completions.create(
            model=VLLM_CHAT_MODEL,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = completion.choices[0].message.content or "{}"
    except (APIConnectionError, APITimeoutError, OpenAIError, ConnectionError) as exc:
        _raise_qwen_overloaded(exc)

    try:
        parsed = MealExtractionResponse.model_validate_json(raw)
    except ValidationError as exc:
        logger.warning("Primary JSON parse failed for extract_food. raw=%s", raw)
        try:
            parsed = MealExtractionResponse.model_validate_json(_normalize_json(raw))
        except (ValidationError, ValueError, json.JSONDecodeError) as parse_exc:
            logger.exception("Failed to parse extract_food response after cleanup.")
            raise ValueError("Failed to parse extracted food JSON.") from parse_exc
    return parsed.items


async def estimate_nutrition_per_100g(product_name: str) -> NutritionPer100g:
    user_msg = (
        f"Estimate approximate nutrition values per 100g for: {product_name}. "
        "Return JSON only."
    )
    try:
        completion = await _client.chat.completions.create(
            model=VLLM_CHAT_MODEL,
            messages=[
                {"role": "system", "content": _NUTRITION_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = completion.choices[0].message.content or "{}"
    except (APIConnectionError, APITimeoutError, OpenAIError, ConnectionError) as exc:
        _raise_qwen_overloaded(exc)

    try:
        return NutritionPer100g.model_validate_json(raw)
    except ValidationError as exc:
        logger.warning("Primary JSON parse failed for nutrition. raw=%s", raw)
        try:
            normalized = _normalize_json(raw)
            return NutritionPer100g.model_validate_json(normalized)
        except (ValidationError, ValueError, json.JSONDecodeError) as parse_exc:
            logger.exception("Failed to parse nutrition response after cleanup.")
            raise ValueError("Failed to parse nutrition JSON.") from parse_exc
