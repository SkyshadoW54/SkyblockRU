"""
Правила для подсказок миньонов — глаголы берём ИЗ КОРПУСА, а не из головы.

Прошлый заход я написал правила под farming/killing/fishing, которых в игре
нет вовсе, и половина миньонов осталась английской. Глаголы теперь
вычитываются из data/work/lore_tooltips.json, поэтому промахнуться нельзя.

Запуск:  python tools/fix_minions.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "ru_ru" / "40-lore.json"
CORPUS = ROOT / "data" / "work" / "lore_tooltips.json"

# Перевод глагола. Ключи сверены с корпусом: chopping, harvesting, mining,
# shovelling, slaying, squashing, struggling — других там нет.
VERBS = {
    "mining": "добывать",
    "chopping": "рубить",
    "harvesting": "собирать",
    "shovelling": "копать",
    "slaying": "убивать",
    "squashing": "давить",
    # ⚠️ «struggling» стоит в паре с предлогом: «struggling with Revenants».
    # Переводился он как «добывать», и выходило «добывать с ревенантами».
    # Предлог живёт в захваченном куске, поэтому глагол берём непереходный.
    "struggling": "сражаться",
}


def corpus_verbs() -> set[str]:
    if not CORPUS.exists():
        return set()
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    found = set()
    for block in data.get("tooltips") or []:
        if "Minion" not in (block.get("item") or ""):
            continue
        for line in block["lines"]:
            match = re.match(r"^generating and (\w+)", line)
            if match:
                found.add(match.group(1))
    return found


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    actual = corpus_verbs()
    missing = actual - set(VERBS)
    if missing:
        print(f"! в корпусе есть глаголы без перевода: {sorted(missing)}")
    unused = set(VERBS) - actual
    if unused:
        print(f"  (в корпусе не встречаются, оставляю про запас: {sorted(unused)})")

    pack = json.loads(PACK.read_text(encoding="utf-8"))
    pack.setdefault("regex", [])
    pack.setdefault("exact", {})

    # Старые правила с выдуманными глаголами убираем — они только мешают.
    before = len(pack["regex"])
    pack["regex"] = [r for r in pack["regex"]
                     if not re.match(r"^\^generating and (farming|killing|fishing)", r.get("p", ""))]
    dropped = before - len(pack["regex"])

    # ⚠️ Предложение не всегда кончается вместе со строкой: у Rabbit Minion
    # «…slaying Rabbits!», а у Pig Minion «…slaying Pigs! Minions» — перенос
    # утащил начало следующей фразы на ту же строку. Правило с [.!]$ такие
    # строки не ловило, и половина миньонов оставалась английской.
    # Хвосты взяты из корпуса, их ровно два.
    TAILS = {"": "", "Minions": " Миньоны", "Requires": " Нужно"}

    rules = []
    for verb, translation in sorted(VERBS.items()):
        for tail, tail_ru in TAILS.items():
            suffix = rf" {tail}$" if tail else "$"
            rules.append({
                "_": (f"Миньон: «{verb}»" + (f", хвост «{tail}»" if tail else "")
                      + ". Материал — в захвате с tg=true: переводится, только "
                        "если есть в словаре. Названия с заглавной буквы там не "
                        "держим, поэтому остаются как в оригинале."),
                "p": rf"^generating and {verb} (.+)[.!]{suffix}",
                "r": f"создавать и {translation} $1!{tail_ru}",
                "tg": True,
            })

    # «Requires dirt or soil nearby so / carrots can be planted. Minions also»
    pack["exact"].update({
        "Requires dirt or soil nearby so": "Нужна земля или почва рядом, чтобы",
        "Requires an open area to place": "Нужно открытое место, чтобы ставить",
        # продолжения перенесённых фраз
        "also work when you are offline!": "также работают, даже когда ты не в сети!",
        "also work when you are": "также работают, даже когда ты",
    })
    rules.append({
        "_": "Продолжение после хвоста «Requires»: «an open area to place clay. Minions»",
        "p": r"^an open area to place (.+)\. Minions$",
        "r": "открытое место, чтобы ставить $1. Миньоны",
        "tg": True,
    })
    rules.append({
        "_": "«… can be planted. Minions also» — материал в захвате",
        "p": r"^(.+) can be planted\. Minions also$",
        "r": "сажать $1. Миньоны также",
        "tg": True,
    })
    rules.append({
        "_": "Хвост про открытое место с названием материала",
        "p": r"^Requires an open area to place (.+)$",
        "r": "Нужно открытое место, чтобы ставить $1",
        "tg": True,
    })

    have = {r["p"] for r in pack["regex"]}
    added = [r for r in rules if r["p"] not in have]
    pack["regex"].extend(added)
    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nубрано выдуманных правил: {dropped}")
    print(f"добавлено правил: {len(added)}, всего: {len(pack['regex'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
