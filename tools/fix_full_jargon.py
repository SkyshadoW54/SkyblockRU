# -*- coding: utf-8 -*-
"""Русский жаргон характеристик в УЖЕ ГОТОВЫХ режимных абзацах.

⚠️ ЗАЧЕМ. В режиме `full` жаргон (`Farming Fortune`, `Magic Find`, `Sweep`)
переводится — это записанное решение. Но режимные абзацы заводились в разные
дни и разными поводами: часть завели ради ИМЕНИ («Ступенчатый бонус: Feast»),
часть ради заголовка, — и жаргон внутри них так и остался английским. Замер
05.09: **373 режимных абзаца** из 3556 несут английский жаргон, то есть
крупнейшая дырка режима. Игрок видит «Даёт +{n} Farming Fortune при сборе»
в подсказке, где всё остальное по-русски.

⚠️ ПЛАТИТЬ НЕ НАДО: текст уже переведён и вычитан, менять надо ОДИН термин
и падеж вокруг него. Падеж тут выводится — управляющее слово стоит рядом
(«Даёт +5» родительный, «к» дательный, подпись со значением именительный),
и всю эту работу давно делает `full_prefill.swap`. Своей копии не заводим:
копия признака в этом проекте расходилась трижды и всегда молча.

⚠️ ЧЕТЫРЕ СВЕРКИ, и каждая от живой беды проекта:
  * число дырок `{n}`/`{s}` обязано совпасть — `fillNumbers` подставляет их
    ПО ПОРЯДКУ, и потерянная дырка получит чужое число;
  * набор ЗНАЧКОВ обязан совпасть — они невидимы в терминале и гибли уже
    четырежды;
  * число §-кодов обязано совпасть — подстановка не смеет трогать разметку;
  * в переводе не должно появиться латиницы там, где её не было.

    python tools/fix_full_jargon.py            покажет
    python tools/fix_full_jargon.py --yes      применит
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

import full_prefill  # noqa: E402

MODE = ROOT / "data" / "work" / "full_paragraphs_ru.json"
CODE = re.compile("\u00a7.")
HOLE = re.compile(r"\{[nsi]\d*\}")
LATIN = re.compile(r"[A-Za-z]")


def icons(text: str) -> list[str]:
    """Значки строки: приватная зона и символы категории So."""
    return [ch for ch in text
            if 0xE000 <= ord(ch) <= 0xF8FF
            or unicodedata.category(ch) == "So"]


def safe(before: str, after: str) -> str:
    """Пусто, если подстановка законна; иначе — причина отказа."""
    if HOLE.findall(before) != HOLE.findall(after):
        return "дырки разошлись"
    if icons(before) != icons(after):
        return "значки разошлись"
    if len(CODE.findall(before)) != len(CODE.findall(after)):
        return "разметка разошлась"
    if LATIN.search(after) and not LATIN.search(before):
        return "появилась латиница"
    return ""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Русский жаргон в режимных абзацах")
    parser.add_argument("--yes", action="store_true", help="применить")
    parser.add_argument("--show", type=int, default=8)
    args = parser.parse_args()

    data = json.loads(MODE.read_text(encoding="utf-8"))
    rows = data["rows"]
    names = full_prefill.table()
    order = sorted(names, key=len, reverse=True)

    fixed, refused, samples = 0, {}, []
    for key, row in rows.items():
        russian = row.get("ru") or ""
        if not russian:
            continue
        text = russian
        for name in order:
            text = full_prefill.swap(text, name, names[name])
        if text == russian:
            continue
        why = safe(russian, text)
        if why:
            refused[why] = refused.get(why, 0) + 1
            continue
        if len(samples) < args.show:
            samples.append((russian, text))
        fixed += 1
        if args.yes:
            row["ru"] = text

    print(f"абзацев поправится: {fixed}")
    for why, count in sorted(refused.items(), key=lambda kv: -kv[1]):
        print(f"   отказ — {why}: {count}")
    for before, after in samples:
        print("   было : " + before[:120].replace("\u00a7", "&"))
        print("   стало: " + after[:120].replace("\u00a7", "&"))
    if not args.yes:
        print("\nСУХОЙ ПРОГОН. Применить: --yes")
        return 0
    MODE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nзаписано. Дальше: python tools/gen_full_paragraphs.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
