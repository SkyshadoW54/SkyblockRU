# -*- coding: utf-8 -*-
"""
ЧАСТИЧНАЯ РАЗМЕТКА — когда у одного предмета часть абзацев цветная, часть нет.

Беда, ради которой написано (31.07, скриншот игрока). У `Ghost Abilities`
десять способностей, и восемь показывались с белым заголовком и подсветкой,
а две — слипшимся серым текстом. В моде поломки не было: у восьми перевод
РАЗМЕЧЕН (`§7∙ §fСпособность призрака:…`), а у двух ПЛОСКИЙ. Плоский мод
красит догадкой и заливает абзац одним цветом.

⚠️ Это ХУЖЕ, чем если бы разметки не было нигде: соседние строки одной
подсказки выглядят по-разному, и глаз цепляется именно за разнобой.
Ровно тот довод, что записан про редкости («соседние пункты списка читают
столбиком, и однородность у них важнее точности каждого по отдельности»).

⚠️ Признак МЕХАНИЧЕСКИЙ и считается по корпусу — без игры и без дампа.
Этим он отличается от `check_headers`, который читает `dump/preview.json`
и потому видит лишь то, на что игрок наводил мышкой: на живых данных он
проверил 23 заголовка из 175 подсказок и про Ghost Abilities промолчал.

Что делает:
  * без аргументов — сравнивает с базовой линией и РУГАЕТСЯ ПРИ РОСТЕ.
    Долг в 489 абзацев сборку не валит (иначе она не собралась бы никогда),
    а вот новый разнобой валит: значит мы только что его и внесли;
  * `--accept` — принять текущее число за новую базовую линию;
  * `--list` — показать предметы, где осталось дописать один-два абзаца:
    это самые дешёвые победы.

    python tools/check_markup_gaps.py
    python tools/check_markup_gaps.py --list
    python tools/check_markup_gaps.py --accept
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
BASELINE = ROOT / "data" / "work" / "markup_gaps_baseline.json"


def measure():
    """Разложить переводы по предметам: где размечено, где плоско."""
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else (data.get("paragraphs") or [])

    by_item = defaultdict(lambda: {"marked": [], "flat": []})
    for entry in items:
        if not isinstance(entry, dict):
            continue
        ru = entry.get("ru") or ""
        item = entry.get("item") or ""
        # ⚠️ Без имени предмета вопрос не ставится вовсе: беда в том, что
        # РЯДОМ в одной подсказке разные абзацы выглядят по-разному.
        if not ru or not item:
            continue
        key = "marked" if "§" in ru else "flat"
        by_item[item][key].append(entry.get("text") or "")

    mixed = {name: rows for name, rows in by_item.items()
             if rows["marked"] and rows["flat"]}
    return by_item, mixed


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accept", action="store_true",
                        help="принять текущее число за базовую линию")
    parser.add_argument("--list", action="store_true",
                        help="показать предметы с самым коротким остатком")
    parser.add_argument("--show", type=int, default=20, help="сколько строк показать")
    args = parser.parse_args()

    if not CORPUS.exists():
        print(f"нет корпуса: {CORPUS}")
        return 1

    by_item, mixed = measure()
    gaps = sum(len(rows["flat"]) for rows in mixed.values())

    print(f"предметов с переводом:        {len(by_item)}")
    print(f"из них разметка ЧАСТИЧНАЯ:    {len(mixed)}")
    print(f"плоских абзацев внутри них:   {gaps}")
    print("   (это и есть работа: цвет соседей уже известен)")

    if args.list:
        # Сперва те, где дописать осталось меньше всего, а размечено много:
        # там разнобой заметнее всего, а работы на один абзац.
        order = sorted(mixed.items(),
                       key=lambda kv: (len(kv[1]["flat"]), -len(kv[1]["marked"])))
        print()
        print("%-40s %6s %6s" % ("предмет", "плоск", "разм"))
        for name, rows in order[:args.show]:
            print("%-40s %6d %6d" % (name[:40], len(rows["flat"]), len(rows["marked"])))
        if len(order) > args.show:
            print(f"   ... ещё {len(order) - args.show}")

    known = {}
    if BASELINE.exists():
        known = json.loads(BASELINE.read_text(encoding="utf-8"))

    if args.accept:
        BASELINE.write_text(json.dumps({"items": len(mixed), "paragraphs": gaps},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
        print()
        print(f"базовая линия принята: предметов {len(mixed)}, абзацев {gaps}")
        return 0

    if not known:
        print()
        print("базовой линии нет — принять текущее: --accept")
        return 0

    was = known.get("paragraphs", 0)
    print()
    if gaps > was:
        # ⚠️ Ругаемся только на РОСТ. Существующий долг сборку не валит:
        # красный сторож в круге приучает не смотреть на красное.
        print(f"СЛОМАНО: разнобой ВЫРОС — было {was}, стало {gaps} (+{gaps - was})")
        print("   Значит только что появился предмет, где часть абзацев цветная,")
        print("   а часть плоская. Разметить: python tools/color_lore.py --apply")
        print("   Если рост осознан (купили новые переводы) — принять: --accept")
        return 1
    if gaps < was:
        print(f"стало ЛУЧШЕ: было {was}, стало {gaps} (-{was - gaps})")
        print("   Принять новую планку: --accept")
        return 0
    print(f"без изменений: {gaps} (планка {was})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
