# -*- coding: utf-8 -*-
"""Влить пачку ручного перевода режима full в заготовку.

    python tools/full_load.py                  сухой прогон
    python tools/full_load.py --yes            влить
    python tools/full_load.py --file FILE      другая пачка

Пара к `full_batch.py`: тот выгружает 60 строк, этот принимает заполненное
поле "ru". Дальше `gen_full_strings.py --write` собирает словарь.

⚠️ КЛЮЧ БЕРЁТСЯ ИЗ ФАЙЛА (поле "key"), а не из напечатанного списка:
значки Hypixel лежат в приватной зоне юникода и из терминала копируются
ПРОБЕЛОМ. Записанная грабля проекта, всплывавшая пять раз.

⚠️ ТРИ КАТЕГОРИИ, А НЕ ДВЕ. Кроме перевода есть решения:
    "-"   переводить нечего  -> _asis      (имя, метка, код, ник)
    "~"   обрывок переноса   -> _fragments (лечится абзацем, покупать вредно)
Без отдельного списка обрывки всплывали бы в КАЖДОЙ пачке и путались
с решениями «нечего».

Проверки на приёме — те же, что у платного прогона:
  * набор МАСОК {iN} обязан совпасть: потерянная маска значит потерянный
    значок на экране;
  * число дырок {n}/{s} обязано совпасть: движок подставляет их ПО ПОРЯДКУ;
  * ЧУЖАЯ ПИСЬМЕННОСТЬ (иероглиф посреди русской фразы) — брак, который
    глаз пропускает, а проверка ловит;
  * ТОЖДЕСТВЕННЫЙ перевод — это решение «оставить как есть», ему место
    в _asis, а не в словаре.
"""
import argparse
import json
import pathlib
import re
import sys
import unicodedata

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from translate_tooltips import ALIEN_SCRIPTS, mask_icons  # noqa: E402

WORK = ROOT / "data" / "work"
SRC = WORK / "full_strings.json"
MARK = re.compile(r"\{i\d+\}")
HOLE = re.compile(r"\{[ns]\}")
CYR = re.compile("[а-яА-ЯёЁ]")


def alien(text: str, origin: str) -> str:
    """Знак чужой письменности, которого НЕ БЫЛО в оригинале."""
    for char in text:
        if char in origin or char.isascii():
            continue
        try:
            name = unicodedata.name(char)
        except ValueError:
            continue
        if any(name.startswith(s) for s in ALIEN_SCRIPTS):
            return char
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=str(WORK / "_batch_next.json"))
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    path = pathlib.Path(args.file)
    if not path.exists():
        print("нет пачки:", path)
        return 1
    rows = json.loads(path.read_text(encoding="utf-8"))
    data = json.loads(SRC.read_text(encoding="utf-8"))
    strings = data.setdefault("strings", {})
    asis = data.setdefault("_asis", [])
    frags = data.setdefault("_fragments", [])

    good, nothing, fragment, bad = {}, [], [], []
    for row in rows:
        ru = (row.get("ru") or "").strip()
        key = row["key"]
        if not ru:
            continue
        if ru == "-":
            nothing.append(key)
            continue
        if ru == "~":
            fragment.append(key)
            continue
        en = row["en"]
        if MARK.findall(en) != MARK.findall(ru):
            bad.append((key, "потеряна маска значка"))
            continue
        if sorted(HOLE.findall(en)) != sorted(HOLE.findall(ru)):
            bad.append((key, "разошлось число дырок {n}/{s}"))
            continue
        stray = alien(ru, key)
        if stray:
            bad.append((key, f"чужая письменность: {stray!r}"))
            continue
        if not CYR.search(ru) and not ru.startswith("@"):
            bad.append((key, "перевод без кириллицы — это решение, ставь «-»"))
            continue
        masked, mapping = mask_icons(key)
        if ru == masked or ru == key:
            nothing.append(key)
            continue
        for mark, char in mapping.items():
            ru = ru.replace(mark, char)
        good[key] = ru

    print(f"в пачке: {len(rows)}")
    print(f"  перевод:          {len(good)}")
    print(f"  переводить нечего:{len(nothing):4}")
    print(f"  обрывок:          {len(fragment)}")
    if bad:
        print(f"  ⚠️ ОТБРАКОВАНО:   {len(bad)}")
        for key, why in bad:
            print(f"      {why}: {key[:60]!r}")
    if not args.yes:
        print("\nСУХОЙ ПРОГОН. Влить: --yes")
        return 1 if bad else 0
    if bad:
        print("\nНЕ ПИШУ: сперва починить отбракованное")
        return 1

    strings.update(good)
    for key in nothing:
        if key not in asis:
            asis.append(key)
    for key in fragment:
        if key not in frags:
            frags.append(key)
    SRC.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nвлито. строк {len(strings)}, «нечего» {len(asis)}, обрывков {len(frags)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
