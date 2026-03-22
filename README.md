# CalorAI

On-premise сервис учёта калорий с голосовым вводом (Telegram), локальными ML-моделями и PostgreSQL + pgvector.

## Архитектура GPU

В `docker-compose.yml` зафиксировано **разделение GPU**:

| Сервис | GPU | Назначение |
|--------|-----|------------|
| **vLLM** (Qwen2.5-72B) | **0, 1, 2** | Tensor parallel = 3; большая языковая модель и запросы к LLM изолированы на трёх картах |
| **API** (FastAPI + aiogram + эмбеддинги / Whisper) | **3** | Отдельная карта под HTTP, бота и тяжёлые локальные модели (`sentence-transformers`, `faster-whisper`) |

Благодаря этому разделению:

- Запросы к API и вебхук Telegram **не конкурируют за VRAM** с 72B-моделью в vLLM: LLM и прикладной слой обрабатываются **параллельно** на разных GPU.
- Риск **Out of Memory (OOM)** на одной карте снижается: веса Qwen не делят память с контейнером API, где дополнительно могут быть загружены эмбеддер и Whisper.

> **Примечание:** Секция `deploy.resources.reservations.devices` в Compose учитывается в Docker Compose v2 с поддержкой NVIDIA Container Toolkit; при необходимости уточните синтаксис для вашей версии Compose / Swarm.

## Требования

- Docker + Docker Compose v2  
- NVIDIA GPU (в т.ч. 4× H100 для целевой конфигурации) и [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)  
- Python 3.11 (для локального запуска скриптов вне контейнера)

## Переменные окружения

Создайте файл `.env` в корне проекта (пример):

```env
DATABASE_URL=postgresql+asyncpg://calorai:calorai@db:5432/calorai
TELEGRAM_BOT_TOKEN=your_bot_token
VLLM_BASE_URL=http://vllm:8000/v1
WEBHOOK_PUBLIC_URL=https://your-domain.example.com/webhook
POSTGRES_USER=calorai
POSTGRES_PASSWORD=calorai
POSTGRES_DB=calorai
API_PORT=8001
```

Для Telegram webhook URL должен быть **HTTPS** и совпадать с маршрутом `POST /webhook` вашего приложения (например `https://api.example.com/webhook`).

## Быстрый запуск production-стека

### Вариант A: Bash-скрипт

```bash
chmod +x start_prod.sh
./start_prod.sh
```

По умолчанию после `db` и `vllm` скрипт ждёт **120 секунд** (модель ~72B грузится в VRAM 1–2 минуты). Изменить паузу:

```bash
export VLLM_WAIT_SECONDS=180
./start_prod.sh
```

### Вариант B: Makefile

```bash
make start-prod
```

Пауза задаётся так же: `VLLM_WAIT_SECONDS=180 make start-prod`.

### Что делает сценарий

1. `docker compose up -d db vllm` — PostgreSQL и vLLM в фоне.  
2. Ожидание загрузки весов vLLM в VRAM.  
3. `docker compose up -d api` — сборка и запуск FastAPI.

## Миграции и инициализация данных

1. Применить миграции Alembic (из корня проекта, с установленными зависимостями и `DATABASE_URL`):

```bash
export DATABASE_URL=postgresql+asyncpg://calorai:calorai@localhost:5432/calorai
export PYTHONPATH=.
alembic upgrade head
```

2. Заполнить справочник из **10 базовых продуктов** с эмбеддингами:

```bash
export DATABASE_URL=postgresql+asyncpg://calorai:calorai@localhost:5432/calorai
export TELEGRAM_BOT_TOKEN=your_bot_token
export PYTHONPATH=.
python -m app.db.seed
```

`TELEGRAM_BOT_TOKEN` нужен для загрузки настроек приложения (`app.core.config`), как и при запуске API.

Скрипт `app/db/seed.py` асинхронно подключается к БД, для каждого продукта вызывает `get_embedding()` (модель `intfloat/multilingual-e5-large`, префикс `query:`) и вставляет или обновляет строки в таблице `products`. Рекомендуется запускать на машине с **GPU**, доступным для PyTorch (как у API), чтобы ускорить расчёт эмбеддингов.

Через Makefile:

```bash
make seed
```

## Разработка API локально

```bash
pip install -r requirements.txt
export DATABASE_URL=...
export TELEGRAM_BOT_TOKEN=...
export PYTHONPATH=.
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Проверки (верификационные скрипты)

В репозитории есть вспомогательные скрипты проверки этапов, например:

- `python verify_step_1.py`
- `python verify_step_4.py`

Смотрите их docstring для условий запуска.

## Стек

- Python 3.11, FastAPI, aiogram 3  
- PostgreSQL 15 + pgvector  
- vLLM (OpenAI-совместимый API), локальные модели: faster-whisper, sentence-transformers  

---

**Проект готов к развёртыванию** при корректной настройке `.env`, GPU, миграций и webhook в Telegram Bot API.
