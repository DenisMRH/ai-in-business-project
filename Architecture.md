### 1. Архитектура системы

В MVP мы делаем ставку на **модульный монолит** (Backend API) и **локальный ML-инференс** (STT, LLM, эмбеддинги на своём железе или VPS с GPU), чтобы не зависеть от внешних API и не отправлять пользовательские данные третьим сторонам.

**Flow данных и компоненты:**
1. **Telegram / Web UI** отправляют аудио или текст.
2. **FastAPI Backend** принимает запрос (webhook).
3. Аудио обрабатывается **локальным STT** (Whisper / faster-whisper).
4. Текст идёт в **локальную LLM** для извлечения сущностей (Structured JSON).
5. По извлеченным продуктам делается поиск в **PostgreSQL (pgvector)** для получения КБЖУ и ГИ.
6. Бэкенд сводит математику, сохраняет в **PostgreSQL** и отдает ответ пользователю.

```text
+-------------------+      +-----------------------------------------+
| Web App Dashboard |      |         Local ML inference stack        |
| (React / Vue)     |      |  +----------------+  +---------------+  |
+---------+---------+      |  | Local Whisper  |  | Local LLM     |  |
          | REST           |  | (Speech->Text) |  | (e.g. Qwen,   |  |
          v                |  | faster-whisper) |  | Llama via     |  |
+-------------------+      |  +-------^--------+  | Ollama/vLLM)  |  |
|  Telegram Bot     | webhook         |          +-------^-------+  |
|  (User Voice)     |--------> +-------|----------|---------------+  |
+-------------------+          |          FastAPI Backend          |
                               |  1. Telegram Webhook Handler      |
                               |  2. Audio Processing Pipeline     |
                               |  3. NLP / Meal Extraction Engine  |
                               |  4. RAG / Vector Search Logic     |
                               +------------------+----------------+
                                                  | SQL / pgvector
                               +------------------v----------------+
                               |           PostgreSQL 15+          |
                               |  - Users, Meals, History          |
                               |  - Product DB + Embeddings        |
                               +-----------------------------------+
```

---

### 2. Технологический стек

- **Backend:** Python + **FastAPI**. Идеально для ML-интеграций, нативно асинхронный (важно для ожидания ответов от локальной LLM).
- **Telegram:** **aiogram 3.x**. Современный асинхронный фреймворк, отлично работает с FastAPI вебхуками.
- **Speech-to-Text:** **локальный Whisper** (например **faster-whisper** или **whisper.cpp**). Работает на CPU (медленнее) или GPU (комфортная скорость); качество распознавания русского зависит от выбранной весовой модели (small/medium/large).
- **LLM:** **локальная модель** (через **Ollama**, **llama.cpp**, **vLLM** и т.п.) — например семейства **Qwen2.5**, **Llama 3.x**, **Mistral** в квантованном виде. Задача — Structured Data Extraction (выдача JSON); промпт и парсинг ответа на стороне бэкенда.
- **RAG / База данных:** **PostgreSQL + pgvector**. *Не нужно тянуть отдельный Qdrant/Pinecone!* Реляционные данные и векторы продуктов будут жить в одной базе. Это колоссально упрощает бэкапы и джоины.
- **Embeddings:** **локальная модель эмбеддингов** (**sentence-transformers**, **FastEmbed** и т.д.) — например многоязычные **E5**, **BGE**, **multilingual MiniLM**; размерность вектора задаётся выбранной моделью (см. схему БД).
- **Хостинг:** VPS с достаточным RAM/VRAM под выбранные модели + **Docker Compose**; при необходимости отдельный GPU-сервер для инференса.
- **Очереди:** Для MVP **не обязательны**. FastAPI `BackgroundTasks` или асинхронное выполнение при webhook-запросе; при росте нагрузки — очередь (Celery / Redis) для длинных запросов к локальной LLM.

---

### 3. Flow обработки сообщения (Пайплайн)

1. **Webhook Reception:** Бот получает `voice` сообщение. aiogram триггерит хендлер.
2. **Audio Fetch:** Скачиваем `.ogg` файл с серверов Telegram.
3. **STT (Распознавание):** Передаём файл в локальный Whisper (faster-whisper). Получаем текст: *"На завтрак съел два яйца, тост с авокадо и капучино"*.
4. **Entity Extraction (LLM):** Отправляем текст в локальную LLM с жестким промптом и JSON Schema (описание в разделе 4).
5. **Normalization & Vectorization:** Для каждого найденного продукта получаем эмбеддинг его названия локальной embedding-моделью.
6. **RAG Search:** Идем в PostgreSQL (`pgvector`). Ищем ближайшие по косинусному расстоянию продукты в нашей справочной таблице.
7. **Calculation:** Считаем финальные КБЖУ (КБЖУ продукта из базы на 100г * граммовку из JSON).
8. **DB Persistence:** Сохраняем `Meal` и `MealItems` в базу с привязкой к `user_id`.
9. **Feedback Generation:** (Опционально) Передаём суммарные КБЖУ приема пищи в локальную LLM для генерации короткого совета ("Отличный завтрак, но не хватает белка...").
10. **Response:** Отправляем текст в Telegram пользователю.

