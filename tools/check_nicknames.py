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

# ⚠️ ПРИЗНАК «ПО ВИДУ НИКА» СЛЕП К ИМЕНАМ ИЗ ОДНИХ БУКВ.
#
# NICK требует цифру или подчёркивание, иначе он записывал бы в ники обычные
# слова. Но у половины игроков ник — просто слово: Kgriseup, zuhnia,
# sentiences, nograssbro. Они прошли сторожа и уехали в раздачу: 56 записей
# в 90-from-game.json, а сторож при этом печатал «чисто».
#
# Ловим по СТРУКТУРЕ СТРОКИ: там, где Hypixel ставит ник, стоит ник — каким бы
# он ни был. Тот же приём, что в TelemetryFilter (реплика игрока = метка уровня
# в начале) и в report.OWNER (владелец из притяжательной формы).
#
# Группа 2 — сам ник; чинится он ОБОБЩЕНИЕМ в «{s}», а не удалением записи:
# «RARE REWARD! {s} found …» полезен всем и никого не называет.
STRUCTURAL = [
    re.compile(r"^(RARE REWARD! )(\S+)( found )"),
    re.compile(r"^(RNG DROP! )(\S+)( just found )"),
    re.compile(r"^(☠ )(\S+)( (?:was |fell |drowned|died|burned|starved|suffocated))"),
    re.compile(r"^()(\S+)('s Profile$)"),
    re.compile(r"^(LOOT SHARE You received loot for assisting )(\S+?)(!?$)"),
    re.compile(r"^()(\S+)( invited .* to visit )"),
    re.compile(r"^(Player: )(\S+)($)"),
    # ⚠️ Ник в ПРИТЯЖАТЕЛЬНОЙ форме — вторая сторона приглашения:
    # «{s} accepted _Skyshadow_'s invite!». Первую («X invited …») признак
    # ловил, а эту нет, и строка уезжала в покупку вместе с чужим именем.
    re.compile(r"^(\{s\} accepted )(\S+?)('s invite)"),
]

# служебные слова, которые под признак попадают, но ником не являются
NOT_NICK = {
    "item_lore", "item_name", "name_tag", "action_bar", "boss_bar",
    "skyblockru", "ru_ru", "en_us", "sb_stats", "sb_enchants",
    "vanilla_names", "sidebar_test", "stat_jargon", "co_op", "co_ops",
    # ⚠️ C418 — композитор Minecraft, его имя стоит в названиях музыкальных
    # дисков («C418 - cat»). Под признак «буквы с цифрой» попадает, ником
    # не является, и удалять такие записи нельзя.
    "c418",
    # ⚠️ «☠ You died.» — это САМ ИГРОК, а не ник: Hypixel пишет так о твоей
    # смерти, о чужой пишет «☠ <ник> died». Структурный признак их не
    # различает, поэтому слово названо явно.
    "you", "your",
}

# ⚠️ КОЛИЧЕСТВО, А НЕ НИК: «Dark Oak Log x512», «Gave you: … x32».
COUNT = re.compile(r"^x\d+$", re.I)

# ⚠️ ЧИСТИМ ТОЛЬКО ТО, ЧТО СОБРАНО В ЖИВОЙ ИГРЕ. В остальных словарях ник
# внутри строки — часть ТЕКСТА HYPIXEL, а не данные игрока: реплики NPC
# упоминают ютуберов («[NPC] Goon: [YOUTUBE] im_a_squid_kid…»), названия
# дисков — композитора. Такие записи законны и нужны всем.
FROM_GAME = {"90-from-game.json", "96-paragraphs.json", "95-tooltips.json"}


def known_names() -> set[str]:
    """Имена NPC и локаций — их трогать нельзя.

    ⚠️ ГРУППУ «highlight» СЮДА БРАТЬ НЕЛЬЗЯ, и это стоило сторожу зрения.
    Она собрана из слов, которые Hypixel подсветил в чате, — а в строках
    «RARE REWARD! Kgriseup found …» подсвечен НИК ИГРОКА. Ники попадали
    в защищённые имена, сторож считал их законными и печатал «чисто»,
    пока в словаре лежали Kgriseup, SocksAreGreat, Astrobit.
    Структурный признак сильнее: «highlight» говорит лишь «слово выделено»,
    а структура — «на этом месте стоит ник».
    """
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import protected
        groups = protected.collect_groups()
    except Exception:
        return set()
    out: set[str] = set()
    for group, items in groups.items():
        if group == "highlight":
            continue
        out |= {str(n).lower() for n in items}
    return out


