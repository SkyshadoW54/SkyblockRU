# -*- coding: utf-8 -*-
"""
Убирает из дампа то, что переводить НЕ НАДО НИКОГДА: ники, гильдии, даты.

Зачем. Мод собирает всё, что не смог перевести, и счётчик в чате показывает
сумму: «+2 новых строк для перевода (всего 32418)». Игрок заметил, что цифра
не сходится с работой, — и был прав. Замер по живому дампу:

    боковая панель   6188 строк, годных для перевода    160
    таб               707 строк, годных                 131

Остальное — «[123] RubyPeach», «{n}/{n}/{n} M{n}B» и прочие ники. Каждый новый
игрок плодит новую «уникальную» строку: файл пухнет, счётчик растёт, упираются
потолки сбора — а работы за этим нет.

С 01.08 мод их и не собирает (`UnknownStrings.isNoise`), но накопленное надо
убрать отдельно — файл накопительный и сам не почистится.

    python tools/clean_noise.py          показать, что уйдёт
    python tools/clean_noise.py --yes    убрать (с копией рядом)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_queue import worth_translating  # noqa: E402

DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")
# ⚠️ Чистим ТОЛЬКО панель и таб. В `item_name` лежат имена предметов — их мы
# не переводим, но они нужны инструментам как список того, что трогать нельзя
# (`make_queue.real_item_headers`). Выбросив их, мы бы сломали защиту имён.
NOISY = ("scoreboard", "tab")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Убрать мусор из дампа")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--show", type=int, default=8)
    args = parser.parse_args()

    if not DUMP.exists():
        print("нет collected.json")
        return 1
    doc = json.loads(DUMP.read_text(encoding="utf-8"))
    sources = doc.get("sources") or {}

    was = sum(len(rows) for rows in sources.values() if isinstance(rows, dict))
    drop: dict[str, list[str]] = {}
    for name in NOISY:
        rows = sources.get(name)
        if not isinstance(rows, dict):
            continue
        drop[name] = [line for line in rows if not worth_translating(line, name)]

    total = sum(len(rows) for rows in drop.values())
    print("строк в дампе: %d" % was)
    for name, rows in drop.items():
        left = len(sources[name]) - len(rows)
        print("   %-11s уйдёт %5d, останется %4d" % (name, len(rows), left))
        for line in rows[:args.show]:
            print("        %s" % line[:56])
    print("\nвсего уйдёт: %d, останется: %d" % (total, was - total))

    if not args.yes:
        print("\nсухой прогон. Убрать: --yes")
        return 0

    # ⚠️ Копия обязательна: дамп копится месяцами и восстановить его неоткуда.
    backup = ROOT / "data" / "work" / "archive" / "collected-before-clean.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DUMP, backup)

    contexts = doc.get("contexts") or {}
    order = doc.get("order") or {}
    for name, rows in drop.items():
        for line in rows:
            sources[name].pop(line, None)
            contexts.pop(line, None)
            order.pop(line, None)
    DUMP.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    now = sum(len(rows) for rows in sources.values() if isinstance(rows, dict))
    print("\nубрано: %d, было %d, стало %d" % (total, was, now))
    print("копия: %s" % backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
