# -*- coding: utf-8 -*-
"""
Размечает плоские переводы ПО СОБСТВЕННЫМ данным, а не по признакам.

Зачем. Цвет мы сейчас восстанавливаем эвристикой («кусок уцелел дословно —
красим его прежним цветом»), и это признано слабейшим подходом: у него нет
источника правды, поэтому правка одного случая ломает соседний. Игрок сказал
об этом прямо: «чинишь одно — ломается другое, я не могу каждый раз искать
такие баги».

Здесь источник правды есть — НАШИ ЖЕ размеченные абзацы. В них 8590 разных
кусков с проставленным цветом, и у 933 из них цвет ВСЕГДА один. Если «к силе»
в двухстах проверенных абзацах красное, то и в двести первом оно красное —
это не догадка, а счёт.

⚠️ Порог обязателен. У 89% кусков цвет РАЗНЫЙ в разных абзацах: «Даёт» бывает
серым и золотым, зависит от предмета. Берём только те, где цвет один и виден
не меньше MIN_SEEN раз — иначе перекрасим по случайному совпадению.

⚠️ Проверяется главное: ТЕКСТ НЕ МЕНЯЕТСЯ. Ставим только §-коды; если после
снятия кодов строка разошлась хоть на знак, правка отбрасывается.

    python tools/mark_by_known.py          показать, что разметится
    python tools/mark_by_known.py --yes    применить
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"

CODES = re.compile("§.")
SPACE = re.compile(r"\s+")
# кусок размеченного перевода: код и текст до следующего кода
PIECE = re.compile(r"§([0-9a-f])((?:(?!§).)+)")

# ⚠️ Сколько раз надо увидеть кусок ОДНОГО цвета, чтобы поверить.
# При 1–2 встречах это совпадение: цвет зависит от предмета и от соседей.
MIN_SEEN = 3
# Короткие куски не берём: «V», «10», «и» совпадут в любой фразе и раскрасят
# её клочьями. Тот же порог, что у переноса цвета в моде.
MIN_LENGTH = 4


def plain(text: str) -> str:
    return SPACE.sub(" ", CODES.sub("", text)).strip()


def steady_colours(marked: list[str]) -> dict[str, str]:
    """Кусок -> его цвет, но только если он ВСЕГДА один и виден часто."""
    seen: dict[str, Counter] = defaultdict(Counter)
    for ru in marked:
        for code, text in PIECE.findall(ru):
            core = text.strip()
            if len(core) >= MIN_LENGTH:
                seen[core][code] += 1
    return {core: counts.most_common(1)[0][0]
            for core, counts in seen.items()
            if len(counts) == 1 and sum(counts.values()) >= MIN_SEEN}


def paint(ru: str, known: dict[str, str], body: str = "§7") -> str | None:
    """Ставит коды известным кускам. Пересечения отбрасываем.

    ⚠️ Куски ЦВЕТА ТЕЛА пропускаем. Первый прогон обвесил §7 обычные слова
    («Нажми», «, чтобы», «твоего») — они и правда всегда серые, но тело и так
    серое, и разметка ничего не меняет, зато засоряет перевод и мешает
    следующим правкам. Красим ТОЛЬКО то, что от тела отличается.
    """
    places: list[tuple[int, int, str]] = []
    for core, code in known.items():
        if "§" + code == body:
            continue
        at = ru.find(core)
        if at < 0:
            continue
        if any(at < end and start < at + len(core) for start, end, _ in places):
            continue
        places.append((at, at + len(core), code))
    if not places:
        return None
    out = ru
    for start, end, code in sorted(places, reverse=True):
        out = out[:start] + "§" + code + out[start:end] + body + out[end:]
    return body + out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Разметка по собственным данным")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--show", type=int, default=8)
    args = parser.parse_args()

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = doc.get("paragraphs") or []
    marked = [p["ru"] for p in paragraphs if p.get("ru") and "§" in p["ru"]]
    known = steady_colours(marked)
    print("размеченных абзацев: %d" % len(marked))
    print("устойчивых пар «кусок -> цвет» (>=%d встреч, цвет один): %d"
          % (MIN_SEEN, len(known)))

    done, skipped = [], 0
    for para in paragraphs:
        ru = para.get("ru")
        if not ru or "§" in ru:
            continue
        painted = paint(ru, known)
        if not painted:
            continue
        if plain(painted) != plain(ru):
            skipped += 1
            continue
        done.append((para, painted))

    print()
    print("разметится абзацев: %d" % len(done))
    if skipped:
        print("  отброшено (текст разошёлся): %d" % skipped)
    for para, painted in done[:args.show]:
        print("   %s" % painted[:88])

    if not args.yes:
        print("\nсухой прогон. Применить: --yes")
        return 0

    for para, painted in done:
        para["ru"] = painted
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nразмечено: %d (правились только §-коды)" % len(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
