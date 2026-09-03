# -*- coding: utf-8 -*-
"""
Абзацы для РЕЖИМА ПОЛНОГО ПЕРЕВОДА: те же тексты, но с русскими терминами.

⚠️ ЗАЧЕМ ОТДЕЛЬНАЯ ВЕРСИЯ, а не замена слов на лету. В обычном режиме жаргон
(«Mining Fortune») и зачарования («Growth V») остаются английскими — это
решения игрока, и абзац в корпусе переведён именно так. В режиме их надо
показать по-русски, но ПРЯМАЯ ЗАМЕНА даёт «Повышает Удача шахтёра»: русскому
термину нужен падеж, а падеж машинно не выводится — записанное правило
проекта, на нём же стоит отказ rename_term гадать формы.

Поэтому режимный перевод — отдельная строка, и правится в ней ТОЛЬКО термин
вместе с падежом. Заготовка предзаполняется обычным переводом, так что
переводить заново ничего не нужно.

⚠️ Словарь идёт с priority МЕНЬШЕ, чем у корпуса (96-paragraphs = 21):
у секции paragraphs, как и у exact, побеждает меньший priority. Значит
при включённом режиме показывается режимная версия, при выключенном —
обычная, потому что режимный словарь просто не грузится.

    python tools/gen_full_paragraphs.py --skeleton
    python tools/gen_full_paragraphs.py --export FILE --limit 60
    python tools/gen_full_paragraphs.py --load FILE
    python tools/gen_full_paragraphs.py --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ⚠️ Консоль Windows — cp1251: без обёртки инструмент падает на первом же
# русском слове, и это выглядит как поломка задачи, а не вывода.
# Записанная грабля проекта (третий инструмент за сессию).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

CORPUS = WORK / "paragraphs.json"
SKELETON = WORK / "full_paragraphs_ru.json"
PACK = PACKS / "ru_ru" / "86-full-paragraphs.json"


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def corpus_rows() -> list[dict]:
    data = load(CORPUS, [])
    if isinstance(data, list):
        return data
    for value in data.values():
        if isinstance(value, list):
            return value
    return []


def english_terms() -> list[str]:
    """Термины, которые режим обязан показать по-русски.

    Берём их у САМИХ режимных словарей, а не заводим свой список: разойдись
    они — и мы бы правили абзацы под термин, которого режим не переводит.
    """
    import terms as project_terms
    out = set(project_terms.STAT_JARGON)
    client = set()
    for name in ("77-sb-enchants.json", "78-sb-stats.json"):
        pack = load(PACKS / "ru_ru" / name, {})
        for key, value in (pack.get("glossary") or {}).items():
            out.add(key)
            # ⚠️ Термин, чей перевод — @ключ, отдаёт КЛИЕНТ игрока
            # («Respiration» -> «Подводное дыхание»). Требовать от нас
            # русского слова тут неверно: своё было бы хуже клиентского,
            # а абзац из-за этого нельзя было принять ВООБЩЕ.
            if isinstance(value, str) and value.startswith("@"):
                client.add(key)
        # ⚠️ @ключ у характеристики стоит в ПРАВИЛАХ, а не в глоссарии:
        # «^Respiration: (…)$» -> «@enchantment.minecraft.respiration: $1».
        # Смотреть только глоссарий значило требовать от нас своего слова
        # там, где режим и так показывает клиентское, — и абзац нельзя было
        # принять ВООБЩЕ.
        rules = pack.get("regex") or []
        if isinstance(rules, dict):
            rules = list(rules.values())
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if not str(rule.get("r") or "").lstrip("$123456789 ").startswith("@"):
                continue
            head = re.match(HEAD_OF_RULE, rule.get("p") or "")
            if head:
                client.add(head.group(1).replace(chr(92), "").strip())
    return sorted(out - client, key=len, reverse=True)


HEAD_OF_RULE = re.compile(r"\^([A-Za-z' " + chr(92) * 2 + r"]{3,32})[:( ]")
CODE = re.compile("§.")
ROMAN = re.compile(r"[IVXLC]{1,6}$")
# Значок Hypixel — символ приватной зоны юникода.
ICONS = re.compile(r"[-]")
HOLES = re.compile(r"\{[ns]\}")


def standalone(text: str, needle: str) -> bool:
    """
    Термин стоит САМ ПО СЕБЕ, а не внутри чужого слова или имени.

    Три случая, на которых голое `needle in text` врёт, и все три пойманы
    на живых данных:

    * ЧУЖОЕ СЛОВО. «Magnet» сидит внутри «Magnetic», «Experience» —
      внутри «Experienced», «Drain» — внутри «Drains». Требуем границу
      по буквам.
    * §-КОД СЛЕВА. Буква кода неотличима от буквы слова: у «§lUltimate
      Wise» слева видится «l», и обычная граница не срабатывает. Коды
      снимаем перед проверкой соседа. Записанная грабля проекта.
    * СОСТАВНОЕ ИМЯ. «Harvest Feast» — событие, «Fear Mongerer» — NPC,
      «Kill Combo» — перк, «Rat's Blessing» — способность. Два заглавных
      слова подряд это имя целиком, и лезть в него нельзя. Римский
      уровень при этом не в счёт: «Growth V» — имя ПЛЮС уровень.
    """
    for match in re.finditer(rf"(?:(?<=§.)|(?<![A-Za-z])){re.escape(needle)}(?![A-Za-z])",
                             text):
        before = CODE.sub("", text[:match.start()]).rstrip()
        previous = re.search(r"([A-Za-z']+)$", before)
        if previous and previous.group(1).lstrip("'")[:1].isupper():
            continue
        after = CODE.sub("", text[match.end():]).lstrip()
        nxt = re.match(r"([A-Za-z]+)", after)
        if nxt and nxt.group(1)[0].isupper() and not ROMAN.match(nxt.group(1)):
            continue
        return True
    return False


def found_in(text: str, needles: list[str]) -> list[str]:
    return [n for n in needles if standalone(text, n)]


# ⚠️ Заголовок абзаца: «Бонус полного комплекта: X», «Способность: X».
# Имя внутри переводится ТОЛЬКО в режиме, и от этого расходятся два пути.
HEAD_PREFIX = re.compile(r"^(?:Tiered Bonus|Full Set Bonus|Piece Bonus|Ability|Bonus): ")
COUNTER = re.compile(r"\(\{n\}/\{n\}\)")
NAME_WORDS = re.compile(r"[A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*)*")


def heading_of(key: str) -> str | None:
    """Заголовок абзаца целиком, вместе со счётчиком.

    ⚠️ Одной регуляркой это не берётся: счётчик «({n}/{n})» необязателен,
    и нежадный хвост обрывал имя на первом же пробеле — «Tiered Bonus: Depth»
    вместо «Tiered Bonus: Depth Champion ({n}/{n})». Поэтому счётчик ищем
    отдельно, а без него имя — это слова с Заглавной подряд.
    """
    start = HEAD_PREFIX.match(key)
    if not start:
        return None
    rest = key[start.end():]
    counter = COUNTER.search(rest)
    if counter and counter.start() <= 62:
        return key[:start.end() + counter.end()]
    name = NAME_WORDS.match(rest)
    if not name or name.end() > 60:
        return None
    return key[:start.end() + name.end()]


_HEADS: set[str] = set()


def known_heads() -> set[str]:
    """Заголовки, которые проект уже признал таковыми — из `41-headers`.

    ⚠️ У питомцев заголовок ГОЛЫЙ («Primal Force», «First Pounce»), без
    подписи с двоеточием, и по форме его от прозы не отличить. Зато он
    есть в словаре заголовков: `gen_headers` вырезает их из купленных
    абзацев по ЦВЕТУ, то есть по данным сервера. Это и берём за признак.
    """
    if not _HEADS:
        pack = load(PACKS / "ru_ru" / "41-headers.json", {})
        _HEADS.update(k for k in (pack.get("exact") or {}) if len(k) < 60)
    return _HEADS


def heading_candidates(key: str) -> list[str]:
    """Кандидаты в заголовок, от длинного к короткому.

    ⚠️ Без счётчика конец заголовка по форме не виден: «Ability: Overindulgence
    Grants you…» — «Grants» тоже с Заглавной. Поэтому не гадаем, а спрашиваем
    словарь: верный кандидат тот, чей перевод он знает. Тот же приём, что
    `markedHeadEnds` в моде — список кандидатов, выбор по совпадению.
    """
    head = heading_of(key)
    if not head:
        # заголовок без подписи: самый длинный префикс, известный как заголовок
        heads = known_heads()
        best = None
        for cut in range(len(key), 3, -1):
            if key[cut - 1] == " ":
                continue
            piece = key[:cut]
            if piece in heads:
                best = piece
                break
        return [best] if best else []
    out = [head]
    while " " in head:
        head = head.rsplit(" ", 1)[0]
        if head.endswith(":"):
            break
        out.append(head)
    return out


def clashing_heading(key: str) -> bool:
    """Разойдётся ли заголовок этого абзаца с построчным в режиме full.

    ⚠️⚠️ ЭТО СЛИПШИЙСЯ ЗАГОЛОВОК НА ЭКРАНЕ, а не косметика. `Paragraphs.header`
    режет заголовок своей строкой, только если вырезанное СОВПАДАЕТ с
    построчным переводом первой строки. В режиме построчный даёт «Ступенчатый
    бонус: Покоритель глубин», а обычный абзац несёт «...: Depth Champion» —
    совпадения нет, резка отменяется, и заголовок втекает в описание.
    Заодно пропадает цвет: подмена ведущих кодов идёт при резке.
    Замер 28.08: таких абзацев 146.
    """
    import status  # ленивый импорт: status тянет словари
    # ⚠️ Останавливаться на ПЕРВОМ известном кандидате нельзя: общее правило
    # «^Ability: (.+)$» знает любой хвост, и «Ability: Overindulgence Grants»
    # проходит как известный, давая одинаковый перевод в обоих режимах.
    # Спрашиваем ВСЕ кандидаты: расхождение хотя бы у одного и есть беда.
    for head in heading_candidates(key):
        plain = status.lookup(head, _PLAIN(), origin="item_lore")
        mode = status.lookup(head, _MODE(), origin="item_lore")
        if plain and mode and plain[0] != mode[0]:
            return True
    return False


_DICTS: dict[str, object] = {}


def _PLAIN():
    import status
    if "plain" not in _DICTS:
        _DICTS["plain"] = status.Dictionaries()
    return _DICTS["plain"]


def _MODE():
    import status
    if "mode" not in _DICTS:
        _DICTS["mode"] = status.Dictionaries(groups={"full"})
    return _DICTS["mode"]


def do_skeleton() -> int:
    needles = english_terms()
    old = load(SKELETON, {}) or {}
    ready = old.get("rows", {})

    fresh: dict[str, dict] = {}
    for row in corpus_rows():
        russian = row.get("ru")
        if not russian:
            continue
        hits = found_in(russian, needles)
        # ⚠️ Второй повод завести режимную версию — расходящийся ЗАГОЛОВОК
        # (см. `clashing_heading`): без неё абзац слипается на экране.
        if not hits and not clashing_heading(row["text"]):
            continue
        key = row["text"]
        was = ready.get(key, {})
        fresh[key] = {
            # ⚠️ Предзаполняем ОБЫЧНЫМ переводом: править надо только термин.
            "ru": was.get("ru") or russian,
            "base": russian,
            "terms": hits[:4],
            "live": row.get("live") or 0,
            "done": bool(was.get("done")),
        }

    # ⚠️⚠️ ПЕРЕНОСИМ ГОТОВЫЕ ЗАПИСИ, даже если текущий отбор их не берёт.
    # Заготовка пополняется не только этим отбором: часть записей влита
    # руками (`--load`) и через `full_prefill`. Замер 28.08: пересборка
    # выбросила бы 525 готовых переводов — словарь усох бы с 1854 до 1329,
    # причём МОЛЧА, потому что `--write` пишет только помеченные `done`.
    # Та же семья, что «пересборка корпуса стирает абзацы»: файл, который
    # пересобирается, обязан переносить чужую работу, а не только свою.
    kept = 0
    for key, was in ready.items():
        if key in fresh or not was.get("done") or not was.get("ru"):
            continue
        fresh[key] = dict(was)
        kept += 1

    ordered = dict(sorted(fresh.items(), key=lambda kv: (-kv[1].get("live", 0), kv[0])))
    save(SKELETON, {
        "_comment": "Абзацы для режима полного перевода: тот же текст, но "
                    "с русскими терминами. Поле base — обычный перевод "
                    "(в нём термин английский), ru — режимный. Правь ТОЛЬКО "
                    "термин и падеж вокруг него, а done ставь true, когда "
                    "запись готова. Порядок — по числу игроков, видевших абзац.",
        "rows": ordered,
    })
    done = sum(1 for r in ordered.values() if r.get("done"))
    print(f"абзацев в заготовке: {len(ordered)}, готово {done}, "
          f"ждут {len(ordered) - done}")
    if kept:
        print(f"перенесено готовых, которых текущий отбор не берёт: {kept}")
    return 0


def do_export(path: Path, limit: int) -> int:
    data = load(SKELETON, {}) or {}
    task = []
    for key, row in data.get("rows", {}).items():
        if row["done"]:
            continue
        task.append({"key": key, "terms": row["terms"], "live": row["live"],
                     "base": row["base"], "ru": row["base"]})
        if len(task) >= limit:
            break
    save(path, task)
    print(f"выгружено {len(task)} абзацев -> {path}")
    print("правь в поле ru ТОЛЬКО термин и падеж вокруг него")
    return 0


def do_load(path: Path) -> int:
    task = load(path)
    if not isinstance(task, list):
        print("файл задания должен быть списком записей")
        return 1
    data = load(SKELETON, {}) or {}
    rows = data.get("rows", {})
    needles = english_terms()

    taken, refused = 0, []
    for item in task:
        key = item.get("key", "")
        value = (item.get("ru") or "").strip()
        if not value or key not in rows:
            if key not in rows:
                refused.append(f"{key[:50]!r}: НЕ НАЙДЕНО в заготовке")
            continue
        left = found_in(value, needles)
        if left:
            # ⚠️ Смысл записи — убрать английский термин. Остался — работа
            # не сделана, и молча принимать её нельзя: словарь распухнет
            # копиями, которые ничего не меняют.
            refused.append(f"{key[:44]!r}: термин остался английским: {left[:2]}")
            continue
        if value == rows[key]["base"]:
            refused.append(f"{key[:44]!r}: перевод совпал с обычным — править нечего")
            continue
        # ⚠️ ЗНАЧКИ обязаны совпасть с обычным переводом. Правится режимная
        # версия РУКАМИ, а символы Hypixel лежат в приватной зоне юникода
        # и из терминала копируются ПРОБЕЛОМ — записанная грабля проекта.
        # Замер до этой проверки: из 93 готовых абзацев значки потеряли 39,
        # и увидел это игрок на экране, а не сторож.
        # ⚠️ ДЫРКИ обязаны совпасть с обычным переводом. Режимная версия
        # отличается одним ТЕРМИНОМ, а термин дырок не содержит — значит
        # расхождение значит потерю текста. Поймано сверкой: у девяти записей
        # оборвался хвост («…пока предмет в руках.» вместо «…в руках. Даёт
        # +5☯ Combat Wisdom против эндерменов.»), и увидеть это на глаз
        # нельзя: предложение кончается точкой и выглядит целым.
        holes = (len(HOLES.findall(rows[key]["base"])),
                 len(HOLES.findall(value)))
        if holes[0] != holes[1]:
            refused.append(f"{key[:44]!r}: ДЫРОК стало {holes[1]}, "
                           f"а в обычном переводе {holes[0]} — потерян текст")
            continue
        want, got = ICONS.findall(rows[key]["base"]), ICONS.findall(value)
        if want != got:
            refused.append(f"{key[:44]!r}: ЗНАЧКИ потеряны "
                           f"({len(want)} было, {len(got)} стало)")
            continue
        rows[key]["ru"] = value
        rows[key]["done"] = True
        taken += 1

    data["rows"] = rows
    save(SKELETON, data)
    print(f"принято {taken} из {len(task)}")
    for line in refused[:15]:
        print(f"   {line}")
    return 0


# порог берём У СОСЕДА: своя копия числа разошлась бы при первой правке
from merge_paragraphs import EXACT_MAX  # noqa: E402


def do_write() -> int:
    data = load(SKELETON, {}) or {}
    rows = {k: v for k, v in data.get("rows", {}).items() if v.get("done")}
    if not rows:
        print("готовых записей нет — писать нечего")
        return 1

    pack = {
        "id": "full_paragraphs",
        # ⚠️ 19, А НЕ 20: у `97-enchant-sections` тоже было 20, и при
        # РАВНОМ priority победитель решался порядком чтения файлов —
        # то есть случаем. Записанная грабля проекта. Пять режимных
        # абзацев из-за этого показывались обычной версией.
        "priority": 19,
        "default": False,
        "group": "full",
        "about": "описания с русскими терминами (Mining Fortune -> Удача "
                 "шахтёра) — для режима полного перевода",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_full_paragraphs.py из "
                    "data/work/full_paragraphs_ru.json — правь заготовку. "
                    "Это ТЕ ЖЕ абзацы, что в 96-paragraphs, но с русскими "
                    "терминами. priority МЕНЬШЕ, чем у корпуса, поэтому при "
                    "включённом режиме побеждает эта версия; при выключенном "
                    "словарь просто не грузится.",
        "only": ["item_lore"],
        "paragraphs": {k: v["ru"] for k, v in sorted(rows.items())},
        # ⚠️⚠️ ДУБЛЬ В `exact` ОБЯЗАТЕЛЕН, иначе режимный перевод НЕ ВИДЕН.
        #
        # У корпуса (96-paragraphs) короткие абзацы лежат ЕЩЁ И в `exact` —
        # на случай, когда у игрока шире окно и абзац приходит одной строкой.
        # А `exact` движок ищет РАНЬШЕ абзацев, независимо от priority секции
        # paragraphs. Своей секции `exact` здесь не было, поэтому обычный
        # перевод выигрывал ВСЕГДА:
        #     режим: «Даёт +{n}☘ к Удаче фермера за каждый уровень»
        #     видно: «Даёт +{n}☘ к Farming Fortune за каждый уровень»
        # Замер 28.08: так гасли 945 режимных абзацев из 1298 — 73% работы.
        # Нашёл игрок скриншотом, спросив «почему в full нет перевода».
        #
        # Порог тот же, что у корпуса (merge_paragraphs.EXACT_MAX): длиннее
        # него строка целиком не приходит, и запись была бы мёртвым грузом.
        # Спрашиваем его у соседа, копию не заводим — разошлись бы.
        "exact": {k: v["ru"] for k, v in sorted(rows.items()) if len(k) <= EXACT_MAX},
    }
    save(PACK, pack)
    print(f"записано {PACK.name}: {len(rows)} абзацев")
    print("⚠️ впиши файл в packs/index.json, иначе он молча не загрузится")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeleton", action="store_true")
    parser.add_argument("--export", metavar="FILE")
    parser.add_argument("--load", metavar="FILE")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int, default=60)
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
