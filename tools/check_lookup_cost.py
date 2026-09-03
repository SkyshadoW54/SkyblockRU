"""
Не собирает ли `status.lookup` регулярки ЗАНОВО на каждую строку.

Зачем. 29.08 отчёт `report.py`, который в CLAUDE.md назван первой дешёвой
командой сессии («за 2-3 минуты»), шёл СОРОК МИНУТ. Замер профилировщиком:
из 34.4 секунды на 300 строк 32.1 приходились на `re._compile`, вызванный
113 095 раз, — то есть 377 компиляций регулярки на КАЖДУЮ строку.

Причина оказалась не в коде, а в РОСТЕ СЛОВАРЯ. `lookup` перебирает записи
с дыркой `{s}` и собирал из каждой шаблон заново (`re.escape` + замены +
`re.fullmatch` со строкой-шаблоном). Внутренний кэш Python это скрывал, пока
таких записей было меньше 512 — ровно столько регулярок он держит. Записей
стало 544, кэш начал вытесняться на каждом обороте и перестал работать вовсе.

⚠️ БЕДА ТИХАЯ ПО ПОСТРОЕНИЮ, и в этом её цена. Ничего не ломается, ответы
верные, ни один сторож не краснеет — инструмент просто перестаёт быть дешёвым.
Заметить это можно только по часам, а списывается оно на «данных стало больше».
Порог перешагнули молча, и когда именно — сказать уже нельзя.

Поэтому проверяем не ВРЕМЯ (оно зависит от машины и врёт), а ПРИЗНАК:
число компиляций не должно РАСТИ вместе с числом строк. Сколько бы строк
мы ни спросили, регулярка каждой записи собирается один раз.

Оба края обязательны:
  * живой путь: вторая сотня строк почти не компилирует — кэш работает;
  * ПОДСАДКА прежнего кода: та же сотня компилирует сотнями — значит замер
    видит беду, а не молчит по своей слепоте.

Запуск:
  python tools/check_lookup_cost.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import status  # noqa: E402

# Сколько строк в пачке. Больше не нужно: признак смотрит на РОСТ, а не
# на абсолютное число, и на сотне он виден так же ясно, как на тысяче.
BATCH = 150

# ⚠️ Порог задан НА СТРОКУ, а не общим числом: общий пришлось бы правит
# всякий раз, когда меняется размер пачки. Живой путь компилирует ноль;
# запас в половину компиляции на строку оставлен на случай, когда во второй
# пачке встретится запись, которой не было в первой.
MAX_PER_LINE = 0.5


def live_lines(limit: int) -> list[str]:
    """Живые строки из дампа — выдуманные тут не годятся."""
    collected = status.DUMP / "collected.json"
    if not collected.exists():
        return []
    data = json.loads(collected.read_text(encoding="utf-8"))
    seen: list[str] = []
    known: set[str] = set()
    for source, entries in (data.get("sources") or {}).items():
        for line in entries:
            clean = status.clean(line)
            if clean and clean not in known:
                known.add(clean)
                seen.append(clean)
            if len(seen) >= limit:
                return seen
    return seen


class Counter:
    """Считает НАСТОЯЩИЕ компиляции: промахи мимо кэша, а не вызовы re.*."""

    def __init__(self) -> None:
        self.count = 0
        self.original = None

    def __enter__(self) -> "Counter":
        self.original = re._compiler.compile
        counter = self

        def counted(*args, **kwargs):
            counter.count += 1
            return counter.original(*args, **kwargs)

        re._compiler.compile = counted
        return self

    def __exit__(self, *_) -> None:
        re._compiler.compile = self.original


def old_way(line: str, dic: status.Dictionaries) -> None:
    """
    Прежний код: шаблон собирается и компилируется на каждую строку.

    Нужен ПОДСАДКОЙ. Без него «компиляций 0» значит лишь «замер ничего
    не увидел», и отличить работающий кэш от слепого сторожа нечем.
    """
    for key in dic.templates:
        if "{s}" not in key:
            continue
        pattern = re.escape(key)
        pattern = pattern.replace(re.escape("{s}"), status.NAME_HOLE)
        pattern = pattern.replace(re.escape("{n}"), status.NUMBER_HOLE)
        re.fullmatch(pattern, line)


def main() -> int:
    if not hasattr(re, "_compiler"):
        print("СЛОМАНО: у этой сборки Python нет re._compiler —"
              " считать компиляции нечем, проверка невозможна")
        return 1

    dic = status.Dictionaries()
    holes = sum(1 for key in dic.templates if "{s}" in key)
    print(f"записей с дыркой {{s}}: {holes}")
    print(f"кэш регулярок Python: {re._MAXCACHE} штук"
          f"{'  <-- МЕНЬШЕ, чем записей: сам по себе он уже не спасает'
             if holes >= re._MAXCACHE else ''}")

    lines = live_lines(BATCH * 2)
    if len(lines) < BATCH * 2:
        print(f"СЛОМАНО: живых строк всего {len(lines)},"
              f" нужно {BATCH * 2} — проверять не на чем")
        return 1

    first, second = lines[:BATCH], lines[BATCH:BATCH * 2]

    # первая пачка греет кэш, вторая и есть замер
    for line in first:
        status.lookup(line, dic)
    with Counter() as counter:
        for line in second:
            status.lookup(line, dic)
    live = counter.count

    with Counter() as counter:
        for line in second:
            old_way(line, dic)
    probe = counter.count

    limit = BATCH * MAX_PER_LINE
    print(f"\nживой путь:  {live:6} компиляций на {BATCH} строк"
          f"  ({live / BATCH:.2f} на строку, порог {MAX_PER_LINE})")
    print(f"ПОДСАДКА:    {probe:6} компиляций на те же строки"
          f"  ({probe / BATCH:.1f} на строку)")

    bad = 0
    if live > limit:
        bad += 1
        print("\nСЛОМАНО: регулярки собираются заново на каждую строку —"
              " кэш `status.hole_rule` не работает.")
        print("  Признак тот же, что 29.08: отчёт станет считать минутами,"
              " и никто не скажет, почему.")
    if probe <= limit:
        bad += 1
        print("\nСЛОМАНО: подсадка прежнего кода НЕ покраснела —"
              " значит замер слеп и молчал бы при настоящей беде.")

    print()
    if bad:
        print(f"СЛОМАНО: {bad}")
        return 1
    print(f"СЛОМАНО: 0 — регулярка каждой записи собирается один раз"
          f" (подсадка ловит: {probe} против {live})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
