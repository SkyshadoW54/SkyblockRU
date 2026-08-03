"""
Съехавшие ЗАГОЛОВКИ: строка была отдельной, а стала слитой с описанием.

Беда, ради которой написано. Hypixel ставит пункт так:

    ∙ Class Passive: Doubleshot          <- заголовок, своя строка, свой цвет
    50% chance to shoot a second arrow.  <- описание

а на экране выходило слипшееся «∙ Пассивка класса: Doubleshot 50% шанс
выпустить вторую стрелу.». Заметить это можно было только сравнив русский
скриншот с английским — то есть глазами и вручную, на каждом предмете.

⚠️ Признак берётся из ДАННЫХ, а не из текста перевода: в `before` заголовок —
это строка, целиком набранная ОДНИМ цветом, а следующая строка набрана другим.
Сравнивать переводы напрямую нельзя (заголовок переведён), а цвет и структура
строк переживают перевод и сравниваются железно.

⚠️ Источник — `dump/preview.json`: мод пишет туда подсказку ДО и ПОСЛЕ перевода
вместе с цветами. Файл НЕ накопительный: это отчёт о поведении КОНКРЕТНОГО jar,
и копить его вредно (иначе будем чинить давно починенное). Значит данные в нём —
за последнюю игровую сессию, и чем больше игрок походил по меню, тем полнее
проверка. Пусто — сходить в игру.

Запуск:
  python tools/check_headers.py
  python tools/check_headers.py --show 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/preview.json")

# Цвета, которыми Hypixel набирает ОПИСАНИЕ. Заголовок красится иначе —
# на этом и стоит признак.
BODY_COLORS = {"gray", "dark_gray"}

# Кириллица в строке значит «уже переведено» — проверять там нечего
CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def line_text(line: list) -> str:
    return "".join(piece[1] for piece in line)


def one_color(line: list) -> str | None:
    """Цвет строки, если она набрана ЦЕЛИКОМ одним цветом, иначе None."""
    colors = {piece[0] for piece in line if piece[1].strip()}
    return colors.pop() if len(colors) == 1 else None


def headers_of(lines: list) -> list[int]:
    """
    Номера строк-ЗАГОЛОВКОВ: строка одного цвета, а следующая — другого,
    причём следующая набрана цветом описания.

    ⚠️ Требуем, чтобы СЛЕДУЮЩАЯ строка была телом (серой). Без этого под
    признак попадал бы любой цветной список, где каждая строка своего цвета,
    и сторож зашумел бы на ровном месте.
    """
    out = []
    for index, line in enumerate(lines[:-1]):
        # ⚠️ ПЕРВУЮ строку пропускаем: это ИМЯ ПРЕДМЕТА, а мод режет его
        # как границу абзаца (`Paragraphs.nameAside`), а не как заголовок.
        # Без этого сторож объявлял поломкой «Crafting Table» и «Bone».
        if index == 0:
            continue
        text = line_text(line).strip()
        if not text:
            continue
        # ⚠️ Строка уже по-русски — значит перевод для неё есть, проверять
        # нечего. В `before` попадает и переведённое: имя предмета и часть
        # строк мод переводит раньше, чем доходит до абзацев.
        if CYRILLIC.search(text):
            continue
        # ⚠️ Список зачарований через запятую заголовком НЕ является:
        # «Sharpness VII, Smite VII, Tabasco III» — это перечисление, мод режет
        # его по секциям (`ParagraphColors.sections`), а не как заголовок.
        if "," in text:
            continue
        # Разделитель из дефисов Hypixel рисует своей строкой — переводить
        # там нечего.
        if not any(ch.isalnum() for ch in text):
            continue
        color = one_color(line)
        if color is None or color in BODY_COLORS:
            continue
        nxt = lines[index + 1]
        if not line_text(nxt).strip():
            continue
        next_color = one_color(nxt)
        if next_color in BODY_COLORS:
            out.append(index)
    return out


def merged(after: list, color: str, head_text: str) -> bool:
    """
    Заголовок слился с описанием: в переводе есть строка, которая НАЧИНАЕТСЯ
    куском цвета заголовка и продолжается куском цвета тела.
    """
    for line in after:
        if len(line) < 2:
            continue
        if line[0][0] != color:
            continue
        if any(piece[0] in BODY_COLORS and piece[1].strip() for piece in line[1:]):
            return True
    return False


def translated_lines() -> set:
    """
    Строки, для которых есть ПОСТРОЧНЫЙ перевод.

    ⚠️ Ради этого сторож и переделан. Сначала он сравнивал `before` и `after`
    из `preview.json` — то есть отчёт КОНКРЕТНОГО jar. Отчёт пишется в игре,
    и после правки он остаётся вчерашним: сторож честно показывал поломку,
    которой в новом jar уже нет, и БЛОКИРОВАЛ сборку до похода в игру.
    Красный сторож в круге приучает не смотреть на красное — это записано
    в CLAUDE.md.

    Проверять надо ПРИЧИНУ, а её видно без игры: мод режет заголовок, только
    если вырезанное совпадает с переводом ПЕРВОЙ СТРОКИ (`Paragraphs.header`).
    Нет такого перевода — резка отменится, заголовок слипнется с описанием.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import status
    except ImportError:
        return set()
    dic = status.Dictionaries()
    known = set(dic.exact) | set(dic.templates)

    def covered(text: str) -> bool:
        clean = status.clean(text).strip()
        if not clean or clean in known:
            return True
        return status.lookup(clean, dic) is not None

    return {"__check__": covered}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Заголовки, слипшиеся с описанием")
    parser.add_argument("--show", type=int, default=10)
    args = parser.parse_args()

    if not DUMP.exists():
        print(f"нет файла: {DUMP}")
        print("Сходи в игру и наведи курсор на предметы — мод запишет подсказки.")
        return 0

    cases = json.loads(DUMP.read_text(encoding="utf-8")).get("cases") or []
    print(f"подсказок в дампе: {len(cases)}")

    covered = translated_lines().get("__check__")
    if covered is None:
        print("не удалось прочитать словари — проверять нечем")
        return 0

    broken = {}
    checked = 0
    for case in cases:
        before = case.get("before") or []
        if not before:
            continue
        for index in headers_of(before):
            checked += 1
            head = line_text(before[index]).strip()
            if not covered(head):
                broken.setdefault(head, case.get("item", ""))

    print(f"заголовков проверено: {checked}")
    print()
    if not broken:
        print("=== СЛИПШИХСЯ ЗАГОЛОВКОВ НЕТ ===")
        print("    У каждого заголовка есть построчный перевод — значит мод")
        print("    отрежет его своей строкой, как в оригинале.")
        return 0

    print(f"=== СЛОМАНО: {len(broken)} ===")
    print("    Заголовок стоит ОТДЕЛЬНОЙ строкой, но построчного перевода у него")
    print("    НЕТ — значит резка отменится (Paragraphs.header сверяет вырезанное")
    print("    с переводом первой строки), и заголовок слипнется с описанием.")
    print("    Лечится правилом или записью на эту строку, а НЕ отказом от склейки.")
    for head, item in list(broken.items())[:args.show]:
        print(f"   [{item[:26]:28}] {head[:52]}")
    if len(broken) > args.show:
        print(f"   ... ещё {len(broken) - args.show}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
