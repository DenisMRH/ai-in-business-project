from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.embeddings import get_embedding

if TYPE_CHECKING:
    from app.services.llm_engine import ExtractedMealItem

# Порог косинусного расстояния (pgvector `<=>`): выше — считаем, что совпадения нет
COSINE_DISTANCE_MATCH_THRESHOLD = 0.25
logger = logging.getLogger(__name__)


async def match_product(session: AsyncSession, product_name: str) -> Product:
    try:
        vec = await get_embedding(product_name)
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

        from app.services.llm_engine import estimate_nutrition_per_100g

        nutrition = await estimate_nutrition_per_100g(product_name)
        new_product = Product(
            name=product_name,
            embedding=vec,
            kcal_per_100g=nutrition.kcal,
            protein_per_100g=nutrition.protein,
            fat_per_100g=nutrition.fat,
            carb_per_100g=nutrition.carb,
        )
        session.add(new_product)
        await session.flush()
        return new_product
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
