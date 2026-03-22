"""
Проверка шага 4: расчёт порции (КБЖУ) в calculate_meal с моком сессии и match_product.

Запуск из корня проекта:
  set PYTHONPATH=.
  python verify_step_4.py
"""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://calorai:calorai@localhost:5432/calorai",
)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "verify-step-4")


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass


class TestCalculateMealPortionMath(unittest.IsolatedAsyncioTestCase):
    async def test_150g_portion_from_kcal_per_100g(self) -> None:
        """150 г при 200 ккал/100 г → 300 ккал; белок 10 г/100 г → 15 г и т.д."""
        _ensure_utf8_stdio()

        from app.services import rag_service

        fake_product = SimpleNamespace(
            id=1,
            kcal_per_100g=200.0,
            protein_per_100g=10.0,
            fat_per_100g=4.0,
            carb_per_100g=30.0,
        )

        session = AsyncMock()

        extracted = SimpleNamespace(
            items=[
                SimpleNamespace(name="тестовый продукт", weight_grams=150),
            ]
        )

        with patch.object(rag_service, "match_product", new_callable=AsyncMock) as mock_match:
            mock_match.return_value = fake_product
            totals, items_out = await rag_service.calculate_meal(session, extracted)

        factor = 150 / 100.0
        self.assertAlmostEqual(totals["total_kcal"], 200.0 * factor)
        self.assertAlmostEqual(totals["total_protein"], 10.0 * factor)
        self.assertAlmostEqual(totals["total_fat"], 4.0 * factor)
        self.assertAlmostEqual(totals["total_carb"], 30.0 * factor)

        self.assertEqual(len(items_out), 1)
        item = items_out[0]
        self.assertAlmostEqual(item["portion_kcal"], 300.0)
        self.assertAlmostEqual(item["portion_protein"], 15.0)
        self.assertAlmostEqual(item["portion_fat"], 6.0)
        self.assertAlmostEqual(item["portion_carb"], 45.0)
        self.assertEqual(item["product_id"], 1)
        self.assertEqual(item["weight_grams"], 150)

        mock_match.assert_awaited_once_with(session, "тестовый продукт")


if __name__ == "__main__":
    _ensure_utf8_stdio()
    unittest.main()
