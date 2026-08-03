# -*- coding: utf-8 -*-
"""
Перенос перевода на ВАРИАНТЫ того же абзаца — бесплатно, без API.

Один и тот же текст попадает в корпус несколькими ключами: Hypixel режет его
по ширине окна ИГРОКА, добавляет «✯» перку министра, меняет регистр слова
(«rabbits» / «Rabbits»). Ключ абзаца строится по тексту, поэтому каждый такой
вариант — отдельная запись, и переведён обычно ОДИН из них. На экране это
выглядит как «перевод пропал»: игрок прислал подсказки кандидатов в мэры,
где половина перков английская, хотя все девять давно переведены.

Признак совпадения нарочно СТРОГИЙ: снимаем «✯», схлопываем пробелы и
сравниваем без учёта регистра. Всё остальное обязано совпасть знак в знак —
иначе перенесём перевод на другой текст. Так «Schedules an extra Spooky
Festival» не станет переводом для «...an extra Fishing Festival»: сервер
переписал перк, и это РАЗНЫЕ вещи, хоть и похожие.

    python tools/fill_variants.py          показать, что перенесётся
    python tools/fill_variants.py --yes    применить
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pkey  # noqa: E402

CORPUS = ROOT / "data" / "work" / "paragraphs.json"
CODES = re.compile("§.")
# знак перка министра: он есть у одного варианта и нет у другого
STAR = "✯"


def shape(text: str) -> str:
    """Ключ без того, что Hypixel меняет от случая к случаю."""
    plain = CODES.sub("", text).replace(STAR, " ")
    return re.sub(r"\s+", " ", plain).strip().lower()


def with_star(ru: str, need: bool) -> str | None:
    """Подогнать звезду перевода под оригинал. None — если подогнать нельзя."""
    has = STAR in ru
    if has == need:
        return ru
    if need:
        # звезду ставим В НАЧАЛО, перед первым видимым знаком, сохраняя коды
        match = re.match(r"^((?:§.)*)(.*)$", ru, re.S)
        return f"{match.group(1)}{STAR} {match.group(2)}"
    # звезда есть, а в оригинале её нет — убираем вместе с пробелом за ней
    return re.sub(re.escape(STAR) + r"\s*", "", ru, count=1)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Перенос перевода на варианты абзаца")
    parser.add_argument("--yes", action="store_true", help="применить")
    parser.add_argument("--show", type=int, default=15)
    args = parser.parse_args()

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = doc.get("paragraphs") or []

    # доноры: у кого перевод есть. Если у одной формы доноров несколько
    # и переводы разные — не берём ни один: угадывать, какой верен, нельзя.
    donors: dict[str, str | None] = {}
    for para in paragraphs:
        ru = para.get("ru")
        if not ru:
            continue
        key = shape(pkey.key_of(para.get("lines") or []))
        if key in donors and donors[key] is not None and shape(donors[key]) != shape(ru):
            donors[key] = None
        else:
            donors.setdefault(key, ru)

    filled, skipped_star, ambiguous = [], 0, 0
    for para in paragraphs:
        if para.get("ru") or para.get("nothing"):
            continue
        raw = pkey.key_of(para.get("lines") or [])
        key = shape(raw)
        donor = donors.get(key)
        if donor is None:
            if key in donors:
                ambiguous += 1
            continue
        ru = with_star(donor, STAR in raw)
        if ru is None:
            skipped_star += 1
            continue
        filled.append((para, raw, ru))

    print(f"абзацев без перевода: {sum(1 for p in paragraphs if not p.get('ru') and not p.get('nothing'))}")
    print(f"можно закрыть переводом ДРУГОГО варианта: {len(filled)}")
    if ambiguous:
        print(f"  пропущено (у формы разные переводы, гадать нельзя): {ambiguous}")
    print()
    for para, raw, ru in filled[:args.show]:
        print(f"   {raw[:64]}")
        print(f"      -> {ru[:64]}")
    if len(filled) > args.show:
        print(f"   ... ещё {len(filled) - args.show}")

    if not args.yes:
        print("\nсухой прогон. Применить: --yes")
        return 0

    for para, _raw, ru in filled:
        para["ru"] = ru
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано переводов: {len(filled)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
