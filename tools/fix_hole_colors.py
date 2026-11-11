# -*- coding: utf-8 -*-
"""Вернуть цвет ЧИСЛУ в режимном переводе абзаца, если ручная правка его потеряла.

    python tools/fix_hole_colors.py            покажет, что поправит
    python tools/fix_hole_colors.py --write    поправит data/work/full_paragraphs_ru.json

Беда, ради которой написано (13.10, снимок игрока — Fierce Tarantula Helmet
в режиме full). В обычном переводе «Grants +75 ♥ Health» число зелёное:
«Даёт §a+{n}§7 §c к здоровью§7». Режимная версия того же абзаца правилась
руками (термин «Health» -> «здоровью»), и при переписывании цвет у числа
отвалился: «Даёт +{n} §c к здоровью§7» — на экране «+75» серое, а в
оригинале зелёное. Таких абзацев в заготовке 120 из 7 504 — не опечатка,
а класс: правка термина руками теряет РАЗМЕТКУ ВОКРУГ ЧИСЕЛ, потому что
число стоит рядом с термином и переписывается вместе с ним.

Что делает. Для каждой готовой записи (`done`) сверяет `ru` (режимная
версия) с `base` (обычный перевод, он же источник разметки). Берёт
ТОЛЬКО самый узкий и бесспорный случай: в `base` число обёрнуто своим
цветом целиком — «§a+{n}§7», «§c{n}%§7», «§b{n}x§7» (код прямо перед
знаком/числом, код прямо после), — а в `ru` то же по счёту число стоит
голым, в цвете окружающего текста. Тогда в `ru` ставится тот же код перед
числом и возврат к цвету, который там действовал, после него.

Чего НЕ делает, нарочно:
  * не трогает числа, у которых в `ru` уже стоит код рядом — это решение
    человека («§c+{n}x§7 к §cурону» переписано осознанно);
  * не трогает цветные куски со словами («§c+{n} к силе§7»): где кончается
    термин в русской фразе, машина не знает — записанное правило проекта;
  * не меняет ни одного знака текста: только вставляет §-коды. Проверка —
    текст без кодов до и после совпадает знак в знак.

⚠️ Число — это дырка `{n}`; `{s}` не число и цвета по этому признаку не
получает. Знаки рядом с дыркой: слева `+`/`-`, справа `%`/`x` — ровно те,
что встречаются в разметке Hypixel у чисел («+100%», «2x»).

Сторож на обоих краях — `--selftest`: подсаженная потеря чинится,
осознанная переразметка и кусок со словами остаются как были.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work" / "full_paragraphs_ru.json"

SECTION = "§"
CODE = re.compile("§[0-9a-fk-or]")
# цветной кусок из ОДНОГО числа: код, знак, дырка, суффикс, код
NUM_SPAN = re.compile(r"(§[0-9a-f])([+\-]?\{n\}[%x]?)(?=§[0-9a-fk-or])")
HOLE = re.compile(r"\{n\}")


def color_at(text: str, pos: int) -> str:
    """Какой цветовой код действует перед позицией pos (последний §-код слева)."""
    found = ""
    for hit in CODE.finditer(text, 0, pos):
        code = hit.group(0)
        if code[1] in "0123456789abcdef":
            found = code
        elif code == "§r":
            found = ""
    return found


def strip_codes(text: str) -> str:
    return CODE.sub("", text)


def fix_one(base: str, ru: str) -> tuple[str, list[str]]:
    """Вернуть исправленный `ru` и список того, что поправлено."""
    if not base or not ru:
        return ru, []
    base_holes = [m.start() for m in HOLE.finditer(base)]
    ru_holes = [m.start() for m in HOLE.finditer(ru)]
    if len(base_holes) != len(ru_holes):
        # число дырок разошлось — это другая беда, её ловит загрузчик
        return ru, []

    # какие по счёту дырки в base обёрнуты цветом целиком
    wrapped: dict[int, tuple[str, str, str]] = {}
    for hit in NUM_SPAN.finditer(base):
        code, span = hit.group(1), hit.group(2)
        hole_pos = hit.start(2) + span.index("{n}")
        index = base_holes.index(hole_pos)
        prefix = span[: span.index("{n}")]
        suffix = span[span.index("{n}") + 3:]
        wrapped[index] = (code, prefix, suffix)

    notes: list[str] = []
    out = ru
    # правим справа налево, чтобы позиции левых дырок не сдвигались
    for index in sorted(wrapped, reverse=True):
        code, prefix, suffix = wrapped[index]
        hole = [m.start() for m in HOLE.finditer(out)][index]
        start = hole - len(prefix)
        end = hole + 3 + len(suffix)
        if start < 0 or out[start:hole] != prefix or out[hole + 3:end] != suffix:
            continue
        # рядом уже стоит код — человек красил сам, не лезем
        if start >= 2 and out[start - 2] == SECTION:
            continue
        current = color_at(out, start)
        if current == code:
            continue
        # сразу после числа уже стоит код — возврат цвета не нужен
        if end + 1 < len(out) and out[end] == SECTION:
            back = ""
        else:
            back = current if current else "§r"
        out = out[:start] + code + out[start:end] + back + out[end:]
        notes.append(f"{code}{prefix}{{n}}{suffix}{back}")
    if strip_codes(out) != strip_codes(ru):
        raise AssertionError("текст изменился — правка отменена")
    return out, notes


def selftest() -> int:
    cases = [
        # подсаженная потеря — чинится
        ("§7Даёт §a+{n}§7 §c к здоровью§7.", "§7Даёт +{n} §c к здоровью§7.",
         "§7Даёт §a+{n}§7 §c к здоровью§7."),
        # процент и возврат к цвету тела
        ("§7на §2{n}%§7 на §a{n}§7 с.", "§7на §2{n}%§7 на {n} с.",
         "§7на §2{n}%§7 на §a{n}§7 с."),
        # осознанная переразметка — не трогаем
        ("§7и §c+{n}x§c к §cурону§7", "§7и §c+{n}x§7 к §cурону§7",
         "§7и §c+{n}x§7 к §cурону§7"),
        # кусок со словами — не трогаем
        ("§7Даёт §c+{n} к силе§7 всем", "§7Даёт +{n} к силе всем",
         "§7Даёт +{n} к силе всем"),
        # код уже стоит сразу после — ставим только перед
        ("§7за каждые §b{n}§7§b Magic Find§7", "§7за каждые {n}§b Магического поиска§7",
         "§7за каждые §b{n}§b Магического поиска§7"),
        # число дырок разошлось — ничего
        ("§7максимум §a{n}§7 из {n}", "§7максимум {n}", "§7максимум {n}"),
    ]
    bad = 0
    for base, ru, want in cases:
        got, _ = fix_one(base, ru)
        if got != want:
            bad += 1
            print(f"СЛОМАНО:\n  base {base}\n  ru   {ru}\n  ждал {want}\n  дал  {got}")
    print(f"selftest: {len(cases) - bad} из {len(cases)} верно")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--show", type=int, default=12)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if selftest():
        print("selftest не прошёл — файл не трогаю")
        return 1

    data = json.loads(WORK.read_text(encoding="utf-8"))
    rows = data.get("rows", {})
    done_before = sum(1 for v in rows.values() if v.get("done"))
    changed: list[tuple[int, str, list[str]]] = []
    for key, row in rows.items():
        if not row.get("done"):
            continue
        fixed, notes = fix_one(row.get("base") or "", row.get("ru") or "")
        if notes:
            changed.append((int(row.get("live") or 0), key, notes))
            row["ru"] = fixed
    changed.sort(reverse=True)
    print(f"готовых записей: {done_before}; чисел без цвета возвращено в {len(changed)} абзацах")
    for live, key, notes in changed[: args.show]:
        print(f"   [{live}] {key[:70]}")
        print(f"        {' '.join(notes)}")

    if not args.write:
        print()
        print("СУХОЙ ПРОГОН. Записать: --write")
        return 0
    if not changed:
        print("править нечего")
        return 0
    stamp = time.strftime("%Y%m%d")
    backup = WORK.with_name(WORK.name + f".bak-{stamp}-holecolors")
    if not backup.exists():
        shutil.copy2(WORK, backup)
    WORK.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    done_after = sum(1 for v in json.loads(WORK.read_text(encoding="utf-8"))
                     .get("rows", {}).values() if v.get("done"))
    print(f"записано: {WORK.relative_to(ROOT)}; готовых было {done_before}, стало {done_after}; копия {backup.name}")
    if done_after != done_before:
        print("⚠️ число готовых записей изменилось — проверь копию")
        return 1
    print("дальше: python tools/gen_full_paragraphs.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
