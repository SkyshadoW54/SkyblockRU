# -*- coding: utf-8 -*-
"""Ники игроков в словарях — найти и убрать.

Зачем. Словари собираются из ЖИВОЙ игры, и вместе с надписями туда попадают
ники: «[NPC] Rosetta: Hey Player_123!!!», «Unlocked by: Player_123».
Такая запись бесполезна всем, кроме одного человека — у остальных другой
ник, и совпадения не будет НИКОГДА. А ещё это персональные данные, которые
уезжают в jar каждому игроку и в публичный репозиторий.

⚠️ Признак не «слово с большой буквы»: половина имён NPC выглядит так же
(Agatha, Arachne, Bartender). Ник опознаётся по ДВУМ условиям сразу:
  * содержит цифру или подчёркивание — у имён NPC такого не бывает;
  * не значится в protected (там NPC и локации с вики).
Пропустить ник не страшно — он останется мёртвой записью. Удалить лишнее
дороже, поэтому признак нарочно узкий.

⚠️ Чистить надо в ТРЁХ местах: словарь, корпус и архив очереди. Правка
только в словаре живёт до первой пересборки — записанная грабля проекта.

  python tools/check_nicknames.py          показать
  python tools/check_nicknames.py --fix    убрать
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
WORK = ROOT / "data" / "work"

# слово, похожее на ник: латиница с цифрой или подчёркиванием
NICK = re.compile(r"\b(?=[A-Za-z0-9_]{3,16}\b)(?=[A-Za-z0-9_]*[0-9_])[A-Za-z_][A-Za-z0-9_]*\b")

# служебные слова, которые под признак попадают, но ником не являются
NOT_NICK = {
    "item_lore", "item_name", "name_tag", "action_bar", "boss_bar",
    "skyblockru", "ru_ru", "en_us", "sb_stats", "sb_enchants",
    "vanilla_names", "sidebar_test", "stat_jargon", "co_op", "co_ops",
    # ⚠️ C418 — композитор Minecraft, его имя стоит в названиях музыкальных
    # дисков («C418 - cat»). Под признак «буквы с цифрой» попадает, ником
    # не является, и удалять такие записи нельзя.
    "c418",
}

# ⚠️ КОЛИЧЕСТВО, А НЕ НИК: «Dark Oak Log x512», «Gave you: … x32».
COUNT = re.compile(r"^x\d+$", re.I)

# ⚠️ ЧИСТИМ ТОЛЬКО ТО, ЧТО СОБРАНО В ЖИВОЙ ИГРЕ. В остальных словарях ник
# внутри строки — часть ТЕКСТА HYPIXEL, а не данные игрока: реплики NPC
# упоминают ютуберов («[NPC] Goon: [YOUTUBE] im_a_squid_kid…»), названия
# дисков — композитора. Такие записи законны и нужны всем.
FROM_GAME = {"90-from-game.json", "96-paragraphs.json", "95-tooltips.json"}


def known_names() -> set[str]:
    """Имена NPC и локаций — их трогать нельзя."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import protected
        return {n.lower() for n in protected.collect()}
    except Exception:
        return set()


def nicks_in(text: str, known: set[str]) -> set[str]:
    out = set()
    for word in NICK.findall(text):
        low = word.lower()
        if low in known or low in NOT_NICK:
            continue
        if COUNT.match(word):
            continue
        # «{n}» и «{s}» — наши дырки, а не ники
        if word.startswith("{") or "_" == word or word.isdigit():
            continue
        out.add(word)
    return out


def scan_pack(path: Path, known: set[str]) -> list[tuple[str, str, set[str]]]:
    """Записи словаря, в ключе которых есть ник."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    found = []
    for section in ("exact", "paragraphs", "glossary"):
        block = data.get(section)
        if not isinstance(block, dict):
            continue
        for key in block:
            hits = nicks_in(key, known)
            if hits:
                found.append((section, key, hits))
    return found


def drop_from(path: Path, keys: set[str], sections: tuple[str, ...]) -> int:
    """Убрать ключи из указанных секций файла."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    removed = 0
    for section in sections:
        block = data.get(section)
        if not isinstance(block, dict):
            continue
        for key in list(block):
            if key in keys:
                del block[key]
                removed += 1
    if removed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return removed


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fix = "--fix" in sys.argv
    known = known_names()

    total_keys: set[str] = set()
    all_nicks: set[str] = set()
    print("=== НИКИ В СЛОВАРЯХ ===")
    for path in sorted(PACKS.rglob("*.json")):
        if path.name not in FROM_GAME:
            continue
        found = scan_pack(path, known)
        if not found:
            continue
        print("  %s — записей %d" % (path.name, len(found)))
        for section, key, hits in found[:6]:
            all_nicks |= hits
            print("      [%s] %s" % (section, key[:64]))
        if len(found) > 6:
            print("      ... ещё %d" % (len(found) - 6))
        for section, key, hits in found:
            total_keys.add(key)
            all_nicks |= hits

    if not total_keys:
        print("  чисто — ников не найдено")
        return 0

    print()
    print("ников: %d — %s" % (len(all_nicks), ", ".join(sorted(all_nicks))))
    print("записей к удалению: %d" % len(total_keys))

    if not fix:
        print("\nпоказ — ничего не изменено (--fix уберёт)")
        return 1

    print("\n=== УБИРАЮ ===")
    for path in sorted(PACKS.rglob("*.json")):
        if path.name not in FROM_GAME:
            continue
        gone = drop_from(path, total_keys, ("exact", "paragraphs", "glossary"))
        if gone:
            print("  %-28s -%d" % (path.name, gone))

    # ⚠️ И в источниках: словарь пересобирается из них, иначе ники вернутся
    for name, sections in (("from_game.json", ("exact",)),
                           ("queue_archive.json", ("ru", "exact")),
                           ("queue_pick.json", ("exact",))):
        path = WORK / name
        if path.is_file():
            gone = drop_from(path, total_keys, sections)
            if gone:
                print("  %-28s -%d  (источник)" % (name, gone))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
