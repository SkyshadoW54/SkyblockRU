"""
Делает правила для ванильных зачарований Minecraft.

Смысл: имена вроде Impaling, Sharpness, Protection — обычные ванильные, и у них
уже есть официальный перевод Mojang. Копировать его в наш словарь нельзя и не нужно:
вместо перевода пишем КЛЮЧ (@enchantment.minecraft.impaling), а мод спрашивает
название у самой игры. Плюсы:
  - у игрока с английским клиентом останется английское название;
  - при обновлении Minecraft переводы подтянутся сами;
  - чужой перевод к себе не копируется.

Английские названия берутся из lang-файла клиента — они нужны как ОБРАЗЕЦ для
сопоставления, потому что Hypixel присылает строку именно на английском.

Запуск:  python tools/gen_vanilla_enchants.py
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "common" / "70-enchants.json"
INDEX = OUT.parent / "index.json"

# Клиентский jar, распакованный Gradle при сборке мода
JAR_DIR = Path.home() / ".gradle" / "caches" / "fabric-loom"


def find_client_jar() -> Path | None:
    candidates = sorted(JAR_DIR.rglob("minecraft-client.jar"))
    return candidates[-1] if candidates else None


def main() -> int:
    jar = find_client_jar()
    if jar is None:
        print("не нашёл minecraft-client.jar — собери мод хотя бы раз", file=sys.stderr)
        return 1
    print(f"беру названия из {jar.name}")

    with zipfile.ZipFile(jar) as z:
        names = [n for n in z.namelist() if n.endswith("lang/en_us.json")]
        if not names:
            print("в jar нет lang-файла", file=sys.stderr)
            return 1
        lang = json.loads(z.read(names[0]).decode("utf-8"))

    enchants = {
        key: value for key, value in lang.items()
        if key.startswith("enchantment.minecraft.") and isinstance(value, str)
    }
    print(f"ванильных зачарований: {len(enchants)}")

    rules = []
    for key, english in sorted(enchants.items(), key=lambda kv: -len(kv[1])):
        # Hypixel пишет «Название УРОВЕНЬ» римскими цифрами; уровень оставляем как есть
        rules.append({
            "p": f"^{re.escape(english)} ([IVXLC]+)$",
            "r": f"@{key} $1",
            "_key": key,
        })
        # встречается и без уровня
        rules.append({
            "p": f"^{re.escape(english)}$",
            "r": f"@{key}",
            "_key": key,
        })

    pack = {
        "id": "enchants",
        "priority": 35,
        "_comment": "Ванильные зачарования Minecraft. В переводе стоит не текст, а КЛЮЧ "
                    "(@enchantment.minecraft.*) — мод спрашивает название у самой игры, "
                    "поэтому оно совпадает с ванильным переводом и меняется вместе с языком клиента. "
                    "СГЕНЕРИРОВАНО tools/gen_vanilla_enchants.py — правь генератор, а не этот файл. "
                    "Кастомные зачарования Hypixel сюда не входят: у них ванильного перевода нет.",
        "regex": rules,
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    # index.json теперь разложен по языкам: common — языконезависимые,
    # languages.<язык> — перевод. Файл мимо списка мод не загрузит.
    listing = index.setdefault("common", [])
    if OUT.name not in listing:
        listing.append(OUT.name)
        listing.sort()
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"добавил {OUT.name} в index.json")

    print(f"правил: {len(rules)}")
    print(f"записано: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
