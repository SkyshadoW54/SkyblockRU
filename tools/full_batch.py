# -*- coding: utf-8 -*-
"""Следующая пачка строк на РУЧНОЙ перевод для режима full.

    python tools/full_batch.py            60 строк по частоте
    python tools/full_batch.py --size 80  другой размер

⚠️ ОТБОР ВЫЧИТАЕТ ВСЁ, ЧТО РАБОТОЙ НЕ ЯВЛЯЕТСЯ, и каждый вычет — записанная
грабля проекта:
  * ГЛОССАРИЙ. `status.lookup` его НЕ ЗОВЁТ, а движок зовёт: списки зачарований
    («Cleave V, Critical VI, Cubism V») в игре переводятся. Без этой проверки
    отбор звал работой 369 уже закрытых строк.
  * МЕХАНИКА МОДА. Перековки и звёзды прокачки собирает `Reforge.compose`
    по NBT — в словаре такого ключа нет и быть не может.
  * ОБРЫВКИ ПЕРЕНОСА. У них нет своего смысла, покупать вредно — лечатся
    переводом абзаца. Держатся отдельным списком `_fragments`.
  * КОМАНДЫ и ЧУЖАЯ РЕКЛАМА («/warp hub», «/visit prtl{n} - Online Hub»).

⚠️ Значки маскируются в `{i1}`: из терминала они копируются ПРОБЕЛОМ, и без
масок ключ не совпадёт ни разу. Ключ для вливания берётся из файла пачки,
а не из напечатанного списка.
"""
import argparse
from collections import Counter
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import status  # noqa: E402
import check_nicknames  # noqa: E402
from translate_tooltips import mask_icons  # noqa: E402

WORK = ROOT / "data" / "work"
TODO = WORK / "_full_todo.json"
SRC = WORK / "full_strings.json"
CYR = re.compile("[а-яА-ЯёЁ]")
AT = re.compile(r"@[a-z]|⟨из игры")
STARS = re.compile(r"[✪✦➊-➓⚚✧]")
CMD = re.compile(r"/(warp|visit|is|hub|ah|bz|pets|sbmenu|home|quests|craft|chapters|reclaim|help|tp)", re.I)
AD = re.compile(r"/visit|feat\.|Click|#\{n\}|\[v\{n\}\]|\|\|\|")
JUNK = re.compile(r"^[\s{}\dnsk/,.:%()|-]+$")
# ⚠️ РИМСКИЕ ЦИФРЫ ОДИНАКОВЫ НА ЛЮБОМ ЯЗЫКЕ, и строка из них одних — не работа:
# «I ➡ II», «III➜IV», «VII!» — это повышение уровня, переводить там нечего.
# Записанное решение проекта («113 строк семей — не работа вовсе»), но признак
# жил в `pick_queue`, а сюда его не перенесли: 26.08 такие строки занимали
# по три места в каждой пачке ручного перевода.
ROMAN_ONLY = re.compile(r"^[IVXLC\s.,!➡➜→\-]+$")
# ⚠️ ТЕХНИЧЕСКИЙ ИДЕНТИФИКАТОР («minecraft:oak_log», «send:lobby») — не текст,
# а служебная строка, которую Hypixel показывает как есть. Переводить её нельзя
# ни в каком режиме: по ней игра ищет предмет. Замер 26.08: 33 штуки в списке
# работы, по десятку на пачку.
TECH_ID = re.compile(r"^[a-z_]+:[a-z0-9_/.]+$")
# ⚠️ НАБОР ЗАЧАРОВАНИЙ — КОМБИНАТОРИКА, покупать его нельзя. Строка склеивается
# из того, что стоит на предмете: «Caster VI, Charm V, Expertise X» — один ключ,
# «Caster VI, Charm V, Corruption V» — уже другой, и таких столько, сколько
# игроки собрали. Замер 26.08: 1134 строки в списке работы, а непереведённых
# ИМЁН внутри них — восемь. То есть 1134 строки стоят перевода 8 зачарований,
# и переводить надо ИМЯ (заготовка `data/work/enchants.json`), а не набор.
# Записанное решение проекта («наборов бесконечно много»), просто отбор о нём
# не знал и отдавал по десятку таких строк в каждую пачку.
ENCH_ITEM = re.compile(r"^[A-Z][A-Za-z'\- ]*\s[IVXLC]{1,6}$")


