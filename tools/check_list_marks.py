"""
Ищет СПИСКИ, которые мод склеивает в прозу, потому что не знает их знака.

Беда. Мод не склеивает абзац, если несколько строк начинаются одинаковым
знаком — это список, и перенос размазал бы его в кашу. Но список знаков
(`ColorLayout.CHOICE_MARKS`) выписан руками, и Hypixel спокойно берёт похожий
символ из другого места таблицы Unicode. Так «∙» (U+2219) прошло мимо «•»
(U+2022): глазом неотличимо, а для машины это разные знаки — и подсказка
класса склеилась в «Пассивка класса: Doubleshot 50% шанс выпустить вторую
стрелу» одной строкой.

Инструмент смотрит ЖИВЫЕ подсказки и находит все знаки, которыми начинаются
три и более строки подряд, — и говорит, какие из них моду неизвестны.

Запуск:  python tools/check_list_marks.py
"""
from __future__ import annotations

import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLTIPS = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/tooltips.json")
LAYOUT = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "ColorLayout.java"

MARKS_LINE = re.compile(r"CHOICE_MARKS\s*=\s*\n?\s*Set\.of\(([^)]*)\)", re.S)
MIN_LINES = 3


def known_marks() -> set[str]:
    """Знаки, которые мод СЧИТАЕТ списочными — читаем прямо из его исходника."""
    text = LAYOUT.read_text(encoding="utf-8")
    match = MARKS_LINE.search(text)
    if not match:
        return set()
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def first_mark(line: str) -> str:
    """Первый знак строки, если это НЕ буква и НЕ цифра."""
    stripped = line.strip()
    if not stripped:
        return ""
    first = stripped[0]
    if first.isalnum() or first.isspace():
        return ""
    return first


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not TOOLTIPS.exists():
        print(f"нет дампа подсказок: {TOOLTIPS}")
        return 1

    known = known_marks()
    print(f"мод знает знаков: {len(known)}")

    data = json.loads(TOOLTIPS.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else (data.get("tooltips") or list(data.values()))

    # знак -> (сколько списков, пример)
    found: dict[str, list] = collections.defaultdict(list)
    for row in rows:
        lines = row.get("lines") if isinstance(row, dict) else row
        if not lines:
            continue
        run: list[str] = []
        for line in list(lines) + [""]:
            mark = first_mark(str(line))
            if run and (not mark or mark != first_mark(run[0])):
                if len(run) >= MIN_LINES:
                    found[first_mark(run[0])].append(run[0].strip())
                run = []
            if mark:
                run.append(str(line))
        if len(run) >= MIN_LINES:
            found[first_mark(run[0])].append(run[0].strip())

    unknown = {mark: rows for mark, rows in found.items() if mark not in known}
    print(f"знаков-списков в живых подсказках: {len(found)}, из них МОД НЕ ЗНАЕТ: {len(unknown)}\n")

    if not unknown:
        print("все списки распознаются — склеиваться в прозу нечему")
        return 0

    print("=== НЕИЗВЕСТНЫЕ ЗНАКИ ===")
    print("Такой список мод склеит в одну строку, и структура пропадёт.\n")
    for mark, examples in sorted(unknown.items(), key=lambda kv: -len(kv[1])):
        try:
            name = unicodedata.name(mark)
        except ValueError:
            name = "приватная зона Hypixel"
        print(f"  {len(examples):4} списков   U+{ord(mark):04X}  {mark!r}   {name}")
        print(f"        например: {examples[0][:70]}")
    print("\nЗнак добавляют в ColorLayout.CHOICE_MARKS, а потом ОБЯЗАТЕЛЬНО")
    print("прогоняют python tools/check_colors.py — он покажет, какие подсказки")
    print("поменяют поведение: правило гасит абзац, и купленный перевод может")
    print("перестать применяться.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
