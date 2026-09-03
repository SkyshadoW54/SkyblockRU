# -*- coding: utf-8 -*-
"""
Надписи над существами для РЕЖИМА ПОЛНОГО ПЕРЕВОДА:
«[Lv{n}] Sheep» -> «[Ур. {n}] Овца».

⚠️ ЗАМЕР, ради которого это делается: 604 разных существа, 20 091 показ —
вторая по величине семья непереведённого после хвоста прокачки.

⚠️ РАЗВЁРТКА ПО ЖИВЫМ СТРОКАМ, а не правилом. Правило («[Lv{n}] X» с tg)
опирается на догадку, что захват совпадёт с ключом словаря, и промах виден
только в игре. Хуже того: совпавшее правило гасит запись строки в дамп,
и непереведённое существо стало бы невидимым для отчётов. Точная запись
такого не умеет — не нашлась, строка честно уходит в дамп.

⚠️ ВАНИЛЬНЫМ СУЩЕСТВАМ ПЕРЕВОД НЕ ПИШЕМ: отдаём @ключ, и имя подставляет
сам клиент игрока. Так оно совпадает с тем, что человек видит в одиночной
игре, и меняется вместе с языком клиента. Тот же приём, что у предметов.

    python tools/gen_mob_names.py --skeleton   заготовка из живых строк
    python tools/gen_mob_names.py --export FILE --limit 200
    python tools/gen_mob_names.py --load FILE
    python tools/gen_mob_names.py --write      собрать 85-mob-names.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gen_reforges  # noqa: E402  формы прилагательного и список родов

# ⚠️ Консоль Windows — cp1251, и `print` со значком «⚠️» роняет скрипт
# на первой же находке. Записанная грабля проекта: инструмент, падающий
# на печати, ВРЁТ О СВОЕЙ РАБОТЕ — вывод оборван, а выглядит как поломка
# того, что он проверял. У сторожа это хуже вдвое: он молчит, пока всё
# хорошо, и ломается ровно тогда, когда нашёл беду.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

SKELETON = WORK / "mob_names_ru.json"
PACK = PACKS / "ru_ru" / "85-mob-names.json"
PLAYERS = WORK / "from_players.json"

# «[Lv12] Sheep», «[Lvl 100] Bee» — метка уровня, дальше имя существа.
# ⚠️ СКОБОК МОЖЕТ НЕ БЫТЬ: над мобами подземелий Hypixel пишет «Lv{n} X»,
# а над мобами слееров метки нет вовсе — только полоса здоровья. Пока
# признак требовал скобок, 880 надписей не видел ни сбор, ни развёртка.
# ⚠️ ДИАПАЗОН УРОВНЕЙ: в меню питомцев Hypixel пишет «[Lvl 1 ➡ 100] Bee» —
# это фильтр «от и до», а не надпись над головой. Замер 26.08: 213 строк
# одной семьи, и ни одна не переводилась, хотя «[Lvl {n}] Bee» закрыта
# давно. Стрелок ДВЕ (U+27A1 и U+2192) — берём обе, как их шлёт сервер.
HEAD = re.compile(r"^(?:\[Lvl? ?\{n\}(?: ?[➡→] ?\{n\})?\]|Lvl? ?\{n\})\s*")
# Хвост: полоса здоровья и звезда питомца. Снимаем, чтобы имя было именем.
# Хвост: полоса здоровья (с суффиксами k/M/B), сердце, звезда питомца
# и знак «✯» у боссов. Снимаем, чтобы имя было именем.
TAIL = re.compile(r"(?:\s*\{n\}[kMB]?/\{n\}[kMB]?\s*❤?"
                  r"|\s*❤|\s*✦|\s*✯|\s*\{n\}[kMB]?)+\s*$")

# ⚠️ ОСТАТОК §-КОДА, приклеившийся к имени: «aCorrupted Sprawla» — это
# «§aCorrupted Sprawl§a», у которого потерялись сами «§». Строки приходят
# такими ОТ ИГРОКОВ, то есть портятся ещё при сборе; переводить их как есть
# значило бы завести в словаре несуществующие имена.
STUCK_CODE = re.compile("^([0-9a-fk-or])(.+)" + chr(92) + "1$")

# Редкость питомца в скобках — не часть имени: «Banshee (RARE)».
RARITY = re.compile(r" \((?:COMMON|UNCOMMON|RARE|EPIC|LEGENDARY|MYTHIC|SPECIAL|DIVINE|ULTIMATE)\)$")
# Значок типа существа стоит ПЕРЕД именем и относится к нему, а не к тексту.
# ⚠️ ЗНАЧКИ БЫВАЮТ ОБЫЧНЫМ ЮНИКОДОМ: «✯» у элитных, «☠» у боссов слеера,
# «⚝» у мини-боссов. Приватной зоной признак ограничивать нельзя —
# на этом 114 надписей с «✯» уезжали в заготовку вместе со значком,
# то есть заводили несуществующее имя существа.
MARK = re.compile("^((?:[" + chr(0xE000) + "-" + chr(0xF8FF) + "]|[✯☠⚝⚔]|\\[[^]]*\\]|\\s)+)")
# Рамка вокруг имени босса: «﴾ Magma Boss ﴿». Тоже обрамление.
FRAME = re.compile("^[﴾\\s]+|[﴿\\s]+$")
# Полоса здоровья босса рисуется блоками: «Magma Boss ███████».
BAR = re.compile(r"\s*█+\s*$")
# ⚠️ item_name и item_lore тоже: питомец в инвентаре подписан так же
# («[Lvl 100] Sheep ✦»), и без этих областей он остаётся английским.
# ⚠️ `boss_bar` тоже: имя босса Hypixel пишет и в полосе сверху
# (« ☠ Revenant Horror I {n}❤», «Wise Dragon»), и без этой области
# оно оставалось английским при готовом переводе.
AREAS = ("name_tag", "screen", "chat", "tab", "scoreboard",
         "item_name", "item_lore", "menu_title", "boss_bar")


# Имя цвета -> §-код. Иначе разметку не собрать: мод пишет цвета словами.
CODES = {
    "black": "0", "dark_blue": "1", "dark_green": "2", "dark_aqua": "3",
    "dark_red": "4", "dark_purple": "5", "gold": "6", "gray": "7",
    "dark_gray": "8", "blue": "9", "green": "a", "aqua": "b",
    "red": "c", "light_purple": "d", "yellow": "e", "white": "f",
}

# ⚠️ ЦВЕТА БЕРЁМ ИЗ ДАННЫХ, А НЕ «КРАСИМ ВСЁ КРАСНЫМ». Замер по собранным
# надписям: из 30 имён красных 9, ЗОЛОТЫХ 12, белых 3, плюс синие,
# фиолетовые и зелёные. Правило «имя моба красное» испортило бы две трети —
# ровно как записанная грабля про цвет значка, где устойчивых оказалась
# лишь треть.
PANEL_COLORS = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru"
                    "/dump/panel-colors.json")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def marked_lines() -> dict[str, list]:
    """Раскладка цветов по строкам надписей — ключом служит тот же шаблон."""
    data = load(PANEL_COLORS, {}) or {}
    out: dict[str, list] = {}
    for case in data.get("cases", []):
        if case.get("source") != "name_tag":
            continue
        out.setdefault(case["key"], case.get("pieces") or [])
    return out


def colorize(pieces: list, english: str, russian: str, key: str = "") -> str | None:
    """Собрать размеченный перевод: цвета кусков из данных, имя — русское.

    ⚠️ Числа в кусках ЖИВЫЕ («Lv60», «45,000»), а ключ обобщён — поэтому
    после склейки обобщаем их обратно. Иначе запись не совпала бы ни разу.
    """
    parts, replaced = [], False
    for colour, text in pieces:
        if english and english in text and not replaced:
            text = text.replace(english, russian, 1)
            replaced = True
        # ⚠️ ОБОБЩАЕМ ТЕКСТ КУСКА, а не готовую строку: цифра §-кода для
        # регулярки чисел неотличима от числа, и «§8[» превращалось в «§{n}[».
        # Записанная грабля проекта — 191 шаблон из 850 однажды так и умер.
        text = NUMBER.sub("{n}", text)
        code = CODES.get(colour)
        parts.append(("§" + code if code else "") + text)
    if not replaced:
        return None
    built = "".join(parts)
    # ⚠️ СВЕРЯЕМ СКЛЕЙКУ С КЛЮЧОМ. Разбор кусков теряет пробел после имени
    # («Golden Ghoul» + «45,000» вместо «Golden Ghoul 45,000»), и без сверки
    # имя слиплось бы с числом прямо на экране. Проверка заодно ловит любое
    # другое расхождение: не сошлось — не размечаем вовсе.
    if key:
        plain = NUMBER.sub("{n}", "".join(text for _c, text in pieces))
        if plain != key:
            fixed = plain.replace(english, english + " ", 1)
            if fixed != key:
                return None
            built = built.replace(russian, russian + " ", 1)
    return built


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def vanilla_keys() -> dict[str, str]:
    """Английское имя существа -> ключ локализации Minecraft."""
    import gen_vanilla_names as gv
    jar = gv.find_client_jar()
    if not jar:
        return {}
    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            if name.endswith("assets/minecraft/lang/en_us.json"):
                lang = json.loads(archive.read(name))
                break
        else:
            return {}
    return {value: key for key, value in lang.items()
            if key.startswith("entity.minecraft.") and isinstance(value, str)}


# Полоса здоровья над мобом: «{n}k/{n}k❤», «{n}M❤», «{n}/{n}».
#
# ⚠️ ТОЛЬКО В КОНЦЕ СТРОКИ. Сердце «❤» встречается и в описаниях способностей
# («- Heal {n}❤ when hit»), и в подписях характеристик («❤ Health: {n}»),
# а надпись над существом им КОНЧАЕТСЯ. Без этой оговорки в заготовку имён
# уехало 97 кусков лора.
#
# ⚠️ Проверять «начинается с Health» НЕЛЬЗЯ: под это подходит законный префикс
# подземелья «Healthy Crypt Lurker». Признак по написанию снова поймал бы своё
# же — записанная грабля проекта.
# ⚠️ После сердца бывает ещё значок: « ☠ Voidgloom Seraph IV {n}M❤ ✯» —
# звезда элиты стоит ПОСЛЕДНЕЙ. Хвост допускаем, иначе надпись не узнаётся.
HEALTH = re.compile(r"(?:\{n\}[kMB]?/\{n\}[kMB]?|\{n\}[kMB]?)\s*❤\s*[✯✦⚝]?\s*$"
                    r"|\{n\}[kMB]?/\{n\}[kMB]?\s*[✯✦⚝]?\s*$"
                    r"|❤\s*[✯✦⚝]?\s*$")


def mob_lines() -> dict[str, int]:
    """
    Живые надписи над существами и сколько игроков их видели.

    ⚠️ ПРИЗНАКА ДВА, и одного мало. Метка уровня («[Lv {n}]») есть у питомцев
    и у мобов открытого мира, а над мобами подземелий и слееров её нет вовсе —
    там только полоса здоровья: «Healthy Guardian {n}k❤», «☠ Voidgloom Seraph
    IV {n}M❤». Пока сбор требовал метку, 880 надписей не видел никто: ни
    заготовка, ни развёртка.

    ⚠️ ИСТОЧНИКОВ ТОЖЕ ДВА. Строки от игроков покрывают ходовое, а рамка
    босса («﴾  Bonzo {n}k❤ ﴿») и мобы редких этажей есть только в НАШЕМ
    дампе. Пока читался один файл, такие формы в словарь не попадали —
    имя переведено, а надпись на экране английская.
    """
    out: dict[str, int] = {}
    sources = [load(PLAYERS, {})]
    try:
        import make_queue
        sources.append(make_queue.load("collected.json").get("sources") or {})
    except Exception:            # дампа нет — работаем на том, что прислали
        pass
    for data in sources:
        if not isinstance(data, dict):
            continue
        for area in AREAS:
            block = data.get(area)
            if not isinstance(block, dict):
                continue
            for line, seen in block.items():
                # ⚠️ РАМКУ СНИМАЕМ ДО ПРОВЕРКИ. У босса надпись кончается
                # не сердцем, а закрывающей скобкой («﴾ Bonzo {n}❤ ﴿»), и
                # признак «полоса здоровья в конце» её не узнавал: 45 надписей
                # боссов не попадали ни в заготовку, ни в словарь.
                text = FRAME.sub("", line.strip())
                if HEAD.match(text) or HEALTH.search(text):
                    number = seen if isinstance(seen, int) else 1
                    out[line] = max(out.get(line, 0), number)
    return out


def lines_with_level() -> dict[str, int]:
    """Прежнее имя: остаётся, чтобы не ломать чужие вызовы."""
    return mob_lines()


def name_of(line: str) -> tuple[str, str]:
    """Имя существа из строки. Второе значение — значок типа, если он был."""
    rest = FRAME.sub("", line.strip())
    icon = ""
    # ⚠️ Обрамление идёт СЛОЯМИ и в разном порядке: «✯ Lv{n} Zombie», «[Lv{n}] ✯ Bee».
    # Снимаем по кругу, пока снимается, — иначе половина имён уезжает со значком.
    for _ in range(3):
        rest = HEAD.sub("", rest.strip())
        mark = MARK.match(rest)
        if mark:
            icon = icon or mark.group(1)
            rest = rest[len(mark.group(1)):]
    rest = RARITY.sub("", rest).strip()
    rest = BAR.sub("", rest).strip()
    rest = TAIL.sub("", rest).strip()
    # Руна ᛤ у элитных существ — тоже обрамление, а не часть имени.
    rest = rest.rstrip().removesuffix(chr(0x16E4)).strip()
    stuck = STUCK_CODE.match(rest)
    if stuck and stuck.group(2)[:1].isupper():
        rest = stuck.group(2)
    return rest.strip(), icon


# ⚠️ ПРЕФИКСЫ ПОДЗЕМЕЛИЙ — КОМБИНАТОРИКА, а не 216 отдельных имён. Hypixel
# вешает на моба модификатор («Healthy Guardian», «Speedy Zombie Knight»),
# и основа у него та же. Замер 23.08: девять префиксов дают 216 имён, и у ВСЕХ
# основа уже лежит в заготовке — то есть перевод основы закрывает и связку.
#
# ⚠️ Формы берутся у перековок (`gen_reforges.forms_from`), а не пишутся заново:
# правила русского прилагательного одни и те же, а вторая копия однажды
# разошлась бы. Род основы выводим по её ПЕРЕВОДУ — как `Reforge.compose`.
PREFIXES = {
    "Healthy": "Здоровый",
    "Stormy": "Грозовой",
    "Speedy": "Быстрый",
    "Healing": "Исцеляющий",
    "Flaming": "Пылающий",
    "Fortified": "Укреплённый",
    "Boomer": "Взрывной",
    "Golden": "Золотой",
    "Stealth": "Скрытный",
    # ⚠️ Добавлено 26.08 по замеру: «Corrupted» даёт 69 строк, и у 58
    # основ из 59 перевод УЖЕ есть — то есть развёртка почти бесплатна.
    # Слова взяты по БОЛЬШИНСТВУ купленного, а не на вкус: «Испорченный»
    # 121 запись, «Замороженный» 16 против «Замёрзший» 10.
    "Corrupted": "Испорченный",
    "Blessed": "Благословенный",
    "Frozen": "Замороженный",
}


def is_mob_name(name: str) -> bool:
    """
    Имя существа это или подпись со значением.

    ⚠️ Признак сбора («полоса здоровья в конце») ловит и статистику подземелья:
    «Team Damage Dealt: {n}B❤», «Stored: {n}/{n}». Отличает их ДВОЕТОЧИЕ —
    у надписи над существом его не бывает, а подпись им и кончается.
    """
    text = name.strip()
    return bool(text) and not text.endswith(":") and not text.startswith("-")


def gender_of(russian: str) -> int:
    """
    Род по первому слову перевода: 0 мужской, 1 женский, 2 средний, 3 мн. ч.

    ⚠️ МЯГКИЙ ЗНАК РОДА НЕ ВЫДАЁТ («слизь» женского, «трюфель» мужского),
    поэтому список исключений ЯВНЫЙ и берётся у перековок — своей копии
    не заводим, иначе они разойдутся при первом пополнении.
    """
    head = russian.split()[0].lower().strip("«»\"',.") if russian.split() else ""
    for gender, words in gen_reforges.GENDERS.items():
        if head in words:
            return {"f": 1, "n": 2}.get(gender, 0)
    # ⚠️ У дефисного имени род задаёт ПЕРВАЯ часть: «Крестьянин-зомби» мужской,
    # а по хвосту «зомби» признак решал иначе.
    head = head.split("-")[0]
    # ⚠️ ПРИЗНАКА «-и значит множественное» ЗДЕСЬ НЕТ, и это замер, а не вкус:
    # он давал мн. ч. пятерым — «Зомби», «Банши», «Йети», «Гризли»,
    # «Крестьянин-зомби», — а все они несклоняемые мужского рода. Настоящего
    # множественного среди имён существ не встретилось ни разу.
    if head.endswith(("а", "я")):
        return 1
    if head.endswith(("о", "е")):
        return 2
    return 0


def with_prefix(english: str, names: dict[str, str]) -> str | None:
    """Перевод имени с префиксом подземелья, собранный из основы."""
    for prefix, male in PREFIXES.items():
        if not english.startswith(prefix + " "):
            continue
        base = english[len(prefix) + 1:]
        russian = names.get(base)
        if not russian:
            return None
        forms = gen_reforges.forms_from(male)
        # ⚠️ У ВАНИЛЬНОГО имени в значении стоит @ключ, и род по нему не виден.
        # Но он виден в ЛОКАЛИЗАЦИИ КЛИЕНТА: «guardian» -> «Страж» (м.),
        # «sheep» -> «Овца» (ж.). Род берём оттуда, а само имя оставляем
        # ключом — пусть подставляет клиент, как и решено для ванильных.
        if russian.startswith("@"):
            import status
            plain = status.vanilla_lang().get(russian[1:].split()[0], "")
            if not plain:
                return None
            return forms[gender_of(plain)] + " " + russian
        return forms[gender_of(russian)] + " " + russian[0].lower() + russian[1:]
    return None


def do_skeleton() -> int:
    old = load(SKELETON, {}) or {}
    ready = old.get("names", {})
    asis = set(old.get("_asis", []))
    vanilla = vanilla_keys()

    seen: dict[str, int] = {}
    for line, count in mob_lines().items():
        name, _icon = name_of(line)
        if is_mob_name(name):
            seen[name] = seen.get(name, 0) + count

    fresh: dict[str, dict] = {}
    auto = 0
    ready_names = {k: (v.get("ru") if isinstance(v, dict) else v)
                   for k, v in ready.items()}
    ready_names = {k: v for k, v in ready_names.items() if v}
    by_prefix = 0
    for name in sorted(seen, key=lambda n: (-seen[n], n)):
        if name in asis:
            continue
        was = ready.get(name, {})
        value = was.get("ru", "") if isinstance(was, dict) else was
        if not value and name in vanilla:
            # ⚠️ Не переводим сами: @ключ отдаёт имя клиенту игрока.
            value = "@" + vanilla[name]
            auto += 1
        # ⚠️ Имя с ПРЕФИКСОМ подземелья в список работы не берём: его соберёт
        # развёртка из основы. Иначе «Healthy Guardian», «Speedy Guardian»
        # и «Stormy Guardian» просились бы поштучно — 216 записей на девять
        # прилагательных.
        if not value and with_prefix(name, ready_names):
            by_prefix += 1
            continue
        fresh[name] = {"ru": value, "seen": seen[name]}

    save(SKELETON, {
        "_comment": "Имена существ для режима полного перевода. ИСТОЧНИК "
                    "ПРАВДЫ — этот файл, словарь 85-mob-names.json собирается "
                    "из него. Значение, начинающееся с @, — ключ локализации "
                    "Minecraft: имя подставит сам клиент. Порядок — по числу "
                    "игроков, видевших существо.",
        "_asis": sorted(asis),
        "names": fresh,
    })
    done = sum(1 for row in fresh.values() if row["ru"])
    print(f"существ: {len(fresh)}, переведено {done}, ждут {len(fresh) - done}")
    if auto:
        print(f"  ванильных закрыто @ключом (перевод даст клиент): {auto}")
    if by_prefix:
        print(f"  закрыто развёрткой префикса подземелья: {by_prefix}")
    top = [n for n, r in fresh.items() if not r["ru"]][:10]
    print("  верхушка:", ", ".join(top))
    return 0


def do_export(path: Path, limit: int) -> int:
    data = load(SKELETON, {}) or {}
    task = [{"en": name, "ru": "", "_seen": row["seen"]}
            for name, row in data.get("names", {}).items() if not row["ru"]][:limit]
    save(path, task)
    print(f"выгружено {len(task)} имён -> {path}")
    return 0


def foreign(text: str) -> list[str]:
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
    data = load(SKELETON, {}) or {}
    names = data.get("names", {})
    asis = set(data.get("_asis", []))

    taken, marked, refused = 0, 0, []
    for row in task:
        value = (row.get("ru") or "").strip()
        key = row.get("en", "")
        if not value:
            continue
        if key not in names:
            refused.append(f"{key!r}: НЕ НАЙДЕНО в заготовке")
            continue
        if value == "-":
            asis.add(key)
            names.pop(key, None)
            marked += 1
            continue
        bad = foreign(value)
        if bad:
            refused.append(f"{key!r}: чужая письменность {bad}")
            continue
        if value == key:
            refused.append(f"{key!r}: перевод совпал с оригиналом — ставь «-»")
            continue
        names[key]["ru"] = value
        taken += 1

    data["names"], data["_asis"] = names, sorted(asis)
    save(SKELETON, data)
    print(f"влито {taken} из {len(task)}"
          + (f", помечено «переводить нечего»: {marked}" if marked else ""))
    for line in refused[:20]:
        print(f"   {line}")
    return 0


def do_write() -> int:
    data = load(SKELETON, {}) or {}
    names = {k: v["ru"] for k, v in data.get("names", {}).items() if v.get("ru")}
    if not names:
        print("переведённых имён нет — писать нечего")
        return 1

    # ⚠️ Разворачиваем ровно те строки, что РЕАЛЬНО приходили: значок типа,
    # полоса здоровья и звезда питомца бывают в разных сочетаниях, и гадать
    # об их наборе незачем — он есть в данных.
    entries: dict[str, str] = {}
    missing: set[str] = set()
    colours = marked_lines()
    coloured = 0
    for line in mob_lines():
        name, _icon = name_of(line)
        if not is_mob_name(name):
            continue
        russian = names.get(name) or with_prefix(name, names)
        if not russian:
            missing.add(name)
            continue
        # «[Lv{n}]» -> «[Ур. {n}]»: метка уровня, она же принята у питомцев.
        # ⚠️ Скобок может не быть («Lv{n} Crypt Ghoul»), а у мобов слееров
        # метки нет вовсе — тогда меняем только имя.
        found = HEAD.match(line.strip())
        plain = line
        if found:
            head = found.group(0)
            # ⚠️ МЕТКУ СТРОИМ ИЗ САМОЙ СТРОКИ, а не жёсткой заготовкой:
            # у метки бывает ДИАПАЗОН («[Lvl 1 ➡ 100] Bee» в меню питомцев),
            # и заготовка «[Ур. {n}] » молча его теряла — на экране вышло бы
            # «[Ур. 1] Пчела» вместо «[Ур. 1 ➡ 100] Пчела», то есть фильтр
            # показывал бы не тот диапазон. Задето 213 строк одной семьи.
            russian_head = re.sub(r"Lvl ?", "Ур. ", head)
            russian_head = re.sub(r"Lv ?", "Ур. ", russian_head)
            russian_head = re.sub(r"Ур\. +", "Ур. ", russian_head)
            # ⚠️ СОБИРАЕМ ЯВНО, а не поиском подстроки: `head` взят
            # из `line.strip()`, и у строки с ведущим пробелом replace
            # промахивался МОЛЧА — метка оставалась английской.
            stripped = line.strip()
            plain = russian_head + stripped[len(head):]
        plain = plain.replace(name, russian, 1)
        # ⚠️ ЕСЛИ ЦВЕТА СОБРАНЫ — кладём РАЗМЕЧЕННЫЙ перевод. Иначе цвет имени
        # теряется: механика возврата красит куски, уцелевшие ДОСЛОВНО, а имя
        # переведено. Цвета берутся из данных, а не назначаются: замер по
        # собранным надписям — красных имён 9, ЗОЛОТЫХ 12, есть белые, синие
        # и фиолетовые. «Красить всё красным» испортило бы две трети.
        marked = colours.get(line)
        if marked:
            painted = colorize(marked, name, russian, line)
            if painted:
                # ⚠️ Метку уровня в размеченной строке заменяем ПО СЛОВУ:
                # между «[» и «Lv» стоит §-код, и замена «[Lv{n}]» целиком
                # не совпала бы ни разу — та же грабля, что со значком рядом с кодами.
                painted = painted.replace("Lvl ", "Ур. ", 1).replace("Lv", "Ур. ", 1)
                entries[line] = painted
                coloured += 1
                continue
        entries[line] = plain

    pack = {
        "id": "mob_names",
        "priority": 64,
        "default": False,
        "group": "full",
        "about": "имена существ в надписях над головой "
                 "([Lv 12] Sheep -> [Ур. 12] Овца). По умолчанию выключено",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_mob_names.py из "
                    "data/work/mob_names_ru.json — правь заготовку. "
                    "Записи РАЗВЁРНУТЫ по живым строкам: значок типа, полоса "
                    "здоровья и звезда питомца бывают в разных сочетаниях. "
                    "Правилом это делать нельзя — совпавшее правило гасит "
                    "запись строки в дамп, и непереведённое существо стало бы "
                    "невидимым для отчётов.",
        "only": list(AREAS),
        "exact": dict(sorted(entries.items())),
    }
    save(PACK, pack)
    print(f"записано {PACK.name}: {len(entries)} записей "
          f"({len(names)} имён существ, с ЦВЕТОМ {coloured})")
    if missing:
        print(f"⚠️ без перевода осталось имён: {len(missing)}")
        for name in sorted(missing)[:10]:
            print(f"   {name}")
    print("⚠️ впиши файл в packs/index.json, иначе он молча не загрузится")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeleton", action="store_true")
    parser.add_argument("--export", metavar="FILE")
    parser.add_argument("--load", metavar="FILE")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
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
