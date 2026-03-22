from __future__ import annotations

import asyncio

from app.services import ml_globals

E5_QUERY_PREFIX = "query: "


async def get_embedding(text: str) -> list[float]:
    def _encode_sync() -> list[float]:
        model = ml_globals.embedding_model
        prefixed = f"{E5_QUERY_PREFIX}{text}"
        vec = model.encode(prefixed, convert_to_numpy=True)
        return vec.tolist()

    return await asyncio.to_thread(_encode_sync)
