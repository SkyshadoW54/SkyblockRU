"""Заголовки абзацев для ПОЛНОГО режима — вырезаем из режимных переводов.

⚠️⚠️ БЕЗ ЭТОГО ЗАГОЛОВОК СЛИПАЕТСЯ С ОПИСАНИЕМ. `Paragraphs.header` режет
абзац, только если вырезанный заголовок СОВПАДАЕТ с построчным переводом
первой строки. В режиме абзац даёт русский заголовок («Эффективность
ствола»), а построчный словарь — английский («Trunk Efficiency»), потому
что имена способностей в обычном режиме английские по решению проекта.
Совпадения нет, резка отменяется, и на экране выходит

    Эффективность ствола Даёт +150⛏ Удачи фермера, что повышает…

вместо двух строк. Жалоба игрока 05.09 со скриншотом слона.

⚠️ ПЛАТИТЬ НЕ НАДО: перевод заголовка уже лежит В НАЧАЛЕ режимного абзаца
и помечен своим цветом — его и вырезаем. Тот же приём, каким `gen_headers`
собирает обычные заголовки из корпуса.

⚠️ ЗАЩИТЫ — те же, что у `gen_headers`, и каждая от живой беды:
  * число дырок `{n}`/`{s}` обязано совпасть с английским заголовком;
  * горячая клавиша («SNEAK», «RIGHT CLICK») обязана уцелеть — иначе
    «Ability: Homing Missiles SNEAK» превращается в заголовок без клавиши,
    а её показывают ровно в этой строке;
  * заголовок не может кончаться двоеточием: это обрезок двухцветного
    («Held Item: Foraging Exp Boost» -> «Предмет в руке:»);
  * совпал с обычным — запись лишняя, копить мусор незачем.

    python tools/gen_full_headings.py           покажет
    python tools/gen_full_headings.py --write   впишет в заготовку режима
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

PACKS = ROOT / "src/main/resources/assets/skyblockru/packs/ru_ru"
HEADS = PACKS / "41-headers.json"
MODE = ROOT / "data" / "work" / "full_paragraphs_ru.json"
OUT = ROOT / "data" / "work" / "full_strings.json"

CODES = re.compile("§.")
HOLE = re.compile(r"\{[ns]\}")
# «§7§6Заголовок§7 тело» — цветной кусок в начале и возврат к телу
HEAD = re.compile(r"^(?:§.)*?§([0-9a-fl-o])([^§]+)§7")
KEY_HINT = re.compile(r"\b(?:SNEAK|RIGHT CLICK|LEFT CLICK|ON SHOOT|CLICK|DIG)\b")
KEY_RU = re.compile(r"Shift|ПКМ|ЛКМ|ВЫСТРЕЛ|КОПАЙ|НАЖМИ", re.IGNORECASE)
CYR = re.compile("[а-яА-ЯёЁ]")
MAX_WORDS = 6  # заголовок длиннее — это уже проза


def collect() -> tuple[dict[str, str], dict[str, int]]:
    heads = json.loads(HEADS.read_text(encoding="utf-8"))["exact"]
    rows = json.loads(MODE.read_text(encoding="utf-8"))["rows"]
    # индекс по первому слову: заголовков тысяча, абзацев тысячи
    by_first: dict[str, list[str]] = {}
    for head in heads:
        by_first.setdefault(head.split(" ")[0], []).append(head)
    for key in by_first:
        by_first[key].sort(key=len, reverse=True)

    out: dict[str, str] = {}
    why = {"нет разметки": 0, "нет заголовка в 41-headers": 0,
           "совпал с обычным": 0, "дырки разошлись": 0,
           "потеряна клавиша": 0, "обрезок": 0, "нет кириллицы": 0}
    for key, row in rows.items():
        russian_all = row.get("ru") or ""
        if not russian_all:
            continue
        plain_key = CODES.sub("", key)
        found = HEAD.match(russian_all)
        if not found:
            why["нет разметки"] += 1
            continue
        russian = found.group(2).strip()
        english = next((h for h in by_first.get(plain_key.split(" ")[0], ())
                        if plain_key.startswith(h + " ")
                        and len(h.split()) <= MAX_WORDS), None)
        if not english:
            why["нет заголовка в 41-headers"] += 1
            continue
        if russian in (english, heads[english]):
            why["совпал с обычным"] += 1
            continue
        if HOLE.findall(russian) != HOLE.findall(english):
            why["дырки разошлись"] += 1
            continue
        if KEY_HINT.search(english) and not KEY_RU.search(russian):
            why["потеряна клавиша"] += 1
            continue
        if russian.endswith((":", "—", "-")):
            why["обрезок"] += 1
            continue
        if not CYR.search(russian):
            why["нет кириллицы"] += 1
            continue
        out[english] = russian
    return out, why


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--show", type=int, default=12)
    args = ap.parse_args()

    if not HEADS.exists() or not MODE.exists():
        print("нет исходников:", HEADS, MODE)
        return 1
    found, why = collect()
    print(f"режимных заголовков: {len(found)}")
    for reason, count in sorted(why.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"   пропущено — {reason}: {count}")
    for english, russian in list(found.items())[: args.show]:
        print(f"   {english[:44]:46} -> {russian}")

    if not args.write:
        print("\nСУХОЙ ПРОГОН. Записать: --write")
        return 0

    data = json.loads(OUT.read_text(encoding="utf-8"))
    strings = data["strings"]
    new = 0
    for english, russian in found.items():
        if strings.get(english):
            continue
        strings[english] = russian
        new += 1
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nвписано в заготовку режима: {new} (всего строк {len(strings)})")
    print("дальше: python tools/gen_full_strings.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
