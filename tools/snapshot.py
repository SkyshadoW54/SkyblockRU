"""
СНИМОК подсказок: что игрок видел вчера против того, что увидит сегодня.

⚠️ Зачем. Все проверки проекта смотрят на КУСКИ логики: `check_colors` — на
правило склейки, `check_paragraph_colors` — на раскраску, `check_rules` — на
шаблоны. Каждая честно говорит «замечаний 0», а на экране при этом ломается
список, сливается заголовок или пропадает красный цвет — потому что экран
собирают ВСЕ куски вместе, и ни одна проверка не смотрит на результат целиком.

За один вечер так прошли три регресса, и все три нашёл игрок скриншотами.

Мод пишет `dump/preview.json`: каждая подсказка ДО и ПОСЛЕ перевода, разобранная
на цветные куски. Это и есть то, что видит игрок. Достаточно запомнить снимок
и сравнивать с ним — тогда любая правка показывает построчный диф по всему
экрану, до сборки и без игры.

Запуск:
  python tools/snapshot.py --save       запомнить текущее состояние как эталон
  python tools/snapshot.py              сравнить нынешнее с эталоном
  python tools/snapshot.py --show 40    показать больше расхождений

⚠️ Снимок — это НЕ «как правильно», а «как было». Изменение в дифе может быть
и починкой; смотреть глазами обязательно. Ценность в том, что незамеченным
не пройдёт ничего.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/preview.json")
SNAP = ROOT / "data" / "work" / "preview-snapshot.json"


def load_live() -> dict[str, list]:
    """Подсказки из свежего дампа: имя предмета -> строки с цветами."""
    if not DUMP.exists():
        return {}
    try:
        cases = json.loads(DUMP.read_text(encoding="utf-8")).get("cases") or []
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, list] = {}
    for case in cases:
        item = str(case.get("item") or "")
        after = case.get("after") or []
        if item:
            out[item] = after
    return out


def flat(lines: list) -> list[str]:
    """Строка подсказки как «цвет|текст» — так видно и потерю цвета, и текста."""
    out = []
    for line in lines:
        parts = ["%s|%s" % (piece[0], piece[1]) for piece in line
                 if isinstance(piece, (list, tuple)) and len(piece) >= 2]
        out.append("  ".join(parts))
    return out


def compare(old: dict, new: dict, show: int) -> int:
    gone = sorted(set(old) - set(new))
    fresh = sorted(set(new) - set(old))
    changed = []
    for item in sorted(set(old) & set(new)):
        before, after = flat(old[item]), flat(new[item])
        if before != after:
            changed.append((item, before, after))

    print(f"подсказок в эталоне: {len(old)}, сейчас: {len(new)}")
    print(f"  изменилось: {len(changed)}")
    print(f"  новых: {len(fresh)}   пропало из дампа: {len(gone)}")
    if not changed:
        print()
        print("расхождений нет — экран выглядит ровно как в эталоне")
        return 0

    print()
    for item, before, after in changed[:show]:
        print("=" * 74)
        print(f"  {item}")
        width = max(len(before), len(after))
        for i in range(width):
            was = before[i] if i < len(before) else ""
            now = after[i] if i < len(after) else ""
            if was == now:
                continue
            print(f"    было:  {was[:96]}")
            print(f"    стало: {now[:96]}")
    if len(changed) > show:
        print(f"\n  … ещё {len(changed) - show} (--show покажет больше)")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Снимок подсказок: диф по всему экрану")
    parser.add_argument("--save", action="store_true", help="запомнить текущее как эталон")
    parser.add_argument("--show", type=int, default=12)
    args = parser.parse_args()

    live = load_live()
    if not live:
        print("нет свежего preview.json — поиграй пару минут на текущем jar")
        print("файл:", DUMP)
        return 1

    if args.save:
        SNAP.parent.mkdir(parents=True, exist_ok=True)
        SNAP.write_text(json.dumps({"cases": live}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print(f"эталон сохранён: {len(live)} подсказок -> {SNAP.relative_to(ROOT)}")
        return 0

    if not SNAP.exists():
        print("эталона ещё нет. Сохрани текущее состояние:")
        print("  python tools/snapshot.py --save")
        return 1
    old = json.loads(SNAP.read_text(encoding="utf-8")).get("cases") or {}
    return compare(old, live, args.show)


if __name__ == "__main__":
    raise SystemExit(main())
