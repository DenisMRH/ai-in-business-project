from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import torch
from transformers import pipeline

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# HF automatic-speech-recognition Pipeline (Whisper via PyTorch on GPU)
_whisper_model: Any = None
_embedding_model: SentenceTransformer | None = None


def _load_whisper_model_sync() -> Any:
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = pipeline(
            "automatic-speech-recognition",
            model="openai/whisper-large-v3",
            device="cuda:0",  # Maps to physical GPU 3 in docker
            torch_dtype=torch.float16,
            model_kwargs={"attn_implementation": "sdpa"},
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


def get_whisper_model() -> Any:
    if _whisper_model is None:
        raise RuntimeError("Whisper pipeline is not loaded. Call preload_models() first.")
    return _whisper_model


def get_embedding_model() -> SentenceTransformer:
    if _embedding_model is None:
        raise RuntimeError("Embedding model is not loaded. Call preload_models() first.")
    return _embedding_model