def is_enchant_set(line: str) -> bool:
    """Строка — список зачарований через запятую."""
    parts = [p.strip() for p in line.split(",")]
    return len(parts) >= 2 and all(ENCH_ITEM.match(p) for p in parts)
LATWORD = re.compile(r"(?<![A-Za-z])[A-Za-z]{3,}")


# Источники, где Hypixel подписывает ГОЛОВУ ИГРОКА: список посетителей,
# таб, экран выбора. Ник там стоит строкой целиком.
NICK_SOURCES = {"item_name", "tab", "screen"}
# «Visit popgrain», «To: BoriBori{n}» — подписи кнопок с чужим ником.
NICK_FORM = re.compile(r"^(Visit|To:|From:) [A-Za-z_][A-Za-z0-9_]*( \(More\.\.\.\))?$")
# ⚠️ СПИСОК ИГРОКОВ: «- Wartder», «- T_a_m_a_k_i» — гости острова и участники
# кооператива. Форма та же, что у пункта списка («- Ores», «- Drill»), поэтому
# одного шаблона мало: ник опознаётся ТОЛЬКО если имени нет ни в одном источнике
# проекта И частота ровно ноль. Замер: 16 ников отсеяно, 21 законный пункт цел.
# Держать их у себя нельзя и по второй причине: это чужие персональные данные,
# и однажды их уже пришлось вычищать из истории репозитория.
NICK_LIST = re.compile(r"^- ([A-Za-z_][A-Za-z0-9_]*)$")
# ⚠️ РЕПЛИКА ИГРОКА: «[{n}] ᛝ {s}: you are cringe», «[{n}] {s} is holding [X]».
# Признак тот же, на котором стоит отсев телеметрии (`TelemetryFilter`):
# у реплики игрока на SkyBlock ВСЕГДА есть метка уровня в начале, а служебные
# строки Hypixel с неё не начинаются. Переводить чужую переписку нельзя,
# и держать её у себя тоже: в пачке 18 нашлись строки с неочищенным ником.
# Замер: 18 строк; «[Lvl {n}] Sheep» и «[MVP+] Player» не задеты.
PLAYER_SAID = re.compile(
    r"^\[\{n\}\]\s*\S*\s*"
    r"(?:\{s\}|[A-Za-z_][A-Za-z0-9_]{2,15})\s*[^:]{0,12}:"
    r"|^\[\{n\}\].*\b(?:is holding|is friends with|joined|left the)\b")


def foreign_script(line: str) -> bool:
    """Строка пришла с клиента на ЧУЖОМ языке — переводить нечего.

    ⚠️ Порог в ДВА знака обязателен. Hypixel берёт под значки буквы и цифры
    чужих алфавитов (записанная грабля: сингальская «ථ», бенгальская «৫»),
    и по одному знаку законная строка «Golden Chili Pepper ৫» попала бы
    в отсев. Замер: с порогом 2 отсеивается 6 строк, все настоящие —
    надписи над мобами с японского и корейского клиента.
    """
    from translate_tooltips import ALIEN_SCRIPTS
    import unicodedata

    found = 0
    for char in line:
        if char.isascii():
            continue
        try:
            name = unicodedata.name(char)
        except ValueError:
            continue
        if any(name.startswith(prefix) for prefix in ALIEN_SCRIPTS):
            found += 1
            if found >= 2:
                return True
    return False
