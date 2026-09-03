# -*- coding: utf-8 -*-
"""
Имена способностей питомцев обязаны остаться АНГЛИЙСКИМИ.

⚠️ Решение проекта: имя способности не переводим — как имя предмета. Игрок
прислал скриншот Hedgehog (03.09): «название умения переведено, хотя все
умения питомцев пишутся на английском». Замер по 263 заголовкам способностей
из живых подсказок: по-русски вышли 16, то есть 6% — это разнобой, который
видно СТОЛБИКОМ в одной подсказке («Spiky Quills» рядом с «Грозный фермер»).

Откуда берутся русские имена: заголовок вырезается из купленного АБЗАЦА
(`gen_headers`), а в абзаце его когда-то перевели. Значит чинить надо
корпус и очередь, а `41-headers` пересобрать — правка в нём самом
не переживёт первой же сборки.

⚠️ СПИСОК ИМЁН СОБИРАЕТСЯ ИЗ ДАННЫХ, а не пишется руками: заголовок
способности — это первая строка куска в подсказке «[Lvl N] Имя / X Pet».
Список руками отстал бы от первого нового питомца.

⚠️ ЛОЖНЫЕ СРАБАТЫВАНИЯ ОТСЕИВАЕМ ГЛАЗАМИ, и они есть: «Repeat» — ещё и
кнопка мини-игры («Повтори музыкальный узор»), «Enderman Slayer» — истребитель,
а не способность. Признак «первое слово совпало с именем способности» задевает
их по построению, поэтому инструмент показывает, ЧТО именно поменяет, и без
`--yes` ничего не пишет.

Запуск:
  python tools/fix_pet_abilities.py           сухой прогон
  python tools/fix_pet_abilities.py --yes     применить
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
QUEUE = ROOT / "data" / "work" / "from_game.json"
ARCHIVE = ROOT / "data" / "work" / "queue_archive.json"
LORE = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "ru_ru" / "40-lore.json"
BLOCKS = [
    ROOT / "data" / "work" / "blocks_from_players.json",
    Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/tooltips.json"),
]

CYRILLIC = re.compile("[А-Яа-яЁё]")
CODE = re.compile("§.")

# ⚠️ Не имена способностей, хотя стоят на их месте. Каждое проверено глазами
# по строке, в которой встретилось: «Cost» — подпись цены, «Items Required» —
# требования рецепта, «Looting» — ванильное зачарование (его переводит клиент),
# «Repeat» — кнопка мини-игры, «Enderman Slayer» — истребитель.
NOT_ABILITY = {
    "Cost", "Items Required", "Looting", "Repeat", "Enderman Slayer",
    "Magnetic", "Combat Wisdom Boost", "Fishing Wisdom Boost",
    "This pet only gains XP on the", "This pet's perks are active even",
    "This pet's perks are active",
}


def ability_names() -> set[str]:
    """Заголовки способностей ИЗ ЖИВЫХ ПОДСКАЗОК питомцев."""
    sys.path.insert(0, str(ROOT / "tools"))
    import make_paragraphs as mp

    names: set[str] = set()
    for path in BLOCKS:
        if not path.exists():
            continue
        try:
            blocks = json.loads(path.read_text(encoding="utf-8")).get("tooltips") or []
        except (json.JSONDecodeError, OSError):
            continue
        for block in blocks:
            lines = block.get("lines") or []
            if len(lines) < 3 or not lines[0].startswith("[Lvl") or not lines[1].endswith(" Pet"):
                continue
            for run in mp.runs_of(lines[2:]):
                head = run[0]
                if len(run) < 2 or ":" in head or "{n}" in head or head.isupper():
                    continue
                if head.startswith(("Left-click", "Right-click", "Shift", "Progress",
                                    "MAX", "Can be", "Click", "Held Item", "Requires")):
                    continue
                if re.fullmatch(r"[A-Z][A-Za-z' -]+", head):
                    names.add(head)
    return names - NOT_ABILITY


def known_russian(name: str) -> set[str]:
    """
    Как ЭТО имя переведено построчно — спрашиваем словари, а не угадываем.

    ⚠️ Первая версия искала границу заголовка по кириллице и обрезала его
    посреди («Slow and Steady но верно», «Stronger Bones крепкие кости»):
    у заголовка из нескольких слов границы по форме нет. А построчный перевод
    заголовка у нас ЕСТЬ — его и вырезал `gen_headers`. Значит меняем ровно
    известный текст, и гадать не о чем. Не знаем перевода — честно пропускаем.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import status

    global _DICT
    if _DICT is None:
        _DICT = status.Dictionaries()
    out: set[str] = set()
    for origin in ("item_lore", "item_name", None):
        found = status.lookup(name, _DICT, origin=origin) if origin else status.lookup(name, _DICT)
        if found and found[0] and CYRILLIC.search(found[0]):
            out.add(CODE.sub("", found[0]).strip())
    return out


