"""
Тождественные записи («A to Z» -> «A to Z»): где ЗАМЫСЕЛ, а где мусор.

Такие записи рождаются сами, когда термин делают английским заменой
(rename_term.py, restore_by_replace.py): русский перевод меняется на оригинал,
и запись становится тождественной. Мод честно зовёт её бесполезной — а она
бывает нужна, и тогда жалоба горит всегда. Вечно красный сторож приучает
не смотреть на красное, то есть прячет настоящую беду.

Разбираем на две корзины, спрашивая ДВИЖОК, а не вид строки:

  ИНСТРУМЕНТ  строка входит в абзац, у которого есть перевод.
              Paragraphs.listed обходит ВСЕ строки куска и спрашивает
              Translator.lookup у каждой; пустой ответ хотя бы у одной значит
              «построчно закрыто не всё» — и мод разрежет абзац, подменив
              собой построчный путь. Так устроен фильтр сортировки
              «▶ A to Z / Z to A / Lowest Rarity»: имена мы не переводим,
              но записи держат резку. Их помечаем — в словаре они остаются.

  МУСОР       ни правило, ни глоссарий строку не ловят, в абзацах её нет.
              Движок и так вернёт её как есть, значит запись ничего не решает.
              Переносим в «_asis» — это штатная пометка «переводить нечего»:
              очередь такую строку больше не спрашивает (защита от повторной
              покупки цела), а в словарь она не попадает вовсе.

⚠️ Правим ИСТОЧНИК, а не собранный словарь: 90-from-game.json пересобирается
из data/work/from_game.json, и правка в нём живёт до первого прогона. Заодно
чиним АРХИВ очереди — иначе make_queue вернёт перевод обратно при первой же
пересборке (записанная грабля проекта).

Запуск:
  python tools/fix_identity.py           # сухой прогон: покажет и ничего не тронет
  python tools/fix_identity.py --yes     # применить
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
INDEX = PACKS / "index.json"
QUEUE = WORK / "from_game.json"
ARCHIVE = WORK / "queue_archive.json"
CORPUS = WORK / "paragraphs.json"

# Словарь, который собирается ИЗ очереди: только его записи можно чинить
# переносом в «_asis». Остальные приходят из своих генераторов.
QUEUE_PACK = "90-from-game"


def declared() -> set[str]:
    """Только объявленные в index.json: остальные мод не грузит и не проверяет."""
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    names = set(data.get("common") or [])
    for _lang, items in (data.get("languages") or {}).items():
        names.update(items)
    return names


def identity_entries() -> list[tuple[str, Path, str]]:
    """Тождественные записи всех объявленных словарей: (id словаря, файл, ключ)."""
    names = declared()
    found: list[tuple[str, Path, str]] = []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        if path.stem not in names and path.name not in names:
            continue
        pack = json.loads(path.read_text(encoding="utf-8"))
        allow = pack.get("allowIdentity")
        if allow is True:
            continue  # весь файл помечен осознанно (41-headers)
        marked = set(allow) if isinstance(allow, list) else set()
        for key, value in (pack.get("exact") or {}).items():
            if isinstance(value, str) and key == value and key not in marked:
                found.append((path.stem, path, key))
    return found


def walk(node):
    """Корпус лежит гнездом: dict -> list -> записи. Разворачиваем до записей."""
    if isinstance(node, dict):
        if "lines" in node or "text" in node:
            yield node
            return
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def lines_of_translated() -> set[str]:
    """Все строки абзацев, У КОТОРЫХ ЕСТЬ перевод.

    ⚠️ Именно ВСЕ, а не первые: Paragraphs.listed спрашивает lookup у каждой
    строки куска. Признак «первая строка» был уже механики и пропускал
    «Z to A» — тот держит резку наравне с «▶ A to Z».
    """
    known: set[str] = set()
    if not CORPUS.exists():
        return known
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    for item in walk(data):
        if not str(item.get("ru") or "").strip():
            continue
        for line in item.get("lines") or []:
            known.add(str(line))
    return known


def classify(keys: list[tuple[str, Path, str]], known: set[str]):
    """Раскладывает записи по корзинам. Спрашиваем движок через status.py."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import status  # noqa: PLC0415  (ленивый импорт: status тянет словари)

    dic = status.Dictionaries()
    tools_, junk = [], []
    for pack_id, path, key in keys:
        why = []
        rule, match = status.rule_hit(key, dic)
        if rule is not None and match is not None:
            got = status.expand(rule, match, dic, 0)
            # ⚠️ Через unfill: правило подставляет ЧИСЛА, и «+{n}» -> «+1,234»
            # выглядит изменением, не будучи переводом.
            if got and status.unfill(got) != key:
                why.append(f"правило переведёт: {status.unfill(got)}")
        glossary, _rolled = status.try_glossary(key, dic)
        if glossary and status.unfill(glossary) != key:
            why.append(f"глоссарий переведёт: {status.unfill(glossary)}")
        if key in known:
            why.append("строка абзаца с переводом — держит резку")
        (tools_ if why else junk).append((pack_id, path, key, why))
    return tools_, junk


