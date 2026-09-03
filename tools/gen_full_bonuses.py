# -*- coding: utf-8 -*-
"""
Режимные версии строк-рамок, где имя бонуса держит ТОЧНАЯ запись.

Беда, ради которой написано (27.08, скриншоты игрока). На броне видно:

    Бонус полного комплекта: Expert Miner (0/4)
    Ступенчатый бонус: Witherborn (0/4)

Рамка по-русски, имя английское — при том что в полном режиме имя должно
быть русским, а сама броня уже переведена («Ботинки рвения»). Игрок читает
обе строки в ОДНОЙ подсказке, и разнобой там виден сразу.

⚠️ ПОЧЕМУ НЕ ХВАТИЛО ПРАВИЛА. Строку «Full Set Bonus: X» ловит правило,
и режимное правило с `tg` её перекрывает (`05-full-rules`, priority 36).
А «Tiered Bonus: X» и «Ability: X» у многих предметов закрыты ТОЧНОЙ
записью в `41-headers` — и `exact` движок ищет РАНЬШЕ правил, всегда,
независимо от priority. Значит правилом их не перебить, нужна своя
точная запись с МЕНЬШИМ priority.

⚠️ ИМЯ БЕРЁМ У СЛОВАРЯ, А НЕ ПЕРЕВОДИМ ЗАНОВО. Иначе бонус разойдётся
с бронёй того же сета: «Ботинки рвения» против «бонус Fervor».

Запуск:
  python tools/gen_full_bonuses.py            покажет
  python tools/gen_full_bonuses.py --write    соберёт 06-full-bonuses.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import status  # noqa: E402

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
LANG = "ru_ru"
OUT = PACKS / LANG / "06-full-bonuses.json"
CYR = re.compile("[а-яёА-ЯЁ]")
LATIN = re.compile(r"[A-Za-z]")

# Рамки: (шаблон ключа, как достать имя). Хвост со счётчиком и горячей
# клавишей в имя не входит — он у рамки свой.
FRAMES = [
    re.compile(r"^(?P<head>Full Set Bonus: )(?P<name>.+?)(?P<tail> \([^)]*\))?$"),
    re.compile(r"^(?P<head>Tiered Bonus: )(?P<name>.+?)(?P<tail> \([^)]*\))?$"),
    re.compile(r"^(?P<head>\{n\}-Piece Set Bonus: )(?P<name>.+?)(?P<tail>)$"),
    re.compile(r"^(?P<head>[∙•⦾]? ?Ability: )(?P<name>.+?)"
               r"(?P<tail>\s{2,}[A-Z /]+)?$"),
]


def sources() -> dict[str, str]:
    """Ключ -> его ОБЫЧНЫЙ перевод, из всех включённых словарей."""
    out: dict[str, str] = {}
    for path in sorted(PACKS.rglob("*.json")):
        if path.name in ("index.json", OUT.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # ⚠️ Берём ТОЛЬКО обычные словари: у режимных имя уже русское,
        # и строить поверх них нечего.
        if data.get("group") or data.get("default") is False:
            continue
        for key, value in (data.get("exact") or {}).items():
            if isinstance(value, str) and value:
                out.setdefault(key, value)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--show", type=int, default=10)
    args = ap.parse_args()

    full = status.Dictionaries(groups={"full"}, without={OUT.name})
    made: dict[str, str] = {}
    skipped_no_name = 0
    for key, russian in sources().items():
        for frame in FRAMES:
            hit = frame.match(key)
            if not hit:
                continue
            name = hit.group("name").strip()
            if not name or not LATIN.search(name) or CYR.search(name):
                break
            # Имя должно уже стоять в переводе ДОСЛОВНО — иначе рамка
            # переведена иначе, и подменять вслепую нельзя.
            if name not in russian:
                break
            got = (status.lookup(name, full, origin="item_lore")
                   or status.lookup(name, full, origin="item_name"))
            value = str((got[0] if isinstance(got, tuple) else got) or "")
            if not value or not CYR.search(value):
                skipped_no_name += 1
                break
            fresh = russian.replace(name, value)
            if fresh != russian:
                made[key] = fresh
            break

    print(f"строк-рамок с русским именем: {len(made)}")
    print(f"пропущено (имя ещё не переведено): {skipped_no_name}")
    for key, value in list(made.items())[:args.show]:
        print(f"   {key[:52]}")
        print(f"      -> {value[:52]}")

    if not args.write:
        print()
        print("СУХОЙ ПРОГОН. Записать: --write")
        return 0

    # ⚠️ Пустой словарь не пишем: строки-рамки из источников не исчезают,
    # значит пустой выход — это ошибка разбора, а не «работы нет».
    if not made:
        print("нечего писать — источники не разобрались, файл не трогаю")
        return 1

    pack = {
        "id": "full_bonuses",
        # ⚠️ 6 — ниже обычных словарей (`41-headers` 24, `20-ui` 30):
        # у `exact` побеждает МЕНЬШИЙ priority. Выше уже занятых 1–5.
        "priority": 6,
        "default": False,
        "group": "full",
        "about": "имена бонусов комплекта и способностей по-русски "
                 "(Full Set Bonus: Expert Miner -> Опытный шахтёр)",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_full_bonuses.py — правь СКРИПТ. "
                    "Имена берутся у режимного словаря, рамка — у обычного: "
                    "так бонус не расходится с бронёй того же сета.",
        "exact": dict(sorted(made.items())),
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(f"записано: {OUT.relative_to(ROOT)} ({len(made)} записей)")
    index = json.loads((PACKS / "index.json").read_text(encoding="utf-8"))
    if OUT.name not in (index.get("languages") or {}).get(LANG, []):
        print(f"⚠️ впиши {OUT.name} в index.json -> languages.{LANG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
