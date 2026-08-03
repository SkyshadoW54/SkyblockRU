# -*- coding: utf-8 -*-
"""
Цвет заголовка зачарования в переводе против ЖИВЫХ данных.

Hypixel красит заголовок по-разному у разных предметов, и в разметку перевода
цвет попадал «какой был у того предмета, с которого покупали». На чужом
предмете он выходит неверным — игрок прислал шлем, где «Wisdom V» стало
фиолетовым, хотя сервер шлёт серое. Проверяем по `dump/paragraph-colors.json`:
там мод записал цвет КАЖДОГО куска, который реально видел.

Считаем расхождением только те случаи, где цвет в данных ОДИН-единственный:
если Hypixel красит заголовок по-разному (обычное зачарование серое,
ультимативное фиолетовое), спорить не с чем.

    python tools/check_head_colors.py          показать расхождения
    python tools/check_head_colors.py --yes    поправить разметку
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

COLORS = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/paragraph-colors.json")
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
CODE = {"black": "0", "dark_blue": "1", "dark_green": "2", "dark_aqua": "3",
        "dark_red": "4", "dark_purple": "5", "gold": "6", "gray": "7",
        "dark_gray": "8", "blue": "9", "green": "a", "aqua": "b", "red": "c",
        "light_purple": "d", "yellow": "e", "white": "f"}
HEAD = re.compile(r"^[A-Z][A-Za-z' -]*\s[IVXLC]+$")
CODES = re.compile("§.")
SPACE = re.compile(r"\s+")


def plain(text: str) -> str:
    return SPACE.sub(" ", CODES.sub("", text)).strip()


def seen_colors() -> dict[str, dict[str, int]]:
    """Какими цветами Hypixel РЕАЛЬНО красит каждый заголовок и сколько раз."""
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if not COLORS.exists():
        return out
    cases = json.loads(COLORS.read_text(encoding="utf-8"))
    for case in (cases.get("cases") or cases):
        if not isinstance(case, dict):
            continue
        for colour, text in (case.get("pieces") or []):
            name = str(text).strip()
            if HEAD.match(name):
                out[name][colour] += 1
    return out


# ⚠️ Сколько раз надо УВИДЕТЬ цвет, чтобы считать его единственным.
#
# Цвет заголовка зависит от ПРЕДМЕТА: в живом дампе «Aqua Affinity I»
# и «Protection V» синие, а «Bank V» и «Growth V» серые — это записано
# в граблях проекта. Встретив заголовок один раз, мы не знаем, всегда ли
# он такой. Порог отсекает такие догадки: без него замер давал 206
# «расхождений», и почти все были случаями «видели один раз».
MIN_SEEN = 5


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Цвет заголовков против данных")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    known = seen_colors()
    if not known:
        print("нет dump/paragraph-colors.json — поиграй, мод его напишет")
        return 0
    steady = {name: next(iter(cols))
              for name, cols in known.items()
              if len(cols) == 1 and sum(cols.values()) >= MIN_SEEN}
    print("заголовков в живых данных: %d" % len(known))
    print("  из них цвет ОДИН и виден >= %d раз: %d" % (MIN_SEEN, len(steady)))

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    bad = []
    for para in doc.get("paragraphs") or []:
        ru = para.get("ru")
        if not ru:
            continue
        # заголовок в переводе: «§7§d§lWisdom V§7 …» — код(ы), имя, возврат
        for match in re.finditer(r"((?:§.)+)([A-Z][A-Za-z' -]*\s[IVXLC]+)", ru):
            codes, name = match.group(1), match.group(2)
            want = steady.get(name)
            if not want:
                continue
            want_code = CODE.get(want)
            colour = [c for c in re.findall("§(.)", codes) if c in CODE.values()]
            if not colour or colour[-1] == want_code:
                continue
            bad.append((para, match.group(0), colour[-1], want_code, name))

    print("заголовков с ЧУЖИМ цветом: %d" % len(bad))
    for _para, whole, got, want, name in bad[:12]:
        print("   %-22s в переводе §%s, а сервер шлёт §%s" % (name, got, want))

    if not bad or not args.yes:
        if bad:
            print("\nсухой прогон. Применить: --yes")
        return 0

    for para, whole, got, want, name in bad:
        fixed = whole.replace("§" + got, "§" + want, 1)
        new = para["ru"].replace(whole, fixed, 1)
        assert plain(new) == plain(para["ru"]), "текст менять нельзя"
        para["ru"] = new
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nпоправлено: %d (правился только цвет)" % len(bad))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
