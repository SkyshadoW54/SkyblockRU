"""
Возвращает ЦВЕТ ЗНАЧКУ характеристики: код должен стоять ПЕРЕД ним.

Что было видно на экране: «Повышает ⛏» серым, а «Mining Speed» строкой ниже
золотым — значок потерял цвет и оторвался от термина.

⚠️ Как надо — известно не из рассуждения, а из источника. В репозитории NEU
лор лежит с §-кодами, и там ровно так:

    §7Increases §6 Mining Speed §7with part

то есть §6 открывается ДО значка, и значок золотой вместе с термином.
А в наших переводах разметка легла иначе:

    §7Повышает  §6Mining Speed§7

Значок остался в сером куске. Почему так вышло: маркер цвета модель ставила
вокруг СЛОВ перевода, а значок словом не является — он к переводу не относится
и в пару «кусок → перевод» не попал.

Правило простое и общее: значок, стоящий вплотную перед цветным куском,
принадлежит ЕМУ, а не предыдущему тексту. Так его красит Hypixel везде,
где значок помечает характеристику.

Запуск:
  python tools/fix_icon_color.py           сухой прогон
  python tools/fix_icon_color.py --yes     применить
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"

# Значок + возможные пробелы + открывающий §-код.
#
# ⚠️ Слева от значка НЕ ДОЛЖНО быть буквы или цифры, и это важно: у формы
# «+{n}❤ §7Health» значок принадлежит ЧИСЛУ слева, а не подписи справа —
# так его и красит Hypixel. Без этого условия правка ломала бы ровно те
# строки характеристик, ради которых всё затевалось.
PATTERN = re.compile(r"(?<![^\W\d_])(?<!\d)([^\w\s§])(\s*)(§[0-9a-fk-or])")


def is_icon(symbol: str) -> bool:
    """
    Значок — это КАТЕГОРИЯ символа, а не диапазон.

    Приватная зона Unicode (иконки Hypixel) плюс символьные категории:
    ❤ здоровье, ☘ удача, ✎ мана. Буквы и цифры не в счёт, даже когда
    Hypixel ставит буквой значок.
    """
    if "" <= symbol <= "":
        return True
    return unicodedata.category(symbol) in ("So", "Sk")


def fix(text: str) -> tuple[str, int]:
    moved = 0

    def swap(match: re.Match) -> str:
        nonlocal moved
        icon, space, code = match.group(1), match.group(2), match.group(3)
        if not is_icon(icon):
            return match.group(0)
        moved += 1
        return code + icon + space

    return PATTERN.sub(swap, text), moved


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="цвет значку характеристики")
    parser.add_argument("--yes", action="store_true", help="применить")
    args = parser.parse_args()

    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = 0
    icons = 0
    shown = 0

    for para in data["paragraphs"]:
        russian = para.get("ru")
        if not russian or "§" not in russian:
            continue
        fixed, moved = fix(russian)
        if not moved:
            continue
        paragraphs += 1
        icons += moved
        if shown < 4:
            shown += 1
            print("  было : " + re.sub("§(.)", r"&\1", russian[:96]))
            print("  стало: " + re.sub("§(.)", r"&\1", fixed[:96]))
            print()
        para["ru"] = fixed

    print(f"абзацев поправлено: {paragraphs}, значков: {icons}")
    if not args.yes:
        print()
        print("сухой прогон — ничего не изменено. Применить: --yes")
        return 0

    CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"записан {CORPUS.name}. Дальше: python tools/merge_paragraphs.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
