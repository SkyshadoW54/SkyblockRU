# -*- coding: utf-8 -*-
"""Абзацы-ДАННЫЕ в очереди: пометить «переводить нечего», а не покупать перевод.

    python tools/mark_data_paragraphs.py            покажет, что пометит, по классам
    python tools/mark_data_paragraphs.py --yes      поставит nothing в data/work/paragraphs.json

Зачем (19.10, «слой 1»). В очереди абзацев лежало 7 255 живых кусков без
перевода, и верхушка по показам — не текст, а данные: история Bazaar с никами
(«{n}d ago Cancelled Buy Order of {n}x Stock of Stonks / by _Uniel7»), списки
участников кооператива, «Missing Enchantments» со списком имён зачарований,
даты «Started: / Summer 1st, Year 418 / 4:30pm», наборы брони «Necklace: X».
Каждый такой кусок уникален (ник, предмет, дата), покупать перевод на каждый —
деньги в стол, а на экране они и так по-русски: мод не нашёл абзац и перевёл
ПОСТРОЧНО, а подписи и шаблоны строк давно в словарях (`48-bazaar`, `26-time`,
`40-lore`, `90-from-game`).

Признак нарочно ДВОЙНОЙ: кусок попадает в один из перечисленных классов
(регулярка по тексту) И каждая его строка либо переводится построчно (движок
через `status.lookup` с областью `item_lore` отдаёт кириллицу или `@ключ`),
либо является данными этого класса (ник в списке участников, имя зачарования
за «›», имя предмета в наборе). Строка, которая не то и не другое, оставляет
кусок в очереди — так «Click to set the Teleport Pad's / destination!» (проза,
попавшая под «Click to») не помечается.

⚠️ `nothing` переживает пересборку корпуса (`make_paragraphs` переносит её по
ключу), но ПРИЧИНА — нет: поле пересборка не хранит. Причина — вывод этого
инструмента и запись в `notes/translation-workflow.md`.

⚠️ Тождественный ответ движка («перевод» = оригинал) переводом не считается —
железное правило проекта, здесь оно проверяется явно.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import status  # noqa: E402

CORPUS = ROOT / "data" / "work" / "paragraphs.json"
CODES = re.compile("§.")
CYR = re.compile("[а-яА-ЯёЁ]")
NUM = re.compile(r"\d+")

# класс -> (признак по тексту куска, признак строки-данных этого класса)
CLASSES: dict[str, tuple[re.Pattern, re.Pattern | None]] = {
    "история Bazaar/аукциона": (
        re.compile(r"\b(ago|Seller:|Buy it now|Bidder|Top bid|Cancelled|Instant (Buy|Sell)|Sell Offer|Buy Order)\b"),
        re.compile(r"^by \S+$")),
    "списки Missing/Non-maxed Enchantments": (
        re.compile(r"(Missing|Non-maxed) [Ee]nchantments"),
        re.compile(r"^›\s")),
    "кооп, друзья, участники": (
        re.compile(r"^(Co-op with|Members:|Online Friends:|Online Party Members:)"),
        # ник в списке: голый, с «- », обобщённый до {s} или с дыркой {n} внутри
        re.compile(r"^(- )?(\{s\}|[A-Za-z0-9_{}]{2,24})$")),
    # время «{n}:{n}pm» в корпусе лежит с дырками, а `26-time` держит точные
    # записи на живые «4:30pm» — на экране оно переводится, здесь это данные
    "даты заданий": (
        re.compile(r"^(Started|Ends|Expires|Starts):"),
        re.compile(r"^\{n\}:\{n\}(am|pm)$")),
    "наборы брони и аксессуаров": (
        re.compile(r"^(Necklace|Helmet|Chestplate|Leggings|Boots|Cloak|Belt|Gloves/Bracelet):"),
        None),
    "служебные двустрочники (привязка, редкость, подсказки клика)": (
        re.compile(r"^(\* Co-op Soulbound \*|Right-[Cc]lick|Click to|Shift Right-click)|^(a )?(COMMON|UNCOMMON|RARE|EPIC|LEGENDARY|MYTHIC|DIVINE|SPECIAL)\b"),
        None),
    "статус улучшений кооператива": (
        re.compile(r"^Profile: .+ Account: "),
        None),
    "таблицы добычи": (
        re.compile(r"^(Common|Uncommon|Rare|Epic|Legendary|RNGesus|Mythic) Loot\b"),
        # пункт добычи: имя предмета или моба, иногда с шансом «({n}%)»;
        # строки характеристик «■ +{n} Mining Speed» — не данные, не берём
        re.compile(r"^[▶•■]\s(?!\+)[^+%]*(\(\{n\}%\))?$")),
}


def covered(line: str, dic: status.Dictionaries) -> bool:
    """Строка переводится построчно: ответ движка с кириллицей или @ключом и не равен оригиналу."""
    got = status.lookup(line, dic, origin="item_lore")
    if not got and "{n}" in line:
        # в корпусе числа уже дырки, а правила ждут цифры («Nick: Archer (50)»):
        # примеряем, как строка выглядит на экране
        got = status.lookup(line.replace("{n}", "1"), dic, origin="item_lore")
    if not got:
        return False
    text = CODES.sub("", str(got[0])).strip()
    if text == CODES.sub("", line).strip():
        return False
    return bool(CYR.search(text) or "@" in text)


def classify(row: dict, dic: status.Dictionaries) -> tuple[str | None, list[str]]:
    """(класс, непокрытые строки) — класс None, если кусок ни под что не подходит."""
    text = row.get("text") or ""
    for name, (shape, data) in CLASSES.items():
        if not shape.search(text):
            continue
        left = []
        for raw in row.get("lines") or []:
            line = str(raw).strip()
            if not line or NUM.fullmatch(line.replace("{n}", "0")):
                continue
            if covered(line, dic):
                continue
            if data is not None and data.match(line):
                continue
            left.append(line)
        return name, left
    return None, []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--show", type=int, default=4)
    ap.add_argument("--all", action="store_true", help="не только виденные в игре (live)")
    args = ap.parse_args()

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    rows = doc.get("paragraphs") or []
    dic = status.Dictionaries()
    waiting = [r for r in rows if not r.get("ru") and not r.get("nothing")
               and (args.all or r.get("live"))]
    mark: list[tuple[str, dict]] = []
    hold: dict[str, list[tuple[dict, list[str]]]] = collections.defaultdict(list)
    for row in waiting:
        name, left = classify(row, dic)
        if name is None:
            continue
        if left:
            hold[name].append((row, left))
        else:
            mark.append((name, row))

    print(f"ждут перевода: {len(waiting)}; данные, закрытые построчно — пометить: {len(mark)}")
    by = collections.Counter(name for name, _ in mark)
    shows = collections.Counter()
    for name, row in mark:
        shows[name] += row.get("live") or 0
    for name, n in by.most_common():
        print(f"\n  {n:4d} абз., {shows[name]:4d} показов — {name}")
        for _, row in [m for m in mark if m[0] == name][: args.show]:
            print(f"       {row['text'][:96]}")
    print("\nв классе, но есть НЕПОКРЫТЫЕ строки — остаются в очереди (это подписи для словаря):")
    for name, items in hold.items():
        lines = collections.Counter(l for _, left in items for l in left)
        print(f"  {len(items):4d} абз. — {name}")
        for line, n in lines.most_common(6):
            print(f"       {n:3d}x {line[:80]}")

    if not args.yes:
        print("\nСУХОЙ ПРОГОН. Пометить: --yes")
        return 0
    if not mark:
        print("помечать нечего")
        return 0
    stamp = time.strftime("%Y%m%d")
    backup = CORPUS.with_name(CORPUS.name + f".bak-{stamp}-datamark")
    if not backup.exists():
        shutil.copy2(CORPUS, backup)
    before = sum(1 for r in rows if r.get("ru"))
    for _, row in mark:
        row["nothing"] = True
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    after = sum(1 for r in json.loads(CORPUS.read_text(encoding="utf-8"))["paragraphs"] if r.get("ru"))
    print(f"\nпомечено nothing: {len(mark)}; переводов было {before}, стало {after}; копия {backup.name}")
    return 0 if before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