---

### 4. NLP / ML логика

**Извлечение сущностей:** Никаких Spacy или регулярных выражений в базовом сценарии. Используем **локальную LLM** с жёстким промптом и ожидаемым JSON в ответе (при необходимости — повтор запроса или валидация через Pydantic).
Мы просим LLM: "Ты нутрициолог. Извлеки продукты из текста. Если вес не указан, оцени стандартную порцию в граммах".

*Пример промпта / JSON схемы:*
```json
{
  "items":[
    {"name": "яйцо куриное вареное", "weight_grams": 110},
    {"name": "тост с авокадо", "weight_grams": 150},
    {"name": "капучино", "weight_grams": 250}
  ]
}
```
**Киллер-фича LLM:** Она сама нормализует "два яйца" в 110 грамм, а "капучино" — в 250 мл (или грамм).

**Сопоставление с базой (Fuzzy matching):**
Мы берем нормализованное имя ("тост с авокадо") -> делаем из него вектор -> ищем в `pgvector`. Если блюдо составное и его нет в базе (например, "салат оливье с колбасой"), то:
*Вариант MVP:* В промпте просим локальную LLM декомпозировать сложные блюда на базовые ингредиенты, если это не фастфуд.

---

### 5. RAG система

**Что в базе (`products`):**
ID, Название (и его вектор), Ккал, Белки, Жиры, Углеводы, ГИ (гликемический индекс). В MVP можно запарсить любую открытую базу продуктов (USDA, FatSecret API) или сгенерировать топ-1000 продуктов через локальную LLM (офлайн).

**Как происходит поиск:**
1. Сначала делаем быстрый SQL поиск `WHERE name ILIKE '%название%'`.
2. Если точного совпадения нет — используем pgvector: `ORDER BY embedding <=> '[0.1, 0.2, ...]' LIMIT 1`.
3. Устанавливаем порог отсечения (distance threshold). Если дистанция слишком велика (в базе нет ничего похожего на "жареный корень мандрагоры"), фоллбек на локальную LLM: мы "на лету" просим модель сгенерировать примерные КБЖУ для этого продукта и **сохраняем как новую запись в таблицу `products`** (самообучающаяся база).

---

### 6. Структура базы данных (PostgreSQL)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id BIGINT PRIMARY KEY, -- Telegram ID
    created_at TIMESTAMP DEFAULT NOW(),
    daily_kcal_goal INT
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE,
    embedding vector(384), -- пример: multilingual MiniLM / fastembed; размерность подставить под выбранную модель
    kcal_per_100g FLOAT,
    protein_per_100g FLOAT,
    fat_per_100g FLOAT,
    carb_per_100g FLOAT,
    gi_index INT -- может быть NULL
);

CREATE TABLE meals (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    meal_time TIMESTAMP DEFAULT NOW(),
    raw_text TEXT, -- что сказал юзер
    total_kcal FLOAT,
    total_protein FLOAT,
    total_fat FLOAT,
    total_carb FLOAT
);

