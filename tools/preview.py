"""
Показывает ПОДСКАЗКУ ПРЕДМЕТА так, как её видит игрок, — прямо в терминале.

Зачем. Пока проверять приходилось скриншотами, круг был такой: игрок увидел
беду, прислал картинку, я угадал причину, собрал jar, он перезапустил игру
и проверил. Один заход — минуты, а бед за вечер десятки. При этом мод держит
подсказку в руках целиком, вместе с цветами: остаётся записать её до и после
перевода, а нарисовать можно и здесь.

Теперь так: игрок открывает пару меню, и весь его экран лежит в
dump/preview.json. Инструмент рисует подсказки настоящими цветами (ANSI),
слева оригинал, справа перевод — видно и текст, и раскраску, и перенос строк.

Запуск:
  python tools/preview.py                    последние подсказки
  python tools/preview.py minion             только те, где в имени есть «minion»
  python tools/preview.py --broken           только там, где ЦВЕТ изменился
  python tools/preview.py --plain            без ANSI-цветов (для файла)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/preview.json")

# Цвета Minecraft -> ANSI. Названия те же, что отдаёт TextColor.serialize().
ANSI = {
    "black": 30, "dark_blue": 34, "dark_green": 32, "dark_aqua": 36,
    "dark_red": 31, "dark_purple": 35, "gold": 33, "gray": 37,
    "dark_gray": 90, "blue": 94, "green": 92, "aqua": 96,
    "red": 91, "light_purple": 95, "yellow": 93, "white": 97,
}
RESET = "\033[0m"


def paint(pieces: list, plain: bool) -> str:
    """
    Строка подсказки в терминал: каждый кусок своим цветом.

    Цвет приходит в виде «gray» либо «gray+b+i»: после плюсов — начертание
    (bold, italic, underline, strikethrough). Мод пишет их тоже: на экране
    они видны, и без них снимок не равен подсказке.
    """
    out = []
    for color, text in pieces:
        name, *flags = color.split("+")
        if plain or name not in ANSI:
            out.append(text)
            continue
        codes = [str(ANSI[name])]
        codes += [{"b": "1", "i": "3", "u": "4", "s": "9"}[f] for f in flags if f in "bius"]
        out.append("\033[" + ";".join(codes) + f"m{text}{RESET}")
    return "".join(out)


def colors_of(rows: list) -> list:
    """Цвета всех кусков подряд — чтобы сравнить раскраску до и после."""
    return [color for row in rows for color, text in row if text.strip()]


def width_of(rows: list) -> int:
    return max((sum(len(t) for _, t in row) for row in rows), default=0)


def starts_lines(lines: list) -> set[str]:
    """Цвета, которые ВСЕГДА начинают строку и никогда не идут в её середине.

    Так устроены блоки Hypixel: тусклая приписка «§8The pet must be visible…»
    и заголовок «§6Ability:» стоят своими строками. Пустой строкой они
    не отделены, и отличить их от прозы можно только по этому.
    """
    starts: set[str] = set()
    inside: set[str] = set()
    for line in lines:
        pieces = [p for p in line if len(p) >= 2 and str(p[1]).strip()]
        for i, piece in enumerate(pieces):
            (starts if i == 0 else inside).add(piece[0])
    return starts - inside


def structure_broken(before: list, after: list) -> list[str]:
    """
    Съехала ли ВЁРСТКА: блок, который был отдельной строкой, влился в текст.

    ⚠️ Эту беду не ловила ни одна проверка, и нашёл её игрок. Цвета целы —
    приписка осталась тусклой; набор цветов тот же; словарь в порядке. Поехала
    СТРУКТУРА: «§8The pet must be visible to apply the item!» занимала целую
    строку, а после склейки абзаца начинается с середины: «…в любое время!
    Питомец должен быть виден,». Пауза, которую делал Hypixel, пропала.

    Признак механический: цвет занимал целую строку в оригинале и перестал
    в переводе. Заголовки и приписки так и устроены, а проза — никогда.
    """
    lost = starts_lines(before) - starts_lines(after)
    # серый — цвет тела, он занимает целые строки и в прозе: не признак
    lost -= {"gray", "white"}
    if not lost:
        return []
    return [f"ВЁРСТКА СЪЕХАЛА: {', '.join(sorted(lost))} — этот блок был отдельной"
            f" строкой, а теперь влит в текст (пропала пауза, которую делал Hypixel)"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if os.name == "nt":
        os.system("")     # включает ANSI в консоли Windows
    parser = argparse.ArgumentParser(description="Подсказка предмета в терминале")
    parser.add_argument("filter", nargs="?", default="", help="часть имени предмета")
    parser.add_argument("--broken", action="store_true", help="только где цвет изменился")
    parser.add_argument("--plain", action="store_true", help="без цветов")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--file", help="другой файл снимков (по умолчанию — из дампа)")
    args = parser.parse_args()

    global DUMP
    if args.file:
        DUMP = Path(args.file)
    if not DUMP.exists():
        print(f"нет файла: {DUMP}")
        print("Он появляется, когда игрок наводит курсор на предметы"
              " с модом свежей сборки.")
        return 1

    cases = json.loads(DUMP.read_text(encoding="utf-8")).get("cases") or []
    picked = [c for c in cases
              if args.filter.lower() in (c.get("item") or "").lower()]
    if args.broken:
        picked = [c for c in picked
                  if colors_of(c.get("before") or []) != colors_of(c.get("after") or [])]

    print(f"подсказок записано: {len(cases)}, показываю: {min(len(picked), args.limit)}")
    if args.filter:
        print(f"  фильтр по имени: «{args.filter}»")
    print()

    for case in picked[:args.limit]:
        before = case.get("before") or []
        after = case.get("after") or []
        title = case.get("item") or "?"
        left = max(width_of(before), 30)

        print("=" * (left + 46))
        print(f"  {title}")
        print("=" * (left + 46))
        print(f"  {'ДО (как прислал Hypixel)':<{left}}    ПОСЛЕ (что увидит игрок)")
        print(f"  {'-' * left}    {'-' * 34}")
        for i in range(max(len(before), len(after))):
            row_a = before[i] if i < len(before) else []
            row_b = after[i] if i < len(after) else []
            text_a = "".join(t for _, t in row_a)
            pad = " " * max(0, left - len(text_a))
            print(f"  {paint(row_a, args.plain)}{pad}    {paint(row_b, args.plain)}")

        for note in structure_broken(before, after):
            print()
            print("  ⚠️ " + note)

        # что изменилось в раскраске: молчаливая потеря цвета — главная беда
        #
        # ⚠️ Считаем НАБОР цветов, а не число кусков. Перенос строки режет
        # термин надвое («§9Enchanted» / «§9Hopper»), а перевод склеивает его
        # обратно в один кусок — цвет при этом цел, но счётчик кусков падает
        # с 2 до 1 и объявляет потерю. Такая жалоба хуже, чем её отсутствие:
        # на неё тратится время, а чинить нечего. Настоящая потеря — это когда
        # цвета не осталось ВОВСЕ.
        was, now = set(colors_of(before)), set(colors_of(after))
        lost = sorted(was - now)
        gained = sorted(now - was)
        if lost or gained:
            print()
            if lost:
                print("  ⚠️ цвета стало МЕНЬШЕ: " + ", ".join(sorted(lost)))
                # ⚠️ Мало знать, ЧТО цвет пропал, — нужна СТРОКА, где это вышло.
                # Без неё приходится глазами сличать два столбца, а при потере
                # в одном слове из сорока это безнадёжно. Разбор писался
                # одноразовым скриптом, поэтому и живёт теперь здесь.
                for line in before:
                    used = {p[0] for p in line if len(p) >= 2 and str(p[1]).strip()}
                    if not used & set(lost):
                        continue
                    shown = " | ".join(f"{p[0]}:{str(p[1])[:24]}" for p in line
                                       if len(p) >= 2 and str(p[1]).strip())
                    print("     потеряно тут: " + shown[:104])
            if gained:
                print("  цвета стало больше: " + ", ".join(sorted(gained)))
        print()

    if not picked:
        print("ничего не подошло под фильтр")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
