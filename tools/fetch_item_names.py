"""
ИМЕНА ПРЕДМЕТОВ от самого сервера — единый список того, что переводить нельзя.

Зачем. Имена предметов мы не переводим по замыслу: по ним ищут на аукционе
и в базаре. Но список собирался из того, что мод УСПЕЛ встретить, плюс из
чужих репозиториев, — то есть был неполон всегда и рос случайно.

У Hypixel есть каталог: `resources/skyblock/items` отдаёт ВСЕ предметы,
включая непродаваемые. Плюс NBT аукциона даёт варианты, которых в каталоге
нет: прокачанные вещи с реколкой и звёздами («Heroic Silent Death»,
«Gilded Midas' Sword ✪✪✪✪✪➎»).

Замер 29.07: каталог 5549 предметов (5322 имени), NBT аукциона 2399 имён,
из них 907 в каталоге отсутствуют.

⚠️ Файл нужен ИМЕННО отдельный, а не «ещё один источник в protected». Причина
в том, что защита имён — решение, а не догадка: список от сервера канонический,
и когда он расходится с нашим, прав он. Отдельный файл видно в git-подобном
сравнении, его можно перечитать глазами и он не смешивается с эвристиками
(«строка редкости в подсказке», «имя из чужого репозитория»).

⚠️ Имена с цветовыми метками (`%%green%%Ballista Fuel Cell`, `§4Sin§5seeker
Scythe`) чистим от разметки, но САМИ НЕ ВЫБРАСЫВАЕМ: на экране игрок видит
именно их, и защищать надо то, что он видит. Служебные заготовки вида
«Axe Preview (Right-Click)» тоже оставляем — переводить их всё равно нельзя.

Запуск:
  python tools/fetch_item_names.py           обновить список
  python tools/fetch_item_names.py --dry     только показать, что изменится
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

CATALOG = "https://api.hypixel.net/v2/resources/skyblock/items"
AUCTION = ROOT / "data" / "work" / "auction_lore.json"
OUT = ROOT / "data" / "work" / "item_names.json"

# Цветовые метки Hypixel: и §-коды, и текстовая форма «%%green%%»
CODES = re.compile(r"§.|%%[a-z_]+%%")


def clean(name: str) -> str:
    return re.sub(r"\s+", " ", CODES.sub("", name)).strip()


def from_catalog() -> dict[str, str]:
    """id -> имя из каталога Hypixel."""
    try:
        with urllib.request.urlopen(CATALOG, timeout=90) as answer:
            data = json.loads(answer.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        print(f"каталог не ответил: {type(error).__name__}")
        return {}
    out = {}
    for item in data.get("items") or []:
        name = clean(str(item.get("name") or ""))
        if name and item.get("id"):
            out[str(item["id"])] = name
    return out


def from_auction() -> dict[str, str]:
    """id -> имя из NBT аукциона: там прокачанные варианты с реколкой и звёздами."""
    if not AUCTION.exists():
        return {}
    try:
        rows = json.loads(AUCTION.read_text(encoding="utf-8")).get("items") or {}
    except (json.JSONDecodeError, OSError):
        return {}
    out = {}
    for item_id, row in rows.items():
        name = clean(str(row.get("name") or ""))
        if name:
            out[str(item_id)] = name
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Имена предметов от сервера")
    parser.add_argument("--dry", action="store_true", help="не записывать файл")
    args = parser.parse_args()

    catalog = from_catalog()
    auction = from_auction()
    if not catalog and not auction:
        print("ни одного источника — нечего писать")
        return 1

    # ⚠️ Накопительно: предмет, снятый с продажи или убранный из каталога,
    # на руках у игроков остаётся, и защита ему по-прежнему нужна.
    known: dict[str, str] = {}
    if OUT.exists():
        try:
            known = json.loads(OUT.read_text(encoding="utf-8")).get("names") or {}
        except (json.JSONDecodeError, OSError):
            known = {}
    was = len(known)

    # Каталог — основа, аукцион дополняет вариантами прокачки.
    extra = {name for name in auction.values() if name not in catalog.values()}
    known.update(catalog)
    for item_id, name in auction.items():
        known.setdefault(item_id + "@auction", name)

    names = sorted(set(known.values()))
    print(f"каталог Hypixel:      {len(catalog)} предметов")
    print(f"NBT аукциона:         {len(auction)} имён, из них не в каталоге {len(extra)}")
    print(f"всего имён в списке:  {len(names)}  (было записей {was})")

    # Сколько из этого защита ещё не знала
    try:
        from protected import real_items
        have = real_items()
        fresh = [name for name in names if name not in have]
        print(f"защита не знала:      {len(fresh)}")
        for name in fresh[:12]:
            print(f"   {name}")
    except (ImportError, OSError):
        pass

    if args.dry:
        print("\nсухой прогон: файл не записан")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_comment": "Item names straight from Hypixel: the catalog "
                    "(resources/skyblock/items) plus NBT of live auctions. "
                    "NEVER translate these - players search for them by name. "
                    "Accumulative: an item pulled from the catalog is still in "
                    "players' inventories. Read by tools/protected.py.",
        "names": known,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
