from __future__ import annotations

import asyncio
import json
import logging
import re

from openai import AsyncOpenAI
from openai import APIConnectionError, APITimeoutError, OpenAIError
from pydantic import BaseModel, Field, ValidationError

from app.core.config import config

VLLM_CHAT_MODEL = "Qwen/Qwen2.5-72B-Instruct"

_EXTRACT_SYSTEM_PROMPT = (
    "You are a nutritionist. Extract food items and weights from the following text "
    "and return ONLY a valid JSON object with this schema: "
    '{"items":[{"name":"string","weight_grams": number}]}. '
    'If there are no foods, return {"items": []}. '
    "Do not include markdown, explanations, or any text outside the JSON object."
)


class ExtractedMealItem(BaseModel):
    name: str
    weight_grams: float = Field(gt=0)


class MealExtractionResponse(BaseModel):
    items: list[ExtractedMealItem]


_NUTRITION_SYSTEM_PROMPT = (
    "You are a nutritionist. The user names a food or dish (any language; often Russian). "
    "If it is unknown, niche, or a homemade dish, estimate plausible values for a typical "
    "serving preparation (per 100 g edible portion). "
    "Return ONLY a JSON object with numeric fields: "
    '{"kcal": number, "protein": number, "fat": number, "carb": number}. '
    "Use grams for protein, fat, carb; kcal for energy. No markdown or extra text."
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
    """
    Parse meal items from user text (e.g. Whisper STT output) via local vLLM (Qwen).

    The OpenAI-compatible client posts to ``config.VLLM_BASE_URL``; vLLM may use
    all GPUs on the host — the API container only needs network access to the service.
    """
    user_text = text.strip()
    if not user_text:
        return []

    # vLLM can stall under load; bounded wait avoids hanging the bot forever
    _LLM_CALL_TIMEOUT_S = 180.0

    try:
        completion = await asyncio.wait_for(
            _client.chat.completions.create(
                model=VLLM_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            ),
            timeout=_LLM_CALL_TIMEOUT_S,
        )
        raw = completion.choices[0].message.content or "{}"
    except asyncio.TimeoutError as exc:
        logger.warning("extract_food: vLLM request timed out after %ss", _LLM_CALL_TIMEOUT_S)
        _raise_qwen_overloaded(exc)
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
        f"Оцени КБЖУ на 100 г съедобной части для продукта или блюда: «{product_name}». "
        "Если блюдо редкое или домашнее — дай разумную оценку по типичному приготовлению. "
        "Верни только JSON: kcal, protein, fat, carb (числа)."
    )
    _LLM_CALL_TIMEOUT_S = 120.0

    try:
        completion = await asyncio.wait_for(
            _client.chat.completions.create(
                model=VLLM_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": _NUTRITION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            ),
            timeout=_LLM_CALL_TIMEOUT_S,
        )
        raw = completion.choices[0].message.content or "{}"
    except asyncio.TimeoutError as exc:
        logger.warning(
            "estimate_nutrition_per_100g: vLLM timed out after %ss",
            _LLM_CALL_TIMEOUT_S,
        )
        _raise_qwen_overloaded(exc)
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
