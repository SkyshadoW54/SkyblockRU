# -*- coding: utf-8 -*-
"""
Цвет ЗНАЧКА — по данным сервера, а не по правилу из головы.

Просьба игрока 01.08: «возьми все значки, которые знаешь, и добавь железное
правило: если значок встречается в описании, он обязан быть такого-то цвета».
Идея верная, но проверка показала, что железным правило бывает НЕ ДЛЯ ВСЕХ:

    ❣  U+2763   §4  100%   <- железно
    ☯  U+262F   §3  100%   <- железно
    ✦  U+E022   §f  100%   <- железно (это Speed, он и правда всегда белый)
    ❤  U+E010   §c   86%   <- НЕ железно: в 14% случаев цвет другой
    ⚔  U+2694   §8   58%   <- зависит от места в строке

Поэтому берём только те, где цвет один в 90% случаев и наблюдений хотя бы 20.
Остальные оставляем как есть: покрасить их «по правилу» значило бы завести
ровно ту эвристику, от которой уходим.

Источники — живые раскладки из игры (`paragraph-colors.json`) и лор аукциона
(`auction_lore.json`): в обоих цвет проставлен САМИМ Hypixel.

    python tools/icon_colors.py          показать таблицу и что изменится
    python tools/icon_colors.py --yes    применить к корпусу
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
LIVE = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/paragraph-colors.json")
AUCTION = ROOT / "data" / "work" / "auction_lore.json"

NAME_TO_CODE = {"black": "0", "dark_blue": "1", "dark_green": "2", "dark_aqua": "3",
                "dark_red": "4", "dark_purple": "5", "gold": "6", "gray": "7",
                "dark_gray": "8", "blue": "9", "green": "a", "aqua": "b",
                "red": "c", "light_purple": "d", "yellow": "e", "white": "f"}
# значки Hypixel: приватная зона плюс символьные блоки, откуда он их берёт
ICON = re.compile(r"[\ue000-\uf8ff\u2600-\u27bf\u2b00-\u2bff]")
CODES = re.compile("§.")
SPACE = re.compile(r"\s+")

# ⚠️ Пороги. Цвет значка бывает разным (у «⚔» устойчивость всего 58%),
# и красить такие «по правилу» — это вернуть эвристику. Берём только те,
# где сервер сам почти не колеблется.
MIN_SHARE = 0.9
MIN_SEEN = 20


def plain(text: str) -> str:
    return SPACE.sub(" ", CODES.sub("", text)).strip()


def observed() -> dict[str, Counter]:
    """Значок -> сколько раз каким цветом его красил Hypixel."""
    seen: dict[str, Counter] = defaultdict(Counter)
    if LIVE.exists():
        for case in (json.loads(LIVE.read_text(encoding="utf-8")).get("cases") or []):
            for colour, text in (case.get("pieces") or []):
                for char in ICON.findall(str(text)):
                    seen[char][NAME_TO_CODE.get(colour, "?")] += 1
    if AUCTION.exists():
        raw = AUCTION.read_text(encoding="utf-8")
        for match in re.finditer(r"§([0-9a-f])((?:(?!§)[^\"])*)", raw):
            for char in ICON.findall(match.group(2)):
                seen[char][match.group(1)] += 1
    return seen


def steady(seen: dict[str, Counter]) -> dict[str, str]:
    out = {}
    for char, counts in seen.items():
        total = sum(counts.values())
        code, best = counts.most_common(1)[0]
        if total >= MIN_SEEN and best / total >= MIN_SHARE and code != "?":
            out[char] = code
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Цвет значков по данным сервера")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    seen = observed()
    table = steady(seen)
    print("значков встречено: %d, из них цвет УСТОЙЧИВ: %d" % (len(seen), len(table)))
    for char, code in sorted(table.items(), key=lambda kv: -sum(seen[kv[0]].values())):
        counts = seen[char]
        total = sum(counts.values())
        print("   U+%04X  §%s   %5d встреч, %.0f%% одного цвета"
              % (ord(char), code, total, 100 * counts[code] / total))

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    fixed, touched = 0, 0
    for para in doc.get("paragraphs") or []:
        ru = para.get("ru")
        if not ru:
            continue
        out, changed = ru, 0
        for char, code in table.items():
            # значок уже покрашен верно — не трогаем
            wrong = re.compile(r"§(?!" + code + r")[0-9a-f]([^§]*?)" + re.escape(char))
            def repaint(match, code=code, char=char):
                return "§" + code + match.group(1) + char
            new = wrong.sub(repaint, out)
            if new != out:
                changed += 1
                out = new
        if changed and plain(out) == plain(ru):
            para["ru"] = out
            fixed += 1
            touched += changed
    print()
    print("абзацев с чужим цветом значка: %d (мест: %d)" % (fixed, touched))
    if not args.yes:
        print("\nсухой прогон. Применить: --yes")
        return 0
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("применено (правились только §-коды)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
