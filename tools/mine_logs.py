"""
Достаёт из логов Minecraft имена, которые Hypixel подсветил своим цветом.

Зачем. В репликах NPC названия мест, персонажей и видов существ выделены
отдельным цветом: «go and find §6Captain Baha §fin the §bFishing Outpost§f!».
Переводить их нельзя, а список таких имён вёлся руками — и руками он всегда
неполон: на каждом новом острове появляются новые.

Цвет тут — ДАННЫЕ ОТ СЕРВЕРА, а не догадка по виду текста. Проблема была
в другом: дамп мода снимает §-коды при записи (иначе не совпал бы словарь),
и признак пропадал. Из 468 строк чата в дампе цвет сохранила НИ ОДНА.

А вот клиент Minecraft пишет чат в свой лог как есть, вместе с кодами, и логи
лежат за все прошлые сессии. То есть заново ходить по диалогам не надо —
всё уже записано, надо просто прочитать.

Результат ложится в data/work/highlighted.json, откуда его читает protected.py.
Тот же файл пишет и сам мод (Highlights.java) в папку дампа — два независимых
источника одного и того же признака.

Запуск:
  python tools/mine_logs.py
  python tools/mine_logs.py --show      посмотреть, что нашлось, и где
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = Path("C:/MultiMC/instances/26.2/.minecraft/logs")
OUT = ROOT / "data" / "work" / "highlighted.json"

CHAT = re.compile(r"\[CHAT\] (.*)$")

# Кусок текста со своим цветом: §X и всё до следующего §
SEGMENT = re.compile(r"\u00a7([0-9a-fk-or])([^\u00a7]*)")

# Только цветовые коды. k-o это жирный/курсив/подчёркивание — они цвет не меняют.
COLOR_CODES = set("0123456789abcdef")

# Похоже на имя собственное: слова с заглавной, латиница, от одного до четырёх.
# Апостроф ради «Necron's», дефис ради «Nether-Warts».
# Служебные слова внутри имени пишутся со строчной: «Trial of Fire»,
# «Heart of the Mountain». Без них имя резалось на куски и в список попадал
# огрызок «Trial».
WORD = "[A-Z][A-Za-z'-]+"
LINK = "(?:of|the|and|in|on)"
# «Lumber Jack», «Trial of Fire», «Heart of the Mountain» — связки внутри
# имени пишутся со строчной, и без них имя резалось на огрызки.
NAME = re.compile(WORD + r"(?:\s+" + LINK + r"){0,2}"
                  + r"(?:\s+" + WORD + r"(?:\s+" + LINK + r"){0,2}){0,3}")

# Реплика живого игрока: ранг в скобках или уровень числом впереди.
# Ники оттуда — не имена мира, а случайные люди на сервере.
PLAYER_CHAT = re.compile(r"^(?:\[\d+\]|\[(?:VIP|MVP|YOUTUBE|ADMIN)|\S*\s*\[(?:VIP|MVP))")

# Подсвечены, но именами не являются
NOT_A_NAME = {
    "CLICK", "Click", "You", "Your", "The", "A", "An", "It", "New", "Right",
    "Left", "Warning", "Error", "Yes", "No", "OK", "Welcome", "Contribute",
    "Congratulations", "Reward", "Rewards", "Level", "Levels",
}

MIN_LENGTH = 4


def segments(line: str) -> list[tuple[str, str]]:
    """Строка -> список (цвет, текст). Кусок без кода получает цвет ''."""
    out: list[tuple[str, str]] = []
    first = line.find("\u00a7")
    if first > 0:
        out.append(("", line[:first]))
    elif first < 0:
        return [("", line)]
    color = ""
    for code, text in SEGMENT.findall(line):
        if code in COLOR_CODES:
            color = code
        # k-o не меняют цвет, но текст после них принадлежит текущему цвету
        if text:
            out.append((color, text))
    return out


def base_color(parts: list[tuple[str, str]]) -> str:
    """
    Цвет, которым набрана БОЛЬШАЯ ЧАСТЬ строки, — он и есть фон.

    ⚠️ Не цвет первого куска. У реплики NPC первым идёт «§e[NPC] », и если
    считать фоном жёлтый, то фоном перестанет быть белое тело реплики —
    а значит «Welcome to the...» тоже сойдёт за подсветку. По объёму текста
    признак устойчив: фон всегда длиннее выделения.
    """
    weight: Counter = Counter()
    for color, text in parts:
        weight[color] += len(text)
    return weight.most_common(1)[0][0] if weight else ""


def names_in(line: str) -> list[str]:
    parts = segments(line)
    if len(parts) < 2:
        return []
    base = base_color(parts)
    found = []
    for color, text in parts:
        if not color or color == base:
            continue
        for name in NAME.findall(text.strip()):
            name = name.strip()
            if len(name) < MIN_LENGTH or name in NOT_A_NAME:
                continue
            if name.upper() == name:
                # ЗАГЛАВНЫМИ Hypixel набирает выделение, а не имена:
                # «CLICK HERE», «NEW RABBIT». Настоящие имена так не пишут.
                continue
            found.append(name)
    return found


def chat_lines() -> list[str]:
    if not LOGS.exists():
        print(f"нет папки логов: {LOGS}")
        return []
    lines = []
    for path in sorted(LOGS.glob("*.log")) + sorted(LOGS.glob("*.log.gz")):
        opener = gzip.open if path.suffix == ".gz" else open
        try:
            with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
                for row in handle:
                    found = CHAT.search(row)
                    if found and found.group(1).strip():
                        lines.append(found.group(1).rstrip("\n"))
        except OSError:
            continue
    return lines


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="показать находки с примерами")
    parser.add_argument("--min", type=int, default=1,
                        help="сколько раз слово должно встретиться (порог не нужен, "
                             "отбор идёт по признакам имени)")
    args = parser.parse_args()

    lines = chat_lines()
    print(f"строк чата в логах: {len(lines)}")
    coloured = [line for line in lines if "\u00a7" in line]
    print(f"из них с §-кодами:  {len(coloured)}")
    if not coloured:
        print("цвета нет — логи пусты или чат в них не пишется")
        return 1

    counts: Counter = Counter()
    where: dict[str, list[str]] = defaultdict(list)
    for line in coloured:
        plain = re.sub(r"§.", "", line).strip()
        if PLAYER_CHAT.match(plain):
            # Ник игрока защищать через этот список незачем: он не имя мира,
            # а случайный человек, и такие ники плодятся без конца.
            continue
        for name in names_in(line):
            counts[name] += 1
            if len(where[name]) < 2:
                where[name].append(re.sub(r"\u00a7.", "", line)[:90])

    # Уже переводится словарём — значит это НЕ имя, а термин, который Hypixel
    # просто выделил цветом. Свой словарь важнее: иначе одно подсвеченное
    # «Defense» запретило бы переводить характеристику по всему проекту.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from protected import translated_terms
    known = translated_terms()
    dropped = sorted(name for name in counts if name in known)
    for name in dropped:
        del counts[name]

    # ⚠️ Отбираем ПО ПРИЗНАКАМ ИМЕНИ, а не по числу встреч.
    #
    # «Captain Baha» встретился ровно один раз — и это настоящее имя, потерять
    # которое дороже всего. А «Bring» из «[NPC] Kelly: Bring me 128 Spruce
    # Logs!» встретился столько же, но это обычный глагол. Считать встречи
    # бессмысленно: они не различают эти два случая.
    #
    # Различают два признака: имя из двух слов и больше — всегда имя; одно
    # слово — имя, если оно почти не пишется со строчной в наших же текстах.
    from protected import looks_like_name
    ordinary = sorted(name for name in counts if not looks_like_name(name))
    picked = {name: count for name, count in counts.most_common()
              if count >= args.min and looks_like_name(name)}
    print(f"подсвеченных имён: {len(picked)}")
    if dropped:
        print(f"отброшено (их переводит наш словарь): {len(dropped)} — "
              f"{', '.join(dropped[:8])}")
    if ordinary:
        print(f"отброшено (обычные английские слова): {len(ordinary)} — "
              f"{', '.join(ordinary[:10])}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_comment": "Имена собственные, подсвеченные Hypixel своим цветом. Добыто "
                    "из логов Minecraft скриптом tools/mine_logs.py. Переводить "
                    "их НЕЛЬЗЯ. Читает tools/protected.py.",
        "names": picked,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"записано: {OUT.relative_to(ROOT)}")

    if args.show:
        print("\nчто нашлось:")
        for name, count in sorted(picked.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {count:3}x  {name}")
            for example in where[name][:1]:
                print(f"         {example}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
