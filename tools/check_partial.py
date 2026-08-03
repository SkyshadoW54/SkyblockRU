# -*- coding: utf-8 -*-
"""
ЧАСТИЧНО ПЕРЕВЕДЁННЫЕ ПОДСКАЗКИ — то, что игрок находит глазами.

Беда, ради которой написано. Игрок водит курсором по предметам, замечает
«тут русский, а строкой ниже английский», присылает скриншот — и так по кругу.
Находки случайны, узнаём с задержкой, а он работает сканером. При этом данные
для поиска у нас УЖЕ ЕСТЬ: мод пишет в `dump/preview.json` каждую подсказку
ДО и ПОСЛЕ перевода.

⚠️ Признак не тот, что у `report.py`. Там смесь ВНУТРИ строки
(«Даёт +2 Шанс двойной поклёвки»), а здесь смесь ПО ПОДСКАЗКЕ: строка целиком
осталась английской, а соседняя переведена. Именно это видно на экране
и именно это игрок присылает скриншотами.

Что считается непереведённой строкой:
  * после перевода она не изменилась,
  * в ней есть латинские БУКВЫ (число и значок не в счёт),
  * она не закрыта РЕШЕНИЕМ: имя предмета, имя NPC, место, жаргон
    (`terms.STAT_JARGON`), выключенный словарь.

⚠️ Последний пункт — половина ценности инструмента. Без него список
открывался зачарованиями дрели («Flowstate III», «Lapidary V»): игрок сам
их выключил, а отчёт звал бы это работой. Отчёт, показывающий решения,
приучает не смотреть в отчёт.

    python tools/check_partial.py              список подсказок
    python tools/check_partial.py --lines      сразу строки, по частоте
    python tools/check_partial.py --item Tank  разбор одной подсказки
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/preview.json")

CODES = re.compile(r"\u00a7.")
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")


def text_of(row) -> str:
    """Строка подсказки из кусков [[цвет, текст], …] или готовой строки."""
    if isinstance(row, str):
        return CODES.sub("", row)
    return CODES.sub("", "".join(p[1] for p in row if len(p) > 1))


def load_filters():
    """Что переводить НЕ надо — берём у тех, кто уже это решил."""
    import protected
    import terms
    guarded = {name.lower() for name in protected.collect()}
    jargon = {name.lower() for name in terms.STAT_JARGON}

    # ⚠️ ВЫКЛЮЧЕННЫЙ СЛОВАРЬ — это решение «оставить английским», а не дырка.
    # Спрашиваем `make_queue.already_translated`: там уже учтено, что
    # у пакетов с «default»: false берётся ВСЁ, включая regex и глоссарий.
    decided, rules = set(), []
    try:
        import make_queue
        known, _guarded, covered = make_queue.already_translated()
        decided = {key.lower() for key in known}
        rules = covered
    except Exception as failure:          # инструмент не должен падать из-за фильтра
        print(f"не смог прочитать решения по словарям: {failure}")
    return guarded, jargon, decided, rules


def untranslated(line: str, guarded: set, jargon: set,
                 decided=frozenset(), rules=()) -> bool:
    """Осталась ли строка английской ПО СУЩЕСТВУ, а не по форме."""
    if not LATIN_WORD.search(line):
        return False

    stripped = line.strip()
    # Закрыто РЕШЕНИЕМ: строка есть в словаре (в том числе выключенном).
    if stripped.lower() in decided:
        return False
    for rule in rules:
        try:
            if rule.search(stripped):
                return False
        except AttributeError:
            continue

    # ⚠️ Строка из одних защищённых имён — это не работа, а решение.
    # Без этого список забился бы именами предметов: их 9271, и мы
    # не переводим их нарочно (по ним ищут на аукционе).
    clean = line.lower()
    for name in guarded | jargon:
        if name in clean:
            clean = clean.replace(name, " ")
    return bool(LATIN_WORD.search(clean))


def scan(cases, guarded, jargon, decided=frozenset(), rules=()):
    rows = []
    for case in cases:
        before = [text_of(r) for r in (case.get("before") or [])]
        after = [text_of(r) for r in (case.get("after") or [])]
        if not before or not after or len(before) != len(after):
            continue
        # ⚠️ ИМЯ ПРЕДМЕТА не в счёт: оно стоит первой строкой и остаётся
        # английским НАРОЧНО. Без этого список забивался именами
        # («Glacial Divan's Drill», «Gold Ore»), то есть показывал решение.
        item = (case.get("item") or "").strip()
        translated, left = 0, []
        for index, (was, now) in enumerate(zip(before, after)):
            if not was.strip():
                continue
            if index == 0 and item and now.strip() == item:
                continue
            if was != now:
                translated += 1
            elif untranslated(now, guarded, jargon, decided, rules):
                left.append(now)
        # ⚠️ Нас интересует ЧАСТИЧНОЕ: если не переведено НИЧЕГО, это просто
        # ненаписанный перевод, он и так виден в отчётах по частоте.
        # А вот «половина русская, половина нет» — то, что режет глаз.
        if translated and left:
            rows.append((case.get("item") or "?", translated, left))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lines", action="store_true", help="строки, а не подсказки")
    parser.add_argument("--item", help="разобрать одну подсказку по имени")
    parser.add_argument("--show", type=int, default=15)
    args = parser.parse_args()

    if not DUMP.exists():
        print(f"нет файла: {DUMP}")
        print("Он появляется, когда игрок наводит курсор на предметы в игре.")
        return 0

    cases = json.loads(DUMP.read_text(encoding="utf-8")).get("cases") or []
    guarded, jargon, decided, rules = load_filters()
    rows = scan(cases, guarded, jargon, decided, rules)

    print(f"подсказок в дампе: {len(cases)}")
    print(f"переведены ЧАСТИЧНО: {len(rows)}")
    print()

    if args.item:
        for item, translated, left in rows:
            if args.item.lower() not in item.lower():
                continue
            print(f"=== {item}  (переведено строк: {translated})")
            for line in left:
                print(f"    {line[:88]}")
            print()
        return 0

    if args.lines:
        counter = Counter()
        for _, _, left in rows:
            counter.update(left)
        print("НЕПЕРЕВЕДЁННЫЕ СТРОКИ по числу подсказок, где они встретились:")
        for line, count in counter.most_common(args.show * 3):
            print(f"  {count:4d}x  {line[:84]}")
        return 0

    rows.sort(key=lambda r: -len(r[2]))
    print("%-34s %8s %8s" % ("подсказка", "русских", "англ."))
    for item, translated, left in rows[:args.show]:
        print("%-34s %8d %8d" % (item[:34], translated, len(left)))
        print("      %s" % left[0][:78])
    if len(rows) > args.show:
        print(f"   ... ещё {len(rows) - args.show}")
    print()
    print('Разбор одной: python tools/check_partial.py --item "имя"')
    print("Только строки: python tools/check_partial.py --lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
