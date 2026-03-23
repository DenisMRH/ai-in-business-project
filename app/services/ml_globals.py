from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faster_whisper import WhisperModel
    from sentence_transformers import SentenceTransformer

_whisper_model: WhisperModel | None = None
_embedding_model: SentenceTransformer | None = None


def _load_whisper_model_sync() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            "large-v3",
            device="cuda",
            device_index=0,
            compute_type="float16",
        )
    return _whisper_model


def _load_embedding_model_sync() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(
            "intfloat/multilingual-e5-large",
            device="cuda:0",
        )
    return _embedding_model


def _is_oom_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "out of memory" in message or "cuda oom" in message


async def preload_models() -> None:
    try:
        await asyncio.to_thread(_load_whisper_model_sync)
        await asyncio.to_thread(_load_embedding_model_sync)
    except Exception as exc:
        if not _is_oom_error(exc):
            raise

        await asyncio.sleep(10)
        await asyncio.to_thread(_load_whisper_model_sync)
        await asyncio.to_thread(_load_embedding_model_sync)


def get_whisper_model() -> WhisperModel:
    if _whisper_model is None:
        raise RuntimeError("Whisper model is not loaded. Call preload_models() first.")
    return _whisper_model


def get_embedding_model() -> SentenceTransformer:
    if _embedding_model is None:
        raise RuntimeError("Embedding model is not loaded. Call preload_models() first.")
    return _embedding_model
