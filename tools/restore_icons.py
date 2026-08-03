"""
Возвращает иконки Hypixel, потерянные при переводе.

Модель выбрасывает символы приватной зоны, несмотря на явное указание в правилах:
на экране они выглядят мусором, и рука тянется их убрать. Спорить с этим бесполезно —
проще восстановить механически, благо позиция иконки однозначно выводится из оригинала.

Две наблюдаемые потери, обе чинятся точно:
  Gemstones: [◆] [◆]        ->  Самоцветы: [] []          (скобки пустые)
  Grants +{n}◆ Treasure     ->  Даёт +{n} Шанса сокровищ  (иконка после {n} выпала)

Запуск:
  python tools/restore_icons.py data/work/lore_tooltips.json
Либо вызывается сам после прогона перевода.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BRACKET = re.compile(r"\[([^\[\]]*)\]")
PLACEHOLDER = re.compile(r"\{n\}")


# Категории знаков, которыми Hypixel помечает характеристики.
# Co — приватная зона (собственные значки), So/Sk/Sm — обычные символы,
# Po — маркеры списка. Буквы и тире сюда намеренно не попадают.
MARKER_CATEGORIES = {"Co", "So", "Sk", "Sm", "Po"}


def is_icon(ch: str) -> bool:
    """
    Значок Hypixel, который обязан пережить перевод.

    ⚠️ Раньше тут была ТОЛЬКО приватная зона U+E000..U+F8FF. Но по корпусу видно,
    что характеристики Hypixel помечает и обычными символами: ❤ здоровье,
    ☘ ☯ ✎ ❈ ✯ ⚓ и маркер списка ‣ — больше полутора тысяч вхождений. Все они
    проходили мимо проверки и мимо восстановления: выброшенное ❤ считалось
    нормой. Отсюда правило — значок определяется КАТЕГОРИЕЙ символа, а не
    диапазоном.

    Буквы не в счёт, даже когда Hypixel ставит их как значок (в корпусе так
    используется Ж): отличить букву-значок от буквы в тексте нечем.
    """
    return ord(ch) > 127 and unicodedata.category(ch) in MARKER_CATEGORIES


def icons_of(text: str) -> list[str]:
    return [c for c in text if is_icon(c)]


def restore_line(src: str, ru: str) -> str:
    """Возвращает ru с восстановленными иконками. Меняет только то, что уверенно выводится."""
    lost = [c for c in icons_of(src) if ru.count(c) < src.count(c)]
    if not lost:
        return ru

    # --- случай 1: иконки внутри квадратных скобок ---
    src_groups = BRACKET.findall(src)
    ru_groups = BRACKET.findall(ru)
    if src_groups and len(src_groups) == len(ru_groups):
        # переносим содержимое скобок как есть: там гнёзда под самоцветы,
        # переводить внутри нечего
        out, index = [], 0
        for part in BRACKET.split(ru):
            out.append(part)
        rebuilt = ru
        for i, group in enumerate(src_groups):
            if icons_of(group):
                # заменяем i-ю пару скобок целиком
                count = 0

                def swap(match, target=i, value=group):
                    nonlocal count
                    current, count = count, count + 1
                    return f"[{value}]" if current == target else match.group(0)

                rebuilt = BRACKET.sub(swap, rebuilt)
        ru = rebuilt
        lost = [c for c in icons_of(src) if ru.count(c) < src.count(c)]
        if not lost:
            return ru

    # --- случай 2: иконка сразу после числа ---
    # В оригинале «+{n}◆», в переводе «+{n}» — вставляем на то же место.
    #
    # ⚠️ Считаем номер САМОЙ ДЫРКИ, а не «которая по счёту иконка». Раньше тут
    # был список одних лишь иконок, и его индекс молча приравнивался к номеру
    # дырки. Совпадает это только когда иконки висят на первых дырках подряд;
    # у «Bonus ({n}/{n}) Grants +{n}◆ Trophy» иконка уезжала на первую дырку.
    # Построчно такое почти не встречалось, а в абзацах — у 116 записей корпуса.
    # ⚠️ Форм ДВЕ, и вторая долго не работала:
    #     «+{n}◆ Fishing Speed»      — значок вплотную;
    #     «+{n} ◆ Crit Damage»       — значок через пробел.
    # Умели только первую, и вторая уходила в брак целиком: на прогоне 50 абзацев
    # это была пятая часть — оплаченный и выброшенный перевод. В корпусе таких 287.
    # Запоминаем ХВОСТ как есть (со своим пробелом) и его же вставляем обратно.
    icons_after: dict[int, str] = {}
    for index, hole in enumerate(PLACEHOLDER.finditer(src)):
        tail = src[hole.end():hole.end() + 1]
        if tail and is_icon(tail):
            icons_after[index] = tail
        elif tail == " ":
            second = src[hole.end() + 1:hole.end() + 2]
            if second and is_icon(second):
                icons_after[index] = " " + second
    if icons_after:
        holes = list(PLACEHOLDER.finditer(ru))
        if len(holes) > max(icons_after):
            # идём с конца, чтобы позиции не съезжали
            for index in sorted(icons_after, reverse=True):
                tail = icons_after[index]
                icon = tail.strip()
                if ru.count(icon) >= src.count(icon):
                    continue
                at = holes[index].end()
                # если в переводе за дыркой и так пробел — свой не добавляем
                if tail.startswith(" ") and ru[at:at + 1] == " ":
                    at += 1
                    tail = icon + " "
                ru = ru[:at] + tail + ru[at:]
    return ru


def restore_file(path: Path, quiet: bool = False) -> int:
    """
    Чинит иконки в рабочем файле. Форматов два, и они разные по устройству:
      tooltips   — блок, где lines и ru это СПИСКИ строк (перевод построчный);
      paragraphs — абзац, где text и ru это ОДНА строка (перевод целиком).
    Различаем по имени секции, а не по форме записи: секция названа явно.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    fixed, left = 0, 0

    def report(owner: str, src: str) -> None:
        nonlocal left
        left += 1
        if not quiet:
            print(f"  ! не восстановил: {owner}: {src[:46]!r}")

    for block in data.get("tooltips") or []:
        if not block.get("ru"):
            continue
        for i, (src, ru) in enumerate(zip(block["lines"], block["ru"])):
            if not icons_of(src):
                continue
            new = restore_line(src, ru)
            if new != ru:
                block["ru"][i] = new
                fixed += 1
            if [c for c in icons_of(src) if block["ru"][i].count(c) < src.count(c)]:
                report(block.get("item") or "?", src)

    for para in data.get("paragraphs") or []:
        ru = para.get("ru")
        src = para.get("text") or ""
        if not ru or not icons_of(src):
            continue
        new = restore_line(src, ru)
        if new != ru:
            para["ru"] = new
            fixed += 1
        if [c for c in icons_of(src) if para["ru"].count(c) < src.count(c)]:
            report(para.get("item") or "?", src)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if not quiet:
        print(f"иконок восстановлено в строках: {fixed}")
        print(f"осталось нерешённых строк: {left}")
    return fixed


def main() -> int:
    # В отчёт попадает исходная строка вместе с иконкой, а консоль тут cp1251:
    # без этого скрипт падал на UnicodeEncodeError вместо того, чтобы отчитаться.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])
    if not path.is_absolute():
        path = ROOT / path
    restore_file(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
