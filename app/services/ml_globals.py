"""
Глобальные тяжёлые модели (lazy loading): загрузка при первом обращении, не при импорте модуля.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from faster_whisper import WhisperModel
    from sentence_transformers import SentenceTransformer

_whisper_model: Any = None
_embedding_model: Any = None


def _load_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    return _whisper_model


def _load_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(
            "intfloat/multilingual-e5-large",
            device="cuda",
        )
    return _embedding_model


def __getattr__(name: str) -> Any:
    if name == "whisper_model":
        return _load_whisper_model()
    if name == "embedding_model":
        return _load_embedding_model()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
