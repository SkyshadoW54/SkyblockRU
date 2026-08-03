"""
Реестр ХАРАКТЕРИСТИК с вики: имя, значок, цвет и что она делает.

⚠️ Почему это лучше нашего списка. `terms.STAT_JARGON` собран из того, что мод
встретил на экране, — то есть заведомо неполон, как оказалось и с зачарованиями
(98 у нас против 131 на вики). Здесь список идёт из `Module:Statname/Data` —
это ТОТ ЖЕ источник, из которого вики рисует значки в своих таблицах, поэтому
он полный и содержит:

  * `name`      — как характеристика называется («Mining Fortune»);
  * `character` — значок Hypixel (☘, ❈, ⸕), тот самый, что виден в подсказке;
  * `color`     — каким цветом её красит игра.

Цвет особенно важен: правило справки требует красить заголовок так же, как
Hypixel красит термин в игре, иначе игрок читает пояснение как про другое слово.
Раньше цвет приходилось подсматривать в дампе вручную.

Описания («что делает») берутся со страницы `Stats` — там таблицы по разделам:
Combat, Mining, Farming, Foraging, Fishing, Hunting, Misc, Wisdom, Rift.

Запуск:
  python tools/fetch_stats_wiki.py           показать сводку
  python tools/fetch_stats_wiki.py --apply   записать data/work/stats_wiki_en.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_wiki import fetch  # noqa: E402
from fetch_enchant_wiki import unwrap  # noqa: E402

OUT = ROOT / "data" / "work" / "stats_wiki_en.json"

# ['mining fortune'] = { name = 'Mining Fortune', … shortcode = 'mnf', … }
BLOCK = re.compile(r"\['([^']+)'\]\s*=\s*\{(.*?)\n\t\}", re.S)


def field(body: str, key: str) -> str:
    match = re.search(key + r"\s*=\s*'([^']*)'", body)
    return match.group(1) if match else ""


def registry() -> dict[str, dict]:
    """Все характеристики: код -> имя, значок, цвет."""
    raw = fetch("Module:Statname/Data")
    found: dict[str, dict] = {}
    for key, body in BLOCK.findall(raw):
        name = field(body, "name")
        if not name:
            continue
        found[key.strip()] = {
            "name": name,
            "short": field(body, "shortcode"),
            "icon": field(body, "character"),
            "color": field(body, "color"),
        }
    return found


def effects(reg: dict[str, dict]) -> dict[str, dict]:
    """
    Что делает характеристика — из таблиц на странице «Stats».

    Строка таблицы: |{{Stat|hp}} \n |100 \n |{{bc}} \n |The Max Health…
    ⚠️ Ячейка предела бывает объединённой (rowspan) и в строке отсутствует,
    поэтому на неё не опираемся: берём ПЕРВУЮ ячейку как код, а ПОСЛЕДНЮЮ —
    как описание. Иначе половина строк разъезжается.
    """
    raw = fetch("Stats")
    section = ""
    out: dict[str, dict] = {}
    rows = raw.split("\n|-")
    for row in rows:
        head = re.search(r"^==+\s*(.+?)\s*==+$", row, re.M)
        if head:
            section = head.group(1)
        cells = [c.strip() for c in row.split("\n|") if c.strip()]
        if not cells:
            continue
        code = re.match(r"\{\{[Ss]tat\|([^|}]+)\}\}$", cells[0])
        if not code:
            continue
        key = code.group(1).strip().lower()
        desc = unwrap(cells[-1]) if len(cells) > 1 else ""
        if not desc or desc.startswith("{{"):
            continue
        out[key] = {"desc": desc, "section": section}
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Характеристики с вики")
    parser.add_argument("--apply", action="store_true", help="записать файл")
    args = parser.parse_args()

    reg = registry()
    print(f"характеристик в реестре вики: {len(reg)}")
    facts = effects(reg)
    print(f"из них с описанием на «Stats»: {len(facts)}")

    # Сводим: ключ реестра или shortcode -> запись
    by_code: dict[str, str] = {}
    for key, item in reg.items():
        by_code[key] = key
        if item["short"]:
            by_code[item["short"].lower()] = key
        by_code[item["name"].lower()] = key

    # ⚠️ Половина кодов на странице — АЛИАСЫ («td», «ms», «cold»), и в самом
    # реестре их нет: они лежат отдельным модулем. Без него не сходилось
    # 13 характеристик из 79, включая ходовые True Defense и Mining Speed.
    try:
        alias_raw = fetch("Module:Statname/Aliases")
        for short, full in re.findall(r"\['([^']+)'\]\s*=\s*'([^']+)'", alias_raw):
            if full in reg:
                by_code.setdefault(short.strip().lower(), full)
    except Exception as error:  # noqa: BLE001 — сеть
        print(f"  алиасы не пришли ({error}), часть кодов не сойдётся")

    merged: dict[str, dict] = {}
    for code, fact in facts.items():
        key = by_code.get(code)
        if not key:
            continue
        item = reg[key]
        merged[item["name"]] = {
            "icon": item["icon"],
            "color": item["color"],
            "desc": fact["desc"],
            "section": fact["section"],
        }
    print(f"сведено (имя + значок + цвет + описание): {len(merged)}")

    # Чего у нас нет
    try:
        import terms
        ours = set(terms.of("stat_jargon")) | set(terms.of("stat"))
    except Exception:  # noqa: BLE001
        ours = set()
    new = sorted(set(merged) - ours)
    print(f"нет в наших списках: {len(new)}")
    print()
    for name in list(merged)[:6]:
        item = merged[name]
        print(f"  {item['icon']} {name} ({item['color']}) — {item['desc'][:52]}")

    if not args.apply:
        print()
        print("это СУХОЙ прогон — чтобы записать, добавь --apply")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(f"записано: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