CREATE TABLE meal_items (
    id SERIAL PRIMARY KEY,
    meal_id INT REFERENCES meals(id),
    product_id INT REFERENCES products(id),
    weight_grams INT,
    calculated_kcal FLOAT
);
```

---

### 7. API дизайн (FastAPI)

- `POST /webhook/telegram` — принимает апдейты от ТГ.
- `POST /api/v1/voice` — для Web Dashboard (отправка аудио).
  *Payload:* `multipart/form-data` (audio_file).
  *Response:*
  ```json
  {
    "meal_id": 12,
    "recognized_text": "съел два яйца",
    "totals": {"kcal": 155, "protein": 13, "fat": 11, "carb": 1.1},
    "advice": "Отлично, белковый перекус!"
  }
  ```
- `GET /api/v1/stats?user_id=123&period=week`
  *Response:* Массив дней с агрегированными КБЖУ для отрисовки графиков на дашборде.

---

### 8. Telegram UX

**Flow:**
1. **Юзер:** (Голосовое сообщение 0:04) "Съел тарелку борща со сметаной и кусок черного хлеба."
2. **Бот:** ⏳ *Анализирую твой прием пищи...* (отправляется мгновенно, чтобы юзер видел реакцию).
3. **Бот:** (через 2-3 секунды)
   🍲 **Обед записан!**
   • Борщ (300г) — 145 ккал
   • Сметана 20% (30г) — 62 ккал
   • Хлеб черный (40г) — 80 ккал

   📊 **Итого за прием:** 287 ккал | Б: 8г | Ж: 12г | У: 34г
   📈 **За сегодня:** 1250 / 2000 ккал

   *Комментарий нутрициолога:* Хороший выбор! ГИ средний. В следующий раз добавь кусочек мяса для добора белка.

---

### 9. MVP scope

✅ **Что входит:**
- Телеграм-бот (голос и текст).
- ИИ-распознавание продуктов + граммовок (локальные модели).
- Векторный RAG по базовой таблице продуктов (топ 1000 + автодополнение).
- Подсчет КБЖУ.
- Простая статистика за день/неделю (прямо в боте + API для дашборда).
- AI-советы (короткий комментарий к еде).

❌ **Что НЕ входит (отрезаем без жалости):**
- Аутентификация по логину/паролю (в MVP только привязка по Telegram ID).
- Сканирование штрихкодов.
- Сложные медицинские диеты (кето, диабет).
- Шаринг в соцсети.
- Оплата и подписки.

---

### 10. План разработки (Roadmap) ~ 10 дней

- **День 1:** Настройка окружения. Поднятие FastAPI + PostgreSQL с pgvector (Docker Compose). Установка рантайма для локальных моделей (Ollama / vLLM + faster-whisper по выбору).
- **День 2:** Схема БД, CRUD операции. Заливка начального сида (CSV с топ-1000 продуктов) + офлайн-генерация для них эмбеддингов локальной embedding-моделью.
- **День 3:** Подключение Telegram Webhook (`aiogram`). Заглушки хендлеров.
- **День 4:** Интеграция локального Whisper (faster-whisper). Скачивание аудио -> текст.
- **День 5:** Написание промптов для локальной LLM. Парсинг Structured JSON ответа (валидация Pydantic).
- **День 6:** Написание RAG-поиска по БД (SQL + вектор). Связка с пайплайном.
- **День 7:** Расчет математики КБЖУ, сохранение приема пищи в базу.
- **День 8:** API для аналитики. Формирование красивых ответов в ТГ.
- **День 9:** Обработка ошибок (что если ничего не найдено, что если голос не распознан).
- **День 10:** Деплой на VPS (с учётом ресурсов под модели), тестирование, донастройка промптов.

---

### 11. Риски и узкие места

1. **Ошибки STT (Whisper не расслышал):**
   *Решение:* В локальном Whisper задать **initial_prompt** / контекст ("еда, завтрак, обед, нутрициология, граммы") — это задаёт контекст и снижает галлюцинации. При необходимости — более крупная весовая модель (medium/large).
2. **Неточные граммовки ("съел яблоко"):**
   *Решение:* LLM в промпте строго инструктируется использовать средние веса (яблоко = 150г, банан = 120г), если юзер не сказал точный вес.
3. **Слишком много запросов в БД (latency):**
   *Решение:* В MVP не критично. Но для продуктов можно добавить Redis LRU кэш для векторов.
4. **Сложные блюда ("бабушкин пирог"):**
   *Решение:* Если дистанция pgvector слишком велика, локальная LLM делает on-the-fly расчет "бабушкиного пирога" (оценивает в 350 ккал/100г), и мы сохраняем это в БД как кастомный продукт пользователя.
5. **Ресурсы сервера:** локальные LLM и Whisper требуют RAM/VRAM; для MVP заложить мониторинг и при необходимости более лёгкие квантизации (Q4, Q5).

---

### 12. Минимальный код-скелет

**Структура проекта (MVC / Clean Architecture lite):**
```text
calorai/
├── app/
│   ├── main.py              # FastAPI app & webhooks
│   ├── bot/                 # Aiogram логика
│   │   ├── handlers.py
│   ├── core/                # Конфиг, пути к моделям
│   ├── services/
│   │   ├── llm_engine.py    # локальная llm + JSON парсинг
│   │   ├── stt_engine.py    # faster-whisper / локальный Whisper
│   │   ├── embeddings.py    # sentence-transformers / FastEmbed
│   │   ├── vector_db.py     # Поиск продуктов через pgvector
│   ├── models/              # SQLAlchemy / SQLModel модели
├── docker-compose.yml
├── requirements.txt
```

**Пример Telegram Handler (`bot/handlers.py`):**
```python
from aiogram import Router, F
from aiogram.types import Message
from app.services.stt_engine import transcribe_audio
from app.services.llm_engine import extract_food_from_text
from app.services.vector_db import calculate_kbzhu

router = Router()

@router.message(F.voice)
async def handle_voice_meal(message: Message):
    # 1. Сразу даем фидбек
    status_msg = await message.reply("⏳ Анализирую...")

    try:
        # 2. Скачиваем аудио и STT
        audio_path = await download_voice(message.voice.file_id)
        text = await transcribe_audio(audio_path)

        # 3. LLM Entity Extraction
        meal_data = await extract_food_from_text(text)

        # 4. RAG + Расчет
        totals, report_text = await calculate_kbzhu(meal_data.items)

        # 5. Сохранение в БД (псевдокод)
        # await db.save_meal(message.from_user.id, totals)

        # 6. Ответ
        await status_msg.edit_text(report_text)

    except Exception as e:
        await status_msg.edit_text("Не удалось распознать еду. Попробуй еще раз!")
```