def structural_nick(text: str) -> str | None:
    """Ник, найденный ПО СТРУКТУРЕ строки, а не по написанию.

    Возвращает само имя — его место в строке задано форматом Hypixel,
    поэтому признак не зависит от того, есть ли в нике цифры.
    """
    for rule in STRUCTURAL:
        match = rule.match(text)
        if match:
            name = match.group(2)
            # «{s}» уже обобщён — это не ник, а дырка.
            if name and "{s}" not in name:
                return name
    return None


def generalized(text: str) -> str:
    """Строка с ником, заменённым на дырку «{s}»."""
    for rule in STRUCTURAL:
        match = rule.match(text)
        if match and "{s}" not in match.group(2):
            start, end = match.span(2)
            return text[:start] + "{s}" + text[end:]
    return text


def nicks_in(text: str, known: set[str]) -> set[str]:
    out = set()
    # Структурный признак идёт ПЕРВЫМ: он видит то, чего не видит написание.
    structural = structural_nick(text)
    if structural:
        low = structural.lower()
        if low not in known and low not in NOT_NICK:
            out.add(structural)
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


def generalize_in(path: Path, sections: tuple[str, ...], known: set[str]) -> tuple[int, int]:
    """Ник -> «{s}» там, где он найден ПО СТРУКТУРЕ. Возвращает (обобщено, слито).

    ⚠️ Обобщение лучше удаления: «RARE REWARD! {s} found …» полезен ВСЕМ
    игрокам и никого не называет, а удалённая запись — просто потерянный
    перевод, который завтра купят заново.

    ⚠️ Ник меняем И В ПЕРЕВОДЕ: движок подставляет «{s}» по порядку, и если
    дырка есть в ключе, а в переводе стоит чужое имя — на экране будет чужой
    ник вместо своего.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0, 0
    changed = merged = 0
    for section in sections:
        block = data.get(section)
        if not isinstance(block, dict):
            continue
        for key in list(block):
            nick = structural_nick(key)
            if not nick or nick.lower() in known or nick.lower() in NOT_NICK:
                continue
            fresh = generalized(key)
            if fresh == key:
                continue
            value = block.pop(key)
            if isinstance(value, str) and nick in value:
                value = value.replace(nick, "{s}")
            if fresh in block:
                merged += 1          # такой шаблон уже есть — лишняя копия
            else:
                changed += 1
            block[fresh] = value
    if changed or merged:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return changed, merged


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

    # ⚠️ СПЕРВА ОБОБЩАЕМ, ПОТОМ УДАЛЯЕМ. Порядок важен: обобщённая запись
    # («RARE REWARD! {s} found …») перестаёт содержать ник и в список
    # на удаление уже не попадает — то есть перевод сохраняется.
    print("\n=== ОБОБЩАЮ (ник -> {s}) ===")
    targets = [p for p in sorted(PACKS.rglob("*.json")) if p.name in FROM_GAME]
    for path in targets:
        did, dup = generalize_in(path, ("exact", "paragraphs", "glossary"), known)
        if did or dup:
            print("  %-28s +%d обобщено%s"
                  % (path.name, did, (", %d слито с готовым" % dup) if dup else ""))
    for name, sections in (("from_game.json", ("exact",)),
                           ("queue_archive.json", ("ru",)),
                           ("queue_pick.json", ("exact",))):
        path = WORK / name
        if path.is_file():
            did, dup = generalize_in(path, sections, known)
            if did or dup:
                print("  %-28s +%d обобщено  (источник)" % (name, did))

    # Что осталось после обобщения — ник не на своём месте, такое удаляем.
    total_keys = set()
    for path in targets:
        for _section, key, _hits in scan_pack(path, known):
            total_keys.add(key)
    if not total_keys:
        print("\nвсё обобщено — удалять нечего")
        return 0

    print("\n=== УБИРАЮ ОСТАТОК ===")
    for path in targets:
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
