"""
Собирает словарь времени для боковой панели: «9:30am» -> «9:30 утра».

Зачем отдельный файл и генератор: части суток в русском зависят от ЧАСА
(2 часа дня, но 8 вечера), а движок в шаблонах заменяет все числа на {n} —
час до правила не доживает. Значит нужна отдельная запись на каждый час.
Руками это 400+ строк, поэтому генерируем.

Минуты у Hypixel идут через 10, отсюда небольшой размер. Попадётся другое
значение — сработает общий шаблон «{n}:{n}am ☀» из 25-sidebar.json, он просто
покажет время без части суток. Хуже, но не сломано.

Запуск:  python tools/gen_time.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "ru_ru" / "26-time.json"

# Часы SkyBlock идут с шагом 10 минут.
MINUTES = range(0, 60, 10)

# Значок рядом со временем: солнце днём, луна ночью. Бывает и без него.
ICONS = ["", " ☀", " ☽"]


def part_of_day(hour12: int, half: str) -> str:
    """
    Часть суток по русским правилам, а не по механическому am/pm.

    ночи   23:00-04:59
    утра   05:00-11:59
    дня    12:00-17:59
    вечера 18:00-22:59
    """
    hour24 = hour12 % 12 + (12 if half == "pm" else 0)
    if 5 <= hour24 <= 11:
        return "утра"
    if 12 <= hour24 <= 17:
        return "дня"
    if 18 <= hour24 <= 22:
        return "вечера"
    return "ночи"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    exact: dict[str, str] = {}
    for hour in range(1, 13):
        for minute in MINUTES:
            for half in ("am", "pm"):
                word = part_of_day(hour, half)
                for icon in ICONS:
                    key = f"{hour}:{minute:02d}{half}{icon}"
                    exact[key] = f"{hour}:{minute:02d} {word}{icon}"

    pack = {
        "id": "time",
        # Раньше 25-sidebar: там лежит общий шаблон без части суток,
        # он должен оставаться запасным вариантом, а не побеждать.
        "priority": 26,
        "_comment": ("Время на боковой панели. Собран скриптом tools/gen_time.py — "
                     "правь скрипт, а не этот файл. Часть суток зависит от часа "
                     "(2 часа ДНЯ, но 8 ВЕЧЕРА), поэтому запись на каждый час."),
        "exact": exact,
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.name}: {len(exact)} записей")
    print("примеры:")
    for key in ("2:00pm ☀", "8:30pm ☽", "3:10am ☽", "9:30am ☀"):
        print(f"  {key}  ->  {exact[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
