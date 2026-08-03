"""
Делает правила для ванильных названий предметов и блоков.

СУТЬ. У игрока с русским клиентом переводы Mojang уже лежат на диске: 778
предметов, 1943 блока. Но Hypixel присылает предмет с ЗАДАННЫМ именем «Coal»,
и Minecraft показывает эту строку буквально, минуя собственный перевод.
Отсюда и берётся английский уголь на русском клиенте.

Лечится так: ловим английское название и подставляем ключ (@item.minecraft.coal).
Мод спрашивает перевод у самой игры — получается ровно то, что игрок видит
в одиночной игре. Чужой перевод при этом никуда не копируется, а у игрока
с английским клиентом всё останется английским.

⚠️ ПО УМОЛЧАНИЮ ВЫКЛЮЧЕНО. Названия предметов ищут на аукционе и базаре, а по
русскому названию поиск ничего не найдёт. Поэтому файл создаётся, но в index.json
не прописывается. Включить — дописать "80-vanilla-names.json" в index.json
либо положить файл в config/skyblockru/packs/ у себя.

Запуск:  python tools/gen_vanilla_names.py
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "common" / "80-vanilla-names.json"
JAR_DIR = Path.home() / ".gradle" / "caches" / "fabric-loom"

# Слишком короткие названия ловят лишнее, а односимвольные вовсе бессмысленны
MIN_LENGTH = 3


def find_client_jar() -> Path | None:
    candidates = sorted(JAR_DIR.rglob("minecraft-client.jar"))
    return candidates[-1] if candidates else None


def main() -> int:
    jar = find_client_jar()
    if jar is None:
        print("не нашёл minecraft-client.jar — собери мод хотя бы раз", file=sys.stderr)
        return 1

    with zipfile.ZipFile(jar) as z:
        names = [n for n in z.namelist() if n.endswith("lang/en_us.json")]
        if not names:
            print("в jar нет lang-файла", file=sys.stderr)
            return 1
        lang = json.loads(z.read(names[0]).decode("utf-8"))

    # Предметы важнее блоков: если название совпадает, берём предметный ключ
    by_english: dict[str, str] = {}
    collisions = 0
    for prefix in ("item.minecraft.", "block.minecraft."):
        for key, english in lang.items():
            if not key.startswith(prefix) or not isinstance(english, str):
                continue
            if len(english) < MIN_LENGTH:
                continue
            if english in by_english:
                collisions += 1
                continue
            by_english[english] = key

    # Термины, а не правила целой строки: в описании название стоит ВНУТРИ фразы
    # («нужен Coal»), и правило вида ^Coal$ там не сработает никогда.
    glossary = {english: f"@{key}" for english, key in by_english.items()}

    pack = {
        "id": "vanilla_names",
        "priority": 60,
        "_comment": "Ванильные названия предметов и блоков — ТОЛЬКО в описаниях предметов. "
                    "Заголовки не трогаем: по русскому названию вещь не найти на аукционе. "
                    "В переводе стоит КЛЮЧ, а не текст — мод спрашивает название у самой игры, "
                    "поэтому оно совпадает с ванильным и меняется вместе с языком клиента. "
                    "СГЕНЕРИРОВАНО tools/gen_vanilla_names.py.",
        "only": ["item_lore"],
        "glossary": glossary,
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"названий собрано: {len(by_english)} (совпадений имён пропущено: {collisions})")
    print(f"записано: {OUT.relative_to(ROOT)}")
    print()
    print("Файл создан, но НЕ включён: в index.json не прописан.")
    print("Включить — дописать туда \"80-vanilla-names.json\".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
