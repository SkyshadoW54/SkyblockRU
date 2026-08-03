"""
Записи для полосы над хотбаром — ПО КОЛОНКАМ, а не на всю строку целиком.

Полоса собрана из колонок через несколько пробелов, и середина всё время
разная: защита, опыт навыка, локация, DPS, задание. Правил на каждое
сочетание нужны были бы десятки, и Hypixel добавляет новые. Мод теперь
переводит колонки по отдельности, значит и записи нужны на колонку.

Иконки:  сердце,  защита,  мана,  локация.

Запуск:  python tools/add_actionbar.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "ru_ru" / "20-ui.json"

HEART, SHIELD, MANA, PLACE = "", "", "", ""

EXACT = {
    f"{{n}}{SHIELD} Defense": f"{{n}}{SHIELD} Защита",
    f"{{n}}/{{n}}{MANA} Mana": f"{{n}}/{{n}}{MANA} Мана",
    "{n} DPS": "{n} урона/с",
    "{n} second": "{n} с",
    "{n} seconds": "{n} с",
    # Snow Cannon: игрок сидит на пушке, стреляет и слезает. Что это именно
    # пушка, видно из чата («☃ You dismounted the Snow Cannon!»), а не из самой
    # колонки. Слово FIRE переводим «выстрел» — так уже переведена соседняя
    # строка той же пушки: «RIGHT-CLICK to shoot.» -> «ПКМ — выстрел.»
    "SHIFT to DISMOUNT": "ШИФТ — слезть",
    "RIGHT-CLICK to FIRE": "ПКМ — выстрел",
    "{n}s to FIRE": "{n} с до выстрела",
    # График цены на базаре. Целой строкой перевод уже куплен, но игрок видит
    # её и разрезанной на колонки — тогда работают только эти две записи.
    "Left-Click to switch span": "ЛКМ — сменить период",
    "Right-Click to zoom": "ПКМ — масштаб",
}

RULES = [
    {
        "_": ("Прибавка опыта навыка. Название навыка — в захвате с tg=true: "
              "оно переводится по словарю, поэтому одно правило закрывает все "
              "навыки сразу, а не по правилу на каждый."),
        "p": r"^\+([\d,]+) ([A-Za-z]+) \(([\d,.]+)/([\d,.]+k?)\)$",
        "r": "+$1 $2 ($3/$4)",
        "tg": True,
    },
    {
        "_": "Опыт SkyBlock с пояснением в скобках — само пояснение не трогаем",
        "p": r"^\+([\d,]+) SkyBlock XP \((.+)\) \(([\d,.]+)/([\d,.]+)\)$",
        "r": "+$1 опыта SkyBlock ($2) ($3/$4)",
    },
    {
        "_": "Прибавка опыта без скобок",
        "p": r"^\+([\d,]+) ([A-Za-z]+) XP$",
        "r": "+$1 опыта: $2",
        "tg": True,
    },
]

# Живые колонки из дампа
TESTS = [
    f"{{n}}{SHIELD} Defense",
    f"{{n}}/{{n}}{MANA} Mana",
    "+36 Foraging (3,308/5k)",
    "+4 Combat (120/5k)",
    "SHIFT to DISMOUNT",
    "RIGHT-CLICK to FIRE",
]

GROUP = re.compile(r"\$(\d)")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    pack.setdefault("exact", {})
    pack.setdefault("regex", [])

    added_exact = {k: v for k, v in EXACT.items() if k not in pack["exact"]}
    pack["exact"].update(added_exact)

    have = {rule["p"] for rule in pack["regex"]}
    added_rules = [rule for rule in RULES if rule["p"] not in have]
    pack["regex"].extend(added_rules)

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"строк добавлено: {len(added_exact)}, правил добавлено: {len(added_rules)}\n")

    for text in TESTS:
        if text in pack["exact"]:
            print(f"  {text!r}\n    -> {pack['exact'][text]!r}  (точное совпадение)")
            continue
        for rule in pack["regex"]:
            match = re.match(rule["p"], text)
            if match:
                result = GROUP.sub(lambda m: match.group(int(m.group(1))), rule["r"])
                note = " (навык переведётся по словарю)" if rule.get("tg") else ""
                print(f"  {text!r}\n    -> {result!r}{note}")
                break
        else:
            print(f"  {text!r}\n    -> НЕ СОВПАЛО")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
