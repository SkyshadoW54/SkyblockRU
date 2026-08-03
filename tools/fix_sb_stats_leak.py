"""
Возвращает из выключенного sb_stats записи, чья подпись НЕ значится жаргоном.

⚠️ Как они туда попали. `split_sb_stats` уносит запись, если в КЛЮЧЕ есть
жаргонное слово. «Heat Resistance: +5» содержит «Heat» — и уехало вместе с ним,
хотя переводиться должно («Heat — английский, Heat Resistance — переводим»,
решение игрока). То же с «Treasure Chance» (внутри «Chance») и «Your Bonus:
{n} Sugar Cane Fortune» (внутри «Fortune»).

Последствие было двойным: на экране английский вместо перевода, а справка
по Shift показывала статью про КОРОТКИЙ термин — «Heat» вместо «Heat
Resistance», потому что длинного в тексте она уже не видела.

⚠️ Признак возврата — подпись целиком, а не вхождение слова. Именно подмена
этих двух вопросов и создала беду.

Запуск:
    python tools/fix_sb_stats_leak.py          показать
    python tools/fix_sb_stats_leak.py --yes    вернуть
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "ru_ru"
JARGON_PACK = PACKS / "78-sb-stats.json"
HOME_PACK = PACKS / "10-stats.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))

LABEL = re.compile(r"^([A-Za-z][A-Za-z' ]*?)\s*:")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Возврат ошибочно выключенных записей")
    parser.add_argument("--yes", action="store_true", help="применить")
    args = parser.parse_args()

    import terms as registry
    jargon = set(registry.of("stat_jargon"))

    data = json.loads(JARGON_PACK.read_text(encoding="utf-8"))
    home = json.loads(HOME_PACK.read_text(encoding="utf-8"))

    move_exact, move_gloss = {}, {}
    for key, value in (data.get("exact") or {}).items():
        match = LABEL.match(key)
        if match and match.group(1).strip() not in jargon:
            move_exact[key] = value
    for key, value in (data.get("glossary") or {}).items():
        if key not in jargon:
            move_gloss[key] = value

    print(f"вернуть точных записей: {len(move_exact)}, из глоссария: {len(move_gloss)}")
    for key, value in move_exact.items():
        print(f"  {key!r} -> {value!r}")
    for key, value in move_gloss.items():
        print(f"  глоссарий {key!r} -> {value!r}")

    if not (move_exact or move_gloss):
        return 0
    if not args.yes:
        print("\nСУХОЙ ПРОГОН. Применить: --yes")
        return 0

    for key in move_exact:
        data["exact"].pop(key, None)
    for key in move_gloss:
        data["glossary"].pop(key, None)
    home.setdefault("exact", {}).update(move_exact)
    home.setdefault("glossary", {}).update(move_gloss)

    JARGON_PACK.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    HOME_PACK.write_text(json.dumps(home, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nперенесено в {HOME_PACK.name}: {len(move_exact) + len(move_gloss)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
