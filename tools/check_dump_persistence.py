"""
Сверяет, что каждый файл дампа ОСОЗНАННО либо копится, либо обнуляется.

Зачем отдельная проверка. Мод пишет дамп несколькими файлами, и они делятся
на два разных вида, которые легко перепутать:

  ДАННЫЕ ОТ СЕРВЕРА — строки, подсказки, цвета кусков. От версии мода
    не зависят, собираются игрой по крупицам и должны ПЕРЕЖИВАТЬ перезапуск:
    UnknownStrings.load() поднимает их с диска при старте.

  ОТЧЁТЫ О ПОВЕДЕНИИ — что мод решил, как выглядит экран, где вышла смесь
    языков. Это история КОНКРЕТНОГО jar, и копить её вредно: она заставляет
    чинить давно починенное. Так уже было с mixed.json — жалоба от прошлого
    jar выглядела как свежая беда.

Беда, от которой сторож поставлен: файл первого вида забыли прочитать при
старте. Тогда коллекция пуста, а первая же автозапись подменяет файл на
диске — и собранное за прошлую сессию исчезает. Ошибок нет, в логе тишина,
счёт просто каждый раз начинается с нуля.

Наступали дважды. Сперва на collected.json («так и потеряли первые несколько
тысяч строк» — комментарий в UnknownStrings.load). Потом на
paragraph-colors.json, и там дороже: живые цвета — ЕДИНСТВЕННЫЙ источник
разметки для 2329 абзацев, потому что в репозитории NEU лежат одни предметы,
а меню и экраны есть только в игре. Хуже всего, что стирал их именно
перезапуск ради проверки очередной правки.

Морали для этого не хватило: она была записана про первый файл, а грабля
пришла со вторым. Поэтому проверка механическая — новый файл дампа, не
отнесённый ни к одному виду, останавливает сборку и заставляет решить.

Запуск:  python tools/check_dump_persistence.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JAVA = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "UnknownStrings.java"

# Файлы, которые ОБЯЗАНЫ подниматься при старте: это собранные данные.
# Для каждого сказано, кто их потом читает, — чтобы следующий читатель
# видел цену потери, а не просто список имён.
ACCUMULATED = {
    "collected.json": "строки по источникам и частоты — их читают все инструменты",
    "tooltips.json": "подсказки блоками — из них make_paragraphs.py строит корпус",
    "highlighted.json": "имена, подсвеченные Hypixel, — список того, что НЕ переводим",
    "paragraph-colors.json": "цвета кусков абзацев — единственный источник разметки "
                             "для меню и экранов, в NEU их нет",
    "item-ids.json": "идентификаторы предметов из NBT — приходят от сервера "
                     "и от версии jar не зависят; собираются медленно, по одному "
                     "предмету за наведение",
}

# Файлы, которые обнуляются НАМЕРЕННО: это отчёт о поведении текущего jar.
REPORTS = {
    "color-cases.json": "что мод РЕШИЛ про склейку — решение прошлого jar "
                        "проверять бессмысленно",
    "preview.json": "как выглядит экран СЕЙЧАС; накопив, будем искать беды, "
                    "которых уже нет",
    "mixed.json": "смесь языков; уже сейчас накопительный, и это мешает — "
                  "в нём лежит починенное",
    "untranslated.json": "отчёт по непереведённому, строится заново из collected",
    "untranslated.txt": "то же самое глазами",
}

WRITES = re.compile(r'writeAtomic\(dumpDir\.resolve\("([^"]+)"\)')
READS = re.compile(r'dumpDir\.resolve\("([^"]+)"\)')


def main() -> int:
    if not JAVA.exists():
        print(f"нет файла {JAVA}")
        return 1
    source = JAVA.read_text(encoding="utf-8")

    written = set(WRITES.findall(source))
    # Чтение — это любое упоминание файла ВНЕ вызова записи.
    read = set(READS.findall(source)) - written | {
        name for name in READS.findall(source)
        if re.search(r'Path \w+ = dumpDir\.resolve\("' + re.escape(name) + r'"\)', source)
    }

    problems: list[str] = []
    notes: list[str] = []

    for name in sorted(written):
        if name in ACCUMULATED:
            if name in read:
                notes.append(f"  [копится] {name} — {ACCUMULATED[name]}")
            else:
                problems.append(
                    f"  {name} объявлен накопительным, но при старте НЕ ЧИТАЕТСЯ.\n"
                    f"      Значит собранное пропадёт при первом же перезапуске игры.\n"
                    f"      Цена: {ACCUMULATED[name]}.\n"
                    f"      Чинится методом load...() рядом с loadParagraphColors().")
        elif name in REPORTS:
            notes.append(f"  [обнуляется] {name} — {REPORTS[name]}")
        else:
            problems.append(
                f"  {name} — НОВЫЙ файл дампа, и решение о нём не принято.\n"
                f"      Впиши его в ACCUMULATED (данные от сервера — копить,\n"
                f"      и тогда добавь чтение при старте) либо в REPORTS\n"
                f"      (отчёт о поведении этого jar — обнулять).")

    for name in sorted(ACCUMULATED):
        if name not in written:
            notes.append(f"  [нет записи] {name} — мод его больше не пишет, "
                         f"строку из ACCUMULATED можно убрать")

    print(f"файлов дампа: {len(written)}")
    for line in notes:
        print(line)

    if problems:
        print()
        print(f"=== СЛОМАНО: {len(problems)} ===")
        for line in problems:
            print(line)
        return 1

    print()
    print("замечаний нет: каждый файл дампа либо копится, либо обнуляется осознанно")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
