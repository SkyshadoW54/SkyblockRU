"""
Абзацы меню из заготовки -> словарь мода (94-menus.json).

Почему ОТДЕЛЬНЫЙ словарь, а не корпус. Эти абзацы собраны из репозитория NEU,
а не из нашего дампа. Положи их в `data/work/paragraphs.json` — и первая же
пересборка корпуса их выбросит: `make_paragraphs` оставляет только то, что
есть в источниках СЕЙЧАС. Проект на этом уже терял 1610 переводов за один
запуск.

⚠️ priority 22 — НИЖЕ, чем у корпуса (21). У секции `paragraphs` движок делает
put, поэтому побеждает пакет с МЕНЬШИМ priority: купленный перевод корпуса
важнее нашей заготовки, если ключи вдруг совпадут.

Запуск:  python tools/merge_menu_paragraphs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "work" / "menu_paragraphs.json"
LANG = "ru_ru"
PACK = (ROOT / "src" / "main" / "resources" / "assets" / "skyblockru"
        / "packs" / LANG / "94-menus.json")
INDEX = (ROOT / "src" / "main" / "resources" / "assets" / "skyblockru"
         / "packs" / "index.json")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not SOURCE.exists():
        print(f"нет заготовки: {SOURCE}")
        print("собрать: python tools/fetch_neu_menus.py")
        return 1

    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    ready = {key: item["ru"] for key, item in data["paragraphs"].items() if item.get("ru")}
    if not ready:
        print("переводов нет — переводить в data/work/menu_paragraphs.json")
        return 1

    PACK.parent.mkdir(parents=True, exist_ok=True)
    PACK.write_text(json.dumps({
        "id": "menus",
        "priority": 22,
        "_comment": "Абзацы ЭКРАНОВ (деревья Heart of the Mountain и Heart of the "
                    "Forest). Собраны tools/fetch_neu_menus.py из constants/ "
                    "репозитория NEU — там они лежат С §-КОДАМИ, поэтому перевод "
                    "размечен точно, а не догадкой. Править надо ЗАГОТОВКУ "
                    "data/work/menu_paragraphs.json, этот файл пересобирается.",
        "paragraphs": ready,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    marked = sum(1 for value in ready.values() if "§" in value)
    print(f"записано абзацев: {len(ready)}, из них с разметкой: {marked}")
    print(f"  {PACK}")

    # ⚠️ Не вписать в index.json — значит словарь молча не загрузится.
    # Так однажды не работали 36 зачарований.
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    languages = index.setdefault("languages", {})
    files = languages.setdefault(LANG, [])
    name = PACK.name
    if name not in files:
        # ⚠️ Порядок в index.json НЕ трогаем: движок сортирует пакеты по
        # priority, а перестановка чужих строк — лишний повод для расхождений.
        files.append(name)
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  вписан в index.json ({LANG})")
    else:
        print(f"  уже в index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
