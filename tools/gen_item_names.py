# -*- coding: utf-8 -*-
"""
Названия предметов SkyBlock для РЕЖИМА ПОЛНОГО ПЕРЕВОДА.

Список берётся У СЕРВЕРА (`data/work/item_names.json` — каталог Hypixel),
а не собирается из того, что мод успел встретить: собранное по крупицам
всегда неполно, и это записанная беда проекта (зачарований у нас было 98
против 131 на вики, локаций 45 против 275).

    python tools/gen_item_names.py --skeleton         завести/пополнить заготовку
    python tools/gen_item_names.py --export FILE.json --limit 200
        (заполнить поле "ru" у каждой записи)
    python tools/gen_item_names.py --load FILE.json   влить обратно
    python tools/gen_item_names.py --write            собрать 81-item-names.json

⚠️ ИСТОЧНИК ПРАВДЫ — заготовка `data/work/item_names_ru.json`, а не собранный
словарь: словарь автосборный, и ручная правка в нём живёт до первой пересборки.

⚠️ ПОРЯДОК — ПО ЧИСЛУ ИГРОКОВ, которые видели предмет. Переводить каталог
подряд бессмысленно: 6360 имён, а на экране у людей мелькают несколько сотен.
Частота считается по `from_players.json` с нормализацией (снимаем ковку,
звёзды и префикс перековки), потому что «Fierce Hyperion ✪✪✪✪✪» и «Hyperion» —
одна вещь.

⚠️ ЗНАЧКИ ВЫДАЮТСЯ МАСКАМИ {i1}, {i2}. Символы Hypixel лежат в приватной зоне
юникода и при копировании из терминала молча превращаются в пробел — на этом
проект обжигался трижды (переводы абзацев, разметка цветом, ручные пачки).

⚠️ ВАНИЛЬНЫЕ НАЗВАНИЯ СЮДА НЕ БЕРЁМ. Их переводит `80-vanilla-names`
через @ключи, то есть текст берётся у самого клиента игрока: он точен
по построению и меняется вместе с языком игры. Своя запись была бы хуже
и разошлась бы с инвентарём.
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

CATALOG = WORK / "item_names.json"
SKELETON = WORK / "item_names_ru.json"
PACK = PACKS / LANG / "81-item-names.json"
VANILLA = PACKS / "common" / "80-vanilla-names.json"
PLAYERS = WORK / "from_players.json"

# Значок Hypixel: приватная зона плюс те символы, которыми он помечает ковку
# и звёзды. Буквы не в счёт — Hypixel берёт под значки и буквы чужих алфавитов,
# но в ИМЕНАХ предметов их не бывает, а маскировать буквы опасно.
# ⚠️ Диапазон задаём КОДАМИ, а не буквальными символами: записанная грабля
# проекта — в буквальном виде дефис между значками читается как «минус»,
# и регулярка начинает ловить обычный дефис («Auto-closing»).
ICON = re.compile("[-✪✦✧⭐➜➀-➉]")

# ⚠️ СЕМЬИ, КОТОРЫЕ ЗАКРЫВАЕТ ОДНО ПРАВИЛО, а не 800 записей.
#
# «Oak Minion I … XII» — это 61 тип миньона на дюжину уровней, то есть чистая
# комбинаторика: 718 имён, у которых меняется только римская цифра. Переводить
# их поштучно значит платить временем за то, что делает один шаблон, и вдобавок
# заводить разнобой — каждая запись переводилась бы в свой заход.
#
# Правило берёт захват ЦЕЛИКОМ («Oak Minion») и переводит его по словарю
# (`tg: true`), а уровень переносит как есть. Значит переводить надо БАЗУ,
# и она добавляется в заготовку, даже если сервер шлёт только варианты
# с уровнем.
#
# ⚠️ Захват переводится ПОЛНОСТЬЮ, а не по словам: у «Oak Minion» перевод
# «Дубовый миньон» — прилагательное согласовано с родом, и по частям это
# не собрать (записанная грабля проекта про род).
FAMILIES = (
    (r"^(.+ Minion) ([IVXL]+) (Upgrade Stone)$", "Камень улучшения: $1 $2",
     "камень улучшения миньона"),
    (r"^(.+ Minion) ([IVXL]+)$", "$1 $2", "миньон с уровнем"),
    (r"^(.+) Mk\. ([IVX]+)$", "$1 Mk. $2", "инструмент с поколением"),
    (r"^(.+) - Tier ([IVXL]+)$", "$1 - ступень $2", "вещь со ступенью"),
)

# Хвост уровня в ПЕРЕВОДЕ: римская цифра, «Mk. III», «- ступень XII».
# Нужен, чтобы снять уровень с уже переведённого варианта и получить базу.
LEVEL_TAIL = re.compile(r"(?:\s*-\s*ступень)?\s*(?:Mk\.\s*)?[IVXL]+\s*$")

# Хвост прокачки: звёзды ковки, метки мастерства. Снимается при подсчёте
# частоты — «Hyperion ✪✪✪✪✪» и «Hyperion» это одна вещь.
UPGRADE_TAIL = re.compile("[\\s-✪✦✧⭐➀-➉]+$")


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def catalog_names() -> list[str]:
    """Канонические имена от сервера."""
    data = load(CATALOG, {})
    names = data.get("names", {})
    if isinstance(names, dict):
        return sorted({v for v in names.values() if isinstance(v, str) and v.strip()})
    return sorted({n for n in names if isinstance(n, str)})


def vanilla_keys() -> set[str]:
    """Что уже переводит словарь ванильных названий — своей записи не заводим."""
    data = load(VANILLA, {})
    return set(data.get("glossary", {})) | set(data.get("exact", {}))


def family_base(name: str) -> str | None:
    """Если имя — вариант семьи с уровнем, вернуть БАЗУ. Иначе None."""
    for pattern, _replacement, _why in FAMILIES:
        found = re.match(pattern, name)
        if found:
            return found.group(1)
    return None


def base_of(name: str, catalog: set[str]) -> str:
    """Имя без ковки и без префикса перековки: «Fierce Hyperion ✪✪✪» -> «Hyperion»."""
    clean = UPGRADE_TAIL.sub("", name).strip()
    clean = re.sub(r"\s+x[\d,]+$", "", clean)
    parts = clean.split(" ", 1)
    if len(parts) == 2 and parts[1] in catalog:
        return parts[1]
    return clean


def seen_counts(catalog: set[str]) -> dict[str, int]:
    """Сколько РАЗНЫХ игроков видели предмет. Порядок работы задаёт это, а не алфавит."""
    players = load(PLAYERS, {})
    raw = players.get("item_name", {}) if isinstance(players, dict) else {}
    counts: dict[str, int] = {}
    for name, number in raw.items():
        key = base_of(name, catalog)
        if key:
            counts[key] = counts.get(key, 0) + (number if isinstance(number, int) else 1)
    return counts


def do_skeleton() -> int:
    """Завести или пополнить заготовку. Готовые переводы сохраняются."""
    names = catalog_names()
    if not names:
        print("каталога имён нет — сперва python tools/fetch_item_names.py")
        return 1
    catalog = set(names)
    known = vanilla_keys()
    counts = seen_counts(catalog)

    old = load(SKELETON, {})
    ready = old.get("names", {}) if isinstance(old, dict) else {}
    asis = set(old.get("_asis", []) if isinstance(old, dict) else [])

    fresh, bases, skipped_vanilla = {}, {}, 0
    for name in names:
        if name in known:
            # ⚠️ Ванильное название — его переводит клиент через @ключ.
            skipped_vanilla += 1
            continue
        if name in asis:
            # ⚠️ РЕШЕНИЕ «переводить нечего» хранится, а не принимается заново.
            # Без этого «X» и подобные метки лезли бы в КАЖДУЮ пачку, и каждый
            # раз их пришлось бы разбирать сызнова — а решение уже принято.
            continue
        base = family_base(name)
        if base is not None:
            # Вариант с уровнем закрывает правило — в работу идёт только база.
            bases[base] = bases.get(base, 0) + counts.get(name, 0)
            continue
        fresh[name] = ready.get(name, "")

    # ⚠️ База добавляется в работу, даже если сервер её не шлёт: «Oak Minion»
    # сам по себе не встречается, но именно он — единица перевода.
    for base, seen in bases.items():
        if base not in fresh and base not in asis:
            guess = ready.get(base, "")
            if not guess:
                # ⚠️ ПЕРЕВОД ВАРИАНТА НЕ ТЕРЯЕМ. Если «Oak Minion I» когда-то
                # перевели руками, а теперь семья свернулась в базу, перевод
                # обязан переехать на базу: иначе пересборка молча съедает
                # оплаченную работу — записанная беда проекта.
                for variant, done in ready.items():
                    if done and family_base(variant) == base:
                        guess = LEVEL_TAIL.sub("", done).strip()
                        break
            fresh[base] = guess
        counts.setdefault(base, 0)
        counts[base] = max(counts.get(base, 0), seen)

    # ⚠️ КАТАЛОГА СЕРВЕРА НЕ ХВАТАЕТ, и это замер, а не догадка. Кроликов
    # Hoppity's Hunt («Petunia», «Suri», «Abi» — 453 имени) в
    # `resources/skyblock/items` НЕТ ВОВСЕ: это головы в меню Chocolate
    # Factory, а не продаваемые вещи. При включённом режиме они оставались
    # английскими, хотя игрок просил перевести всё.
    #
    # Признак «это вещь, а не кнопка» берём готовый — `protected.real_items`
    # (каталог сервера ПЛЮС «в подсказке есть строка редкости»). Своего
    # признака не заводим: их в проекте уже трое, и они расходились.
    # ⚠️ Берём только ГОЛОЕ имя — из одних букв. Первая версия брала любое
    # имя с экрана и притащила 2297 записей, среди которых «[Lvl {n}] Sheep»,
    # «◆ Blood Rune I», «Personal Compactor {n}» — это ОБЁРТКИ вокруг имени
    # (уровень питомца, значок с уровнем руны, номер), то есть комбинаторика.
    # Её закрывает разворачивание семей, а не поштучный перевод: иначе
    # заготовка распухнет тем, что переводится один раз и подставляется.
    import protected  # ленивый импорт: он тянет корпуса
    real = protected.real_items()
    # ⚠️ ПЕРЕКОВАННОЕ ИМЯ В ЗАГОТОВКУ НЕ БЕРЁМ: «Ancient Final Destination
    # Boots» мод собирает механикой из NBT (`Reforge.compose`) — префикс
    # отдельно, основа отдельно. Поштучный перевод был бы 148 перековок
    # на 5000 имён, то есть сотни тысяч записей, и это уже решено.
    reforge_pack = load(PACKS / LANG / "84-reforges.json", {}) or {}
    prefixes = set((reforge_pack.get("reforges") or {}).keys())
    plain = re.compile(r"^[A-Za-z][A-Za-z' \-]*$")
    from_screen = 0
    # ⚠️ И НАШ ДАМП тоже, а не только присланное игроками. `seen_counts`
    # читает `from_players.json` — по нему считается ОЧЕРЁДНОСТЬ работы,
    # и это верно. Но кролик «Napoleon» попался только нам, в очередь
    # он не попадал и потому не попал бы в заготовку вовсе.
    for title in list(counts) + sorted(seen_titles()):
        if title in fresh or title in known or title in asis or title in catalog:
            continue
        if not plain.match(title) or title not in real:
            continue
        if family_base(title) is not None:
            continue
        # ⚠️ Отсекаем перековку ТОЛЬКО когда остаток — известное имя вещи.
        # Голое «первое слово это перековка» выбросило 18 законных имён:
        # «Blessed Frog», «Lunar Rat Skin», «Fortified Silverfish Skin» —
        # там первое слово ЧАСТЬ имени. Записанная грабля проекта, и она же
        # объясняет, почему `Reforge.compose` спрашивает NBT, а не форму.
        head = title.split(" ", 1)
        if len(head) == 2 and head[0] in prefixes and head[1] in real:
            continue
        fresh[title] = ready.get(title, "")
        from_screen += 1

    ordered = dict(sorted(fresh.items(), key=lambda kv: (-counts.get(kv[0], 0), kv[0])))
    done = sum(1 for value in ordered.values() if value)
    if from_screen:
        print(f"добавлено имён С ЭКРАНА (в каталоге сервера их нет): {from_screen}")
    save(SKELETON, {
        "_comment": "Названия предметов SkyBlock для режима полного перевода. "
                    "ИСТОЧНИК ПРАВДЫ — этот файл; словарь 81-item-names.json "
                    "собирается из него и ручную правку в нём затрёт. "
                    "Порядок — по числу игроков, видевших предмет. "
                    "Ванильные названия сюда не входят: их переводит клиент "
                    "через @ключи в 80-vanilla-names.json.",
        "_asis_comment": "Переводить нечего: одиночные метки, коды, латынь. "
                         "Решение хранится здесь, иначе те же строки лезли бы "
                         "в каждую пачку заново. Ставится «-» в поле ru задания.",
        "_asis": sorted(asis),
        "names": ordered,
    })
    print(f"каталог сервера: {len(names)}")
    print(f"  ванильных (переводит клиент): {skipped_vanilla}")
    print(f"  в заготовке: {len(ordered)}, переведено {done}, ждут {len(ordered) - done}")
    top = [n for n in ordered if not ordered[n]][:8]
    print("  верхушка по охвату:", ", ".join(top))
    return 0


def mask_icons(text: str) -> tuple[str, list[str]]:
    """Значки -> {i1}, {i2}: из терминала они копируются пробелом."""
    icons: list[str] = []

    def swap(match: re.Match) -> str:
        icons.append(match.group(0))
        return "{i%d}" % len(icons)

    return ICON.sub(swap, text), icons


def unmask_icons(text: str, icons: list[str]) -> str:
    for number, icon in enumerate(icons, 1):
        text = text.replace("{i%d}" % number, icon)
    return text


def do_export(path: Path, limit: int) -> int:
    data = load(SKELETON, {})
    names = data.get("names", {})
    if not names:
        print("заготовки нет — сперва --skeleton")
        return 1
    catalog = set(catalog_names())
    counts = seen_counts(catalog)

    task = []
    for name, value in names.items():
        if value:
            continue
        masked, icons = mask_icons(name)
        task.append({
            "en": masked,
            "ru": "",
            "_key": name if not icons else "",
            "_icons": icons,
            "_seen": counts.get(name, 0),
        })
        if len(task) >= limit:
            break
    save(path, task)
    print(f"выгружено {len(task)} имён -> {path}")
    print("  заполнить поле \"ru\"; значки стоят масками {i1}, {i2} — перенести как есть")
    return 0


def foreign_letters(text: str) -> list[str]:
    """Чужая письменность в переводе — брак: читается нормально, а на экране иероглиф."""
    bad = []
    for char in text:
        if char.isspace() or not char.isalpha():
            continue
        if "" <= char <= "":
            continue
        try:
            name = unicodedata.name(char)
        except ValueError:
            bad.append(char)
            continue
        if not name.startswith(("LATIN", "CYRILLIC")):
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
        translation = (row.get("ru") or "").strip()
        if not translation:
            continue
        key = row.get("_key") or unmask_icons(row.get("en", ""), row.get("_icons", []))
        if key not in names:
            refused.append(f"{key!r}: НЕ НАЙДЕНО в заготовке")
            continue
        # «-» значит «переводить нечего»: метка, код, латынь. Решение
        # запоминается, чтобы строка не просилась в работу каждую пачку.
        if translation == "-":
            asis.add(key)
            names.pop(key, None)
            marked += 1
            continue
        # ⚠️ Значки сверяем НАБОРАМИ: потерянная маска — потерянный значок
        # на экране, а на глаз «+{n} Intelligence» и «+{n}⸎ Intelligence»
        # неотличимы.
        want = ICON.findall(key)
        got = ICON.findall(unmask_icons(translation, row.get("_icons", [])))
        if want != got:
            refused.append(f"{key!r}: значки не совпали ({len(want)} против {len(got)})")
            continue
        bad = foreign_letters(translation)
        if bad:
            refused.append(f"{key!r}: чужая письменность {bad}")
            continue
        if translation == key:
            refused.append(f"{key!r}: перевод совпал с оригиналом — "
                           f"оставь поле пустым, если переводить нечего")
            continue
        names[key] = unmask_icons(translation, row.get("_icons", []))
        taken += 1

    data["names"] = names
    data["_asis"] = sorted(asis)
    save(SKELETON, data)
    print(f"влито {taken} из {len(task)}"
          + (f", помечено «переводить нечего»: {marked}" if marked else ""))
    if refused:
        print(f"отбраковано {len(refused)}:")
        for line in refused[:20]:
            print(f"   {line}")
    return 0


def expand_families(names: dict[str, str], catalog: list[str]) -> tuple[dict, list]:
    """Развернуть семьи с уровнем в ТОЧНЫЕ записи.

    ⚠️ ПОЧЕМУ НЕ ПРАВИЛОМ (решение игрока 22.08: «давай без перевода
    правилами, они не совсем точные и могут сломаться»).

    Правило вида «^(.+ Minion) ([IVXL]+)$» с `tg` работает, но опирается
    на две догадки сразу: что захват совпадёт ровно с ключом словаря
    и что перевод захвата найдётся. Промахнётся — и на экране «Oak миньон V»,
    причём молча. Точная запись такого не умеет: не нашлась — строка честно
    уходит в дамп.

    Цена решения — размер словаря (821 запись вместо четырёх строк), и она
    невелика: словарь и так автосборный, а руками всё равно переводится
    только БАЗА («Oak Minion» → «Дубовый миньон»).
    """
    out, missing = {}, []
    for full in catalog:
        base = family_base(full)
        if base is None:
            continue
        translated = names.get(base)
        if not translated:
            missing.append(full)
            continue
        # Подставляем перевод базы на её место, остальное (уровень, «Upgrade
        # Stone») переносим как есть — ровно то, что делало бы правило,
        # но результат виден здесь и сейчас, а не в игре.
        for pattern, replacement, _why in FAMILIES:
            found = re.match(pattern, full)
            if not found:
                continue
            groups = list(found.groups())
            groups[0] = translated
            line = replacement
            for number, value in enumerate(groups, 1):
                line = line.replace(f"${number}", value)
            # «Upgrade Stone» словами не переводится захватом — заменяем сами.
            line = line.replace("Upgrade Stone", "").strip()
            out[full] = " ".join(line.split())
            break
    return out, missing


# ⚠️ ОБЁРТКИ вокруг имени, которые Hypixel навешивает на ЭКРАНЕ, а в каталоге
# их нет: счётчик стопки и значок слева. Из-за них имя, перевод которого
# у нас ЕСТЬ, оставалось английским — замер по живому дампу: 37 строк
# со счётчиком и десятки со значком.
#
# ⚠️ Хвост ПРОКАЧКИ (звёзды) сюда НЕ входит: его снимает механика
# `Reforge.compose` по NBT, и вторая запись в словаре была бы лишней.
WRAPPERS = (
    (re.compile(r"^(.+?)( x\{n\})$"), "{ru}{tail}"),
    (re.compile(r"^(\{n\}x )(.+)$"), "{head}{ru}"),
    (re.compile(r"^([\ue000-\uf8ff] ?)(.+)$"), "{head}{ru}"),
)

# ⚠️ ЗНАЧОК БЫВАЕТ ОБЫЧНЫМ ЮНИКОДОМ, а не только приватной зоной: «◆ Snow
# Rune I», «✿ Sorrow Boots», «❁ Flawless Jasper Gemstone». Записанная грабля
# проекта (так же обжёгся `gen_stat_forms`): из-за неё развёртка теряла
# 235 заголовков, у которых перевод основы УЖЕ КУПЛЕН.
# ⚠️ Признак по КАТЕГОРИИ Unicode, а не по диапазону: тире и кавычки —
# пунктуация, значком они не являются.
CHECK_MARKS = frozenset("✔✖✓✗")
COUNT_TAIL = re.compile(r"^(.+?)( x\{n\})$")


def is_icon(char: str) -> bool:
    """Символ — ЗНАЧОК Hypixel перед именем предмета."""
    # ⚠️ Знаки чек-листа стоят в той же позиции, но значком НЕ являются:
    # их закрывает `gen_checklist`, а совпадение здесь увело бы строку
    # из его ведения.
    if char in CHECK_MARKS:
        return False
    if unicodedata.category(char).startswith("S") or 0xE000 <= ord(char) <= 0xF8FF:
        return True
    # ⚠️ HYPIXEL БЕРЁТ ПОД ЗНАЧКИ БУКВЫ ЧУЖИХ АЛФАВИТОВ, и категория у них
    # «буква», а не «символ»: части удочки помечены сингальской «ථ» (Hook),
    # чамской «ꨃ» (Line) и тибетской «࿉» (Sinker). Первые две — Lo, поэтому
    # прежний признак их не брал, и заголовок «ථ Hotspot Hook» оставался
    # английским при КУПЛЕННОМ переводе имени.
    # Признак тот же, что в моде (`Paragraphs.isMarkerChar`): буква значит
    # значок, только если её алфавит не латиница и не кириллица. Снятие
    # ничего не решает само — остаток обязан найтись в словаре имён.
    if unicodedata.category(char) in ("Lo", "Lm"):
        try:
            script = unicodedata.name(char).split()[0]
        except ValueError:
            return False
        return script not in ("LATIN", "CYRILLIC")
    return False


def strip_wrappers(title: str) -> tuple[str, str, str]:
    """Снять обёртки: («основа», «что слева», «что справа»).

    ⚠️ Обёрток бывает ДВЕ СРАЗУ («◆ Blood Rune I x{n}»), а прежний цикл брал
    первую подходящую и выходил — вторая оставалась, и основа не находилась.
    """
    head, tail = "", ""
    found = COUNT_TAIL.match(title)
    if found:
        title, tail = found.group(1), found.group(2)
    if title and is_icon(title[0]):
        cut = 2 if len(title) > 1 and title[1] == " " else 1
        head, title = title[:cut], title[cut:]
    return title, head, tail


def seen_titles() -> set[str]:
    """Заголовки предметов, которые ИГРОКИ реально видели."""
    out: set[str] = set()
    dump = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump"
                "/collected.json")
    data = load(dump, {}) or {}
    players = load(PLAYERS, {}) or {}
    # ⚠️ ЗАГОЛОВОК ЧАСТИ УДОЧКИ ПРИХОДИТ В `item_lore`, А НЕ В `item_name`:
    # «ථ Common Hook», «࿉ Junk Sinker» — это первая строка ОПИСАНИЯ, и,
    # читая один `item_name`, развёртка их не видела вовсе. Имя при этом
    # давно переведено, английским оставалась только обёртка со значком.
    for source in ("item_name", "item_lore"):
        out |= set(((data.get("sources") or {}).get(source) or {}))
        rows = players.get(source) if isinstance(players, dict) else None
        if isinstance(rows, dict):
            out |= set(rows)
    return out


def _taken(title: str) -> bool:
    """Строку уже переводит ДРУГОЙ словарь, и не тождественно.

    ⚠️ РУЧНОЙ ПЕРЕВОД СИЛЬНЕЕ МАШИННОЙ ПОДСТАНОВКИ — записанное правило
    проекта. Развёртка читает `item_lore`, а там живут и категории мобов
    (« Ender» -> «Эндерский»), и вычитанные вручную имена
    («▶ L.A.S.R.'s Eye» -> «▶ Око Л.А.З.Е.Р.»). Слепая развёртка давала
    им «Эндер» и «Око L.A.S.R.», то есть РЕГРЕСС.

    Тождественную запись заменять можно и нужно: она означает «перевода
    нет, оставлено как есть», и русское имя её законно улучшает.
    Замер 02.09: берётся 142 формы, отвергается 5 — ровно те, что портили.
    """
    import status  # ленивый: тянет словари
    global _FULL
    if _FULL is None:
        _FULL = status.Dictionaries(groups={"full"})
    found = status.lookup(title, _FULL, origin="item_lore")
    return bool(found and found[0] and found[0] != title)


_FULL = None


def expand_seen_forms(entries: dict[str, str]) -> dict[str, str]:
    """
    Имя в обёртке -> перевод в той же обёртке.

    Разворачиваем ПО ЖИВЫМ СТРОКАМ, а не по всему каталогу: иначе к каждому
    из шести тысяч имён добавилась бы пара выдуманных вариантов, а словарь
    и так самый крупный в моде.
    """
    out: dict[str, str] = {}
    for title in seen_titles():
        if title in entries:
            continue
        # ⚠️ СПЕРВА общий путь: снимаем счётчик и значок (их бывает ДВА сразу),
        # и только если он не сработал — прежние точечные обёртки.
        base, head, tail = strip_wrappers(title)
        if (head or tail) and entries.get(base) and not _taken(title):
            out[title] = head + entries[base] + tail
            continue
        for pattern, shape in WRAPPERS:
            found = pattern.match(title)
            if not found:
                continue
            head, tail = "", ""
            if shape.startswith("{ru}"):
                base, tail = found.group(1), found.group(2)
            else:
                head, base = found.group(1), found.group(2)
            translated = entries.get(base)
            if not translated:
                continue
            out[title] = shape.format(ru=translated, head=head, tail=tail)
            break
    return out


def _close(left: str, right: str, limit: int = 2) -> bool:
    """Строки отличаются не больше чем на `limit` правок (расстояние Дамерау)."""
    if abs(len(left) - len(right)) > limit:
        return False
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (a != b)))
        if min(current) > limit:
            return False
        previous = current
    return previous[-1] <= limit


def do_write() -> int:
    """Собрать словарь режима из заготовки."""
    data = load(SKELETON, {})
    names = {k: v for k, v in data.get("names", {}).items() if v}
    if not names:
        print("переведённых имён нет — писать нечего")
        return 1

    # ⚠️ Семьи с уровнем разворачиваются в точные записи — правил в словаре
    # нет вовсе. Подробности в expand_families.
    catalog = catalog_names()
    expanded, missing = expand_families(names, catalog)
    entries = dict(names)
    entries.update(expanded)

    # Обёртки с экрана (счётчик стопки, значок слева) — по живым строкам.
    wrapped = expand_seen_forms(entries)
    entries.update(wrapped)

    # ⚠️ ДВА РАЗНЫХ ПРЕДМЕТА С ОДНИМ ПЕРЕВОДОМ — беда, а не мелочь: игрок
    # ищет вещь по имени, и два «Мифриловых плаща» в базаре неразличимы.
    # Поймано на живых данных сразу же: Mithril Coat и Mithril Cloak.
    # ⚠️ …но ОДНА И ТА ЖЕ вещь в двух написаниях — не беда, а опечатка
    # СЕРВЕРА, и переводы у неё обязаны совпадать. Живой случай: в каталоге
    # Hypixel лежит «Saphhire Crystal», а на экране встречается «Sapphire
    # Crystal». Развести их значило бы выдумать второй самоцвет.
    # Признак от данных: имена отличаются не больше чем на две правки.
    # ⚠️ Признаков ДВА, и по отдельности каждый врёт. Расстояние 1 разрешает
    # и «Golden Fish» против выдуманного «Golden Dish»; а «в каталоге только
    # одно из имён» само по себе бывает у совсем разных вещей. Порог именно
    # ОДНА правка: у записанной беды «Mithril Coat» / «Mithril Cloak» их две,
    # и она обязана ловиться по-прежнему.
    catalog_set = set(catalog)

    def same_thing(names: list[str]) -> bool:
        if sum(1 for n in names if n in catalog_set) == len(names):
            return False
        first = names[0].lower()
        return all(_close(first, other.lower(), 1) for other in names[1:])

    back: dict[str, list[str]] = {}
    for english, russian in entries.items():
        back.setdefault(russian, []).append(english)
    clashes = {ru: ens for ru, ens in back.items()
               if len(ens) > 1 and not same_thing(ens)}
    if clashes:
        print(f"⚠️ ОДИН ПЕРЕВОД У РАЗНЫХ ИМЁН: {len(clashes)}")
        for russian, english in sorted(clashes.items())[:10]:
            print(f"   {russian!r} <- {english}")
        print("   разведи их, иначе вещи неразличимы по имени")
        return 1

    # ⚠️ Базы, которых ещё нет: варианты с уровнем останутся английскими.
    # Печатаем ЧЕСТНО — молчаливый пропуск читается как «всё переведено».
    if missing:
        bases = sorted({family_base(name) for name in missing})
        print(f"⚠️ не развернулось {len(missing)} имён — нет перевода базы:")
        for base in bases[:10]:
            print(f"   {base}")
        if len(bases) > 10:
            print(f"   ... и ещё {len(bases) - 10}")

    pack = {
        "id": "item_names",
        "priority": 61,
        "default": False,
        "group": "full",
        "about": "названия предметов SkyBlock (Hyperion -> Гиперион). "
                 "По умолчанию выключено: по английскому названию вещь ищут "
                 "на аукционе и в гайдах",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_item_names.py из "
                    "data/work/item_names_ru.json — правь заготовку, а не этот файл. "
                    "ПРАВИЛ ЗДЕСЬ НЕТ НАМЕРЕННО (решение игрока 22.08): семьи "
                    "с уровнем («Oak Minion I … XII») развёрнуты в точные записи. "
                    "Правило с tg опирается на догадку «захват совпадёт с ключом», "
                    "и промах виден только в игре; точная запись не нашлась — "
                    "строка честно уходит в дамп. "
                    "Область только item_name: имя предмета стоит ЗАГОЛОВКОМ "
                    "подсказки, и там его перевод виден сразу.",
        # ⚠️ item_lore ТОЖЕ, и это не расширение «на всякий случай». Имя вещи
        # стоит отдельной СТРОКОЙ и внутри описаний: «Power stone:» / «Ender
        # Monocle», списки наград, витрины. Точная запись срабатывает только
        # на строку ЦЕЛИКОМ, поэтому в прозу она не лезет и падежа не требует —
        # проза остаётся слоем B. Замер по дампу: 1849 строк описания РАВНЫ
        # имени предмета, а спорных (где перевод уже есть другой) — 13,
        # и все они решаются в пользу прежнего словаря: у него priority меньше.
        # ⚠️ ЗАМЕР 23.08: перевод КУПЛЕН, а область его не пускала.
        # Имя стоит ОТДЕЛЬНОЙ строкой и в заголовке кнопки (`menu_title`),
        # и на экране (`screen`), и над стендом с товаром (`name_tag`) —
        # это тот же случай, под который область и задумана. Проверено
        # на конфликт: пересечение ключей с `82-npc-places` — 38, и у всех
        # 38 перевод СОВПАДАЕТ; с `85-mob-names` пересечения нет вовсе.
        "only": ["item_name", "item_lore", "menu_title", "screen",
                 "name_tag"],
        "exact": dict(sorted(entries.items())),
    }
    save(PACK, pack)
    print(f"записано {PACK.name}: {len(entries)} записей "
          f"(из них развёрнуто из семей: {len(expanded)})")
    print("⚠️ впиши файл в packs/index.json, иначе он молча не загрузится")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeleton", action="store_true", help="завести/пополнить заготовку")
    parser.add_argument("--export", metavar="FILE", help="выгрузить пачку на перевод")
    parser.add_argument("--load", metavar="FILE", help="влить переведённую пачку")
    parser.add_argument("--write", action="store_true", help="собрать словарь")
    parser.add_argument("--limit", type=int, default=200, help="сколько имён в пачке")
    args = parser.parse_args()

    if args.skeleton:
        return do_skeleton()
    if args.export:
        return do_export(Path(args.export), args.limit)
    if args.load:
        return do_load(Path(args.load))
    if args.write:
        return do_write()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
