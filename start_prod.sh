#!/usr/bin/env bash
# Запуск production-стека: сначала БД и vLLM, пауза на загрузку весов 72B, затем API.
set -euo pipefail

cd "$(dirname "$0")"

VLLM_WAIT_SECONDS="${VLLM_WAIT_SECONDS:-120}"

echo "Starting PostgreSQL and vLLM..."
docker compose up -d db vllm

echo "Waiting ${VLLM_WAIT_SECONDS}s for vLLM to load Qwen2.5-72B weights into VRAM..."
sleep "${VLLM_WAIT_SECONDS}"

echo "Starting API..."
docker compose up -d api

echo "Done. API port: set API_PORT in .env (default 8001 in docker-compose)."
