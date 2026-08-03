"""
Формы жаргонных характеристик — В САМ выключенный словарь sb_stats.

Зачем. Жаргон (`*Fortune`, `*Wisdom`, `Magic Find`, `Pristine`…) остаётся
на экране английским по решению игрока, а перевод для него лежит в словаре
`78-sb-stats.json` с `default: false` — включается `/skyblockru pack sb_stats on`.

Беда была в том, что переключатель работал НАПОЛОВИНУ. Замер по живому лору
аукциона: жаргонных подписей на экране 1257 разных форм, из них словарь
не закрывал 456, а 26 терминам не хватало форм вовсе — «Farming Fortune: +{n}»
в словаре есть, а «Farming Fortune: +24 (+12)» со скобками ковки нет.

⚠️ Причина не в лени, а в защите, работавшей против нас: `gen_stat_forms`
ПРОПУСКАЕТ пакеты с `default: false`. Правило заводили, чтобы выключенный
словарь не протекал в общий (история с валютой Bits и с «Огранкой V»), —
и оно верное. Но побочно оно оставило сам выключенный словарь неполным:
формы для жаргона не строил никто.

Поэтому формы для жаргона строит ОТДЕЛЬНЫЙ инструмент и кладёт их прямо
в sb_stats. Утечки нет по построению: файл выключен, и пока игрок его
не включит, ни одно из этих правил не применяется.

⚠️ Переводы берём из УЖЕ СУЩЕСТВУЮЩИХ, а не выдумываем: в проекте записан
разнобой («Удача на морковь» / «Удача моркови» / «Удача с морковью»), и третий
вариант тут ни к чему. Схема видна из собранного: `*Wisdom` — «Мудрость
<профессии>», `*Fortune` — «Удача <кого/чего>».

Запуск:  python tools/gen_jargon_forms.py
         python tools/gen_jargon_forms.py --dry
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import terms  # noqa: E402
from gen_stat_forms import ICON, NUMBER, VALUE  # noqa: E402

PACK = (ROOT / "src" / "main" / "resources" / "assets" / "skyblockru"
        / "packs" / "ru_ru" / "78-sb-stats.json")

# ⚠️ Переводы, которых в словарях ещё нет. Схема — как у уже собранных:
# «Мудрость <профессии>» и «Удача <кого/чего>». Урожайные виды удачи названы
# по КУЛЬТУРЕ, а не по профессии: «Удача моркови», не «Удача огородника», —
# иначе двенадцать видов стали бы неразличимы.
#
# ⚠️ «Melon» в Minecraft — АРБУЗ, а не дыня (так он назван в русской
# локализации игры), «Nether Stalk» — адский нарост. Ванильные названия берём
# из игры, а не переводим на слух.
EXTRA = {
    # удача по культурам и материалам
    "Wheat Fortune": "Удача пшеницы",
    "Carrot Fortune": "Удача моркови",
    "Potato Fortune": "Удача картофеля",
    "Pumpkin Fortune": "Удача тыквы",
    "Melon Fortune": "Удача арбузов",
    "Mushroom Fortune": "Удача грибов",
    "Cactus Fortune": "Удача кактусов",
    "Sugar Cane Fortune": "Удача тростника",
    "Cocoa Beans Fortune": "Удача какао",
    "Nether Stalk Fortune": "Удача адского нароста",
    "Fig Fortune": "Удача инжира",
    "Mangrove Fortune": "Удача мангров",
    "Block Fortune": "Удача блоков",
    "Ore Fortune": "Удача руды",
    "Gemstone Fortune": "Удача самоцветов",
    "Dwarven Metal Fortune": "Удача гномьего металла",
    "Hunter Fortune": "Удача охотника",
    # мудрость по профессиям — как у уже собранных шести
    "Carpentry Wisdom": "Мудрость столяра",
    "Enchanting Wisdom": "Мудрость зачарователя",
    "Hunting Wisdom": "Мудрость охотника",
    "Runecrafting Wisdom": "Мудрость рунщика",
    "Social Wisdom": "Мудрость общения",
    "Taming Wisdom": "Мудрость укротителя",
    # прочие механики
    "Bonus Pest Chance": "Доп. шанс Pests",
    "Breaking Power": "Сила разрушения",
    "Gemstone Spread": "Разброс самоцветов",
    "Mining Spread": "Разброс добычи",
    "Heat": "Жар",
    "Trophy Fish Chance": "Шанс трофейной рыбы",
    "Rift Damage": "Урон Разлома",
    "Rift Health": "Здоровье Разлома",
    "Rift Intelligence": "Интеллект Разлома",
    "Rift Mana Regen": "Восстановление маны Разлома",
    "Rift Walk Speed": "Скорость ходьбы Разлома",
}

LABEL = re.compile(r"^([A-Z][A-Za-z' ]{2,30}): ")


def known() -> dict[str, str]:
    """
    Русские варианты жаргона, УЖЕ лежащие в словарях.

    Берём их первыми: разнобой в терминах этот проект уже проходил, и лишний
    синоним стоит дороже, чем кажется — на экране рядом окажутся «Удача
    фермера» и «Удача фермерства».
    """
    packs = PACK.parent.parent
    out: dict[str, str] = {}
    for path in sorted(packs.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key, value in (pack.get("exact") or {}).items():
            match = LABEL.match(key)
            if not match or not isinstance(value, str):
                continue
            name = match.group(1)
            if name not in terms.STAT_JARGON:
                continue
            head = value.split(":")[0].strip()
            # «§7Wheat Fortune» — это не перевод, а осколок разметки
            if head and head != name and "§" not in head and not head.isascii():
                out.setdefault(name, head)
        for rule in (pack.get("regex") or []):
            match = re.match(r"\^([A-Za-z\\' ]{3,32}):", rule.get("p", ""))
            if not match or not rule.get("r"):
                continue
            name = match.group(1).replace("\\", "")
            if name not in terms.STAT_JARGON:
                continue
            head = rule["r"].split(":")[0].strip()
            if head and head != name and "§" not in head and not head.isascii():
                out.setdefault(name, head)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Формы жаргона в выключенный sb_stats")
    parser.add_argument("--dry", action="store_true", help="не записывать файл")
    args = parser.parse_args()

    have = known()
    names = dict(have)
    for name, translation in EXTRA.items():
        names.setdefault(name, translation)
    missing = sorted(t for t in terms.STAT_JARGON if t not in names)

    print(f"жаргонных терминов: {len(terms.STAT_JARGON)}")
    print(f"  перевод уже был в словарях: {len(have)}")
    print(f"  добавлено этим списком:     {len(names) - len(have)}")
    if missing:
        print(f"  БЕЗ ПЕРЕВОДА (форм не будет): {len(missing)}")
        print("    " + ", ".join(missing))

    # Те же четыре формы, что у обычных характеристик: с двоеточием, со значком
    # спереди, со значком после числа и с иконкой в значении. Длинные названия
    # вперёд — иначе «Block Fortune» откусит хвост у «Dwarven Metal Fortune».
    rules = []
    for name in sorted(names, key=len, reverse=True):
        source = re.escape(name)
        target = names[name]
        rules.append({"p": f"^{source}: {VALUE}$", "r": f"{target}: $1"})
        rules.append({"p": f"^({ICON} ?){source} ({NUMBER})$", "r": f"$1{target} $2"})
        rules.append({"p": f"^({NUMBER} ?{ICON} ?){source}$", "r": f"$1{target}"})
        rules.append({"p": f"^{source}: ({ICON}{NUMBER})$", "r": f"{target}: $1"})

    pack = json.loads(PACK.read_text(encoding="utf-8"))
    # ⚠️ ДОПОЛНЯЕМ, а не переписываем. split_sb_stats однажды обнулил этот
    # словарь на втором запуске (242 записи исчезли молча), и грабля записана.
    old = pack.get("regex") or []
    fresh = {rule["p"] for rule in rules}
    kept = [rule for rule in old if rule.get("p") and rule["p"] not in fresh]
    pack["regex"] = rules + kept
    print()
    print(f"правил: было {len(old)}, стало {len(pack['regex'])} "
          f"(новых {len(rules)}, сохранено прежних {len(kept)})")

    if args.dry:
        print("сухой прогон: файл не записан")
        return 0
    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"записано: {PACK.relative_to(ROOT)}")
    print("⚠️ словарь ВЫКЛЮЧЕН по умолчанию — на экране ничего не изменится,")
    print("   пока игрок не наберёт /skyblockru pack sb_stats on")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
