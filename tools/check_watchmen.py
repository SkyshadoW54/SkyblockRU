# -*- coding: utf-8 -*-
"""
СТОРОЖ ВНЕ КРУГА НЕ СТОРОЖИТ — все ли проверки вписаны в `refresh.py`.

Беда, ради которой написано. Ревизия 29.07: в `tools/` тринадцать сторожей,
а в круге сборки вписаны ПЯТЬ. Остальные восемь срабатывали, только если
я о них вспомню, — то есть защитой не были. В тот же день `check_colors`
поймал, что новый знак списка ломает 13 подсказок; вспомнил я о нём
случайно, а не вспомнил бы — правка уехала в jar, и беду нашёл бы игрок.

⚠️ Сторож, о котором надо ПОМНИТЬ, — не защита. Защита это то, что
запускается само и умеет остановить сборку.

⚠️ НЕ ВСЁ обязано быть в круге, и молча требовать этого нельзя: часть
проверок исключена ОСОЗНАННО (шумят, требуют аргумент, ходят в сеть).
Такие перечислены ниже вместе с причиной — список исключений и есть
то место, где решение записано. Красный сторож в круге приучает
не смотреть на красное, поэтому «включить всех» тут неверный ответ.

Запуск:  python tools/check_watchmen.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REFRESH = TOOLS / "refresh.py"

# Осознанно вне круга — с причиной. Прежде чем дописывать сюда имя,
# спроси: сторож правда не годится в круг, или его просто лень чинить?
OUTSIDE = {
    "check_dialogues": "требует аргумент — файл прогона",
    "check_terms": "1389 замечаний, и почти все — устройство режима "
                   "(одна строка, два перевода: обычный и режимный)",
    "check_list_marks": "сам разошёлся с модом: знает меньше знаков, "
                        "чем ColorLayout.CHOICE_MARKS",
    "check_item_ids": "ходит в сеть, в круге это лишние 110 МБ",
    "check_release": "встроен в release.py — там ему и место",
    "check_installed": "проверяет ИНСТАНСЫ, а не сборку: зовётся после неё",
    "check_headers": "признак слишком строгий — 5 ложных находок; "
                      "сперва чинить, потом включать",
    "check_head_colors": "не сторож, а ПРАВИЛКА: печатает расхождения цвета "
                         "и применяет их по --yes",
}


def in_circle() -> set[str]:
    """Имена, которые `refresh.py` действительно запускает."""
    text = REFRESH.read_text(encoding="utf-8")
    return {Path(m).stem for m in re.findall(r'"tools/(check_\w+\.py)"', text)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    all_checks = {p.stem for p in TOOLS.glob("check_*.py")}
    inside = in_circle()
    print(f"сторожей всего: {len(all_checks)}, в круге сборки: {len(inside)}")

    missing = sorted(all_checks - inside - set(OUTSIDE))
    stale = sorted(set(OUTSIDE) - all_checks)
    both = sorted(inside & set(OUTSIDE))

    if stale:
        print("\n⚠️ В списке исключений есть НЕСУЩЕСТВУЮЩИЕ сторожа "
              "(переименовали или удалили):")
        for name in stale:
            print(f"    {name}")
    if both:
        print("\n⚠️ Числится исключением, но В КРУГЕ ЕСТЬ — уберите из списка:")
        for name in both:
            print(f"    {name}")
    if missing:
        print(f"\n=== ⚠️ НЕ В КРУГЕ И БЕЗ ПРИЧИНЫ: {len(missing)} ===")
        print("  Такой сторож срабатывает, только если о нём вспомнить.")
        print("  Либо впишите в refresh.py, либо назовите причину в OUTSIDE.")
        for name in missing:
            print(f"    {name}")
        return 1
    if stale or both:
        return 1
    print("\nСЛОМАНО: 0 — каждый сторож либо в круге, либо исключён с причиной")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
