# -*- coding: utf-8 -*-
"""
СТЫКИ ОБРЫВКОВ — что выходит, когда соседние строки читаются подряд.

Беда, ради которой написано (31.07, Hyperion — самое ходовое оружие):

    оригинал                            перевод
    enemies. Also reduces your damage   врагов. Также снижает твой урон
    taken and grants an absorption      полученного урона и даёт щит
    shield for 5 seconds.               щит на 5 с.

На экране: «Также снижает твой урон ПОЛУЧЕННОГО УРОНА и даёт щит ЩИТ на 5 с.»
Каждый обрывок переводили отдельно, и в каждом переводчик додумывал контекст —
отсюда удвоение на стыках. Записанная грабля: «у обрывка нет своего смысла,
и переводить его в одиночку — гадание».

⚠️ Ни одна прежняя проверка это не ловит, и не случайно: каждая строка
ПО ОТДЕЛЬНОСТИ безупречна — дырки целы, значки на месте, имена не тронуты.
Беда рождается только при чтении подряд, то есть на экране.

Признаки (оба проверены на живых данных, а не выдуманы):

  1. ПОВТОР СЛОВА на стыке — надёжный. На дампе 7 находок, все настоящие
     («…и даёт щит» + «щит на 5 с.»).
  2. ПОВТОР ОСНОВЫ («время» + «времени») — шумит: под него попадают пары
     «заголовок + описание», где повтор законен («Хранилище» / «Храни здесь…»).
     Отсекаются ЦВЕТОМ: у заголовка он свой, у описания — цвет тела.

⚠️ Источник — `dump/preview.json`, то есть то, что мод РЕАЛЬНО показал.
Значит инструмент видит лишь подсказки, которые игрок открывал. Это не
недостаток признака, а свойство источника: полнее данных взять негде,
абзацная сборка тут не поможет — эти строки идут построчно.

    python tools/check_seams.py
    python tools/check_seams.py --all      показать и слабый признак
"""
import argparse
import json
import re
import sys
from pathlib import Path

DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/preview.json")

CODES = re.compile(r"§.")
WORD = re.compile(r"[А-Яа-яЁёA-Za-z]+")
# Предложение кончилось — следующая строка начинает новую мысль, стыка нет.
SENTENCE_END = (".", "!", "?", ":", ";")


def text_of(row) -> str:
    """Строка подсказки из кусков [[цвет, текст], …] или готовой строки."""
    if isinstance(row, str):
        return CODES.sub("", row)
    return CODES.sub("", "".join(p[1] for p in row if len(p) > 1))


def colors_of(row) -> list[str]:
    if isinstance(row, str):
        return []
    return [p[0] for p in row if len(p) > 1]


def stem(word: str) -> str:
    """Грубая основа: русское словоизменение сидит в хвосте."""
    return word.lower().replace("ё", "е")[:5]


def looks_like_header(a_row, b_row) -> bool:
    """
    Пара «заголовок + описание»? У заголовка цвет СВОЙ, у описания — тела.

    Без этого признак повтора основы даёт ложное на «Хранилище» / «Храни
    здесь общие предметы»: повтор есть, а беды нет — так и в оригинале.
    """
    a_colors, b_colors = colors_of(a_row), colors_of(b_row)
    if not a_colors or not b_colors:
        return False
    # у заголовка мало кусков и цвет не совпадает с началом описания
    return len(a_colors) <= 2 and a_colors[-1] != b_colors[0]


def scan(cases):
    exact, loose = [], []
    for case in cases:
        rows = case.get("after") or []
        item = case.get("item") or "?"
        lines = [text_of(r) for r in rows]
        for i in range(len(lines) - 1):
            a_line, b_line = lines[i], lines[i + 1]
            if not a_line.strip() or not b_line.strip():
                continue
            if a_line.rstrip().endswith(SENTENCE_END):
                continue
            left, right = WORD.findall(a_line), WORD.findall(b_line)
            if not left or not right:
                continue
            a, b = left[-1], right[0]
            if a.lower() == b.lower() and len(a) > 2:
                exact.append((item, a_line, b_line, a))
            elif (len(a) > 4 and len(b) > 4 and stem(a) == stem(b)
                    and not looks_like_header(rows[i], rows[i + 1])):
                loose.append((item, a_line, b_line, f"{a}|{b}"))
    return exact, loose


def show(rows, title, limit):
    print(f"=== {title}: {len(rows)} ===")
    seen = set()
    shown = 0
    for item, a_line, b_line, what in rows:
        # один и тот же стык у 15 вариантов Hyperion — показываем однажды
        key = (a_line, b_line)
        if key in seen:
            continue
        seen.add(key)
        if shown >= limit:
            continue
        shown += 1
        print(f"  [{what}] {item[:38]}")
        print(f"      …{a_line[-58:]}")
        print(f"      {b_line[:58]}…")
    if len(seen) > shown:
        print(f"  ... ещё {len(seen) - shown} разных стыков")
    print()
    return len(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true",
                        help="показать и слабый признак (повтор основы)")
    parser.add_argument("--show", type=int, default=10)
    args = parser.parse_args()

    if not DUMP.exists():
        print(f"нет файла: {DUMP}")
        print("Он появляется, когда игрок наводит курсор на предметы в игре.")
        return 0

    data = json.loads(DUMP.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    print(f"подсказок в дампе: {len(cases)}")
    print()

    exact, loose = scan(cases)
    broken = show(exact, "ПОВТОР СЛОВА на стыке (беда)", args.show)
    if args.all:
        show(loose, "повтор основы (смотреть глазами)", args.show)
    elif loose:
        print(f"(повтор основы: {len(loose)} — показать: --all)")
        print()

    if broken:
        print("Это ОБРЫВКИ, переведённые порознь: каждый сам по себе верен,")
        print("а вместе читаются с удвоением. Чинить правкой переводов так,")
        print("чтобы склейка соседних строк была осмысленной.")
        return 1
    print("повторов на стыках нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
