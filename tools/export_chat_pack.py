"""
Переносит переведённые правила чата из рабочего файла в словарь мода.

Рабочий файл data/work/chat_rules.json содержит ВСЕ импортированные шаблоны,
включая ещё не переведённые. В мод попадают только готовые: правило без
перевода движок всё равно пропустит, но незачем раздувать jar пустышками.

Запуск:  python tools/export_chat_pack.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work" / "chat_rules.json"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# Словари разложены по языкам: packs/<язык>/. Скрипты этого проекта делают
# русский, поэтому пишут сюда. Для другого языка — поменять одну строку.
LANG = "ru_ru"
OUT = PACKS / LANG / "60-chat-rules.json"
INDEX = PACKS / "index.json"


def main() -> int:
    if not WORK.exists():
        print(f"нет рабочего файла: {WORK}")
        print("сначала: python tools/fetch_skyhanni.py")
        return 1

    pack = json.loads(WORK.read_text(encoding="utf-8"))
    ready = [r for r in pack.get("regex") or [] if r.get("r")]
    if not ready:
        print("переведённых правил пока нет")
        return 1

    out = {
        "id": "chat_rules",
        "priority": 20,
        "_comment": "Правила для сообщений чата. Шаблоны из SkyHanni-REPO (MIT), переводы наши. "
                    "Файл собирается автоматически из data/work/chat_rules.json — "
                    "правь рабочий файл, а не этот.",
        "_source": "https://github.com/hannibal002/SkyHanni-REPO (MIT)",
        "regex": ready,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # файл должен быть в списке встроенных, иначе мод его не прочитает
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    # index.json теперь разложен по языкам: common — языконезависимые,
    # languages.<язык> — перевод. Файл мимо списка мод не загрузит.
    listing = index.setdefault("languages", {}).setdefault(LANG, [])
    if OUT.name not in listing:
        listing.append(OUT.name)
        listing.sort()
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"добавил {OUT.name} в index.json")

    total = len(pack.get("regex") or [])
    print(f"перенесено правил: {len(ready)} из {total}")
    print(f"записано: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
