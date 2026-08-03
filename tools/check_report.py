"""
Отчёт обязан ЛОВИТЬ беду и не показывать бедой наши решения.

Зачем. `report.py` открывает каждую сессию, и цена вранья в нём высшая:
ложная находка наверху списка приучает не смотреть в список вовсе (эта беда
в проекте уже стоила двух вечеров на scan.py и scan_all.py), а пропущенная
настоящая беда уезжает к игроку и возвращается скриншотом.

⚠️ И «находок нет» с «инструмент ослеп» выглядят ОДИНАКОВО. Ровно так жил
отсев ников: строки «boml9's Profile» и «cherepahaHlov_'s Profile» из отчёта
пропадали — но не потому, что признак их узнавал, а потому, что цифра и «_»
ломали `\b` в регулярке, и слово не находилось ВООБЩЕ. Со стороны это
неотличимо от работающего фильтра. Настоящая смесь языков со словом
«Tier9» прошла бы так же молча.

Поэтому каждый признак проверяется НА ОБА КРАЯ: ложное обязано уйти,
настоящее — остаться. Заведомо истинный случай тут не формальность,
а единственное, что отличает сторожа от молчания.

Запуск:
  python tools/check_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import report  # noqa: E402
import status  # noqa: E402
from protected import collect, real_items, resolve_collisions, wiki_places  # noqa: E402

# --- СМЕСЬ ЯЗЫКОВ: (оригинал, перевод, ждём ли находку) ---
#
# Владелец из притяжательной формы — не смесь: по-русски принадлежность
# передаёт падеж, «'s» отпадает, а имя обязано остаться латиницей.
MIXED = [
    ("guysgv's Profile", "Профиль guysgv", False),
    ("guysgv's Museum", "Музей guysgv", False),
    # ⚠️ цифра и «_» в нике: прежняя регулярка их не видела вовсе
    ("boml9's Profile", "Профиль boml9", False),
    ("cherepahaHlov_'s Profile", "Профиль cherepahaHlov_", False),
    # имя кончается на «s» — апостроф без «s»
    ("nokliis' Profile", "Профиль nokliis", False),
    # имя NPC в притяжательной форме: тот же случай, что записан в protected
    ("Taylor's Cosmetics", "косметика Taylor", False),

    # --- заведомо истинные: обязаны найтись ---
    ("Grants +5 Speed for 3 seconds.", "Даёт +5 Speed на 3 с.", True),
    # владелец есть, но английским осталось ДРУГОЕ слово: отсев обязан
    # снимать ровно владельца, а не всю строку
    ("guysgv's Profile Viewer", "Профиль guysgv Viewer", True),
    # владелец СОХРАНИЛ апостроф — значит переведён не был, это смесь
    ("Zorkul's Breath", "Zorkul's дыхание", True),
    ("Wobblebonk Upgrades", "Wobblebonk улучшения", True),
    # ⚠️ слово с цифрой: ровно тот случай, который прежний признак пропускал
    ("Reach Tier9 to unlock", "Достигни Tier9 чтобы открыть", True),
]

# --- КОЛОНКИ: (строка, кусок, ждём ли его в работе, источник) ---
#
# Двойственное слово («Village», «Mountain») в защиту не входит намеренно,
# но в КОЛОНКЕ ПОЛОСЫ второго смысла у него нет — там всегда метка локации.
#
# ⚠️ Перед «Village» стоит ЗНАЧОК Hypixel U+E067 — он непечатаем и в терминале
# выглядит пробелом. Правя эти строки, не набирай их руками: значок молча
# исчезнет, случай станет проверять не то, а сторож продолжит зеленеть.
# Проверить целость: коды первых символов строки должны содержать U+E067.
BAR = [
    (" Village   1,234/1,234❤", " Village", False, "action_bar"),
    (" Birch Park   500❤", " Birch Park", False, "action_bar"),
    # заведомо истинный: незнакомая колонка обязана остаться работой
    (" Village   Totally Unknown Thing", "Totally Unknown Thing", True, "action_bar"),
    # ⚠️ обратный край ОБЛАСТИ: в чате «Village» — обычное слово, и отсев
    # по списку мест там неверен
    (" Village   Some Other Text", " Village", True, "chat"),
]


def main() -> int:
    bad = 0

    def want(case: str, got: bool, expect: bool, extra: str = "") -> None:
        nonlocal bad
        if got == expect:
            print(f"  ок      {case}")
            return
        bad += 1
        print(f"  СЛОМАНО {case}")
        print(f"          ожидалось {'находка' if expect else 'тишина'},"
              f" вышло {'находка' if got else 'тишина'}")
        if extra:
            print(f"          {extra}")

    print("=== СМЕСЬ ЯЗЫКОВ ===")
    guarded = resolve_collisions(collect(), quiet=True)
    real_load = report.load
    try:
        for src, ru, expect in MIXED:
            report.load = lambda _name, _s=src, _r=ru: {"lines": {_s: _r}}
            found = report.mixed_lines(guarded)
            rest = ", ".join(found[0][2]) if found else ""
            want(f"{src!r} -> {ru!r}", bool(found), expect,
                 f"осталось английским: {rest}" if rest else "")
    finally:
        report.load = real_load

    print("\n=== КУСКИ СТРОК (полоса над хотбаром и наборы вариантов) ===")
    places = wiki_places()
    if not places:
        print("  СЛОМАНО список мест пуст — data/work/places_wiki.json не прочитан")
        return 1
    print(f"  мест в списке: {len(places)}")
    dic = status.Dictionaries()
    items = real_items()
    for line, part, expect, source in BAR:
        left = status.uncovered_columns(line, dic, items, source)
        want(f"[{source}] {part!r}", part in left, expect,
             f"вернулось: {left}" if left != [part] else "")

    print()
    if bad:
        print(f"СЛОМАНО: {bad}")
        return 1
    print("СЛОМАНО: 0 — отчёт ловит настоящее и молчит на решениях")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
