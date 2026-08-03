"""
Спрашивает у API, какие модели сейчас доступны.

Зачем: список моделей у меня в голове устаревает, а выбирать модель наугад —
верный способ получить 404 посреди платного прогона. Тут ответ от самого API.

Запуск:  python tools/list_models.py
"""

from __future__ import annotations

import sys

try:
    from anthropic import Anthropic
except ImportError:
    print("Нет библиотеки anthropic:  pip install anthropic", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = Anthropic()
    try:
        models = list(client.models.list(limit=50))
    except Exception as exception:
        print(f"не смог получить список: {type(exception).__name__}: {exception}")
        return 1

    print(f"моделей доступно: {len(models)}\n")
    for model in models:
        name = getattr(model, "display_name", "")
        created = getattr(model, "created_at", "")
        print(f"  {model.id:26} {name:28} {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
