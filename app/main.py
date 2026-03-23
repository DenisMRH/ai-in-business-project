from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.core.config import config
from app.db.base import async_session_maker
from app.models.meal import Meal


app = FastAPI(
    title="CalorAI API",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "calorai", "vllm_base_url": config.VLLM_BASE_URL}


@app.get("/dashboard/{user_id}", response_class=HTMLResponse)
async def dashboard(user_id: int) -> str:
    start = datetime.now(timezone.utc) - timedelta(days=6)
    async with async_session_maker() as session:
        stmt = select(Meal.meal_time, Meal.total_kcal).where(
            Meal.user_id == user_id,
            Meal.meal_time >= start,
        )
        result = await session.execute(stmt)
        rows = result.all()

    by_day: dict[str, float] = defaultdict(float)
    for meal_time, kcal in rows:
        day_key = meal_time.astimezone(timezone.utc).date().isoformat()
        by_day[day_key] += float(kcal)

    labels: list[str] = []
    values: list[float] = []
    for idx in range(7):
        day = (start + timedelta(days=idx)).date().isoformat()
        labels.append(day)
        values.append(round(by_day.get(day, 0.0), 2))

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CalorAI Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{ font-family: sans-serif; margin: 24px; background: #f6f7fb; }}
    .card {{ background: #fff; border-radius: 14px; padding: 16px; max-width: 900px; margin: 0 auto; }}
    h2 {{ margin-top: 0; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>CalorAI: калории за 7 дней (user {user_id})</h2>
    <canvas id="kcalChart"></canvas>
  </div>
  <script>
    const labels = {labels};
    const data = {values};
    new Chart(document.getElementById("kcalChart"), {{
      type: "line",
      data: {{
        labels,
        datasets: [{{
          label: "Ккал",
          data,
          borderWidth: 2,
          fill: false,
          tension: 0.25
        }}]
      }},
      options: {{ responsive: true }}
    }});
  </script>
</body>
</html>"""
