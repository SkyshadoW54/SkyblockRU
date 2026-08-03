"""
Описания ВСЕХ зачарований с вики — фактами, а не по памяти.

⚠️ Почему это оказалось возможно. Считалось, что до fandom не достучаться:
`WebFetch` отдаёт 402. Но обычный запрос с User-Agent проходит, и в проекте
уже есть `fetch_wiki.py`, который ходит в MediaWiki API напрямую. Описания
зачарований лежат структурировано, шаблоном `EnchantmentPageRow`:

    {{EnchantmentPageRow|Angler
    |desc=Grants {{Statname|scc|+1}} per level.
    |source=
    *1span5~[[Enchantment Table]]
    *6~{{MobSprite|Deep Sea Protector}}
    }}

То есть имя, описание и источник берутся как есть — сочинять нечего.

⚠️ Страница «Enchantments» сама описаний не содержит: она собирает шесть
подстраниц через Transclude. Их и качаем.

Запуск:
  python tools/fetch_enchant_wiki.py           показать, что нашлось
  python tools/fetch_enchant_wiki.py --apply   записать в заготовку
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

OUT = ROOT / "data" / "work" / "enchant_wiki_en.json"

PAGES = [
    "Enchantments/Sword",
    "Enchantments/Bow",
    "Enchantments/Armor",
    "Enchantments/Equipment",
    "Enchantments/Tool",
    "Enchantments/Fishing Rod",
    # ⚠️ УЛЬТИМАТИВНЫЕ живут отдельной страницей, и без неё не хватало 30 штук
    # из 98: Chimera, Legion, Soul Eater, Last Stand, Flash, Fatal Tempo…
    # На «Enchantments» они упомянуты только ссылкой {{For|…}}, описаний там нет.
    "Ultimate Enchantments",
]

# Сокращения характеристик из {{Statname|scc|+1}} — их вики пишет кодом.
# Разворачиваем в те же имена, какими характеристики зовёт сама игра.
STATS = {
    "scc": "Sea Creature Chance", "ff": "Farming Fortune", "mf": "Magic Find",
    "mfo": "Mining Fortune", "fo": "Foraging Fortune", "hf": "Hunter Fortune",
    "str": "Strength", "def": "Defense", "hp": "Health", "int": "Intelligence",
    "cc": "Crit Chance", "cd": "Crit Damage", "as": "Attack Speed",
    "spd": "Speed", "fer": "Ferocity", "ms": "Mining Speed", "ps": "Pristine",
    "td": "True Defense", "hr": "Health Regen", "vit": "Vitality",
    "mp": "Mana Pool", "mr": "Mana Regen", "sr": "Swing Range",
    "cr": "Cold Resistance", "hres": "Heat Resistance", "pr": "Pressure Resistance",
    "resp": "Respiration", "ww": "Wisdom", "ad": "Ability Damage",
    # те же характеристики полными словами — вики пишет и так
    "speed": "Speed", "strength": "Strength", "defense": "Defense",
    "health": "Health", "intelligence": "Intelligence", "ferocity": "Ferocity",
    "damage": "Damage", "sea creature chance": "Sea Creature Chance",
    "fishing speed": "Fishing Speed", "magic find": "Magic Find",
    "pet luck": "Pet Luck", "true defense": "True Defense",
    "fs": "Fishing Speed", "sf": "Sea Creature Chance", "ah": "Ability Damage",
    "mana": "Intelligence", "cdmg": "Crit Damage", "cchance": "Crit Chance",
}

ROW = re.compile(r"\{\{EnchantmentPageRow\|([^\n|}]+)(.*?)\n\}\}", re.S)


def unwrap(text: str) -> str:
    """
    Разворачивает шаблоны вики в обычный текст.

    ⚠️ Порядок важен: сперва шаблоны со ЗНАЧЕНИЕМ ({{Statname}}, {{ID}}),
    потом цветовые обёртки ({{g|2%}} — это просто «2%», зелёный цвет нам
    не нужен, свою разметку мы ставим сами).
    """
    out = text
    # {{Statname|scc|+1}} -> «+1 Sea Creature Chance»
    def stat(match: re.Match) -> str:
        code = match.group(1).strip().lower()
        value = (match.group(2) or "").strip()
        name = STATS.get(code, code.upper())
        return f"{value} {name}".strip()

    # ⚠️ Вики пишет характеристику ДВУМЯ шаблонами: {{Statname|scc|+1}}
    # и {{Stat|cd}} / {{stat|def}}. Первая версия знала только Statname,
    # и «Increases {{Stat|cd}} by X%» превращалось в «Increases cd by X%» —
    # сокращение, которое игрок нигде не видел.
    out = re.sub(r"\{\{[Ss]tat(?:name)?\|([^|}]+)\|([^}]*)\}\}", stat, out)
    out = re.sub(r"\{\{[Ss]tat(?:name)?\|([^}]+)\}\}",
                 lambda m: STATS.get(m.group(1).strip().lower(), m.group(1)), out)
    # {{ID|Chain of the End Times}}, {{MobSprite|X}}, {{Skill|X}}, {{ench|X}}
    out = re.sub(r"\{\{(?:ID|MobSprite|Skill|ench|item)\|([^|}]+)(?:\|[^}]*)?\}\}",
                 r"\1", out, flags=re.I)
    # {{Text anchor|Refrigerate|Refrigerate}} -> второй параметр (видимый текст)
    out = re.sub(r"\{\{Text anchor\|[^|}]*\|([^}]*)\}\}", r"\1", out, flags=re.I)
    # {{Roman numeral|4}} -> IV: игрок видит на предмете римские
    roman = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V",
             "6": "VI", "7": "VII", "8": "VIII", "9": "IX", "10": "X"}
    out = re.sub(r"\{\{Roman numeral\|(\d+)\}\}",
                 lambda m: roman.get(m.group(1), m.group(1)), out, flags=re.I)
    # {{c}} — монеты без числа; {{c|+0.5}} уже развернётся ниже
    out = re.sub(r"\{\{c\}\}", "coins", out, flags=re.I)
    # Цветовые обёртки: {{g|2%}}, {{gold|Treasure}}, {{b|GREAT}}, {{Dark_Aqua|X}}
    for _ in range(3):
        out = re.sub(r"\{\{[a-z_]+\|([^{}]*)\}\}", r"\1", out, flags=re.I)
    # [[Fishing Bait|bait]] -> bait, [[Enchantment Table]] -> Enchantment Table
    out = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", out)
    out = re.sub(r"'''([^']+)'''", r"\1", out)
    out = re.sub(r"''([^']+)''", r"\1", out)
    out = re.sub(r"<[^>]+>", "", out)
    return re.sub(r"\s+", " ", out).strip()


# ⚠️ Ультимативные оформлены НЕ шаблоном, а обычной wikitable: имя лежит
# в {{Text anchor|Bank|…}}, описание — следующей ячейкой с тем же rowspan.
# Без отдельного разбора их не хватало ровно 30 из 98.
ULTIMATE = re.compile(
    r"\{\{Text anchor\|([^|}]+)\|.*?\n\|\s*rowspan=\"\d+\"\s*\|(.*?)(?=\n\|)", re.S)


def parse_ultimate(raw: str) -> dict[str, dict]:
    """Ультимативные зачарования из таблицы на своей странице."""
    found: dict[str, dict] = {}
    for name, desc in ULTIMATE.findall(raw):
        name = name.strip()
        text = unwrap(desc)
        if name and text and name not in found:
            found[name] = {"desc": text, "source": [], "page": "Ultimate"}
    return found


# «'''Paleontologist''' is an Enchantment for Pickaxes … that grants …»
INTRO = re.compile(r"'''(?:.+?)'''\s+(is|are)\s+(.{20,400}?)(?:\.\s|\n\n|$)", re.S)
REDIRECT = re.compile(r"#REDIRECT\s*\[?\[?([^\]\n#]+)", re.I)


def from_own_page(name: str) -> dict | None:
    """
    Описание с ОТДЕЛЬНОЙ страницы зачарования.

    ⚠️ Нужно потому, что списочные страницы знают не всё: 20 зачарований
    из наших 98 там просто нет. У части есть своя страница, у части —
    редирект на раздел, а иные не заведены вовсе — тогда честно возвращаем
    ничего, а не придумываем.
    """
    try:
        raw = fetch(name)
    except Exception:  # noqa: BLE001 — нет страницы, бывает
        return None
    jump = REDIRECT.match(raw.strip())
    if jump:
        target = jump.group(1).strip()
        if target.lower() != name.lower():
            try:
                raw = fetch(target)
            except Exception:  # noqa: BLE001
                return None
    hit = INTRO.search(raw)
    if not hit:
        return None
    text = unwrap(hit.group(2))
    # Отбрасываем служебные хвосты вроде «for Pickaxes, Drills or …»
    if len(text) < 15:
        return None
    return {"desc": text, "source": [], "page": "own"}


def field(body: str, name: str) -> str:
    """Значение поля |desc= или |source= до следующего поля."""
    match = re.search(r"\|" + name + r"=(.*?)(?=\n\||\Z)", body, re.S)
    return match.group(1).strip() if match else ""


def sources(text: str) -> list[str]:
    """
    Откуда берётся: «*1span5~[[Enchantment Table]]» -> «I–V: Enchantment Table».

    Уровни вики пишет арабскими, а игрок видит римские — переводим, иначе
    справка разойдётся с тем, что написано на предмете.
    """
    roman = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII",
             8: "VIII", 9: "IX", 10: "X"}
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("*"):
            continue
        head, _, tail = line[1:].partition("~")
        where = unwrap(tail)
        span = re.match(r"(\d+)span(\d+)", head.strip())
        if span:
            low, count = int(span.group(1)), int(span.group(2))
            label = f"{roman.get(low, low)}–{roman.get(low + count - 1, low + count - 1)}"
        elif head.strip().isdigit():
            label = roman.get(int(head.strip()), head.strip())
        else:
            label = unwrap(head)
        if where:
            out.append(f"{label}: {where}" if label else where)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Описания зачарований с вики")
    parser.add_argument("--apply", action="store_true", help="записать файл")
    args = parser.parse_args()

    found: dict[str, dict] = {}
    for page in PAGES:
        try:
            raw = fetch(page)
        except Exception as error:  # noqa: BLE001 — сеть, причин много
            print(f"  {page}: не пришло ({error})")
            continue
        if page == "Ultimate Enchantments":
            extra = parse_ultimate(raw)
            print(f"  {page}: {len(extra)}")
            for name, item in extra.items():
                found.setdefault(name, item)
            continue
        rows = ROW.findall(raw)
        print(f"  {page}: {len(rows)}")
        for name, body in rows:
            name = name.strip()
            if not name or name in found:
                continue
            found[name] = {
                "desc": unwrap(field(body, "desc")),
                "source": sources(field(body, "source")),
                "page": page.split("/")[-1],
            }

    # ⚠️ Добираем тех, кого нет в списках: у них своя страница либо редирект.
    try:
        import terms
        wanted = set(terms.of("enchant"))
    except Exception:  # noqa: BLE001
        wanted = set()
    missing = sorted(wanted - set(found))
    if missing:
        print()
        print(f"нет в списках, иду по отдельным страницам: {len(missing)}")
        for name in missing:
            item = from_own_page(name)
            if item:
                found[name] = item
                print(f"  + {name}: {item['desc'][:58]}")

    print()
    print(f"зачарований с описанием: {len(found)}")
    for name in list(found)[:5]:
        item = found[name]
        print(f"  {name}: {item['desc'][:70]}")
        if item["source"]:
            print(f"      откуда: {'; '.join(item['source'])[:66]}")

    if not args.apply:
        print()
        print("это СУХОЙ прогон — чтобы записать, добавь --apply")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(f"записано: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
