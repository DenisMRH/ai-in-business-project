from __future__ import annotations

import asyncio

from app.services import ml_globals


async def transcribe_audio(file_path: str) -> str:
    def _transcribe_sync() -> str:
        model = ml_globals.whisper_model
        segments, _info = model.transcribe(file_path)
        parts: list[str] = []
        for seg in segments:
            parts.append(seg.text)
        return "".join(parts).strip()

    return await asyncio.to_thread(_transcribe_sync)
