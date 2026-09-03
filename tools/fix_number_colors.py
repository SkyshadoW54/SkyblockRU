# -*- coding: utf-8 -*-
"""
Возвращает ЦВЕТ ЧИСЛУ в размеченных переводах — по данным сервера.

⚠️ Что видно на экране (скриншот игрока 03.09, питомец Mooshroom Cow):
у Hypixel «Grants §6+0.7☘ Farming Fortune §7for every §c39.8 §c❁ Strength»,
а у нас «за каждые 39.8 §cСилы» — значок и слово красные, а САМО ЧИСЛО серое.
Так же у Hedgehog и у полусотни других подсказок.

Причина не в моде: разметку ставила модель вокруг СЛОВ перевода, а число
рядом с ними оставалось в куске цвета тела. Мод раскладывает ровно по кодам
перевода и ничего не выдумывает — значит чинить надо разметку.

⚠️ ИСТИНА БЕРЁТСЯ У СЕРВЕРА, а не на глаз: цвет каждого числа известен из
лора аукциона (§-коды) и из живых раскладок `dump/paragraph-colors.json`.
Сопоставляем ПО ПОЗИЦИЯМ: набор чисел ключа и перевода совпадает по порядку
(числа переживают перевод дословно). Не совпал — абзац не трогаем вовсе.

⚠️ Правим ТОЛЬКО там, где у нас стоит цвет ТЕЛА: если разметка уже дала числу
свой цвет, значит решение принято и спорить с ним нечем. И не трогаем случаи,
где сервер красит число серым — там и так тело.

Запуск:
  python tools/fix_number_colors.py           сухой прогон
  python tools/fix_number_colors.py --yes     применить
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
AUCTION = ROOT / "data" / "work" / "auction_lore.json"
LIVE = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/paragraph-colors.json")

NAMED = {"black": "0", "dark_blue": "1", "dark_green": "2", "dark_aqua": "3",
         "dark_red": "4", "dark_purple": "5", "gold": "6", "gray": "7",
         "dark_gray": "8", "blue": "9", "green": "a", "aqua": "b", "red": "c",
         "light_purple": "d", "yellow": "e", "white": "f"}

NUMBER = re.compile(r"[+\-]?\d[\d,.]*%?")
HOLE = re.compile(r"[+\-]?\{n\}%?")
COLOR = re.compile(r"§([0-9a-fk-or])")

# ⚠️ Серый и тёмно-серый НЕ ставим: это и есть цвет тела абзаца, добавлять
# для них код значило бы менять ничего и раздувать разметку.
BODYISH = {"7", "8"}


def generalize(text: str) -> str:
    sys.path.insert(0, str(ROOT / "tools"))
    import pkey
    return pkey.generalize(text)


def from_codes(lines: list[str]) -> list[tuple[str, str]]:
    """Пары «цвет, обобщённое число» из строк с §-кодами (лор аукциона)."""
    out: list[tuple[str, str]] = []
    current = "7"
    for line in lines:
        for part in re.split(r"(§[0-9a-fk-or])", line):
            if not part:
                continue
            if part.startswith("§"):
                if part[1] in "0123456789abcdef":
                    current = part[1]
                continue
            for match in NUMBER.finditer(part):
                out.append((current, generalize(match.group(0))))
    return out


def from_pieces(pieces: list[list[str]]) -> list[tuple[str, str]]:
    """То же из живых раскладок: там цвет лежит именем, а не кодом."""
    out: list[tuple[str, str]] = []
    for color, text in pieces:
        code = NAMED.get(str(color).split("+")[0], "7")
        for match in NUMBER.finditer(text):
            out.append((code, generalize(match.group(0))))
    return out


def our_holes(russian: str) -> tuple[str, list[tuple[str, int, str]]]:
    """Цвет тела и список «активный цвет, позиция, дырка» по переводу."""
    first = COLOR.match(russian)
    body = first.group(1) if first and first.group(1) in "0123456789abcdef" else "7"
    holes: list[tuple[str, int, str]] = []
    current = body
    at = 0
    while at < len(russian):
        code = COLOR.match(russian, at)
        if code:
            if code.group(1) in "0123456789abcdef":
                current = code.group(1)
            at = code.end()
            continue
        hole = HOLE.match(russian, at)
        if hole:
            holes.append((current, at, hole.group(0)))
            at = hole.end()
            continue
        at += 1
    return body, holes


def repaint(russian: str, wanted: list[tuple[str, str]]) -> str | None:
    """Перевод, где числу вернули цвет сервера. None — менять нечего."""
    body, holes = our_holes(russian)
    if len(holes) != len(wanted) or [h[2] for h in holes] != [w[1] for w in wanted]:
        return None
    out = russian
    changed = 0
    # идём С КОНЦА: вставка сдвигает позиции, и правка спереди испортила бы их
    for (colour, position, hole), (want, _) in zip(reversed(holes), reversed(wanted)):
        if want == colour or want in BODYISH or colour != body:
            continue
        out = out[:position] + "§" + want + hole + "§" + body + out[position + len(hole):]
        changed += 1
    return out if changed else None


def wanted_colors() -> dict[str, list[tuple[str, str]]]:
    """Ключ абзаца -> цвета его чисел, как их прислал сервер."""
    table: dict[str, list[tuple[str, str]]] = {}
    if AUCTION.exists():
        lore = json.loads(AUCTION.read_text(encoding="utf-8")).get("lore") or {}
        for key, lines in lore.items():
            table.setdefault(key, from_codes(lines))
    if LIVE.exists():
        for case in json.loads(LIVE.read_text(encoding="utf-8")).get("cases") or []:
            key = generalize(case.get("key") or "")
            # живые раскладки ТОЧНЕЕ аукциона: это то, что игрок видел сам
            table[key] = from_pieces(case.get("pieces") or [])
    return table


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="цвет числу по данным сервера")
    parser.add_argument("--yes", action="store_true", help="применить")
    parser.add_argument("--show", type=int, default=8)
    args = parser.parse_args()

    table = wanted_colors()
    print(f"абзацев, где цвет чисел известен от сервера: {len(table)}")

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    rows = doc["paragraphs"]
    changes: list[tuple[dict, str]] = []
    for row in rows:
        russian = row.get("ru")
        if not russian or "§" not in russian:
            continue
        wanted = table.get(row["text"])
        if not wanted:
            continue
        fixed = repaint(russian, wanted)
        if fixed:
            changes.append((row, fixed))

    numbers = sum(fixed.count("§") - row["ru"].count("§") for row, fixed in changes) // 2
    print(f"абзацев с непокрашенным числом: {len(changes)}  (чисел: {numbers})")
    for row, fixed in changes[:args.show]:
        print("   было : " + re.sub("§(.)", r"&\1", row["ru"])[:96])
        print("   стало: " + re.sub("§(.)", r"&\1", fixed)[:96])
        print()

    if not args.yes:
        print("сухой прогон. Применить: --yes")
        return 0

    for row, fixed in changes:
        row["ru"] = fixed
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"поправлено абзацев: {len(changes)}. Дальше: python tools/merge_paragraphs.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
