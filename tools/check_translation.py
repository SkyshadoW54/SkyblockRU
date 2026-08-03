"""
Проверяет перевод механически, без чтения глазами.

Часть ошибок видна только при сверке с оригиналом: пропал значок, съехала
подстановка, строка осталась английской, модель написала {Н} кириллицей.
Такое находится машинно и находиться должно — просматривать тысячи записей
глазами невозможно, а «просмотрел по диагонали» — это не проверка.

Понимает оба рабочих формата, различает их по имени секции:
  data/work/paragraphs.json     — абзац целиком (text -> ru), основной путь
  data/work/lore_tooltips.json  — блок построчно (lines -> ru), старый формат

Замечания делятся на две кучи, и это главное в отчёте:
  СЛОМАНО        — запись нельзя отдавать в мод, на экране будет мусор;
  ПОДОЗРИТЕЛЬНО  — машина не уверена, смотреть глазами.

Что НЕ проверяется: правильность и складность формулировок. Это только
глазами, выборочно, либо вторым проходом модели.

Запуск:
  python tools/check_translation.py data/work/paragraphs.json
  python tools/check_translation.py data/work/paragraphs.json --show 0   (всё)
"""

from __future__ import annotations

import argparse
import functools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from restore_icons import icons_of  # noqa: E402  значок = категория символа, не диапазон

CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")
LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
PLACEHOLDER = re.compile(r"\{[ns]\}")
COLOR = re.compile("§.")

# Любая фигурная группа, кроме правильных {n} и {s}.
# Ловит {Н} кириллицей, { n } с пробелами, {n без скобки, {number} и прочее:
# движок такую не поймёт и покажет игроку как есть.
BAD_HOLE = re.compile(r"\{(?![ns]\})[^{}]{0,20}\}")

# Куча «сломано» — записи, которые нельзя отдавать в мод
BROKEN = "СЛОМАНО"
SUSPECT = "ПОДОЗРИТЕЛЬНО"

# Английское слово со строчной буквы: имена Hypixel пишет с Заглавной
LOWER_EN = re.compile(r"(?<![A-Za-z'\-])[a-z][a-z'\-]{2,}(?![A-Za-z'\-])")
CYRILLIC = re.compile(r"[А-яЁё]")
# то, что законно остаётся латиницей и со строчной
ALLOW_LATIN = {"exp", "xp", "hp", "mvp", "vip", "npc", "gg", "coop", "co-op"}


# Латиница, к которой приклеили кириллицу или апостроф с кириллицей:
# «Outpost'е», «Bahaу». Признак механический и потому надёжный.
DECLINED = re.compile(r"[A-Za-z]{2,}['’ʼ]?[А-яЁё]+")


def icon_counts(text: str) -> Counter:
    return Counter(icons_of(text))


def marks_after_holes(text: str) -> list[str]:
    """
    Какой значок стоит сразу за каждой дыркой. Пустая строка — значка нет.

    Нужно, чтобы поймать ПЕРЕСТАВЛЕННЫЕ дырки. Translator.fillNumbers
    подставляет числа по порядку, поэтому «+{n}❤ здоровья и +{n}✎ маны»,
    переписанное как «+{n}✎ маны и +{n}❤ здоровья», выдаст игроку числа
    наоборот. Значок при своём слове — единственный машинный признак,
    по которому это видно.
    """
    out = []
    for hole in PLACEHOLDER.finditer(text):
        tail = text[hole.end():hole.end() + 1]
        out.append(tail if tail and icons_of(tail) else "")
    return out


