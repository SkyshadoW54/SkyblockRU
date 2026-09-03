# -*- coding: utf-8 -*-
"""
Имена NPC, локаций и перков для РЕЖИМА ПОЛНОГО ПЕРЕВОДА.

Списки берутся у ПРОЕКТА, а не собираются заново: `protected.collect_groups()`
уже сводит их из вики, реплик NPC, надписей над головой и боковой панели,
и у него же стоят сторожа. Свой список разошёлся бы с защитой при первом
пополнении.

    python tools/gen_npc_places.py --skeleton         заготовка
    python tools/gen_npc_places.py --export FILE --limit 200
    python tools/gen_npc_places.py --load FILE
    python tools/gen_npc_places.py --write            собрать 82-npc-places.json

⚠️ ОБЛАСТЬ УЖЕ, ЧЕМ У ПРЕДМЕТОВ, и это нарочно. Имя NPC и название места
стоят ОТДЕЛЬНОЙ строкой в надписи над головой, в заголовке меню и на экране —
там перевод безопасен. А внутри ПРОЗЫ («Поговори с Kat», «в The Garden») то же
имя требует падежа, которого точная запись не знает: «Поговори с Кэт» верно,
а «Отнеси в Сад» из «in The Garden» уже нет. Проза — отдельный этап (слой B),
и до него имена в описаниях остаются английскими.

⚠️ ГРУППЫ РАЗДЕЛЕНЫ, потому что у них разная область применения:
  * npc      — надпись над головой, меню, экран, таб
  * location — то же плюс боковая панель и полоса над хотбаром
  * perk     — только экран (перки деревьев HotM/HotF)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# ⚠️ Консоль Windows — cp1251, и `print` со значком «⚠️» роняет скрипт
# на первой же находке. Записанная грабля проекта: инструмент, падающий
# на печати, ВРЁТ О СВОЕЙ РАБОТЕ — вывод оборван, а выглядит как поломка
# того, что он проверял. У сторожа это хуже вдвое: он молчит, пока всё
# хорошо, и ломается ровно тогда, когда нашёл беду.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
LANG = "ru_ru"

SKELETON = WORK / "npc_places_ru.json"
PACK = PACKS / LANG / "82-npc-places.json"
PLAYERS = WORK / "from_players.json"

# Где перевод безопасен: имя стоит ОТДЕЛЬНОЙ строкой.
#
# ⚠️ `title` — КРУПНАЯ НАДПИСЬ на пол-экрана, которой Hypixel объявляет вход
# в зону («Fishing Outpost», «Deep Caverns»). Её тут не было, и 116 названий
# из 196 оставались английскими при готовом переводе: словарь знает 2165 имён,
# а область его туда не пускала. Замер 23.08 — просмотрены все 116, чужого
# среди них нет: это места, дома NPC и зоны.
#
# ⚠️ Имя там стоит ОДНО и целой строкой, то есть ровно тот случай, под который
# область и задумана. Прозу это не задевает: точная запись срабатывает только
# на строку целиком.
# ⚠️ `boss_bar` добавлен 23.08: имя босса Hypixel пишет и в полосе сверху
# ГОЛЫМ («Wise Dragon», «Bonzo», «The Professor»). Перевод для них давно есть,
# а область туда не пускала — 15 боссов оставались английскими на самом
# заметном месте экрана.
# ⚠️ `chat` добавлен 25.08: имя места приходит в чат ОТДЕЛЬНОЙ строкой
# и со значком (« Community Center»), а перевод лежал готовым. Конфликтов
# нет по замеру: priority 62 — самый большой среди работающих в чате,
# а у `exact` побеждает МЕНЬШИЙ, значит чужие надписи мы не подменим.
AREAS = ["name_tag", "menu_title", "screen", "tab", "scoreboard", "action_bar",
         "title", "item_name", "item_lore", "boss_bar", "chat"]

GROUPS = ("npc", "location", "perk")

# ⚠️ В ПАНЕЛИ И НАД ХОТБАРОМ ЛОКАЦИЯ ПРИХОДИТ СО ЗНАЧКОМ, и мод переводит
# строку ЦЕЛИКОМ: в дампе лежит « Savanna Woodland», а не голое имя.
# Точная запись по имени там не совпадёт НИ РАЗУ — записанная грабля проекта,
# на которой однажды уже потеряли вечер (« Your Island»).
#
# Значки взяты ИЗ ЖИВЫХ строк, а не выдуманы: U+E067 встретился 416 раз,
# U+E020 — 6. Правилом это делать нельзя: совпавшее правило гасит запись
# строки в дамп, и непереведённая локация стала бы невидимой для отчётов.
# ⚠️ ДВОЙСТВЕННЫЕ СЛОВА — ТОЛЬКО СО ЗНАЧКОМ. «Village», «Bank», «Farm»
# по-английски и место, и обычное слово, поэтому в защите их нет (иначе
# сломалась бы проза — записанная грабля про «избран мэром SkyBlock»).
# Но в ПАНЕЛИ двойственности нет: там колонку целиком занимает метка места,
# и значок U+E067 это подтверждает. Тот же приём, что «цвет — признак имени
# ТОЛЬКО В ЧАТЕ»: признак неверен вообще, но верен в своей области.
#
# Голое имя сюда НЕ кладём — только вариант со значком.
MARKED_ONLY = {
    "Village": "Деревня",
    "Bank": "Банк",
    "Auction House": "Аукцион",
    "Farm": "Ферма",
    "Mountain": "Гора",
    "Crypts": "Склепы",
    "Gates to the Mines": "Врата в шахты",
    "Galatea": "Галатея",
    "Lava Springs": "Лавовые источники",
    "Catacombs Entrance": "Вход в Катакомбы",
    # ⚠️ Событие Carnival зовётся «Ярмаркой» в 99 записях (панель, меню,
    # лор). «Карнавал» здесь расходился бы с ними на соседних экранах.
    "Carnival": "Ярмарка",
    "Barracks of Heroes": "Казармы героев",
    "Miria's Hut": "Хижина Miria",
    "Fisherman": "Рыбак",
    "{s}'s Museum": "Музей {s}",
    "??? Island": "Остров ???",
    "The Catacombs (F{n})": "Катакомбы (F{n})",
    "The Catacombs (E)": "Катакомбы (E)",
}

LOCATION_MARKS = ("", "")


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def sources() -> dict[str, set[str]]:
    """Имена по группам — у проекта, своей копии не заводим."""
    import protected
    import terms
    out = {}
    groups = protected.collect_groups()
    out["npc"] = set(groups.get("npc", ()))
    out["location"] = set(groups.get("location", ()))
    out["perk"] = set(terms.of("perk"))
    return out


def seen_counts() -> dict[str, int]:
    """Сколько игроков видели строку — по ней задаётся порядок работы."""
    players = load(PLAYERS, {})
    counts: dict[str, int] = {}
    if not isinstance(players, dict):
        return counts
    for area in AREAS:
        block = players.get(area, {})
        if not isinstance(block, dict):
            continue
        for line, number in block.items():
            value = number if isinstance(number, int) else 1
            counts[line] = max(counts.get(line, 0), value)
    return counts


def do_skeleton() -> int:
    groups = sources()
    counts = seen_counts()
    old = load(SKELETON, {})
    ready = old.get("names", {}) if isinstance(old, dict) else {}
    asis = set(old.get("_asis", []) if isinstance(old, dict) else [])

    # ⚠️ ИМЕНА ПРЕДМЕТОВ СЮДА НЕ ПУСКАЕМ. Списки NPC собраны в том числе
    # по надписи над головой, а Hypixel вешает такие надписи и над стендами
    # с товаром: в группу попали «Spartan Warden Helmet Skin» и «Litter Black
    # Cat Skin». Они уже переведены как ПРЕДМЕТЫ, и второй перевод того же
    # имени дал бы разнобой на одном экране.
    items = load(WORK / "item_names_ru.json", {})
    item_names = {k for k, v in items.get("names", {}).items() if v}
    item_names |= set(items.get("_asis", []))
    skipped_items = 0

    fresh: dict[str, dict] = {}
    for group in GROUPS:
        for name in sorted(groups.get(group, ())):
            if name in asis:
                continue
            # ⚠️ Имя может числиться в двух группах сразу (табличка места висит
            # и над NPC). Первая победившая группа и решает область.
            if name in fresh:
                continue
            if name in item_names:
                skipped_items += 1
                continue
            fresh[name] = {
                "group": group,
                "ru": ready.get(name, {}).get("ru", "") if isinstance(ready.get(name), dict)
                      else ready.get(name, ""),
                "seen": max((count for line, count in counts.items() if name in line),
                            default=0),
            }

    ordered = dict(sorted(fresh.items(), key=lambda kv: (-kv[1]["seen"], kv[0])))
    done = sum(1 for row in ordered.values() if row["ru"])
    save(SKELETON, {
        "_comment": "Имена NPC, локаций и перков для режима полного перевода. "
                    "ИСТОЧНИК ПРАВДЫ — этот файл; словарь 82-npc-places.json "
                    "собирается из него. Порядок — по числу игроков, видевших "
                    "строку с этим именем. В ПРОЗЕ имена остаются английскими: "
                    "там нужен падеж, а точная запись его не знает.",
        "_asis": sorted(asis),
        "names": ordered,
    })
    if skipped_items:
        print(f"  отсеяно имён предметов (переведены отдельно): {skipped_items}")
    for group in GROUPS:
        rows = [r for r in ordered.values() if r["group"] == group]
        print(f"  {group:9} всего {len(rows):4}, переведено "
              f"{sum(1 for r in rows if r['ru']):4}")
    print(f"  ИТОГО {len(ordered)}, переведено {done}, ждут {len(ordered) - done}")
    top = [n for n, r in ordered.items() if not r["ru"]][:8]
    print("  верхушка по охвату:", ", ".join(top))
    return 0


def do_export(path: Path, limit: int, group: str | None) -> int:
    data = load(SKELETON, {})
    names = data.get("names", {})
    if not names:
        print("заготовки нет — сперва --skeleton")
        return 1
    task = []
    for name, row in names.items():
        if row["ru"]:
            continue
        if group and row["group"] != group:
            continue
        task.append({"en": name, "ru": "", "_group": row["group"], "_seen": row["seen"]})
        if len(task) >= limit:
            break
    save(path, task)
    print(f"выгружено {len(task)} имён -> {path}")
    return 0


def foreign_letters(text: str) -> list[str]:
    bad = []
    for char in text:
        if char.isspace() or not char.isalpha():
            continue
        if "" <= char <= "":
            continue
        try:
            if not unicodedata.name(char).startswith(("LATIN", "CYRILLIC")):
                bad.append(char)
        except ValueError:
            bad.append(char)
    return bad


def do_load(path: Path) -> int:
    task = load(path)
    if not isinstance(task, list):
        print("файл задания должен быть списком записей")
        return 1
    data = load(SKELETON, {})
    names = data.get("names", {})
    asis = set(data.get("_asis", []))

    taken, marked, refused = 0, 0, []
    for row in task:
        value = (row.get("ru") or "").strip()
        if not value:
            continue
        key = row.get("en", "")
        if key not in names:
            refused.append(f"{key!r}: НЕ НАЙДЕНО в заготовке")
            continue
        if value == "-":
            asis.add(key)
            names.pop(key, None)
            marked += 1
            continue
        bad = foreign_letters(value)
        if bad:
            refused.append(f"{key!r}: чужая письменность {bad}")
            continue
        if value == key:
            refused.append(f"{key!r}: перевод совпал с оригиналом — ставь «-», "
                           f"если переводить нечего")
            continue
        names[key]["ru"] = value
        taken += 1

    data["names"] = names
    data["_asis"] = sorted(asis)
    save(SKELETON, data)
    print(f"влито {taken} из {len(task)}"
          + (f", помечено «переводить нечего»: {marked}" if marked else ""))
    for line in refused[:20]:
        print(f"   {line}")
    return 0


# «Имя (Метка)»: метка — слова с Заглавной в скобках на конце строки.
TAGGED = re.compile(r"^(.+) \(([A-Z][A-Za-z ]{1,26})\)$")


def seen_with_tag() -> dict[str, set[str]]:
    """
    Имя -> МЕТКИ В СКОБКАХ, с которыми оно реально приходило.

    ⚠️ Hypixel подписывает персонажа не только «(NPC)»: в живых строках есть
    «(Rift NPC)», «(Mayor)», «(Monster)», «(Sea Creature)», «(Animal)»,
    «(Pest)», «(Boss)». Раньше генератор знал ОДНУ метку и только для группы
    `npc` — остальные строки оставались английскими при готовом переводе
    имени. Замер 23.08: развёртка меток закрывает 588 строк.

    ⚠️ Набор меток берём ИЗ ДАННЫХ, а не списком: в тех же скобках стоят
    редкость («(RARE)»), уровень («(VI)») и подсказка управления
    («(Right Click)»). Список отстал бы от первой же новой метки, а данные —
    нет. Защита та же, что у значков: вариант заводится, только если имя
    ЕСТЬ в заготовке, поэтому чужая метка сама по себе ничего не создаёт.
    """
    out: dict[str, set[str]] = {}
    players = load(PLAYERS, {})
    if not isinstance(players, dict):
        return out
    for block in players.values():
        if not isinstance(block, dict):
            continue
        for line in block:
            match = TAGGED.match(line.strip())
            if match:
                out.setdefault(match.group(1), set()).add(match.group(2))
    return out


def seen_with_mark() -> set[str]:
    """Имена, которые РЕАЛЬНО приходили со значком — по живым строкам.

    ⚠️ По группе это не вывести: часть мест числится в группе `npc`, потому
    что табличка локации висит и над персонажем («Savanna Woodland» собрано
    как надпись над головой). Признак берём из данных, а не из нашей же
    разметки — она тут отвечает на другой вопрос.
    """
    out: set[str] = set()
    players = load(PLAYERS, {})
    stores = [players] if isinstance(players, dict) else []
    for store in stores:
        for area in ("scoreboard", "action_bar", "tab", "name_tag"):
            block = store.get(area)
            if not isinstance(block, dict):
                continue
            for line in block:
                for mark in LOCATION_MARKS:
                    if line.startswith(mark + " "):
                        out.add(line[len(mark) + 1:].strip())
    return out


def with_marks(names: dict[str, dict]) -> dict[str, str]:
    """Имена плюс варианты со значком — для панели и полосы над хотбаром."""
    marked = seen_with_mark()
    tagged = seen_with_tag()
    out: dict[str, str] = {}
    for english, russian in MARKED_ONLY.items():
        for mark in LOCATION_MARKS:
            out[f"{mark} {english}"] = f"{mark} {russian}"
    for english, row in names.items():
        out[english] = row["ru"]
        # ⚠️ «Имя (NPC)» — та же надпись, только с меткой: так Hypixel
        # подписывает персонажа в списке заголовков. Замер по строкам
        # от игроков: 416 таких строк, и у 330 имя УЖЕ переведено —
        # они просто не доставались из-за метки.
        # ⚠️ Метки берём ИЗ ЖИВЫХ СТРОК, а «(NPC)» оставляем всегда: она
        # приходит и тем именам, мимо которых игроки пока не ходили.
        tags = set(tagged.get(english, ()))
        if row.get("group") == "npc":
            tags.add("NPC")
        for tag in sorted(tags):
            out[f"{english} ({tag})"] = f"{row['ru']} ({tag})"
        # Локации получают вариант всегда: панель покажет любую, даже ту,
        # мимо которой никто пока не проходил. Прочим — только если такая
        # строка ДЕЙСТВИТЕЛЬНО приходила.
        if row.get("group") != "location" and english not in marked:
            continue
        for mark in LOCATION_MARKS:
            out[f"{mark} {english}"] = f"{mark} {row['ru']}"
    return out


def do_write() -> int:
    data = load(SKELETON, {})
    names = {k: v for k, v in data.get("names", {}).items() if v.get("ru")}
    if not names:
        print("переведённых имён нет — писать нечего")
        return 1

    # ⚠️ ОДИНАКОВЫЙ ПЕРЕВОД У МЕСТА — НЕ ВСЕГДА БЕДА. Hypixel пишет одно
    # и то же место двумя способами («Catacombs» и «The Catacombs»), и по-русски
    # оба честно «Катакомбы». Для ПРЕДМЕТОВ такой дубль опасен — вещи стали бы
    # неразличимы по имени, — а место от артикля другим не становится.
    # Поэтому синонимом считаем пару, отличающуюся только «The ».
    #
    # ⚠️ ТО ЖЕ У СУЩЕСТВА, НАЗВАННОГО ДВУМЯ СЛОВАМИ. «Charged Creeper»
    # и «Powered Creeper» — один и тот же заряженный крипер, Hypixel пишет
    # его по-разному; перевод у них ОБЯЗАН совпадать, и требовать различия
    # значит выдумывать второе русское имя несуществующему существу.
    # Пары перечислены ЯВНО — признака тут нет, каждая проверена глазами.
    # ⚠️ Опечатка САМОГО СЕРВЕРА: Hypixel пишет одного и того же NPC
    # двумя способами, и перевод у них обязан совпадать.
    SYNONYMS = {frozenset({"Charged Creeper", "Powered Creeper"}),
                frozenset({"Kuudra Archaeologist", "Kuudra Archeologist"}),
                # ⚠️ ОДИН NPC В ДВУХ НАПИСАНИЯХ, и это подтверждено данными,
                # а не догадкой: над головой он «Forge Foreman» (name_tag,
                # item_name), а в чате подписывается «Forger» — 30 реплик
                # у игроков против 2 надписей. Требовать разных переводов
                # значит выдумать второе русское имя одному персонажу.
                frozenset({"Forge Foreman", "Forger"})}

    def bare(name: str) -> str:
        return name[4:] if name.startswith("The ") else name

    back: dict[str, list[str]] = {}
    for english, row in names.items():
        back.setdefault(row["ru"], []).append(english)
    clashes = {ru: ens for ru, ens in back.items()
               if len(ens) > 1 and len({bare(e) for e in ens}) > 1
               and frozenset(ens) not in SYNONYMS}
    if clashes:
        print(f"⚠️ ОДИН ПЕРЕВОД У РАЗНЫХ ИМЁН: {len(clashes)}")
        for russian, english in sorted(clashes.items())[:10]:
            print(f"   {russian!r} <- {english}")
        return 1

    pack = {
        "id": "npc_places",
        "priority": 62,
        "default": False,
        "group": "full",
        "about": "имена NPC, названия локаций и перков (Kat -> Кэт, "
                 "The Garden -> Сад). По умолчанию выключено: по английским "
                 "названиям читают гайды и ищут места",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_npc_places.py из "
                    "data/work/npc_places_ru.json — правь заготовку. "
                    "Область УЖЕ, чем у предметов: имя переводится там, где оно "
                    "стоит ОТДЕЛЬНОЙ строкой (надпись над головой, меню, экран, "
                    "панель). Внутри прозы имя требует падежа, и там оно "
                    "остаётся английским до слоя B.",
        "only": AREAS,
        "exact": dict(sorted(with_marks(names).items())),
    }
    save(PACK, pack)
    by_group = {}
    for row in names.values():
        by_group[row["group"]] = by_group.get(row["group"], 0) + 1
    print(f"записано {PACK.name}: {len(names)} записей {by_group}")
    print("⚠️ впиши файл в packs/index.json, иначе он молча не загрузится")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeleton", action="store_true")
    parser.add_argument("--export", metavar="FILE")
    parser.add_argument("--load", metavar="FILE")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--group", choices=GROUPS, help="только одна группа")
    args = parser.parse_args()

    if args.skeleton:
        return do_skeleton()
    if args.export:
        return do_export(Path(args.export), args.limit, args.group)
    if args.load:
        return do_load(Path(args.load))
    if args.write:
        return do_write()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