def apply_queue(junk_keys: set[str], tool_keys: set[str]) -> tuple[int, int]:
    """Мусор -> «_asis» с пустым значением, инструменты -> «_identity»."""
    data = json.loads(QUEUE.read_text(encoding="utf-8"))
    exact = data.get("exact") or {}
    asis = list(data.get("_asis") or [])
    moved = 0
    for key in junk_keys:
        if key in exact:
            exact[key] = ""
            moved += 1
        if key not in asis:
            asis.append(key)
    data["_asis"] = sorted(asis)
    # Пометка едет в словарь через export_pack.py: правим источник, не результат.
    data["_identity"] = sorted(tool_keys)
    QUEUE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return moved, len(tool_keys)


def apply_archive(junk_keys: set[str]) -> int:
    """То же в архиве: иначе make_queue вернёт перевод при первой пересборке."""
    if not ARCHIVE.exists():
        return 0
    data = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    ru = data.get("ru") or {}
    asis = list(data.get("asis") or [])
    dropped = 0
    for key in junk_keys:
        if ru.pop(key, None) is not None:
            dropped += 1
        if key not in asis:
            asis.append(key)
    data["ru"] = ru
    data["asis"] = sorted(asis)
    ARCHIVE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return dropped


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="применить, а не показать")
    args = parser.parse_args()

    rows = identity_entries()
    if not rows:
        print("тождественных записей нет — сторож чист")
        return 0
    known = lines_of_translated()
    if not known:
        print("ОСТАНОВКА: корпус абзацев не прочитан, признак «инструмент» не работает")
        return 1
    tools_, junk = classify(rows, known)

    print(f"тождественных записей: {len(rows)}")
    print(f"строк в абзацах с переводом: {len(known)}\n")

    print(f"=== ЗАМЫСЕЛ — оставляем и помечаем: {len(tools_)} ===")
    for pack_id, _path, key, why in tools_:
        print(f"  [{pack_id}] {key}")
        for reason in why:
            print(f"        {reason}")

    from_queue = [r for r in junk if r[0] == QUEUE_PACK]
    other = [r for r in junk if r[0] != QUEUE_PACK]
    print(f"\n=== МУСОР в очереди — в «_asis»: {len(from_queue)} ===")
    for pack_id, _path, key, _why in from_queue:
        print(f"  [{pack_id}] {key}")
    if other:
        print(f"\n=== МУСОР в ДРУГИХ словарях: {len(other)} ===")
        print("    Они собираются своими генераторами — чинить надо там,")
        print("    правка собранного json живёт до первой пересборки.")
        for pack_id, _path, key, _why in other:
            print(f"  [{pack_id}] {key}")

    if not args.yes:
        print("\nсухой прогон: ничего не изменено (--yes чтобы применить)")
        return 0

    junk_keys = {key for pack_id, _p, key, _w in junk if pack_id == QUEUE_PACK}
    tool_keys = {key for pack_id, _p, key, _w in tools_ if pack_id == QUEUE_PACK}
    moved, marked = apply_queue(junk_keys, tool_keys)
    dropped = apply_archive(junk_keys)
    print(f"\nочередь: снято переводов {moved}, помечено «замысел» {marked}")
    print(f"архив:   снято переводов {dropped}")
    print("дальше: python tools/export_pack.py from_game 90-from-game.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
