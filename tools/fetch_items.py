"""
Скачивает официальный список предметов Hypixel SkyBlock и делает из него
заготовку словаря для перевода.

Источник: https://api.hypixel.net/v2/resources/skyblock/items
Ключ API не нужен - это открытый ресурсный эндпоинт.

Что получается на выходе (папка data/):
  data/en/items.raw.json        - сырой ответ API (чтобы не дёргать сеть каждый раз)
  data/en/item_names.txt        - все английские названия предметов, по одному в строке
  data/en/item_lore.txt         - все строки описаний (уникальные), по частоте
  data/skeleton/items.json      - заготовка пакета перевода: названия -> ""
  data/skeleton/lore.json       - заготовка пакета перевода: строки описаний -> ""

Заготовки НЕ переводят сами - они дают полный список того, что предстоит перевести.
Уже переведённые строки из packs/ подставляются автоматически, чтобы работу
не приходилось делать заново.

Запуск:  python tools/fetch_items.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

API_URL = "https://api.hypixel.net/v2/resources/skyblock/items"

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# В описаниях Hypixel цвета размечены как %%dark_gray%% / %%italic%% и т.п.
COLOR_MARKER = re.compile(r"%%[a-z_]+%%")
# Классические коды форматирования Minecraft
SECTION_CODE = re.compile(r"§[0-9a-fk-orA-FK-OR]")


def strip_formatting(text: str) -> str:
    """Убирает и %%color%%-разметку Hypixel, и обычные коды с параграфом."""
    text = COLOR_MARKER.sub("", text)
    text = SECTION_CODE.sub("", text)
    return text.strip()


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "SkyblockRU/0.1 (translation tool)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_existing_translations() -> dict[str, str]:
    """Собирает уже сделанные переводы из всех пакетов, чтобы не потерять работу."""
    done: dict[str, str] = {}
    if not PACKS.is_dir():
        return done
    for path in sorted(PACKS.rglob("*.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  ! пропускаю {path.name}: {exc}")
            continue
        for src, dst in (pack.get("exact") or {}).items():
            if dst:
                done[src] = dst
    return done


def main() -> int:
    DATA.mkdir(exist_ok=True)
    (DATA / "en").mkdir(exist_ok=True)
    (DATA / "skeleton").mkdir(exist_ok=True)

    raw_path = DATA / "en" / "items.raw.json"
    if "--offline" in sys.argv and raw_path.exists():
        print(f"офлайн-режим: беру {raw_path}")
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        print(f"качаю {API_URL} ...")
        payload = fetch(API_URL)
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  сохранил сырой ответ: {raw_path.relative_to(ROOT)}")

    if not payload.get("success"):
        print("API вернул success=false", file=sys.stderr)
        return 1

    items = payload.get("items") or []
    print(f"предметов в ответе: {len(items)}")

    names: list[str] = []
    lore_counter: Counter[str] = Counter()

    for item in items:
        name = strip_formatting(item.get("name") or "")
        if name:
            names.append(name)

        description = item.get("description") or ""
        for line in description.split("\n"):
            clean = strip_formatting(line)
            if clean:
                lore_counter[clean] += 1

    unique_names = sorted(set(names))
    print(f"уникальных названий: {len(unique_names)}")
    print(f"уникальных строк описаний: {len(lore_counter)}")

    (DATA / "en" / "item_names.txt").write_text(
        "\n".join(unique_names) + "\n", encoding="utf-8"
    )
    (DATA / "en" / "item_lore.txt").write_text(
        "\n".join(f"{count}\t{line}" for line, count in lore_counter.most_common()) + "\n",
        encoding="utf-8",
    )

    done = load_existing_translations()
    print(f"уже переведено (из packs/): {len(done)}")

    def skeleton(keys, pack_id: str, priority: int, comment: str) -> dict:
        exact = {}
        for key in keys:
            exact[key] = done.get(key, "")
        return {
            "id": pack_id,
            "priority": priority,
            "_comment": comment,
            "exact": exact,
        }

    items_skeleton = skeleton(
        unique_names,
        "items",
        30,
        "Названия предметов. Источник: api.hypixel.net/v2/resources/skyblock/items. "
        "Пустая строка = ещё не переведено, такие строки мод игнорирует.",
    )
    lore_skeleton = skeleton(
        [line for line, _ in lore_counter.most_common()],
        "lore",
        40,
        "Строки описаний предметов, отсортированы по частоте: сверху то, что встречается чаще всего.",
    )

    (DATA / "skeleton" / "items.json").write_text(
        json.dumps(items_skeleton, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (DATA / "skeleton" / "lore.json").write_text(
        json.dumps(lore_skeleton, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    filled_items = sum(1 for v in items_skeleton["exact"].values() if v)
    filled_lore = sum(1 for v in lore_skeleton["exact"].values() if v)
    print()
    print("готово:")
    print(f"  data/skeleton/items.json — {filled_items}/{len(unique_names)} переведено")
    print(f"  data/skeleton/lore.json  — {filled_lore}/{len(lore_counter)} переведено")
    print()
    print("дальше: переводи строки прямо в этих файлах и клади их в")
    print("  src/main/resources/assets/skyblockru/packs/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
