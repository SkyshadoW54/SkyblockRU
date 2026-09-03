"""
Делает правила для ванильных названий предметов и блоков.

СУТЬ. У игрока с русским клиентом переводы Mojang уже лежат на диске: 778
предметов, 1943 блока. Но Hypixel присылает предмет с ЗАДАННЫМ именем «Coal»,
и Minecraft показывает эту строку буквально, минуя собственный перевод.
Отсюда и берётся английский уголь на русском клиенте.

Лечится так: ловим английское название и подставляем ключ (@item.minecraft.coal).
Мод спрашивает перевод у самой игры — получается ровно то, что игрок видит
в одиночной игре. Чужой перевод при этом никуда не копируется, а у игрока
с английским клиентом всё останется английским.

⚠️ ПО УМОЛЧАНИЮ ВЫКЛЮЧЕНО. Названия предметов ищут на аукционе и базаре, а по
русскому названию поиск ничего не найдёт. Поэтому файл создаётся, но в index.json
не прописывается. Включить — дописать "80-vanilla-names.json" в index.json
либо положить файл в config/skyblockru/packs/ у себя.

Запуск:  python tools/gen_vanilla_names.py
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "common" / "80-vanilla-names.json"
# ⚠️ ЗАГОЛОВОК — ОТДЕЛЬНЫЙ СЛОВАРЬ, и это не прихоть: область `only` одна
# на весь пакет, а глоссарию в заголовке делать нечего. Он подставляет термин
# ВНУТРИ строки, и у имени SkyBlock, которого нет в нашем каталоге, вышло бы
# «Enchanted Кость» — смесь языков, которую защита stillEnglish не откатит
# (русских слов там не меньше английских). Точная запись такого не умеет:
# она срабатывает только на полное совпадение заголовка.
TITLES = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "common" / "83-vanilla-titles.json"
JAR_DIR = Path.home() / ".gradle" / "caches" / "fabric-loom"

# Слишком короткие названия ловят лишнее, а односимвольные вовсе бессмысленны
MIN_LENGTH = 3


def find_client_jar() -> Path | None:
    candidates = sorted(JAR_DIR.rglob("minecraft-client.jar"))
    return candidates[-1] if candidates else None


def with_counts(names: dict[str, str]) -> dict[str, str]:
    """
    Добавить формы со СЧЁТЧИКОМ СТОПКИ: «Wooden Pickaxe x{n}».

    ⚠️ Зачем. В меню Hypixel пишет заголовок вместе с количеством, и голое
    имя с таким заголовком не совпадает — вещь остаётся английской, хотя
    перевод есть. Замер по живому дампу: 24 таких заголовка.

    ⚠️ Берём ТОЛЬКО те формы, что реально видели на экране: приписывать
    счётчик всем 2581 названию значило бы удвоить словарь ради выдуманных
    строк. Тот же принцип, что у обёрток в `gen_item_names`.

    ⚠️ В значении остаётся @КЛЮЧ: движок разворачивает его В ЛЮБОМ месте
    строки, а не только в начале (проверено по `VanillaNames.expand`).
    Значит имя по-прежнему приходит от самой игры и меняется с её языком.
    """
    dump = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump"
                "/collected.json")
    titles: set[str] = set()
    if dump.exists():
        data = json.loads(dump.read_text(encoding="utf-8"))
        titles |= set(((data.get("sources") or {}).get("item_name") or {}))
    players = ROOT / "data" / "work" / "from_players.json"
    if players.exists():
        rows = json.loads(players.read_text(encoding="utf-8"))
        if isinstance(rows, dict) and isinstance(rows.get("item_name"), dict):
            titles |= set(rows["item_name"])

    out = dict(names)
    added = 0
    for title in titles:
        if title in out or not title.endswith(" x{n}"):
            continue
        base = title[: -len(" x{n}")]
        if base in names:
            out[title] = names[base] + " x{n}"
            added += 1
    if added:
        print(f"  форм со счётчиком добавлено: {added}")
    return out


def main() -> int:
    jar = find_client_jar()
    if jar is None:
        print("не нашёл minecraft-client.jar — собери мод хотя бы раз", file=sys.stderr)
        return 1

    with zipfile.ZipFile(jar) as z:
        names = [n for n in z.namelist() if n.endswith("lang/en_us.json")]
        if not names:
            print("в jar нет lang-файла", file=sys.stderr)
            return 1
        lang = json.loads(z.read(names[0]).decode("utf-8"))

    # Предметы важнее блоков: если название совпадает, берём предметный ключ
    by_english: dict[str, str] = {}
    collisions = 0
    for prefix in ("item.minecraft.", "block.minecraft."):
        for key, english in lang.items():
            if not key.startswith(prefix) or not isinstance(english, str):
                continue
            if len(english) < MIN_LENGTH:
                continue
            if english in by_english:
                collisions += 1
                continue
            by_english[english] = key

    # Термины, а не правила целой строки: в описании название стоит ВНУТРИ фразы
    # («нужен Coal»), и правило вида ^Coal$ там не сработает никогда.
    glossary = {english: f"@{key}" for english, key in by_english.items()}

    pack = {
        "id": "vanilla_names",
        "priority": 60,
        # ⚠️ ЭТИ ДВА ПОЛЯ ОБЯЗАТЕЛЬНЫ, и однажды генератор их уже стёр: словарь
        # молча стал бы включённым у всех, хотя решение — переводить ванильные
        # названия только в режиме полного перевода. Генератор переписывает файл
        # целиком, поэтому всё, что делает словарь необязательным, должно стоять
        # ЗДЕСЬ, а не дописываться в json руками.
        "default": False,
        "group": "full",
        "_comment": "Ванильные названия предметов и блоков — ТОЛЬКО в описаниях предметов. "
                    "Заголовки не трогаем: по русскому названию вещь не найти на аукционе. "
                    "В переводе стоит КЛЮЧ, а не текст — мод спрашивает название у самой игры, "
                    "поэтому оно совпадает с ванильным и меняется вместе с языком клиента. "
                    "СГЕНЕРИРОВАНО tools/gen_vanilla_names.py.",
        "only": ["item_lore"],
        "glossary": glossary,
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")

    # ⚠️ Второй словарь — ЗАГОЛОВКИ подсказок. Без него ванильная вещь остаётся
    # английской именно там, где её имя и написано: «Wheat», «Flint». Замер
    # по строкам от игроков: 1600 из 2581 названий приходят заголовком, и ни
    # одно не пересекается с нашим каталогом имён SkyBlock — чистая прибавка.
    titles = {
        "id": "vanilla_titles",
        "priority": 59,
        "default": False,
        "group": "full",
        "about": "ванильные названия предметов в ЗАГОЛОВКЕ подсказки "
                 "(Wheat -> Пшеница). По умолчанию выключено: по английскому "
                 "названию вещь ищут на аукционе и в базаре",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_vanilla_names.py вместе с "
                    "80-vanilla-names.json. Тот же список, но ТОЧНЫМИ записями "
                    "и в области item_name: в заголовке имя стоит целиком, "
                    "и глоссарий там опасен — он подставил бы термин внутрь "
                    "чужого имени и дал смесь языков. В переводе КЛЮЧ, а не "
                    "текст: имя спрашивается у самой игры.",
        "only": ["item_name", "menu_title", "screen", "name_tag"],
        "exact": dict(sorted(with_counts(glossary).items())),
    }
    TITLES.write_text(json.dumps(titles, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"названий собрано: {len(by_english)} (совпадений имён пропущено: {collisions})")
    print(f"записано: {OUT.relative_to(ROOT)} (описания, глоссарий)")
    print(f"записано: {TITLES.relative_to(ROOT)} (заголовки, точные записи)")
    print()
    print("Файл создан, но НЕ включён: в index.json не прописан.")
    print("Включить — дописать туда \"80-vanilla-names.json\".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
