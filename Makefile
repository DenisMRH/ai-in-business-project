# CalorAI — удобные цели для Linux/macOS (GNU Make). На Windows используйте WSL или start_prod.sh через Git Bash.

.PHONY: start-prod seed

# Поднять db + vLLM, подождать загрузки модели, поднять api
start-prod:
	docker compose up -d db vllm
	@echo "Waiting for vLLM (sleep $${VLLM_WAIT_SECONDS:-120}s)..."
	@sleep $${VLLM_WAIT_SECONDS:-120}
	docker compose up -d api

# Заполнить справочник продуктов (нужны PYTHONPATH и DATABASE_URL; лучше GPU для эмбеддингов)
seed:
	python -m app.db.seed
