"""
Названия ЛОКАЦИЙ и имена NPC с вики — то, что переводить нельзя нигде.

⚠️ Зачем. Списки защищённых имён в проекте собирались из того, что мод
встретил на экране (`protected.py`), и потому заведомо неполны: локация,
мимо которой игрок не ходил, в список не попадала — и её мог перевести
очередной прогон. По названию места игрок ориентируется и ищет варпы,
по имени NPC — гайды; переведённое «Birch Park» ломает и то, и другое.

На вики есть полная таблица: локации помечены шаблоном {{Zone|…}},
а NPC каждой локации — обычными ссылками в своей колонке. Это источник,
а не догадка.

⚠️ Имена, которые НАШ СЛОВАРЬ уже переводит, в защиту не берём: одно
подсвеченное «Defense» когда-то запретило бы переводить характеристику
по всему проекту. Та же грабля записана про `resolve_collisions`.

Запуск:
  python tools/fetch_places.py           показать, что нашлось
  python tools/fetch_places.py --apply   записать в data/work/places_wiki.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_wiki import fetch  # noqa: E402

OUT = ROOT / "data" / "work" / "places_wiki.json"

ZONE = re.compile(r"\{\{Zone\|([^|}]+)")
LINK = re.compile(r"\[\[([^\]|#]+)(?:[^\]]*)?\]\]")
# строка таблицы: колонка NPC идёт после колонки ресурсов
ROW = re.compile(r"\n\|-")

# Слова, которые в колонке NPC означают не персонажа, а механику или предмет.
NOT_NPC = {
    "NPC", "NPCs", "Reforge Anvil", "Auction House", "Bazaar", "Bank",
    "Minion", "Minions", "Wardrobe", "Trades", "Shop", "Shops",
}


def title_case(name: str) -> bool:
    """Похоже ли на имя собственное: значимые слова с заглавной."""
    words = [w for w in re.findall(r"[A-Za-z'\-]+", name)
             if w.lower() not in {"of", "the", "and", "a", "an", "in", "on"}]
    return bool(words) and all(w[0].isupper() for w in words)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Локации и NPC с вики")
    parser.add_argument("--apply", action="store_true", help="записать файл")
    args = parser.parse_args()

    raw = fetch("Locations")

    zones: set[str] = set()
    for hit in ZONE.findall(raw):
        name = hit.strip()
        # {{Zone|private island}} — вики пишет вразнобой; приводим к тому виду,
        # в каком название стоит на экране: с Заглавных.
        if name and len(name) < 40:
            zones.add(" ".join(w[:1].upper() + w[1:] for w in name.split()))

    npcs: set[str] = set()
    for row in ROW.split(raw):
        # ⚠️ Берём ссылки ТОЛЬКО из колонки «NPCs Found», а не из всей строки.
        # Первая версия хватала всё подряд и притащила «Acacia Log», «Apple»,
        # «Aspect of the End» — это колонка «Resources Found», то есть ПРЕДМЕТЫ.
        # Защитив их как имена NPC, мы запретили бы переводить материалы.
        #
        # Колонки идут: зона(ы) | ресурсы | NPC | требования. Значит нужная —
        # ПРЕДПОСЛЕДНЯЯ: число первых колонок пляшет из-за colspan/rowspan,
        # а хвост таблицы устойчив.
        cells = [c.strip() for c in row.split("\n|") if c.strip()]
        # ⚠️ Полных строк ровно четыре колонки: зона | ресурсы | NPC | требования.
        # У строк покороче предпоследняя ячейка — это РЕСУРСЫ, и оттуда лезли
        # «Apple», «Blaze Rod», «Brown Mushroom». Берём только там, где колонок
        # хватает; имена NPC всё равно надёжнее брать из самих реплик
        # (`fetch_dialogues.py`), где говорящий назван прямо.
        if len(cells) < 4:
            continue
        for hit in LINK.findall(cells[-2]):
            name = hit.strip()
            if not name or len(name) > 34 or name in NOT_NPC:
                continue
            if name in zones or not title_case(name):
                continue
            npcs.add(name)

    # ⚠️ Однословные названия отсеиваем ТОЛЬКО по частоте строчного написания,
    # и порог здесь свой — выше, чем у `looks_like_name`.
    #
    # Тот фильтр проверяет ещё и длину («короче четырёх букв — не имя»), а на
    # списке с вики это режет настоящие: Jax, Bob, Sam. И порог у него 3, из-за
    # чего вылетали Jerry (7) и Blacksmith (3) — тоже настоящие.
    #
    # Здесь источник авторитетнее: если вики пометила слово шаблоном {{Zone}},
    # это место. Отбрасываем лишь то, что в НАШИХ текстах постоянно встречается
    # обычным словом — Bank (28 раз), Bone (19), Gemstone (18), Farm (13):
    # защитив их, мы запретили бы переводить слово в прозе.
    OFTEN_LOWERCASE = 10
    try:
        from protected import ordinary_words
        common = ordinary_words()
        def plain_word(name: str) -> bool:
            return " " not in name and common.get(name.lower(), 0) >= OFTEN_LOWERCASE
        thrown = sorted(n for n in zones | npcs if plain_word(n))
        zones = {n for n in zones if not plain_word(n)}
        npcs = {n for n in npcs if not plain_word(n)}
    except Exception:  # noqa: BLE001
        thrown = []

    print(f"локаций найдено: {len(zones)}")
    print(f"имён NPC найдено: {len(npcs)}")
    if thrown:
        print(f"отсеяно как обычные слова: {len(thrown)} — {', '.join(thrown[:10])}")

    # что из этого мы УЖЕ знаем
    try:
        import protected
        known = protected.collect()
    except Exception:  # noqa: BLE001
        known = set()
    new_zones = sorted(zones - known)
    new_npcs = sorted(npcs - known)
    print()
    print(f"НОВЫХ локаций (не было в защите): {len(new_zones)}")
    print("   " + ", ".join(new_zones[:14]))
    print()
    print(f"НОВЫХ имён NPC: {len(new_npcs)}")
    print("   " + ", ".join(new_npcs[:14]))

    # ⚠️ Пересечение с нашим словарём: если слово уже переводится, защищать
    # его нельзя — иначе запретим перевод обычного термина.
    try:
        import status
        dic = status.Dictionaries()
        clash = sorted((zones | npcs) & set(dic.exact))
    except Exception:  # noqa: BLE001
        clash = []
    if clash:
        print()
        print(f"⚠️ уже переводятся словарём, в защиту НЕ берём: {len(clash)}")
        print("   " + ", ".join(clash[:12]))

    if args.apply:
        OUT.write_text(json.dumps({"locations": sorted(zones), "npc": sorted(npcs),
                                   "clash": clash}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print()
        print(f"записано: {OUT.relative_to(ROOT)}")
    else:
        print()
        print("это СУХОЙ прогон — чтобы записать, добавь --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
