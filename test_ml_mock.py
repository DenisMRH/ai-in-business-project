"""
Мок-тесты: Pydantic-парсинг MealExtraction и асинхронные обёртки (asyncio.to_thread)
без загрузки GPU-моделей.

Запуск из корня проекта:
  set PYTHONPATH=.
  python test_ml_mock.py
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://calorai:calorai@localhost:5432/calorai",
)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-ml-mock")


class TestPydanticMealExtraction(unittest.TestCase):
    def test_model_validate_json(self) -> None:
        from app.services.llm_engine import MealExtractionResponse

        raw = '{"items": [{"name": "овсянка", "weight_grams": 200}, {"name": "молоко", "weight_grams": 150}]}'
        m = MealExtractionResponse.model_validate_json(raw)
        self.assertEqual(len(m.items), 2)
        self.assertEqual(m.items[0].name, "овсянка")
        self.assertEqual(m.items[0].weight_grams, 200)


class TestAsyncMLOverlays(unittest.IsolatedAsyncioTestCase):
    async def test_transcribe_audio_uses_to_thread_and_whisper(self) -> None:
        from app.services import ml_globals
        from app.services import stt_engine

        mock_model = MagicMock()
        mock_model.return_value = {"text": " привет "}

        ml_globals._whisper_model = mock_model  # noqa: SLF001

        try:
            text = await stt_engine.transcribe_audio("/tmp/fake.wav")
        finally:
            ml_globals._whisper_model = None  # noqa: SLF001

        self.assertEqual(text, "привет")
        mock_model.assert_called_once()
        call_args = mock_model.call_args
        self.assertEqual(call_args[0][0], "/tmp/fake.wav")
        self.assertEqual(
            call_args[1].get("generate_kwargs"),
            {"language": "russian"},
        )

    async def test_get_embedding_query_prefix_and_to_thread(self) -> None:
        from app.services import embeddings
        from app.services import ml_globals

        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros(1024, dtype=np.float32)

        ml_globals._embedding_model = mock_model  # noqa: SLF001

        try:
            vec = await embeddings.get_embedding("яблоко")
        finally:
            ml_globals._embedding_model = None  # noqa: SLF001

        self.assertEqual(len(vec), 1024)
        expected_arg = f"{embeddings.E5_QUERY_PREFIX}яблоко"
        mock_model.encode.assert_called_once_with(
            expected_arg,
            convert_to_numpy=True,
        )

    async def test_extract_food_mock_openai(self) -> None:
        from app.services.llm_engine import ExtractedMealItem, extract_food

        payload = '{"items": [{"name": "банан", "weight_grams": 120}]}'
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content=payload)),
        ]
        mock_create = AsyncMock(return_value=mock_completion)

        with patch("app.services.llm_engine.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client

            result = await extract_food("съел банан")

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ExtractedMealItem)
        self.assertEqual(result[0].name, "банан")
        self.assertEqual(result[0].weight_grams, 120)
        mock_create.assert_awaited_once()
        kwargs = mock_create.await_args.kwargs
        self.assertEqual(kwargs.get("response_format"), {"type": "json_object"})


if __name__ == "__main__":
    unittest.main()
