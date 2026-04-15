from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.embeddings import get_embedding
from app.services.llm_engine import NutritionPer100g

if TYPE_CHECKING:
    from app.services.llm_engine import ExtractedMealItem

# Порог косинусного расстояния (pgvector `<=>`): выше — считаем, что совпадения нет
COSINE_DISTANCE_MATCH_THRESHOLD = 0.25
logger = logging.getLogger(__name__)


async def _get_product_by_exact_name(
    session: AsyncSession, name: str
) -> Product | None:
    stmt = select(Product).where(Product.name == name)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _persist_llm_product(
    session: AsyncSession,
    name: str,
    vec: list[float],
    nutrition: NutritionPer100g,
) -> Product:
    """
    Сохраняет продукт с КБЖУ от LLM: новая строка или обновление при том же name (unique).
    """
    existing = await _get_product_by_exact_name(session, name)
    if existing is not None:
        existing.embedding = vec
        existing.kcal_per_100g = nutrition.kcal
        existing.protein_per_100g = nutrition.protein
        existing.fat_per_100g = nutrition.fat
        existing.carb_per_100g = nutrition.carb
        await session.flush()
        logger.info("RAG: обновлён продукт по имени после оценки LLM: %s", name)
        return existing

    new_product = Product(
        name=name,
        embedding=vec,
        kcal_per_100g=nutrition.kcal,
        protein_per_100g=nutrition.protein,
        fat_per_100g=nutrition.fat,
        carb_per_100g=nutrition.carb,
    )
    session.add(new_product)
    await session.flush()
    logger.info("RAG: в БД добавлен новый продукт (оценка LLM): %s", name)
    return new_product


async def match_product(session: AsyncSession, product_name: str) -> Product:
    """
    Находит продукт по RAG или создаёт запись: для неизвестного блюда вызывается LLM (КБЖУ на 100 г),
    результат пишется в ``products`` с эмбеддингом для следующих запросов.
    """
    try:
        cleaned = product_name.strip()
        if not cleaned:
            raise ValueError("Пустое название продукта.")

        exact = await _get_product_by_exact_name(session, cleaned)
        if exact is not None:
            return exact

        vec = await get_embedding(cleaned)
        dist_expr = Product.embedding.cosine_distance(vec)

        stmt = (
            select(Product, dist_expr.label("distance"))
            .order_by(dist_expr.asc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.first()

        if row is not None:
            product, distance = row
            if distance is not None and float(distance) <= COSINE_DISTANCE_MATCH_THRESHOLD:
                return product

        # Нет уверенного совпадения — неизвестное или новое блюдо: LLM оценивает КБЖУ → БД для RAG
        from app.services.llm_engine import estimate_nutrition_per_100g

        nutrition = await estimate_nutrition_per_100g(cleaned)
        return await _persist_llm_product(session, cleaned, vec, nutrition)
    except Exception:
        logger.exception("RAG product matching failed for product_name=%s", product_name)
        raise


def _portion_factor(weight_grams: float) -> float:
    return weight_grams / 100.0


async def calculate_meal(
    session: AsyncSession,
    extracted_items: list[ExtractedMealItem],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    total_kcal = 0.0
    total_protein = 0.0
    total_fat = 0.0
    total_carb = 0.0
    items_out: list[dict[str, Any]] = []

    for item in extracted_items:
        product = await match_product(session, item.name)
        factor = _portion_factor(item.weight_grams)

        pk = product.kcal_per_100g * factor
        pp = product.protein_per_100g * factor
        pf = product.fat_per_100g * factor
        pc = product.carb_per_100g * factor

        total_kcal += pk
        total_protein += pp
        total_fat += pf
        total_carb += pc

        items_out.append(
            {
                "name": item.name,
                "weight_grams": item.weight_grams,
                "product_id": product.id,
                "portion_kcal": pk,
                "portion_protein": pp,
                "portion_fat": pf,
                "portion_carb": pc,
            }
        )

    totals: dict[str, float] = {
        "total_kcal": total_kcal,
        "total_protein": total_protein,
        "total_fat": total_fat,
        "total_carb": total_carb,
    }
    return totals, items_out
