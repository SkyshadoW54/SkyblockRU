# -*- coding: utf-8 -*-
"""Строки, где ЗНАЧОК в начале мешает ключу совпасть.

    python tools/gen_full_icons.py            покажет
    python tools/gen_full_icons.py --write    соберёт 01-full-icons.json

⚠️ ПОЧЕМУ ЭТО ВООБЩЕ БЕДА. Мод переводит строку ЦЕЛИКОМ, а Hypixel ставит
перед именем значок: на экране «◆ Blood Rune I», в словаре «Blood Rune I».
Такой ключ не совпадёт НИКОГДА — записанная грабля проекта, всплывавшая уже
у локаций в панели (« Savanna Woodland») и у имён с косметикой.

⚠️ ЗНАЧОК ОБЯЗАН ОТДЕЛЯТЬСЯ ПРОБЕЛОМ, иначе признак съест начало имени там,
где значок и есть первая буква. Это тоже записанная грабля.

⚠️ Снимаем ВТОРЫМ заходом: сперва строка ищется целиком, и если словарь знает
её вместе со значком — трогать нечего. Так правка физически не может подменить
уже работающий перевод.
"""
import argparse
import json
import pathlib
import re
import sys
import unicodedata

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import status  # noqa: E402
import check_nicknames  # noqa: E402

OUT = ROOT / "src/main/resources/assets/skyblockru/packs/ru_ru/01-full-icons.json"
PACKS = ROOT / "src/main/resources/assets/skyblockru/packs"
DUMP = pathlib.Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")
CYR = re.compile("[а-яА-ЯёЁ]")
AT = re.compile(r"@[a-z]")
# ведущий значок: не буква и не цифра, ОТДЕЛЁН ПРОБЕЛОМ
LEAD = re.compile(r"^((?:[^\w\s]|[\ue000-\uf8ff])+)\s+(.+)$")
# ⚠️ ...НО ЗНАЧОК БЫВАЕТ И БУКВОЙ ЧУЖОГО АЛФАВИТА, и тогда класс
# «не буква» его не берёт: части удочки Hypixel помечает СИНГАЛЬСКОЙ буквой
# (Hook), ЧАМСКОЙ (Line) и тибетским символом (Sinker). Первые две —
# категория Lo, то есть для Python обычные БУКВЫ, и заголовок вида
# «<знак> Hotspot Hook» оставался английским при КУПЛЕННОМ переводе имени.
# Признак тот же, что в моде (`Paragraphs.isMarkerChar`): буква значит
# значок, только если её алфавит не латиница и не кириллица. Списка
# алфавитов не заводим — он отстал бы от первой же новой вещи.
LEAD_ANY = re.compile(r"^(\S{1,3})\s+(.+)$")


def _icon_char(char: str) -> bool:
    if 0xE000 <= ord(char) <= 0xF8FF:
        return True
    category = unicodedata.category(char)
    if category.startswith("S") or category.startswith("P"):
        return True
    if category in ("Lo", "Lm"):
        try:
            return unicodedata.name(char).split()[0] not in ("LATIN", "CYRILLIC")
        except ValueError:
            return False
    return False


