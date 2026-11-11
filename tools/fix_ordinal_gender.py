# -*- coding: utf-8 -*-
"""Порядковое числительное согласуется с ИМЕНЕМ СОБЫТИЯ, а не пишется наугад.

⚠️ Hypixel нумерует события («510th Spooky Festival», «3rd Jerry's Workshop»),
и по-русски окончание зависит от РОДА следующего слова: «{n}-я Ярмарка»,
«{n}-й Праздник урожая», «{n}-е Празднование». Каждая строка переводилась
в свой вечер, и в режимной заготовке накопился разнобой: «{n}-й Ярмарка»
100 раз против «{n}-я Ярмарка» 86 — то есть большинство было НЕВЕРНЫМ.

⚠️ ЧИНИМ ТОЛЬКО ИМЕНИТЕЛЬНЫЙ. «{n}-й Ярмарке» и «{n}-й Ярмарки» — это
предложный и родительный, и там «-й» ЗАКОННО («на пятой ярмарке»). Признак
по одному лишь окончанию числительного объявил бы их ошибкой; смотреть надо
на форму самого имени.

⚠️ Род задан ЯВНЫМ списком, а не выведен по окончанию: «Празднование»
среднего, «Жуткий» (фестиваль) мужского — правило по последней букве
ошибётся на обоих. Список пополняется вместе с событиями.

    python tools/fix_ordinal_gender.py         покажет
    python tools/fix_ordinal_gender.py --yes   применит
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Имя события в ИМЕНИТЕЛЬНОМ -> нужное окончание числительного.
GENDER = {
    "Ярмарка": "я", "Охота": "я", "Фиеста": "я", "Феерия": "я",
    "Праздник": "й", "Сезон": "й", "Жуткий": "й", "Фестиваль": "й",
    "Год": "й", "Зоопарк": "й", "Аукцион": "й",
    "Празднование": "е", "Состязание": "е", "Событие": "е",
}

FILES = ["data/work/full_paragraphs_ru.json", "data/work/full_strings.json",
         "data/work/paragraphs.json", "data/work/from_game.json",
         "data/work/queue_archive.json", "data/work/buttons.json",
         "data/work/nametags.json", "data/work/menu_paragraphs.json"]

PAIR = re.compile(r"\{n\}-([йяе])(\s+(?:\u00a7.)?)([А-ЯЁ][а-яё]+)")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Согласовать порядковое с событием")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    seen: collections.Counter = collections.Counter()
    total = 0
    for name in FILES:
        path = ROOT / name
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8")

        def fix(match: re.Match) -> str:
            want = GENDER.get(match.group(3))
            if not want or want == match.group(1):
                return match.group(0)
            seen[f"{{n}}-{match.group(1)} {match.group(3)} -> {{n}}-{want}"] += 1
            return "{n}-" + want + match.group(2) + match.group(3)

        new = PAIR.sub(fix, raw)
        if new == raw:
            continue
        # ⚠️ длина строки не меняется — правится один знак; сверка от беды,
        # когда замена задевала соседний текст
        assert len(new) == len(raw), name
        total += 1
        if args.yes:
            json.loads(new)          # файл обязан остаться разбираемым
            path.write_text(new, encoding="utf-8")

    for what, count in seen.most_common():
        print(f"  {count:4}  {what}")
    print(f"правок: {sum(seen.values())} в {total} файлах")
    if not args.yes:
        print("\nСУХОЙ ПРОГОН. Применить: --yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
