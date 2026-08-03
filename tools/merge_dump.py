"""
Сводит вместе то, что мод собрал в игре, и то, что уже переведено.

Мод складывает незнакомые строки в
  %APPDATA%\\.minecraft\\config\\skyblockru\\dump\\untranslated.json
Этот скрипт добавляет их в рабочий словарь, не затирая уже сделанные переводы,
и убирает записи, которые к этому моменту уже переведены в других пакетах.

Запуск:
  python tools/merge_dump.py                      # найдёт дамп сам
  python tools/merge_dump.py путь/к/untranslated.json
  python tools/merge_dump.py --out work/chat.json  # куда складывать (по умолчанию data/work/from_game.json)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
DEFAULT_OUT = ROOT / "data" / "work" / "from_game.json"


def default_dump_path() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    path = Path(appdata) / ".minecraft" / "config" / "skyblockru" / "dump" / "untranslated.json"
    return path if path.exists() else None


def load_translated() -> dict[str, str]:
    """Все уже переведённые строки — из встроенных пакетов и из рабочих файлов."""
    done: dict[str, str] = {}
    search = [PACKS, ROOT / "data" / "work"]
    for folder in search:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                pack = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for src, dst in (pack.get("exact") or {}).items():
                if dst:
                    done[src] = dst
    return done


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = DEFAULT_OUT
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
        if not out.is_absolute():
            out = ROOT / out

    if args:
        dump_path = Path(args[0])
    else:
        found = default_dump_path()
        if found is None:
            print("дамп не найден. Поиграй с включённым сбором (config.json -> dumpUntranslated),")
            print("выполни в игре /skyblockru dump и запусти скрипт снова,")
            print("либо укажи путь к файлу первым аргументом.", file=sys.stderr)
            return 1
        dump_path = found

    print(f"дамп: {dump_path}")
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    incoming = dump.get("exact") or {}
    print(f"строк в дампе: {len(incoming)}")

    done = load_translated()
    print(f"уже переведено где-либо: {len(done)}")

    existing: dict[str, str] = {}
    if out.exists():
        try:
            existing = (json.loads(out.read_text(encoding="utf-8")).get("exact") or {})
        except (json.JSONDecodeError, OSError):
            existing = {}

    result: dict[str, str] = dict(existing)
    added = 0
    already = 0
    for source in incoming:
        if source in done:
            already += 1
            result.pop(source, None)  # перевод появился в другом пакете — здесь запись лишняя
            continue
        if source not in result:
            result[source] = ""
            added += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "id": out.stem,
        "priority": 20,
        "_comment": "Собрано из игры. Переводи значения, потом положи файл в "
                    "config/skyblockru/packs/ и выполни /skyblockru reload",
        "exact": result,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    left = sum(1 for value in result.values() if not value)
    print()
    print(f"новых строк добавлено: {added}")
    print(f"уже переведено ранее (пропущено): {already}")
    print(f"в файле {out.relative_to(ROOT)}: всего {len(result)}, ждут перевода {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