def split_icon(line: str):
    """(значок, остаток) либо None. Значок отделён пробелом."""
    found = LEAD.match(line)
    if found:
        return found.group(1), found.group(2)
    found = LEAD_ANY.match(line)
    if found and all(_icon_char(c) for c in found.group(1)):
        return found.group(1), found.group(2)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not DUMP.exists():
        print("нет дампа:", DUMP)
        return 1

    # ⚠️ Свой выход исключаем — иначе на втором прогоне генератор увидит уже
    # переведённые строки, решит, что работы нет, и запишет пустой словарь.
    full = status.Dictionaries(without={OUT.name}, groups={"full"})
    # ⚠⚠ ГЕНЕРАТОР ВИДЕЛ ОДИН ИНСТАНС ИЗ ДЕСЯТИ: 21 679 строк против
    # 86 364. Заголовки частей удочки («<знак> Prismarine Sinker») приходят
    # от ИГРОКОВ и из других инстансов, поэтому развёртка их не встречала
    # вовсе — имя переведено, а строка со значком оставалась английской.
    # Та же семья, что записана про `gen_mob_names`: сбор по ОДНОМУ
    # источнику теряет целые формы, и заготовка бодро печатает «ждут 0».
    dump = json.loads(DUMP.read_text(encoding="utf-8"))
    merged: dict[str, dict] = {}
    for source, rows in (dump.get("sources") or {}).items():
        if isinstance(rows, dict):
            merged.setdefault(source, {}).update(rows)
    import glob as _glob
    for _path in _glob.glob("C:/MultiMC/instances/*/.minecraft/config/skyblockru"
                            "/dump/collected.json"):
        try:
            _extra = json.loads(pathlib.Path(_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        for source, rows in (_extra.get("sources") or {}).items():
            if isinstance(rows, dict):
                merged.setdefault(source, {}).update(rows)
    _players = ROOT / "data" / "work" / "from_players.json"
    if _players.exists():
        try:
            _rows = json.loads(_players.read_text(encoding="utf-8"))
        except Exception:
            _rows = {}
        for source, rows in ((_rows.get("sources") or _rows) or {}).items():
            if isinstance(rows, dict):
                merged.setdefault(source, {}).update(rows)
    dump = {"sources": merged}

    exact = {}

    known_names = check_nicknames.known_names()

    nicknamed = 0
    _hand = OUT.parent / "04-full-strings.json"
    by_hand = set()
    if _hand.exists():
        by_hand = set(json.loads(_hand.read_text(encoding="utf-8"))
                      .get("exact", {}))
    for origin, lines in (dump.get("sources") or {}).items():
        rows = lines.items() if isinstance(lines, dict) else ((x, 1) for x in lines)
        for line, _ in rows:
            # ⚠ ДЕШЁВЫЙ ОТСЕВ ПЕРЕД ДОРОГИМ: `status.lookup` при промахе
            # перебирает тысячи правил, а строк теперь 86 тысяч — прогон
            # не укладывался и в десять минут. Значок же проверяется
            # мгновенно, и без него строка нам не нужна вовсе.
            # Записанная грабля проекта (так же лечился `gen_full_names`).
            found = split_icon(line.strip())
            if not found:
                continue
            icon, rest = found
            # ⚠⚠ СПРАШИВАТЬ НАДО НЕ ТОЛЬКО СВОЮ ОБЛАСТЬ. Строка приходит,
            # скажем, из `item_name`, а чужой словарь объявлен для `item_lore` —
            # и защита «строку уже переводят» его не видела. Так развёртка
            # чуть не подменила КАТЕГОРИЮ мобов именем предмета:
            # «<знак> Frozen» -> «Ледяной» стало бы «Замороженный», хотя рядом
            # в списке стоят «Эндерский» и «Жуткий».
            taken = False
            for _area in (origin, "item_lore", "item_name", "name_tag"):
                whole = status.lookup(line, full, origin=_area)
                if whole and (CYR.search(whole[0]) or AT.search(whole[0])):
                    taken = True
                    break
            if taken:
                continue  # словарь знает строку СО значком — не трогаем
            inner = status.lookup(rest, full, origin=origin)
            if not inner or not (CYR.search(inner[0]) or AT.search(inner[0])):
                continue
            # ⚠️ КЛЮЧ ИЗ ЖИВОЙ СТРОКИ МОЖЕТ НЕСТИ ЧУЖОЙ НИК — признак
            # общий на все режимные генераторы, своей копии не заводим.
            value = f"{icon} {inner[0]}"
            key = check_nicknames.safe_key(line, value, known_names)
            if key is None:
                nicknamed += 1
                continue
            exact[key] = value

    # ⚠️⚠️ ПЕРЕНОС ПРЕЖНИХ ЗАПИСЕЙ. Генератор видит только то, что лежит
    # в ДАМПЕ СЕЙЧАС, а дамп чистится и редеет — созданное месяц назад он
    # больше не встретит и молча выбросит. У соседнего `gen_full_names`
    # так усохло 549 -> 198, и 295 строк перестали переводиться ВООБЩЕ.
    # ⚠️ Переносим НЕ ВСЁ: что закрыто ручным переводом или несёт чужой ник —
    # не возвращаем, иначе правка отменится сама при первой пересборке.
    carried = 0
    if OUT.exists():
        _before = json.loads(OUT.read_text(encoding="utf-8")).get("exact", {})
        for _key, _value in _before.items():
            if _key in exact or _key in by_hand:
                continue
            if check_nicknames.nicks_in(_key, known_names):
                continue
            # ⚠⚠ ПЕРЕНОС ТОЖЕ ОБЯЗАН СПРАШИВАТЬ, НЕ ЗАНЯТА ЛИ СТРОКА.
            # Защита стояла только на свежих записях, а прежние переезжали
            # из сборки в сборку без проверки — так «<знак> Frozen» держал
            # «Замороженный» поверх КАТЕГОРИИ мобов «Ледяной» из
            # `46-mob-categories`. Записанная семья: испорченная запись
            # переезжает вместе с добром (было у `gen_full_names`).
            _busy = False
            for _area in ("item_lore", "item_name", "name_tag"):
                _has = status.lookup(_key, full, origin=_area)
                if _has and _has[0] != _value and (CYR.search(_has[0])
                                                   or AT.search(_has[0])):
                    _busy = True
                    break
            if _busy:
                continue
            exact[_key] = _value
            carried += 1
    if carried:
        print(f"перенесено из прежней сборки: {carried}")

    print(f"строк, где значок мешал ключу: {len(exact)}")
    if nicknamed:
        print(f"  чужой ник в строке — обобщено либо отброшено: {nicknamed}")
    for key, value in list(exact.items())[:8]:
        print(f"   {key[:40]!r:42} -> {value[:40]!r}")
    if not args.write:
        print("\nСУХОЙ ПРОГОН. Записать: --write")
        return 0
    if not exact:
        print("ПУСТО — файл НЕ переписан")
        return 1

    pack = {
        "id": "full_icons",
        "priority": 1,
        "default": False,
        "group": "full",
        "about": "Строки со значком перед именем: «◆ Blood Rune I» -> "
                 "«◆ Руна крови I». Часть полного перевода.",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_full_icons.py — правь СКРИПТ. "
                    "Мод переводит строку целиком, а Hypixel ставит значок "
                    "перед именем: ключ без значка не совпадёт никогда.",
        "exact": dict(sorted(exact.items())),
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано: {OUT.name} ({len(exact)} записей)")
    index = PACKS / "index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    files = data["languages"]["ru_ru"]
    if OUT.name not in files:
        files.append(OUT.name)
        files.sort()
        index.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print("вписан в index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
