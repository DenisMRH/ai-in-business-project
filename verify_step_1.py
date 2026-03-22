"""
Проверка шага 1: структура каталогов и наличие секций NVIDIA GPU в docker-compose.yml.
Использует только стандартную библиотеку Python.

Запуск из корня проекта: python verify_step_1.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE_FILE = ROOT / "docker-compose.yml"

REQUIRED_DIRS = [
    ROOT / "app",
    ROOT / "app" / "api",
    ROOT / "app" / "bot",
    ROOT / "app" / "core",
    ROOT / "app" / "db",
    ROOT / "app" / "models",
    ROOT / "app" / "services",
]

REQUIRED_FILES = [
    ROOT / "requirements.txt",
    ROOT / "Dockerfile",
    ROOT / "app" / "main.py",
    ROOT / "app" / "core" / "config.py",
]


def _extract_service_block(text: str, service: str) -> str | None:
    """Вырезает тело сервиса `  name:` до следующего peer-сервиса или top-level volumes/networks."""
    m = re.search(rf"^  {re.escape(service)}:\s*\n", text, re.MULTILINE)
    if not m:
        return None
    tail = text[m.end() :]
    peer = re.search(r"^  [a-zA-Z0-9_-]+:\s*\n", tail, re.MULTILINE)
    if peer:
        return tail[: peer.start()]
    top = re.search(r"^[a-zA-Z0-9_-]+:\s*\n", tail, re.MULTILINE)
    if top:
        return tail[: top.start()]
    return tail


def _nvidia_device_ids_from_block(block: str) -> list[str]:
    """Ищет первый блок driver: nvidia и читает device_ids."""
    if "driver: nvidia" not in block:
        return []
    after = block.split("driver: nvidia", 1)[1]
    m = re.search(
        r"device_ids:\s*((?:\s*-\s*\"[0-9]+\"\s*\n?)+)",
        after,
        re.MULTILINE,
    )
    if not m:
        return []
    return re.findall(r"-\s*\"([0-9]+)\"", m.group(1))


def check_compose_gpu(text: str) -> list[str]:
    errors: list[str] = []

    if "services:" not in text:
        errors.append("В docker-compose.yml нет секции services")

    for name in ("db", "vllm", "api"):
        if _extract_service_block(text, name) is None:
            errors.append(f"Сервис '{name}' не объявлен (блок '  {name}:' не найден)")

    nvidia_count = text.count("driver: nvidia")
    if nvidia_count < 2:
        errors.append(
            "Ожидается минимум два блока driver: nvidia (vllm и api) в deploy.resources.reservations.devices"
        )

    vllm = _extract_service_block(text, "vllm") or ""
    api = _extract_service_block(text, "api") or ""

    if vllm:
        if "deploy:" not in vllm or "resources:" not in vllm:
            errors.append("vllm: отсутствует deploy.resources")
        ids = _nvidia_device_ids_from_block(vllm)
        if not ids:
            errors.append("vllm: не удалось прочитать device_ids для nvidia GPU")
        elif set(ids) != {"0", "1", "2"}:
            errors.append(
                f"vllm: ожидаются GPU device_ids ['0','1','2'], получено {ids}"
            )

    if api:
        if "deploy:" not in api or "resources:" not in api:
            errors.append("api: отсутствует deploy.resources")
        ids = _nvidia_device_ids_from_block(api)
        if not ids:
            errors.append("api: не удалось прочитать device_ids для nvidia GPU")
        elif ids != ["3"]:
            errors.append(f"api: ожидается GPU device_ids ['3'], получено {ids}")

    return errors


def check_fs() -> list[str]:
    errors: list[str] = []
    for d in REQUIRED_DIRS:
        if not d.is_dir():
            errors.append(f"Каталог отсутствует: {d.relative_to(ROOT)}")
    for f in REQUIRED_FILES:
        if not f.is_file():
            errors.append(f"Файл отсутствует: {f.relative_to(ROOT)}")
    return errors


def optional_docker_compose_config() -> list[str]:
    """Если доступен Docker Compose — дополнительно проверяет синтаксис merge-конфига."""
    warnings: list[str] = []
    try:
        r = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        warnings.append(
            "Docker CLI не найден: пропущена проверка `docker compose config` (опционально)."
        )
        return warnings
    except subprocess.TimeoutExpired:
        warnings.append("Таймаут `docker compose config` — пропуск.")
        return warnings

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        warnings.append(
            "docker compose config завершился с ошибкой (проверьте установку Docker и синтаксис): "
            + (err[:500] if err else "нет вывода")
        )
    return warnings


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main() -> int:
    _ensure_utf8_stdio()
    fs_errors = check_fs()

    if not COMPOSE_FILE.is_file():
        fs_errors.append("Файл docker-compose.yml не найден")

    compose_errors: list[str] = []
    if COMPOSE_FILE.is_file():
        compose_text = COMPOSE_FILE.read_text(encoding="utf-8")
        compose_errors = check_compose_gpu(compose_text)

    all_errors = fs_errors + compose_errors
    if all_errors:
        print("Проверка не пройдена:", file=sys.stderr)
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    for w in optional_docker_compose_config():
        print(w, file=sys.stderr)

    print("Проверка пройдена: структура папок и docker-compose.yml (NVIDIA GPU) в порядке.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
