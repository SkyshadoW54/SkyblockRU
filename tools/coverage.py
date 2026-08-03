"""
Карта покрытия: где перевод есть, но БЕЗ ЦВЕТА, и куда за этим цветом идти.

Зачем. Главная дыра проекта — не перевод, а разметка: 62% абзацев переведены
с §-кодами, остальные плоские, и мод красит их догадкой (возвращается 19–47%
подсветки). Закрыть дыру можно только цветами от Hypixel, а они приходят
единственным путём — игрок открывает экран, и мод пишет куски с цветами
в `dump/paragraph-colors.json`.

Беда в том, что ходить приходилось вслепую: «побродите по меню». Этот
инструмент отвечает на два вопроса:

  1. что можно разметить ПРЯМО СЕЙЧАС — цвета уже собраны, идти никуда не надо;
  2. куда сходить, чтобы добрать больше всего, — по предметам и экранам.

⚠️ Мод забирает ВЕСЬ открытый экран разом (ContainerSweepMixin), а не только
то, на что навели мышью. Поэтому «сходить» = открыть меню, и всё его
содержимое с цветами уедет в дамп.

Запуск:
    python tools/coverage.py              сводка и куда идти
    python tools/coverage.py --limit 30   длиннее список
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")

SECTION = re.compile(r"§.")


def load_colors() -> dict[str, dict]:
    """Живые цвета, собранные модом: ключ абзаца -> куски с цветами."""
    path = DUMP / "paragraph-colors.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    rows = data if isinstance(data, list) else (
        data.get("paragraphs") or data.get("cases") or [])
    found = {}
    for row in rows:
        if isinstance(row, dict) and row.get("key"):
            found.setdefault(row["key"], row)
    return found


def has_highlight(row: dict) -> bool:
    """
    Есть ли в абзаце ЧТО размечать: кусок, отличающийся от цвета тела.

    ⚠️ «Цвета собраны» и «есть что размечать» — разные вещи. Одноцветному
    абзацу разметка не нужна вовсе: мод и так покрасит его верно, потому что
    тело абзаца и есть его единственный цвет.

    <p>Куски мод пишет уже разобранными парами (цвет, текст), поэтому цвет
    тела считаем прямо по ним — тем же правилом, что ParagraphColors.body
    и color_lore.body_colour: побеждает цвет, набравший больше КУСКОВ,
    а не знаков, ничья — за серым.
    """
    pieces = [tuple(p) for p in (row.get("pieces") or []) if len(p) == 2]
    if len(pieces) < 2:
        return False
    counts = collections.Counter(color for color, text in pieces if text.strip())
    if not counts:
        return False
    best = max(counts.values())
    top = sorted(color for color, number in counts.items() if number == best)
    body = next((c for c in top if c in ("gray", "dark_gray")), top[0])
    return any(color != body and len(text.strip()) > 1 for color, text in pieces)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Карта покрытия разметкой")
    parser.add_argument("--limit", type=int, default=15, help="длина списков")
    args = parser.parse_args()

    if not CORPUS.exists():
        print(f"нет корпуса: {CORPUS}")
        return 1
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))["paragraphs"]
    colors = load_colors()

    translated = [p for p in corpus if p.get("ru")]
    marked = [p for p in translated if "§" in p["ru"]]
    flat = [p for p in translated if "§" not in p["ru"]]

    # Плоский перевод, но цвета УЖЕ собраны — размечается без похода в игру.
    #
    # ⚠️ «Цвета собраны» и «есть ЧТО размечать» — разные вещи, и путать их
    # значит обещать работу, которой нет. Замер 29.07: из 396 абзацев с
    # собранными цветами подсветку имели РОВНО НОЛЬ — все до одного
    # одноцветные. Инструмент при этом бодро печатал «✓ можно разметить
    # СЕЙЧАС: 396» и цену $0.71.
    #
    # Одноцветному абзацу разметка не нужна вовсе: мод и так покрасит его
    # правильно — тело абзаца и есть его единственный цвет. Поэтому считаем
    # только те, где хоть один кусок отличается от тела, и спрашиваем об этом
    # color_lore — то есть тот самый код, который потом и будет размечать.
    ready, painted = [], []
    need_trip = []
    for para in flat:
        lines = colors.get(para.get("text"))
        if lines is None:
            need_trip.append(para)
            continue
        ready.append(para)
        if has_highlight(lines):
            painted.append(para)

    total = len(translated)
    share = (len(marked) * 100 // total) if total else 0
    print(f"=== РАЗМЕТКА ЦВЕТОМ ===")
    print(f"  переведено абзацев:        {total}")
    print(f"  из них размечено:          {len(marked)} ({share}%)")
    print(f"  плоских (мод угадывает):   {len(flat)}")
    print()
    print(f"  ✓ цвета собраны:           {len(ready)}")
    print(f"     из них С ПОДСВЕТКОЙ:    {len(painted)}   <- вот это и есть работа")
    print(f"     одноцветных:            {len(ready) - len(painted)}   разметка им не нужна")
    print(f"  → нужен поход в игру:      {len(need_trip)}")

    if painted:
        print(f"\n  Команда: python tools/color_lore.py --apply")
        print(f"  Ориентировочно: ${len(painted) * 0.0018:.2f} (замер 26.07: $0.0018 за абзац)")

    # --- куда идти ----------------------------------------------------------
    # Группируем по предмету: это и есть подсказка, какой экран открыть.
    where = collections.Counter()
    for item in need_trip:
        name = (item.get("item") or "").strip()
        where[name or "(без предмета)"] += 1

    print(f"\n=== КУДА СХОДИТЬ: {len(where)} мест ===")
    print("  Открыть экран — и мод заберёт ВСЁ его содержимое разом.")
    for name, count in where.most_common(args.limit):
        print(f"   {count:5}  {name}")
    if len(where) > args.limit:
        others = sum(c for _, c in where.most_common()[args.limit:])
        print(f"   ... ещё {len(where) - args.limit} мест на {others} абзацев")

    # --- сколько цветов собрано вообще --------------------------------------
    #
    # ⚠️ ЗДЕСЬ СТОЯЛ ВРЕДНЫЙ СОВЕТ: «их стоит добавить пересборкой». Проверено
    # 29.07 — пересборка этого НЕ ДЕЛАЕТ, и совет уводил в убыток:
    #
    #   * цвета мод пишет для абзацев МЕНЮ и ЭКРАНОВ, а корпус строится из
    #     tooltips.json — подсказок ПРЕДМЕТОВ. Из 7139 «не из корпуса» при
    #     пересборке туда попадают 167, то есть 2%;
    #   * новые абзацы приходят БЕЗ перевода, а размечать можно только
    #     переведённое: «даст много размеченного» неверно вдвойне;
    #   * пересборка ещё и РИСКОВАННАЯ — из корпуса выпадают абзацы, которых
    #     нет в текущих источниках: 640 штук, из них 447 с оплаченным
    #     переводом (а по одному живому дампу — 4457).
    #
    # Само число полезно как мера НЕОХВАЧЕННОГО материала меню, но решать
    # по нему про пересборку нельзя.
    unknown = [key for key in colors if key not in {p.get("text") for p in corpus}]
    with_ru = sum(1 for key in unknown if (colors[key].get("ru") or "").strip())
    print(f"\n=== СОБРАННЫЕ ЦВЕТА ===")
    print(f"  раскладок в дампе:              {len(colors)}")
    print(f"  из них НЕ из корпуса:           {len(unknown)}")
    print(f"     уже переведены другим слоем: {with_ru}")
    print("  (это экраны и меню; в корпусе их нет и пересборка их туда")
    print("   НЕ ДОБАВИТ — корпус строится из подсказок предметов)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
