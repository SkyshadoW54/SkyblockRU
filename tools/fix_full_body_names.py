# -*- coding: utf-8 -*-
"""Имя в ТЕЛЕ режимного абзаца — подставить там, где падеж виден.

⚠️⚠️ ЗАЧЕМ. Жалоба игрока 07.09 со скриншотом Бэтфона: «Способность:
Whassup? ПКМ Позволяет позвонить Maddox» — рамка по-русски, имя английское.
Замер: **2077 абзацев** несут имя, которое режим переводит, а обычный словарь
нет. Заголовок закрывает `fix_full_headings`, таблицу падежей —
`gen_full_places`, а ТЕЛО абзаца не закрывал никто.

⚠️ ПАДЕЖ НЕ ГАДАЕМ. Подставляем ровно там, где он виден:
  * ИМЕНИТЕЛЬНЫЙ — позиция от `fix_full_headings.nominative_at` (начало
    строки, после двоеточия, после конца предложения);
  * падежные формы — только для имён из таблицы `gen_full_places.PLACES`,
    где формы заданы явно.
Всё прочее оставляем человеку: неверный падеж выглядит готовым текстом
и живёт сессиями — записанное правило проекта.

⚠️ ЗАЩИТЫ те же, что у соседей, и каждая от живой беды: `standalone`
(составное имя), `gender_safe` (согласуемое слово слева), сверка дырок,
значков и §-кодов.

    python tools/fix_full_body_names.py          покажет
    python tools/fix_full_body_names.py --yes    применит
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gen_full_paragraphs as skeleton   # noqa: E402
import gen_full_places as places         # noqa: E402
import fix_full_headings as headings     # noqa: E402

MODE = ROOT / "data" / "work" / "full_paragraphs_ru.json"
CODE = re.compile("\u00a7.")
HOLE = re.compile(r"\{[nsi]\d*\}")
LATIN = re.compile(r"[A-Za-z]")


def icons(text: str) -> list[str]:
    return [ch for ch in text
            if 0xE000 <= ord(ch) <= 0xF8FF
            or unicodedata.category(ch) == "So"]


def safe(before: str, after: str) -> str:
    if HOLE.findall(before) != HOLE.findall(after):
        return "дырки разошлись"
    if icons(before) != icons(after):
        return "значки разошлись"
    if len(CODE.findall(before)) != len(CODE.findall(after)):
        return "разметка разошлась"
    return ""


def put_nominative(text: str, name: str, russian: str) -> str:
    """Подставить имя в позициях ИМЕНИТЕЛЬНОГО, слева направо."""
    pattern = places.name_pattern(name) + r"(?![A-Za-z])"
    out, prev = [], 0
    for match in re.finditer(pattern, text):
        if match.start() < prev:
            continue
        if places.STOP.match(CODE.sub("", text[match.end():])):
            continue
        if not headings.nominative_at(text, match.start()):
            continue
        if not headings.gender_safe(text, match.start()):
            continue
        if not headings.standalone(text, match.start(), match.end()):
            continue
        out.append(text[prev:match.start()] + russian)
        prev = match.end()
    out.append(text[prev:])
    return "".join(out)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Имена в теле режимных абзацев")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--show", type=int, default=10)
    args = parser.parse_args()

    data = json.loads(MODE.read_text(encoding="utf-8"))
    rows = data["rows"]
    import status
    mode_dict = skeleton._MODE()

    fixed, refused, shown = 0, {}, 0
    for key, row in rows.items():
        russian = row.get("ru") or ""
        if not russian:
            continue
        names = skeleton.names_left(russian)
        if not names:
            continue
        text = russian
        # ⚠️ Длинные имена первыми: «Revenant Horror» раньше «Revenant»,
        # иначе половина имени останется английской.
        for name in sorted(names, key=len, reverse=True):
            forms = places.PLACES.get(name)
            if forms:
                text = places.substitute(text, name, forms)
                continue
            got = status.lookup(name, mode_dict, origin="item_lore")
            if not got or not got[0]:
                continue
            text = put_nominative(text, name, got[0])
        if text == russian:
            continue
        why = safe(russian, text)
        if why:
            refused[why] = refused.get(why, 0) + 1
            continue
        fixed += 1
        if shown < args.show:
            print("   было : " + CODE.sub("", russian)[:118])
            print("   стало: " + CODE.sub("", text)[:118])
            shown += 1
        if args.yes:
            row["ru"] = text

    print(f"\nабзацев поправится: {fixed}")
    for why, count in sorted(refused.items(), key=lambda kv: -kv[1]):
        print(f"   отказ — {why}: {count}")
    if not args.yes:
        print("\nСУХОЙ ПРОГОН. Применить: --yes")
        return 0
    MODE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("записано. Дальше: python tools/gen_full_paragraphs.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
