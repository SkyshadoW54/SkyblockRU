"""
Чинит абзацы, в чей ключ вклеилось ИМЯ ПРЕДМЕТА.

Беда. Мод режет имя как границу абзаца (`Paragraphs.nameAside`), а корпус
этого не делал: `without_name` сравнивал строку с именем СЫРЫМ, тогда как
в дампе строки записаны обобщёнными («{n} Chocolate» против «6,805,377
Chocolate»). Имя оставалось в ключе — и купленный перевод мод не спрашивал
НИ РАЗУ. Замер: 148 абзацев, 147 из них переведены.

⚠️ Ключ чинится просто — отрезать имя. А перевод только если имя в нём
осталось ДОСЛОВНЫМ: тогда видно, где оно кончается. Если имя переведено
(«[Lvl {n}] Golden Dragon» -> «[Ур. {n}] Golden Dragon»), граница механически
не выводится, и такие записи мы НЕ ТРОГАЕМ — пусть лучше останутся как есть,
чем обрежутся наугад.

Запуск:
    python tools/fix_name_in_key.py         показать
    python tools/fix_name_in_key.py --yes   починить
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pkey import NUMBER  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Имя предмета в ключе абзаца")
    parser.add_argument("--yes", action="store_true", help="применить")
    args = parser.parse_args()

    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    known = {p.get("text", "") for p in data["paragraphs"]}

    fixed, left, collided = 0, 0, 0
    for para in data["paragraphs"]:
        item = (para.get("item") or "").strip()
        text = para.get("text", "")
        if not item or not text:
            continue
        key = NUMBER.sub("{n}", item)
        prefix = item if text.startswith(item + " ") else (
            key if text.startswith(key + " ") else None)
        if not prefix:
            continue

        ru = para.get("ru") or ""
        if ru and not ru.startswith(prefix + " "):
            left += 1          # имя переведено — границу не вывести
            continue

        new_text = text[len(prefix):].strip()
        if not new_text or len(new_text) < 8:
            left += 1
            continue
        if new_text in known and new_text != text:
            # ⚠️ Такой абзац уже есть — свой перевод у него тоже есть.
            # Молча перезаписывать чужое нельзя.
            collided += 1
            continue

        if args.yes:
            para["text"] = new_text
            if ru:
                para["ru"] = ru[len(prefix):].strip()
            known.add(new_text)
        fixed += 1

    if args.yes:
        CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"починено ключей: {fixed}")
    print(f"оставлено (имя переведено, границу не вывести): {left}")
    print(f"пропущено (такой абзац уже есть): {collided}")
    if not args.yes:
        print("\nСУХОЙ ПРОГОН. Применить: --yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
