# -*- coding: utf-8 -*-
"""
Значки в ключах корпуса — ПО СТРОКАМ ОТ СЕРВЕРА, а не по таблице символов.

⚠️ Зачем. Корпус собран из NEU и с вики, а там значки обычные юникодные
(«☘» U+2618, «❤» U+2764). Сервер же шлёт свои, из приватной зоны (U+E051,
U+E010). Ключ абзаца строится ПО ТЕКСТУ, значит не совпадает — и купленный
перевод не находится НИ РАЗУ. Замер 01.08: так лежит мёртвым грузом
699 абзацев, среди них весь набор Turbo-Crop и Harvesting.

⚠️ Таблицей «символ -> символ» это чинить НЕЛЬЗЯ, и это проверено: карта
неоднозначна. «❁» U+2741 уходит и в U+E050, и в U+E00D; «✈», «♆» и «⚓» —
все три в U+E086. Слепая замена испортила бы ключи там, где сейчас всё верно.

Поэтому сопоставляем СТРОКИ: берём строку корпуса, снимаем значки и пробелы,
ищем строку сервера с тем же скелетом — и подставляем ЕЁ значки по порядку.
Совпал скелет и число значков — замена точная, гадать нечего.

    python tools/fix_icons_by_server.py          показать, что изменится
    python tools/fix_icons_by_server.py --yes    применить
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")
CORPUS = ROOT / "data" / "work" / "paragraphs.json"

PRIVATE = re.compile(r"[-]")
# ⚠️ Диапазон шире «разных символов», но НЕ всеми подряд: «⊙» U+2299
# (Ender Slayer) лежит в математических операторах, и узкий набор его не видел —
# семь записей Ender Slayer оставались с чужим значком.
#
# ⚠️ Геометрические фигуры (25A0-25FF) СЮДА НЕ БЕРЁМ: «▶» и «○» — это
# МАРКЕРЫ СПИСКА, а не значки характеристик. С ними замена задела бы
# 187 ключей и сломала резку списков — проверено сухим прогоном.
ICON = re.compile(r"[\u2190-\u2bff\ue000-\uf8ff]")
SPACE = re.compile(r"\s+")


def list_marks() -> set[str]:
    """
    Знаки списка — ЧИТАЕМ ИЗ МОДА, копию не заводим.

    ⚠️ Они выглядят как значки и лежат в тех же блоках Юникода
    («✔», «✖», «∙»), но это ВЁРСТКА, а не характеристика. Подменишь
    их — сломаешь резку списков, а это в проекте уже стоило 13 подсказок.
    Набор расходился с модом дважды, поэтому берём его оттуда.
    """
    java = (ROOT / "src/main/java/ru/skyblockru/core/ColorLayout.java")
    marks: set[str] = set()
    try:
        text = java.read_text(encoding="utf-8")
    except OSError:
        return marks
    for name in ("CHOICE_MARKS", "EXTRA_CUT"):
        at = text.find(name + " =")
        if at < 0:
            continue
        chunk = text[at:text.find(";", at)]
        marks.update(re.findall(r'"(\W)"', chunk))
    return marks


MARKS = list_marks()


def skeleton(text: str) -> str:
    """Строка без значков и лишних пробелов — по нему сопоставляем."""
    return SPACE.sub(" ", ICON.sub("", text)).strip()


def server_lines() -> list[str]:
    """Всё, что реально прислал сервер: строки дампа и подсказок."""
    out: list[str] = []
    for name, pick in (("collected.json", "sources"), ("tooltips.json", "tooltips")):
        path = DUMP / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        chunk = data.get(pick)
        if isinstance(chunk, dict):
            for entries in chunk.values():
                out.extend(entries)
        elif isinstance(chunk, list):
            for block in chunk:
                out.extend(block.get("lines") or [])
    return out


# значок, необязательный пробел, слово — по слову и опознаём характеристику
AFTER = re.compile(r"([∀-⋿☀-➿⬀-⯿-])(\s*)([A-Za-z][A-Za-z\']*(?:\s+[A-Z][A-Za-z\']*)?)")

# во сколько раз главный значок слова должен превосходить остальные
STEADY = 3


def by_word(lines: list[str]) -> dict[str, str]:
    """
    Слово -> значок, которым сервер помечает ЕГО.

    ⚠️ Сопоставлять целые строки оказалось слишком строго: у большинства
    абзацев есть строки, которых игрок не открывал, и чинилось всего 2 ключа.
    А значок обозначает ХАРАКТЕРИСТИКУ, и она названа тут же — значит пара
    «значок + слово» опознаётся надёжно и без полной строки.

    ⚠️ Неоднозначные слова отсеиваем: у «Health» сервер ставит U+E010 (490 раз)
    и U+E011 (61) — это разные вещи (здоровье и его восстановление). Берём
    слово, только если главный значок втрое превосходит все прочие вместе.
    """
    seen: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for line in lines:
        if not isinstance(line, str) or not PRIVATE.search(line):
            continue
        for icon, _, word in AFTER.findall(line):
            if PRIVATE.match(icon):
                seen[word][icon] += 1
    table: dict[str, str] = {}
    for word, counter in seen.items():
        best, top = counter.most_common(1)[0]
        rest = sum(n for _, n in counter.most_common()[1:])
        if rest == 0 or top >= STEADY * rest:
            table[word] = best
    return table


def fixed_text(row: dict, table: dict[str, str]) -> str | None:
    """Ключ абзаца с серверными значками — или None, если менять нечего."""
    text = row.get("text") or ""
    # ключ с приватной зоной уже серверный, трогать нечего
    if not text or PRIVATE.search(text) or not ICON.search(text):
        return None

    def swap(match: re.Match) -> str:
        icon, gap, word = match.groups()
        if icon in MARKS:
            return match.group(0)
        # ⚠️ Сперва пробуем ПАРУ слов: у «Crit Damage» и «Crit Chance» значки
        # РАЗНЫЕ, а первое слово общее — по нему одному слово отсеивалось
        # как неоднозначное, и размеченный Critical V оставался под вики-значком.
        return table.get(word, table.get(word.split()[0], icon)) + gap + word

    new = AFTER.sub(swap, text)
    return new if new != text else None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Значки ключей по строкам сервера")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--show", type=int, default=12)
    args = parser.parse_args()

    table = by_word(server_lines())
    print(f"слов с устойчивым значком у сервера: {len(table)}")

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    rows = doc["paragraphs"]
    keys = {r.get("text") for r in rows}

    changes: list[tuple[dict, str]] = []
    collide = 0
    for row in rows:
        new = fixed_text(row, table)
        if not new or new == row.get("text"):
            continue
        if new in keys:
            # такой ключ уже есть — сливать записи не наше дело
            collide += 1
            continue
        changes.append((row, new))

    with_ru = sum(1 for row, _ in changes if row.get("ru"))
    print(f"абзацев с чужими значками: {len(changes)}  (из них с переводом: {with_ru})")
    if collide:
        print(f"пропущено — правильный ключ уже есть: {collide}")

    kinds: collections.Counter = collections.Counter()
    for row, new in changes:
        for a, b in zip(ICON.findall(row["text"]), ICON.findall(new)):
            if a != b:
                kinds[(a, b)] += 1
    for (a, b), n in kinds.most_common(8):
        print(f"   {n:5}x  U+{ord(a):04X} -> U+{ord(b):04X}")

    print()
    for row, new in changes[:args.show]:
        print("   было: " + row["text"][:88].replace("\u2618", "☘"))
        print("   стало:" + PRIVATE.sub("◇", new)[:88])
        print()

    if not args.yes:
        print("сухой прогон. Применить: --yes")
        return 0

    shutil.copyfile(CORPUS, CORPUS.with_suffix(".json.bak-icons"))
    before = len(rows)
    added = 0
    for row, new in changes:
        if not row.get("ru"):
            continue
        # ⚠️ Старый ключ НЕ трогаем, а добавляем ВТОРОЙ. Замена выглядела
        # логичной и провалила сверку: по ключам с «вики-значками» абзац
        # достижим из NEU и аукциона, и стереть их значило бы объявить
        # 554 перевода недостижимыми. А второй ключ ничего не отнимает:
        # перевод тот же, стоит ноль, и мод найдёт его на живых строках.
        #
        # ⚠️ Поле `source` обязательно: сторож контракта считает абзац
        # без него собранным из подсказки и требует, чтобы он там нашёлся.
        # Эти записи созданы намеренно — они «ждут своего случая».
        # ⚠️ Значки меняем И В ПЕРЕВОДЕ. Ключ теперь серверный, а перевод
        # выкладывается на экран как есть — оставь в нём «☘» из вики, и игрок
        # увидит обычный клевер вместо иконки Hypixel. Слово рядом ищем то же,
        # но по-русски его нет, поэтому идём по ПОЗИЦИЯМ: набор значков ключа
        # и перевода совпадает по порядку, а если не совпал — перевод не трогаем.
        ru = row["ru"]
        want = ICON.findall(new)
        have = ICON.findall(ru)
        if len(want) == len(have):
            out, at = [], 0
            for char in ru:
                if ICON.match(char):
                    out.append(want[at])
                    at += 1
                else:
                    out.append(char)
            ru = "".join(out)
        rows.append({
            "text": new,
            "lines": row.get("lines") or [],
            "item": row.get("item"),
            "ru": ru,
            "source": "server-icons",
        })
        added += 1
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"добавлено ключей: {added} (абзацев было {before}, стало {len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
