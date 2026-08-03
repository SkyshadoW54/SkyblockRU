"""
Правила для диалогов заданий: NPC просит принести предметы.

Главное здесь — имя предмета попадает в ЗАХВАТ правила, а захваты по умолчанию
не переводятся. Значит испортить название нельзя по устройству правила, и
никакого списка предметов вести не нужно: он всё равно отстал бы от игры.

Запуск:  python tools/add_quest_rules.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "ru_ru" / "30-chat.json"

NPC = r"^\[NPC\] ([A-Za-z0-9_]+): "

RULES = [
    {
        "_": ("Задание «принеси предметы». Имя предмета и число — в захвате, "
              "а захваты не переводятся: название сохранится точь-в-точь, "
              "по нему ищут вещь на аукционе и в базаре."),
        "p": NPC + r"To receive it, we require (.+) x([\d,]+)!$",
        "r": "[NPC] $1: Для этого нужно: $2 x$3",
    },
    {
        "_": "«Возьми в руки предмет» — название снова в захвате",
        "p": NPC + r"I need you to hold your (.+) so I can upgrade it!$",
        "r": "[NPC] $1: Возьми в руки $2, и я его улучшу",
    },
    {
        "p": NPC + r"Congrats on completing tier ([IVXLC]+)!$",
        "r": "[NPC] $1: Поздравляю с завершением ступени $2!",
    },
    {
        "p": NPC + r"You are ready for the next badge rarity!$",
        "r": "[NPC] $1: Ты готов к следующей редкости значка!",
    },
    {
        "_": "Общая форма «нужно N штук предмета» — встречается у разных NPC",
        "p": NPC + r"(.+) requires (.+) x([\d,]+)!$",
        "r": "[NPC] $1: $2 требует: $3 x$4",
    },
]

# Живые строки из дампа — на них и проверяем
TESTS = [
    "[NPC] Ryan: To receive it, we require Dark Oak Log x512!",
    "[NPC] Ryan: I need you to hold your Campfire Initiate Badge III so I can upgrade it!",
    "[NPC] Ryan: Congrats on completing tier V!",
    "[NPC] Ryan: You are ready for the next badge rarity!",
]

GROUP_REF = re.compile(r"\$(\d)")


def apply(rule: dict, text: str) -> str | None:
    """Как правило сработает в моде: $1 -> захваченный кусок, БЕЗ перевода."""
    match = re.match(rule["p"], text)
    if not match:
        return None
    return GROUP_REF.sub(lambda m: match.group(int(m.group(1))), rule["r"])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    pack.setdefault("regex", [])

    existing = {rule["p"] for rule in pack["regex"]}
    added = [rule for rule in RULES if rule["p"] not in existing]
    pack["regex"].extend(added)
    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"добавлено правил: {len(added)}, всего: {len(pack['regex'])}\n")

    problems = 0
    for text in TESTS:
        for rule in pack["regex"]:
            result = apply(rule, text)
            if result:
                print(f"  {text}\n    -> {result}")
                break
        else:
            problems += 1
            print(f"  {text}\n    -> НЕ СОВПАЛО")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