_DICT = None


def head_swapped(russian: str, name: str) -> str | None:
    """Русский заголовок в начале перевода -> английское имя, §-коды на месте."""
    plain = CODE.sub("", russian)
    if plain.startswith(name):
        return None
    for head in sorted(known_russian(name), key=len, reverse=True):
        if not plain.startswith(head):
            continue
        # ⚠️ Меняем в САМОМ переводе, а не в очищенном: §-коды заголовка
        # («§7§6Вожак стаи§7») обязаны остаться на месте, иначе пропадёт цвет.
        at = russian.find(head)
        if at < 0:
            # заголовок разорван §-кодом внутри — не трогаем, случай редкий
            return None
        return russian[:at] + name + russian[at + len(head):]
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="имена способностей питомцев — английские")
    parser.add_argument("--yes", action="store_true", help="применить")
    args = parser.parse_args()

    names = ability_names()
    print(f"имён способностей в живых подсказках: {len(names)}")

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    rows = doc["paragraphs"]
    changes: list[tuple[dict, str, str]] = []
    for row in rows:
        russian = row.get("ru")
        if not russian:
            continue
        for name in names:
            if not row["text"].startswith(name + " "):
                continue
            swapped = head_swapped(russian, name)
            if swapped:
                changes.append((row, name, swapped))
            break

    print(f"абзацев с РУССКИМ именем способности: {len(changes)}")
    for row, name, swapped in changes:
        print(f"  {name}")
        print("     было : " + CODE.sub("", row["ru"])[:86])
        print("     стало: " + CODE.sub("", swapped)[:86])

    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    in_queue = {k: v for k, v in queue["exact"].items()
                if k in names and v and CYRILLIC.search(v)}
    print(f"\nв очереди строк переведены как имена: {len(in_queue)}")
    for key, value in in_queue.items():
        print(f"   {key!r} -> {value!r}")

    lore = json.loads(LORE.read_text(encoding="utf-8"))
    in_lore = {k: v for k, v in (lore.get("exact") or {}).items()
               if k in names and CYRILLIC.search(v or "")}
    print(f"в 40-lore (ручной словарь): {len(in_lore)}")
    for key, value in in_lore.items():
        print(f"   {key!r} -> {value!r}")

    if not args.yes:
        print("\nсухой прогон. Применить: --yes")
        return 0

    for row, _, swapped in changes:
        row["ru"] = swapped
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    # ⚠️ В очереди ставим ПОМЕТКУ «переводить нечего», а не пустое значение:
    # пустое вернётся в работу при первой же пересборке, а решение уже принято.
    asis = queue.setdefault("_asis", [])
    for key in in_queue:
        queue["exact"][key] = ""
        if key not in asis:
            asis.append(key)
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")

    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    for key in in_queue:
        archive["ru"].pop(key, None)
        if key not in archive["asis"]:
            archive["asis"].append(key)
    ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=1), encoding="utf-8")

    for key in in_lore:
        lore["exact"].pop(key, None)
    LORE.write_text(json.dumps(lore, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nпоправлено абзацев: {len(changes)}, снято из очереди: {len(in_queue)},"
          f" из 40-lore: {len(in_lore)}")
    print("дальше: python tools/merge_paragraphs.py && python tools/gen_headers.py --apply"
          " && python tools/export_pack.py from_game 90-from-game.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