NICK_WORD = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def looks_like_nick(line: str, origin: str, seen: int, known: set, items: set) -> bool:
    """Строка — чужой НИК, а не имя из игры.

    ⚠️ Признак узкий НАРОЧНО, и каждое условие снимает свою ошибку:
      * только `item_name`/`tab`/`screen` — в описаниях под ту же форму
        попадают обрывки слов («Ultimate», «Halloween», «Slowness»);
      * частота РОВНО НОЛЬ — ник приходит от одного человека, а обрывок
        от многих («mana» 13 установок, «damage» 7);
      * имени нет ни в защищённых, ни в каталоге предметов — так «Galatea»
        (локация) отличается от «Olzana» (ник).

    ⚠️ Цена ошибки мала и обратима: настоящее имя, попавшее под признак,
    вернётся в работу, как только его пришлёт второй игрок.
    """
    return (origin in NICK_SOURCES and seen == 0 and NICK_WORD.match(line)
            and line not in known and line not in items)


NPC_LINE = re.compile(r"^(?:§.)*\[NPC\]")


def foreign_nick(line: str, items: set, known: set) -> bool:
    """В строке ЧУЖОЙ НИК — спрашиваем сторожа, своей копии не заводим.

    ⚠️ `looks_like_nick` отвечает на ДРУГОЙ вопрос: «строка целиком — голое
    имя». А ник бывает ВНУТРИ фразы: «Visit MAXIMUS_{n}», «- T_a_m_a_k_i»,
    «Arneper_ launched a Bat Firework». Такую строку переводить незачем —
    она не совпадёт ни у кого, кроме одного человека на свете, — и хранить
    у себя чужое имя тоже незачем.

    ⚠️ ДВЕ ОГОВОРКИ, обе от ложных срабатываний признака (проверено):
      * «[NPC] Имя:» — это ГОВОРЯЩИЙ, персонаж игры. У `Nitroholic_` своя
        страница на вики и две закреплённые реплики;
      * имя из КАТАЛОГА сервера — не ник: «Mithril Drill SX-R326» модель
        дрели, а признак видит в «R326» ник.
    Проверено на 17 случаях обоих краёв.
    """
    if NPC_LINE.match(line) or line in items:
        return False
    return bool(check_nicknames.nicks_in(line, known))


# ⚠️ ЧУЖАЯ ЗАГЛУШКА. Строка «[Lvl {LVL}] Rock» приходит от МОДОВ-СОСЕДЕЙ
# (у нас дырки только {n} и {s}), и движок такого не подставит НИКОГДА —
# ключ мёртв по построению. Записанная грабля про подстановки NEU
# («{INTELLIGENCE}», «{FARMING_FORTUNE}» — деньги в стол).
# ⚠️ Замер 26.08: 88 строк, и у 87 есть ДВОЙНИК с нашим «{n}», который
# честно переводится («[Ур. {n}] Камень»). То есть работы тут нет вовсе,
# а в списке они занимали крупнейшую семью.
FOREIGN_HOLE = re.compile(r"\{[A-Z][A-Z_]{2,}\}")


def closed(line: str, origin: str, dic) -> bool:
    """Строка уже переводится — точной записью, правилом ИЛИ глоссарием."""
    found = status.lookup(line, dic, origin=origin)
    if found and (CYR.search(found[0]) or AT.search(found[0])):
        return True
    text, applies = status.try_glossary(line, dic)
    if not (applies and text and CYR.search(text)):
        return False
    # ⚠️ @ключ развернёт КЛИЕНТ — для нас он не английское слово.
    rest = re.sub(r"⟨из игры: [a-z_]+⟩", "", text)
    # ⚠️ РИМСКАЯ ЦИФРА — НЕ АНГЛИЙСКОЕ СЛОВО, она одинакова на любом языке.
    # Записанная грабля проекта: без этого «Кража жизни III, Удача V» считалось
    # непереведённым из-за «III», и списки зачарований забивали каждую пачку.
    rest = re.sub(r"(?<![A-Za-z])[IVXLC]{1,6}(?![A-Za-z])", "", rest)
    return not LATWORD.search(rest)


