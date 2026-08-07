# -*- coding: utf-8 -*-
"""
СКАНЕР ПО ВСЕМУ ЛОРУ АУКЦИОНА — беды без похода в игру.

`scan.py` смотрит `dump/preview.json`, то есть подсказки, на которые игрок
НАВЁЛ КУРСОР. Их десятки. А лор аукциона (`fetch_auction.py`) даёт **11 359
абзацев от 2428 предметов**, причём С §-КОДАМИ — то есть оригинал ровно
в том виде, в каком его пришлёт сервер.

⚠️ Чего в аукционе нет — это «после перевода». Но ждать его из игры не нужно:
перевод мы знаем из словарей (`status.py` повторяет порядок движка), а что
именно мод сделает с абзацем — выводится из тех же правил, по которым он
режет и склеивает. Поэтому здесь проверяются признаки, которым не нужна
отрисовка:

  ЛОСКУТ     в абзаце часть строк переведена, часть нет
  СЛИПНЕТСЯ  заголовок не отделится: построчный перевод разошёлся с абзацем
             (или его нет вовсе) — `Paragraphs.header` требует совпадения
  ИМЯ        заголовок переведён, хотя в оригинале это ИМЯ (кончается на Part,
             Bonus и т.п.) — ломает и поиск на аукционе, и резку

Цвет и перенос остаются за `scan.py`: им нужна настоящая раскладка.

    python tools/scan_all.py                 сводка
    python tools/scan_all.py --kind ЛОСКУТ   один вид
    python tools/scan_all.py --show 20
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

LORE = ROOT / "data" / "work" / "auction_lore.json"

CODES = re.compile(r"§.")
SPACES = re.compile(r"\s+")
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def plain(text: str) -> str:
    return SPACES.sub(" ", CODES.sub("", text or "")).strip()


def generalized(text: str) -> str:
    """Как обобщает числа сам движок — через общий pkey, не своей копией."""
    from pkey import generalize
    return generalize(plain(text))


PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"


def load_filters():
    """Что переводить НЕ надо — берём у тех, кто уже это решил.

    ⚠️ Читаем ВСЕ словари, включая ВЫКЛЮЧЕННЫЕ. Выключенный словарь — это
    решение «оставить английским», а не дырка: игрок сам выключил зачарования
    SkyBlock, и звать их работой значит показывать решение бедой.
    `make_queue.already_translated()` тут не подошёл — правила выключенных
    пакетов он не отдаёт, и первый прогон открывался «Flowstate III» (139
    вхождений), хотя правило для него лежит в 77-sb-enchants.
    """
    import protected
    import terms
    guarded = {n.lower() for n in protected.collect()}
    jargon = {n.lower() for n in terms.STAT_JARGON}

    decided, rules = set(), []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for section in ("exact", "glossary", "paragraphs"):
            for key, value in (pack.get(section) or {}).items():
                if value:
                    decided.add(key.strip().lower())
        for rule in pack.get("regex") or []:
            pattern = rule.get("p")
            if not pattern:
                continue
            try:
                rules.append(re.compile(pattern))
            except re.error:
                continue
    return guarded, jargon, decided, rules


def closed_by_decision(text: str, filters) -> bool:
    """Закрыта ли строка словарём — в том числе ВЫКЛЮЧЕННЫМ."""
    _guarded, _jargon, decided, rules = filters
    stripped = text.strip()
    if not stripped or stripped.lower() in decided:
        return True
    if generalized(stripped).lower() in decided:
        return True
    for rule in rules:
        if rule.search(stripped):
            return True
    return False


def still_english(line, filters) -> bool:
    """Осталась бы строка английской ПО СУЩЕСТВУ, а не по решению."""
    guarded, jargon, _decided, _rules = filters
    if not LATIN_WORD.search(line):
        return False
    if closed_by_decision(line, filters):
        return False

    # ⚠️ Зачарования идут СПИСКОМ через запятую («Legion V, Growth VI,
    # Protection VI»), а правила писаны на ОДНО имя. Строка целиком не
    # совпадает ни с одним — и список выглядел работой, хотя каждое имя
    # в нём закрыто решением. Разбираем по частям.
    parts = [p.strip() for p in line.split(",") if p.strip()]
    if len(parts) > 1 and all(closed_by_decision(p, filters) for p in parts):
        return False

    clean = line.lower()
    for name in guarded | jargon:
        if name in clean:
            clean = clean.replace(name, " ")
    return bool(LATIN_WORD.search(clean))


def leading_color(raw: str) -> str:
    """Первый §-код строки — им Hypixel красит всю строку, если она одноцветна."""
    match = re.match(r"^(?:\s*)(§.)", raw or "")
    return match.group(1) if match else ""


def looks_like_header(rows: list, index: int) -> bool:
    """Заголовок ли строка — ДВА признака, и оба обязательны.

    1. У неё СВОЙ цвет, отличный от следующей. Без этого «заголовком»
       считалась первая строка ЛЮБОГО абзаца, и отчёт открывался прозой
       («This skin can only be applied to», 56 раз).

    2. ⚠️ Следующая строка НАЧИНАЕТ НОВОЕ ПРЕДЛОЖЕНИЕ. Одного цвета мало:
       проза тоже бывает покрашена иначе, и под правило попадали обрывки
       фразы — «This skin will allow you to swap» / «between different
       colors!». Дописывать таким построчный перевод ВРЕДНО: у обрывка нет
       своего смысла, и порознь переведённые половины дают «щит щит»
       и «время времени» (обе беды в этом проекте уже были).
       Признак механический: после заголовка идёт заглавная буква или знак,
       а продолжение фразы начинается со строчной.
    """
    if index + 1 >= len(rows):
        return False
    own = leading_color(rows[index])
    below = leading_color(rows[index + 1])
    if not own or not below or own == below:
        return False

    head = plain(rows[index])
    following = plain(rows[index + 1])
    if not head or not following:
        return False
    # заголовок с двоеточием — заголовок наверняка («Held Item: …»)
    if head.rstrip().endswith(":"):
        return True
    first = following.lstrip()[:1]
    if not first:
        return False
    # строчная латинская или кириллическая — это продолжение фразы
    return not (first.isalpha() and first.islower())


# ⚠️ Хвост «Part» — единственный, что оставлен в признаке ИМЯ.
#
# Первая версия ловила ещё Bonus/Engine/Tank/Skin и дала 38 находок вида
# «Fabled Bonus -> Бонус Fabled». Все ЛОЖНЫЕ: правило `^(.+) Bonus$` ->
# «Бонус $1» существует НАРОЧНО, имя перековки в нём остаётся английским,
# и резка работает — заголовок сверяется с ПЕРЕВОДОМ, а не с оригиналом.
# А вот «X Part» переводить нечем: правила для него нет, и развёрнутое
# «Часть X» ломает и поиск на аукционе, и совпадение заголовка.
NAME_TAIL = re.compile(r"\bPart$")


def main():
    # ⚠️ Консоль тут cp1251, а в находках стоят значки Hypixel из приватной
    # зоны — без этого сканер ПАДАЕТ на печати, уже успев всё посчитать.
    # Та же грабля, что у check_guard: «упал» и «ничего не нашёл» со стороны
    # неотличимы.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kind", help="только один вид находок")
    parser.add_argument("--show", type=int, default=10)
    args = parser.parse_args()

    if not LORE.exists():
        print(f"нет файла: {LORE}")
        print("Собрать: python tools/fetch_auction.py")
        return 0

    import status
    dic = status.Dictionaries()
    filters = load_filters()

    def paragraph_lookup(text: str):
        """Перевод АБЗАЦА — так же строго, как его ищет мод.

        ⚠️ `status.lookup` применяет ПРАВИЛА, а `Translator.lookupParagraph`
        их не применяет НАРОЧНО: абзац меняет несколько строк на экране,
        и ошибиться дороже, чем не перевести. Из-за этого сканер считал
        переведённым «Ability: Pickobulus RIGHT CLICK Throw your pickaxe…» —
        там сработало общее правило `^Ability: ([A-Z].*)$`, поймавшее ВСЮ
        склеенную строку. Мод такого не увидит, и находка была бы ложной.
        Спрашиваем только точные записи и обобщение по числам.
        """
        key = generalized(text)
        for source in (dic.paragraphs, dic.exact, dic.templates):
            got = source.get(key) or source.get(text.strip())
            if got:
                return got
        return None

    data = json.loads(LORE.read_text(encoding="utf-8"))
    lore = data.get("lore") or {}
    print(f"абзацев в лоре аукциона: {len(lore)}")

    found = defaultdict(Counter)
    checked = 0

    for key, lines in lore.items():
        if not isinstance(lines, list) or len(lines) < 2:
            continue
        checked += 1
        texts = [plain(x) for x in lines]

        # перевод абзаца целиком — ищем так же строго, как мод
        whole = paragraph_lookup(" ".join(texts))

        # --- ЛОСКУТ: часть строк переведена, часть нет
        if not whole:
            translated, english = 0, []
            for line in texts:
                if not line:
                    continue
                got = status.lookup(generalized(line), dic)
                if got:
                    translated += 1
                elif still_english(line, filters):
                    english.append(line)
            if translated and english:
                found["ЛОСКУТ"][english[0][:70]] += 1
            continue

        # --- дальше про абзацы, у которых перевод ЕСТЬ
        head = texts[0]
        if not head or len(texts) < 2:
            continue
        # ⚠️ Заголовок опознаём по ЦВЕТУ, а не по месту в абзаце: первая
        # строка бывает и обычной прозой, и тогда резать нечего.
        if not looks_like_header(lines, 0):
            continue
        body = plain(whole[0] if isinstance(whole, tuple) else whole)

        # --- ИМЯ: заголовок кончается на Part/Bonus, а в переводе он развёрнут
        if NAME_TAIL.search(head) and not body.startswith(head):
            found["ИМЯ"][f"{head[:40]} -> {body[:40]}"] += 1
            continue

        # --- СЛИПНЕТСЯ: заголовок не отделится, потому что перевод первой
        # строки не совпадает с началом абзаца (или его нет вовсе)
        got_head = status.lookup(generalized(head), dic)
        head_ru = plain(got_head[0] if isinstance(got_head, tuple) else got_head) if got_head else ""
        if not body.startswith(head) and (not head_ru or not body.startswith(head_ru)):
            found["СЛИПНЕТСЯ"][f"{head[:40]} | абзац: {body[:36]}"] += 1

    print(f"проверено абзацев: {checked}")
    total = sum(sum(c.values()) for c in found.values())
    print(f"находок: {total}")
    print()

    for kind in ("ЛОСКУТ", "СЛИПНЕТСЯ", "ИМЯ"):
        rows = found.get(kind)
        if not rows or (args.kind and args.kind.upper() != kind):
            continue
        print(f"=== {kind}: {sum(rows.values())} (разных: {len(rows)}) ===")
        for note, count in rows.most_common(args.show):
            print(f"  {count:4d}x  {note}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
