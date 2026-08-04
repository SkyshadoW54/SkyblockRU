"""
Переносит готовые переводы из рабочего файла в словарь мода.

Рабочие файлы в data/work/ содержат всё подряд, включая непереведённое.
В мод попадает только готовое: пустые записи движок и так пропустит,
но незачем раздувать ими jar.

Запуск:
  python tools/export_pack.py from_game 90-from-game.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# Словари разложены по языкам: packs/<язык>/. Скрипты этого проекта делают
# русский, поэтому пишут сюда. Для другого языка — поменять одну строку.
LANG = "ru_ru"
INDEX = PACKS / "index.json"


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    source = WORK / f"{sys.argv[1]}.json"
    target = PACKS / LANG / sys.argv[2]

    if not source.exists():
        print(f"нет файла: {source}")
        return 1

    pack = json.loads(source.read_text(encoding="utf-8"))
    exact = {k: v for k, v in (pack.get("exact") or {}).items() if v}
    rules = [r for r in (pack.get("regex") or []) if r.get("r")]

    if not exact and not rules:
        print("переводов пока нет")
        return 1

    out = {
        "id": pack.get("id", target.stem),
        "priority": pack.get("priority", 20),
        "_comment": f"Собрано в игре и переведено. Файл собирается автоматически "
                    f"из data/work/{source.name} — правь рабочий файл, а не этот.",
    }
    if exact:
        out["exact"] = exact
    if rules:
        out["regex"] = rules
    # ⚠️ Пометка «тождественность тут ОСОЗНАННА» едет из рабочего файла.
    #
    # Запись «A to Z» -> «A to Z» выглядит мусором, но держит построчный путь:
    # Paragraphs.listed спрашивает lookup у КАЖДОЙ строки куска, и пустой ответ
    # заставляет мод разрезать абзац вместо точного построчного перевода.
    # Без переноса пометка стиралась бы при каждой пересборке, и сторож
    # снова горел бы на решении игрока (tools/fix_identity.py).
    identity = [k for k in (pack.get("_identity") or []) if k in exact]
    if identity:
        out["allowIdentity"] = sorted(identity)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    # index.json теперь разложен по языкам: common — языконезависимые,
    # languages.<язык> — перевод. Файл мимо списка мод не загрузит.
    listing = index.setdefault("languages", {}).setdefault(LANG, [])
    if target.name not in listing:
        listing.append(target.name)
        listing.sort()
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"добавил {target.name} в index.json")

    print(f"перенесено: {len(exact)} строк, {len(rules)} правил")
    print(f"записано: {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