def closed_by_paragraph() -> set[str]:
    """Строки, которые мод закроет ПЕРЕВОДОМ АБЗАЦА — покупать их вредно.

    ⚠️ Зачем. Hypixel режет описание по ширине окна, и в работу лезут хвосты
    («players.», «Gemstones.», «Increases melee damage dealt by»). У обрывка
    нет своего смысла, а перевод абзаца его закрывает — замер 26.08: из 161
    накопленного обрывка 136 входят в УЖЕ ПЕРЕВЕДЁННЫЙ абзац корпуса, то есть
    на экране они по-русски. В пачке 5 такие занимали 34 места из 60.

    ⚠️ Признак «это список» берём у `make_queue.in_paragraphs`, а не пишем
    заново: абзац-СПИСОК мод не склеивает никогда (ColorLayout бережёт
    структуру), и его строки закрытыми считать нельзя — на этой самой ошибке
    проект трижды терял перевод удочки. Своя копия признака разошлась бы
    с первой же правкой.

    ⚠️ Проверяем ИМЕННО перевод абзаца, а не просто вхождение: непереведённый
    абзац ничего не закрывает, и его строки — настоящая работа.
    """
    import make_queue  # ленивый импорт: make_queue сам тянет status

    corpus = WORK / "paragraphs.json"
    if not corpus.exists():
        return set()
    safe = make_queue.in_paragraphs()
    out: set[str] = set()
    for para in json.loads(corpus.read_text(encoding="utf-8")).get("paragraphs") or []:
        if not para.get("ru"):
            continue
        for row in para.get("lines") or []:
            row = str(row)
            if row in safe:
                out.add(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size", type=int, default=60)
    ap.add_argument("--out", default=str(WORK / "_batch_next.json"))
    args = ap.parse_args()
    if not TODO.exists():
        print("нет списка работы:", TODO)
        return 1

    known = set()
    if SRC.exists():
        data = json.loads(SRC.read_text(encoding="utf-8"))
        known = (set(data.get("_asis") or []) | set(data.get("_fragments") or [])
                 | set(data.get("strings") or {}))
    dic = status.Dictionaries(groups={"full"})
    rows = json.loads(TODO.read_text(encoding="utf-8"))
    # ⚠️ СТАРЫЙ ФОРМАТ ({"exact": {строка: ""}}) теряет ИСТОЧНИК, а без
    # него нельзя спросить словарь: у `item_lore` и `chat` разные области.
    # Молча брать оттуда строки нельзя — отбор станет добрее движка.
    if isinstance(rows, dict):
        print("список работы в СТАРОМ формате (без источника).")
        print("Пересобрать: python tools/full_coverage.py --out",
              TODO.relative_to(ROOT))
        return 1

    import make_queue  # ленивый импорт: тянет status
    import protected
    protected_names = protected.collect()
    real_items = protected.real_items()
    nicks = 0
    nick_known = check_nicknames.known_names()
    by_para = closed_by_paragraph()
    # ⚠️ ОТЛОЖЕННЫЕ — это ОБРЫВКИ переноса, а не «переводить нечего».
    # Работа по ним есть, но делается ПЕРЕВОДОМ АБЗАЦА, а не покупкой строки
    # (записанная грабля: у обрывка нет своего смысла). Пометка `_asis` тут
    # была бы неверной — она означает принятое решение.
    # Замер 26.08: без этого списка 98 разобранных обрывков всплывали
    # в верхушке КАЖДОЙ пачки и съедали её наполовину.
    postponed = set()
    skip_file = WORK / "_batch_skip.json"
    if skip_file.exists():
        postponed = set(json.loads(skip_file.read_text(encoding="utf-8")))
    unknown_enchants: Counter = Counter()
    open_columns: Counter = Counter()
    batch, dropped = [], 0
    for row in rows:
        line, origin = row["line"].strip(), row["src"]
        if line in known or not re.search(r"[A-Za-z]", line) or JUNK.match(line):
            dropped += 1
            continue
        if ROMAN_ONLY.match(line) or TECH_ID.match(line) or FOREIGN_HOLE.search(line):
            dropped += 1
            continue
        if line in postponed:
            dropped += 1
            continue
        # ⚠️ РЕШЕНИЯ ПРОЕКТА спрашиваем у `make_queue`, а не заводим свои:
        # там лежит признак «перевод совпал бы с оригиналом», и в нём, среди
        # прочего, ВАРИАНТ ОТВЕТА NPC — его решено не переводить совсем
        # (решение игрока 17.08: половина набора даёт «[Конечно!] [Give me
        # a moment.]», то есть смесь языков). Без этого отбор предлагал их
        # переводить, и 26.08 я на этом попался: «[Yes!]» уехал как «[Да!]».
        listed = NICK_LIST.match(line)
        if (listed and row.get("seen", 0) == 0
                and listed.group(1) not in protected_names
                and listed.group(1) not in real_items
                and not status.lookup(listed.group(1), dic, origin=origin)):
            nicks += 1
            dropped += 1
            continue
        if PLAYER_SAID.search(line) or foreign_script(line) or NICK_FORM.match(line):
            nicks += 1
            dropped += 1
            continue
        if foreign_nick(line, real_items, nick_known):
            nicks += 1
            dropped += 1
            continue
        if looks_like_nick(line, origin, row.get("seen", 0), protected_names, real_items):
            nicks += 1
            dropped += 1
            continue
        if make_queue.nothing_to_translate(line):
            dropped += 1
            continue
        # ⚠️ ПОЛОСУ НАД ХОТБАРОМ МОД ПЕРЕВОДИТ ПО КОЛОНКАМ, а не целиком:
        # «{n}/{n}❤   {i} Village   {n}/{n}✎ Mana» — это три колонки через
        # несколько пробелов, и строка ЦЕЛИКОМ не совпадёт с ключом никогда.
        # Записанная грабля проекта («замер по целым строкам полосы врёт
        # по построению»), но отбор её не знал: пачка 12 наполовину состояла
        # из таких строк. Работа тут — НЕЗАКРЫТАЯ КОЛОНКА, её и показываем.
        if status.COLUMNS.search(line):
            for col in status.COLUMNS.split(line):
                col = col.strip()
                if col and not closed(col, origin, dic) and not JUNK.match(col):
                    open_columns[col] += 1
            dropped += 1
            continue
        if is_enchant_set(line):
            # ⚠️ Сигнал НЕ ТЕРЯЕМ: непереведённые имена из наборов копим
            # и печатаем отдельным списком — это и есть настоящая работа.
            for part in line.split(","):
                part = part.strip()
                if not closed(part, origin, dic):
                    unknown_enchants[part.rsplit(" ", 1)[0]] += 1
            dropped += 1
            continue
        if CMD.search(line) or AD.search(line):
            dropped += 1
            continue
        if closed(line, origin, dic):
            dropped += 1
            continue
        if line in by_para:
            dropped += 1
            continue
        bare = STARS.sub("", line).strip()
        if (bare != line and closed(bare, origin, dic)) or STARS.search(line):
            dropped += 1
            continue
        parts = bare.split(" ", 1)
        if len(parts) == 2 and closed(parts[1], origin, dic):
            dropped += 1
            continue
        batch.append(row)
        if len(batch) >= args.size:
            break

    out = [{"n": i, "src": r["src"], "en": mask_icons(r["line"].strip())[0],
            "key": r["line"].strip(), "seen": r["seen"], "ru": ""}
           for i, r in enumerate(batch, 1)]
    pathlib.Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(f"отсеяно как закрытое/не-работа: {dropped}")
    if nicks:
        print(f"отсеяно чужих НИКОВ (головы игроков в меню): {nicks}")
    if open_columns:
        print(f"⚠️ колонки полосы над хотбаром БЕЗ перевода: {len(open_columns)}")
        for col, count in open_columns.most_common(10):
            print(f"      {count:5}  {col[:56]}")
    if unknown_enchants:
        print(f"⚠️ в наборах зачарований встретились имена БЕЗ перевода: "
              f"{len(unknown_enchants)} — их место в data/work/enchants.json")
        for name, count in unknown_enchants.most_common(10):
            print(f"      {count:5}  {name}")
    print(f"в пачке: {len(out)}  ->  {args.out}")
    print()
    for r in out:
        print(f"{r['n']:3}. [{r['src']:10}] {r['seen']:4} уст.  {r['en'][:62]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
