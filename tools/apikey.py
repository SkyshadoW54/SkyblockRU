"""
Проверка ключа API до отправки запросов.

Смысл: ошибку в ключе видно сразу, а не после четырёх неудачных запросов
с невнятным «invalid x-api-key». Самый частый промах — задвоенный префикс:
человек копирует ключ целиком в шаблон, где префикс уже написан.
"""

from __future__ import annotations

import os
import sys

PREFIX = "sk-ant-"


def check(quiet: bool = False) -> bool:
    """Правдоподобен ли ключ. Печатает, что именно не так, и как починить."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not key:
        print("Ключ не задан (переменная ANTHROPIC_API_KEY пуста).", file=sys.stderr)
        print("  1. Создай ключ на console.anthropic.com -> API keys", file=sys.stderr)
        print('  2. setx ANTHROPIC_API_KEY "вставь-сюда-ключ-целиком"', file=sys.stderr)
        print("  3. ЗАКРОЙ окно терминала и открой новое", file=sys.stderr)
        return False

    if key.count(PREFIX) > 1:
        print("В ключе ДВА префикса sk-ant- — он склеен из шаблона и самого ключа.",
              file=sys.stderr)
        print("Вставлять надо ключ целиком, ничего не дописывая спереди:", file=sys.stderr)
        print('  setx ANTHROPIC_API_KEY "sk-ant-api03-..."', file=sys.stderr)
        print("Затем закрыть окно терминала и открыть новое.", file=sys.stderr)
        return False

    if not key.startswith(PREFIX):
        print(f"Ключ не начинается с {PREFIX} — похоже, скопирован не он.", file=sys.stderr)
        return False

    if len(key) < 40:
        print("Ключ подозрительно короткий — возможно, скопировался не целиком.",
              file=sys.stderr)
        return False

    if not quiet:
        # показываем только хвост: по нему можно опознать ключ, но не воспользоваться им
        print(f"ключ на месте (…{key[-6:]})")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if check() else 1)