def glossary_terms() -> dict[str, str]:
    terms = {}
    for path in sorted(PACKS.rglob("*.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for src, dst in (pack.get("glossary") or {}).items():
            if dst and not dst.startswith("@"):
                terms[src] = dst
    return terms


@functools.lru_cache(maxsize=1)
def _lowered(names: frozenset) -> frozenset:
    return frozenset(name.lower() for name in names)


def guarded_lower(guarded) -> frozenset:
    """
    Защищённые имена в нижнем регистре — ОДИН раз на прогон.

    ⚠️ Множество строилось заново на КАЖДОЕ английское слово в каждом абзаце:
    991 имя на 6418 переводов — до 6.3 млн лишних операций. Вся проверка
    занимала 265 секунд из шести минут круга сборки, и это была не работа,
    а одна и та же работа, повторённая миллионы раз.
    """
    return _lowered(frozenset(guarded))


@functools.lru_cache(maxsize=1)
def _compiled(pairs: tuple) -> tuple:
    return tuple((term, re.compile(r"\b" + re.escape(term) + r"\b"),
                  expected.lower(), expected)
                 for term, expected in pairs)


def term_patterns(terms: dict) -> tuple:
    """
    Термины глоссария со ЗАРАНЕЕ скомпилированным шаблоном.

    ⚠️ Шаблон собирался и компилировался внутри двойного цикла: 178 терминов
    на 6418 абзацев — 1 142 404 компиляции одной и той же регулярки. Встроенный
    кэш `re` тут не помогает: строку шаблона всё равно собирают заново.
    """
    return _compiled(tuple(sorted(terms.items())))


def check_pair(src: str, ru: str, guarded: set[str],
               terms: dict[str, str], misses: Counter) -> list[tuple[str, str, str]]:
    """
    Сверяет одну пару «оригинал — перевод».
    Возвращает список (куча, что за беда, подробности).
    """
    from protected import check_block

    found: list[tuple[str, str, str]] = []
    pair = f"{src[:58]!r}\n        -> {ru[:58]!r}"

    if not ru.strip():
        return [(BROKEN, "перевод пустой", repr(src[:60]))]

    # --- ломающие вёрстку и подстановку ---

    if "\n" in ru or "\r" in ru:
        # Мод раскладывает абзац по словам через пробел: перенос склеится с соседом
        found.append((BROKEN, "перенос строки внутри перевода", pair))

    if len(PLACEHOLDER.findall(src)) != len(PLACEHOLDER.findall(ru)):
        found.append((BROKEN, "изменилось число дырок {n}/{s}", pair))

    bad = BAD_HOLE.findall(ru)
    if bad:
        # Самая коварная: выглядит как подстановка, а движок её не знает
        found.append((BROKEN, "кривая подстановка", f"{bad} в {ru[:52]!r}"))

    # Английское имя просклоняли: «в Fishing Outpost'е», «Baha'у».
    # Имена собственные мы не переводим, а раз не переводим — они и не
    # склоняются. Падеж должно брать на себя русское слово-подпорка
    # («на острове Lotus Atoll»), а не окончание, приклеенное к латинице.
    glued = DECLINED.findall(ru)
    if glued:
        found.append((BROKEN, "английское имя просклоняли", f"{glued} в {ru[:52]!r}"))

    lost = icon_counts(src) - icon_counts(ru)
    if lost:
        shown = " ".join(f"{c}(U+{ord(c):04X})" for c in lost)
        found.append((BROKEN, "потерян значок", f"{shown} в {pair}"))

    # ⚠️ §-коды в переводе абзаца — это РАЗМЕТКА ЦВЕТОМ (masking), а не порча.
    # Проверка писалась до неё и считала кодом-выдумкой каждую размеченную
    # запись: 3268 ложных «поломок» из 3452, то есть отчёт стал бесполезен
    # ровно в тот день, когда разметка пошла в дело. Выдумкой код был бы,
    # если бы менялся ТЕКСТ, — а это ловит сверка ниже.
    plain_ru = COLOR.sub("", ru)

    # ⚠️ Защищённые имена ищем в тексте БЕЗ кодов: «§cCatacombs§7» — это имя
    # на месте, а не переведённое. Иначе 184 хороших абзаца шли в брак.
    # ⚠️ Английское слово со СТРОЧНОЙ буквы, окружённое кириллицей, — недоперевод.
    #
    # «Пусть blaze и эфемерные создания, их пепел вечен» прошло все проверки:
    # дырки целы, значки на месте, имена не тронуты — фраза формально исправна,
    # а на деле бессмысленна. Ловится по регистру: имена Hypixel пишет с Заглавной,
    # значит строчное английское слово посреди русского текста именем не бывает.
    # Кириллица с ОБЕИХ сторон отсекает законные случаи — «the» внутри «Aspect
    # of the End» окружено латиницей, а URL и вставки вроде «C'est magnifique»
    # стоят среди своих же слов. На корпусе признак дал 5 находок и 0 ложных.
    for match in LOWER_EN.finditer(plain_ru):
        word = match.group(0)
        if word in ALLOW_LATIN or word in guarded_lower(guarded):
            continue
        left = plain_ru[:match.start()].split()[-1:] or [""]
        right = plain_ru[match.end():].split()[:1] or [""]
        if CYRILLIC.search(left[0]) and CYRILLIC.search(right[0]):
            found.append((SUSPECT, "английское слово осталось непереведённым",
                          f"{word!r} в {plain_ru[:56]!r}"))
            break

    gone = check_block([src], [plain_ru], guarded)
    if gone:
        found.append((BROKEN, "защищённое имя переведено", f"{', '.join(gone)} в {pair}"))

    # --- поводы посмотреть глазами ---

    # Только когда значки на месте: если значок просто выброшен, порядок и так
    # разойдётся, и вторая жалоба на ту же запись — чистый шум.
    if not lost and any(marks_after_holes(src)) \
            and marks_after_holes(src) != marks_after_holes(ru):
        found.append((SUSPECT, "дырки {n} могли переставиться", pair))

    if src == ru:
        found.append((SUSPECT, "перевод совпал с оригиналом", repr(src[:60])))
    elif not CYRILLIC.search(ru) and len(LATIN_WORD.findall(ru)) >= 2:
        # Названия предметов сюда попадут тоже — это подсказка, а не приговор
        found.append((SUSPECT, "осталось английским", repr(ru[:60])))

    if ru.count("(") != ru.count(")") or ru.count("[") != ru.count("]"):
        found.append((SUSPECT, "скобки не сошлись", repr(ru[:60])))

    # Русский длиннее английского примерно на четверть. Втрое — это уже
    # не перевод, а пересказ: абзац раздуется в лишние строки на экране.
    if len(src) >= 25:
        ratio = len(ru) / len(src)
        if ratio > 1.9:
            found.append((SUSPECT, f"перевод длиннее в {ratio:.1f} раза", pair))
        elif ratio < 0.5:
            found.append((SUSPECT, f"перевод короче в {1 / ratio:.1f} раза", pair))

    # Регистр не в счёт: Hypixel пишет «Speed» с большой буквы, а по-русски
    # внутри фразы это «скорость» с маленькой. Сверять посимвольно — значит
    # получить сотни ложных тревог и похоронить в них настоящие.
    ru_lower = ru.lower()
    for term, pattern, expected_lower, expected in term_patterns(terms):
        if pattern.search(src) and expected_lower not in ru_lower:
            misses[f"{term} -> {expected}"] += 1

    return found


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Проверка качества перевода")
    parser.add_argument("file")
    parser.add_argument("--show", type=int, default=6,
                        help="сколько примеров на каждую беду (0 — все)")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path
    data = json.loads(path.read_text(encoding="utf-8"))

    from protected import collect, resolve_collisions
    guarded = resolve_collisions(collect(), quiet=True)
    terms = glossary_terms()
    misses: Counter = Counter()
    found: list[tuple[str, str, str]] = []
    checked = 0
    # разные оригиналы с одинаковым переводом — потеря смысла
    by_translation: dict[str, set[str]] = defaultdict(set)

    paragraphs = data.get("paragraphs") or []
    blocks = data.get("tooltips") or []

    if paragraphs:
        done = [p for p in paragraphs if p.get("ru")]
        print(f"формат: абзацы. переведено {len(done)} из {len(paragraphs)}\n")
        for para in done:
            checked += 1
            found += check_pair(para["text"], para["ru"], guarded, terms, misses)
            by_translation[para["ru"]].add(para["text"])
    elif blocks:
        done = [b for b in blocks if b.get("ru")]
        print(f"формат: блоки построчно. переведено {len(done)} из {len(blocks)}\n")
        for block in done:
            src_lines, ru_lines = block["lines"], block["ru"]
            if len(src_lines) != len(ru_lines):
                found.append((BROKEN, "число строк не совпало",
                              f"{block.get('item')}: {len(src_lines)} -> {len(ru_lines)}"))
                continue
            for src, ru in zip(src_lines, ru_lines):
                # Пустая строка — это отступ. Он обязан остаться отступом.
                if (not src.strip()) != (not ru.strip()):
                    found.append((BROKEN, "отступы съехали", f"{src[:40]!r} -> {ru[:40]!r}"))
                    continue
                if not src.strip():
                    continue
                checked += 1
                found += check_pair(src, ru, guarded, terms, misses)
                by_translation[ru].add(src)
    else:
        print(f"в файле нет ни абзацев, ни блоков: {path}")
        return 1

    if not checked:
        print("переводить ещё нечего — проверять тоже")
        return 0

    for russian, sources in by_translation.items():
        if len(sources) > 1:
            found.append((SUSPECT, "разные оригиналы, один перевод",
                          f"{russian[:46]!r} <- " + " | ".join(repr(s[:34]) for s in sources)))

    # --- отчёт ---
    buckets: dict[str, dict[str, list[str]]] = {BROKEN: defaultdict(list),
                                                SUSPECT: defaultdict(list)}
    for bucket, kind, detail in found:
        buckets[bucket][kind].append(detail)

    for bucket in (BROKEN, SUSPECT):
        kinds = buckets[bucket]
        total = sum(len(v) for v in kinds.values())
        print(f"=== {bucket}: {total} ===")
        if not total:
            print("  ничего\n")
            continue
        for kind, items in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
            print(f"\n  {kind}: {len(items)}")
            limit = len(items) if args.show == 0 else args.show
            for detail in items[:limit]:
                print(f"     {detail}")
            if len(items) > limit:
                print(f"     ... ещё {len(items) - limit} (--show 0 покажет все)")
        print()

    print("=== термины мимо глоссария ===")
    if misses:
        for term, count in misses.most_common(10):
            print(f"   {count:4}x  {term}")
        print("   (может быть и нормально: падеж, синоним, другое место во фразе)")
    else:
        print("   расхождений нет")

    broken = sum(len(v) for v in buckets[BROKEN].values())
    suspect = sum(len(v) for v in buckets[SUSPECT].values())
    print(f"\nзаписей проверено: {checked}")
    print(f"СЛОМАНО: {broken}   ПОДОЗРИТЕЛЬНО: {suspect}")
    print("\n⚠️ Складность формулировок этим не проверяется — только глазами "
          "или вторым проходом модели.")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
