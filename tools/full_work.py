# -*- coding: utf-8 -*-
"""
Сколько в «работе» режима НАСТОЯЩЕЙ работы — разбор выгрузки `full_coverage`.

Вопрос игрока 23.08: «реально ли там 26 тысяч». По опыту проекта ответ почти
всегда «нет», и записан он четырежды: общий счётчик меряет РАЗМЕР ДАННЫХ.
Здесь тот же разбор по слоям, но уже ВНУТРИ слоя «ПЕРЕВОД».

    python tools/full_coverage.py --dump data/work/cov_rows.json
    python tools/full_work.py data/work/cov_rows.json
    python tools/full_work.py data/work/cov_rows.json --layer поштучно --limit 40

⚠️ Работает по ВЫГРУЗКЕ, а не гоняет движок заново: замер идёт минут двадцать,
а разбирать его хочется много раз и с разных сторон.

Что вычитается и почему (замер 23.08, 26 805 -> ~11 000):

| слой | почему не поштучная работа |
|---|---|
| дубль между источниками | одна фраза приходит и в `item_lore`, и в `item_name` |
| обрывок лора | полфразы от переноса: лечится абзацем, покупать ВРЕДНО |
| семья | 499 правил и развёрток закрывают 7818 строк |
| «имя + римский уровень» | уровни навыков, бестиария, коллекций — правило |
| ник, заглушка, одни числа | переводить нечего |

⚠️ **ВЫРОЖДЕННЫЙ СКЕЛЕТ СЕМЬЁЙ НЕ СЧИТАЕТСЯ.** «‹имя›» и «‹имя›!» — это просто
одиночные слова, рамки для правила у них нет. Без этой оговорки в «семьи»
уезжали 4033 строки, и отчёт обещал закрыть правилами то, по чему правило
писать не на что. Записанная грабля порога.

⚠️ **Остаток — ВЕРХНЯЯ граница, а не точное число.** В нём остаются ники
(«GlitchMoustache's Island»), разделители и строки чужих языков; отделить их
машинно нечем — это уже глазами, пачками, как и весь ручной перевод.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import find_families as ff  # noqa: E402
import pick_queue  # noqa: E402

# ⚠️ Скелет из одного «имени» — не семья: правило писать не на что.
DEGENERATE = re.compile(r"^<имя>[^\w<]*$")
# «Alchemy IV», «Bestiary Milestone CCCV» — уровень, а не отдельная строка.
ROMAN_TAIL = re.compile(r"^(.+?)\s+[IVXLCDM]{1,8}$")
# Заглушка чужого формата: «[Lvl {LVL}] Mole». Ключ с ней не совпадёт никогда.
PLACEHOLDER = re.compile(r"\{[A-Z_]{2,}\}")
# Строка без слов: одни числа, дырки и знаки.
NUMS_ONLY = re.compile(r"^[\W\d{}nsk/%+.,-]*$")
# Ник, уже обобщённый числами: «{n}c{n}e{n}a{n}'s Head».
NICK = re.compile(r"[A-Za-z]*\{n\}[A-Za-z]*\{n\}")

FRAGMENT = "обрывок лора (лечится абзацем)"
FAMILY = "в семье (правило или развёртка)"
ALONE = "поштучно"


def is_fragment(line: str, sources: set[str]) -> bool:
    """
    Полфразы, разрезанной переносом по ширине окна.

    ⚠️ Только для `item_lore`: перенос есть там, где Hypixel режет описание.
    В однострочном источнике признак записывает в обрывки законные подписи —
    это уже отдельная запись в CLAUDE.md.

    ⚠️ Здесь он нужен ВТОРОЙ раз, потому что `pick_queue.classify` спрашивает
    про жаргон и зачарования РАНЬШЕ обрывка: строка «Your Axe gains +{n} ☯
    Sweep on» уходит в «жаргон», а в режиме жаргон переводится — и полфразы
    оказывается работой. Замер: так всплыло 1965 строк.
    """
    if "item_lore" not in sources:
        return False
    text = line.strip()
    if not pick_queue.ENDS.search(text) and len(pick_queue.words_only(text)) >= 3:
        return True
    first = next((ch for ch in text if ch.isalpha()), "")
    return bool(first and first.islower()
                and not pick_queue.STARTS_WITH_HOLE.match(text))


def split(rows: list[dict]) -> tuple[dict[str, str], dict[str, int], list[str]]:
    """Разложить работу по непересекающимся слоям."""
    work: dict[str, set[str]] = {}
    for row in rows:
        if row["layer"] == "ПЕРЕВОД":
            work.setdefault(row["line"], set()).add(row["source"])

    families = collections.defaultdict(list)
    for line in work:
        families[ff.skeleton(line)].append(line)
    family_of = {line: skel for skel, lines in families.items()
                 if len(lines) >= 3 and not DEGENERATE.match(skel)
                 for line in lines}

    layer: dict[str, str] = {}
    seen: dict[str, int] = collections.Counter()
    alone: list[str] = []
    for line in sorted(work):
        if is_fragment(line, work[line]):
            layer[line] = FRAGMENT
        elif line in family_of:
            layer[line] = FAMILY
            seen[family_of[line]] += 1
        else:
            layer[line] = ALONE
            alone.append(line)
    return layer, seen, alone


def sift(alone: list[str]) -> tuple[collections.Counter, list[str]]:
    """Отсеять из поштучного то, что переводить нечего."""
    out = collections.Counter()
    rest = []
    for line in alone:
        text = line.strip()
        if PLACEHOLDER.search(text):
            out["заглушка чужого формата"] += 1
        elif NUMS_ONLY.match(text):
            out["одни числа и знаки"] += 1
        elif NICK.search(text):
            out["похоже на ник"] += 1
        elif ROMAN_TAIL.match(text) and len(text.split()) <= 4:
            out["«имя + римский уровень»"] += 1
        else:
            rest.append(line)
    return out, rest


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dump", help="выгрузка tools/full_coverage.py --dump")
    parser.add_argument("--layer", help="показать строки слоя")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--out", help="записать остаток поштучной работы")
    args = parser.parse_args()

    rows = json.loads(Path(args.dump).read_text(encoding="utf-8"))["rows"]
    pairs = sum(1 for row in rows if row["layer"] == "ПЕРЕВОД")
    layer, seen, alone = split(rows)
    junk, rest = sift(alone)

    print("«работа» в замере (пары источник+строка): %6d" % pairs)
    print("РАЗНЫХ ТЕКСТОВ:                           %6d   (дублей %d)"
          % (len(layer), pairs - len(layer)))
    print("=" * 62)
    counts = collections.Counter(layer.values())
    for name in (FRAGMENT, FAMILY, ALONE):
        print("  %-38s %6d" % (name, counts[name]))
    print("  из поштучного отсеивается:")
    for name, count in junk.most_common():
        print("      %-34s %6d" % (name, count))
    print("=" * 62)
    print("  семей: %d (закрывают %d строк)" % (len(seen), counts[FAMILY]))
    print("  ПОШТУЧНАЯ РАБОТА, верхняя граница:      %6d" % len(rest))

    if args.layer:
        chosen = ([l for l, name in layer.items() if name == args.layer]
                  if args.layer != "остаток" else rest)
        print("\n=== %s: %d ===" % (args.layer, len(chosen)))
        for line in chosen[:args.limit]:
            print("   %s" % line[:90])

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"_comment": "поштучная работа режима full, см. tools/full_work.py",
             "exact": {line: "" for line in rest}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print("\nзаписано:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
