from __future__ import annotations

import asyncio
import logging

from app.services import ml_globals

logger = logging.getLogger(__name__)


async def transcribe_audio(file_path: str) -> str:
    def _transcribe_sync() -> str:
        model = ml_globals.get_whisper_model()
        segments, _info = model.transcribe(file_path)
        parts: list[str] = []
        for seg in segments:
            parts.append(seg.text)
        return "".join(parts).strip()

    try:
        return await asyncio.to_thread(_transcribe_sync)
    except Exception:
        logger.exception("Whisper transcription failed. file_path=%s", file_path)
        raise
