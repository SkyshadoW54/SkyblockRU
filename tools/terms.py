"""
ГРУППЫ ТЕРМИНОВ проекта: кто есть кто и что с этим делать.

Зачем. Термины проекта лежали кучей и каждый потребитель собирал своё
подмножество: `protected.py` — имена, `gen_stat_forms.py` — характеристики,
`translate_ai.py` — глоссарий. За один вечер это трижды дало «правило есть,
но не во всех путях», а взять категорию ЦЕЛИКОМ было нельзя вовсе — приходилось
перечислять слова руками.

Здесь они собраны в один реестр с группой у каждого. Отсюда две вещи, ради
которых всё и затевалось:

  * взять группу и что-то с ней сделать — `of("npc")`;
  * запретить переводить группу одним словом — `forbidden(["enchant"])`,
    а не перечисляя 93 названия.

⚠️ Реестр НИЧЕГО не выдумывает: группа известна в момент сбора, и раньше
её просто выбрасывали. «[NPC] Ryan:» приносит источник chat, локацию —
боковая панель, зачарования помечены в заготовке. Мы лишь перестали
терять то, что и так знали.

⚠️ Группа «не переводим» и группа «переводим» тут ОБЕ: реестр отвечает
на вопрос «что это», а не «трогать ли». Иначе мобы и материалы, которые
мы переводим, в него бы не попали — и группами нельзя было бы пользоваться
для чего-то, кроме запрета.

Запуск:
  python tools/terms.py                    сводка по группам
  python tools/terms.py --group npc        список группы
  python tools/terms.py --find "Magic Find"   в какой группе слово
  python tools/terms.py --forbid enchant,stat  что попадёт под запрет
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import protected  # noqa: E402

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
ENCHANTS = ROOT / "data" / "work" / "enchants.json"

# ХАРАКТЕРИСТИКИ, которые остаются английскими (словарь sb_stats).
#
# ⚠️ Источник списка — САМ HYPIXEL, а не наш словарь. У предметов в
# api.hypixel.net/v2/resources/skyblock/items есть поле «stats», и его ключи
# (MINING_SPEED, SEA_CREATURE_CHANCE) — канонический перечень: 66 штук.
# Наш словарь для этого не годился, в нём вперемешку лежат подписи вроде
# «Стоимость» и «Дата», характеристиками не являющиеся.
# Пересобрать список: python tools/fetch_items.py, затем сверить.
#
# ⚠️ Имена записаны ТАК, КАК ИХ ПИШЕТ ПОДСКАЗКА, а не как зовётся ключ API:
# в API «CRITICAL_CHANCE», а на экране «Crit Chance», и ловить надо второе.
#
# ⚠️ Это НЕ «список того, что не переводим»: перевод для них есть и лежит
# в словаре sb_stats, просто выключенном по умолчанию. Игрок включает его
# командой /skyblockru pack sb_stats on.
STAT_JARGON = {
    # ⚠️ ГРАНИЦА ПРОХОДИТ ЗДЕСЬ: остаются английскими только те, чью суть
    # одним переводом не передать — механика SkyBlock, которой нужна справка.
    # «Mining Fortune» это не «удача шахтёра», а шанс добыть лишний ресурс;
    # «Magic Find», «Pristine», «Overbloom» по-русски не говорят ни о чём.
    # А «Damage», «Strength», «Defense» объясняются одним словом, и латиница
    # там ничего не даёт — только делает подсказку наполовину непереведённой.
    #
    # Удача и мудрость (Fortune, Wisdom) — все английские: перевод «удача»
    # и «мудрость» механику не объясняет, по ним читают гайды.
    "Mining Fortune", "Farming Fortune", "Foraging Fortune",
    "Gemstone Fortune", "Block Fortune", "Ore Fortune", "Dwarven Metal Fortune",
    "Wheat Fortune", "Carrot Fortune", "Potato Fortune", "Pumpkin Fortune",
    "Melon Fortune", "Mushroom Fortune", "Cactus Fortune", "Sugar Cane Fortune",
    "Cocoa Beans Fortune", "Nether Stalk Fortune", "Fig Fortune",
    "Mangrove Fortune",
    "Mining Wisdom", "Farming Wisdom", "Foraging Wisdom", "Fishing Wisdom",
    "Alchemy Wisdom", "Combat Wisdom",
    # ⚠️ «Hunter Fortune» в поле stats у предметов не приходит, поэтому список
    # API его не отдал — а на экране он есть, и без него выходил разнобой
    # в одной подсказке: метка «Удача охотника: +3» и рядом «Даёт +3 Hunter
    # Fortune». Все *Fortune английские, этот не исключение.
    # ⚠️ «HuntING Wisdom», а не «Hunt Wisdom»: в игре встречается именно первое
    # («Hunting Wisdom: +5» в дампе). Под неверным именем термин не защищался,
    # а статья справки не находилась бы НИ РАЗУ — ключ ищется вхождением
    # в текст подсказки.
    "Hunter Fortune", "Hunting Wisdom", "Runecrafting Wisdom",
    # Остальные виды мудрости — по тому же правилу «все Wisdom английские».
    # Их не было в списке просто потому, что мод их ещё не встречал.
    "Carpentry Wisdom", "Taming Wisdom", "Social Wisdom", "Enchanting Wisdom",
    # кастомные механики: без пояснения не понять
    "Magic Find", "Pet Luck", "Pristine", "Overbloom", "Ferocity",
    # ⚠️ «Vitality» переводилась как «Живучесть» — решение игрока отменено
    # 31.07. Слово знакомое, но механику НЕ передаёт: это не запас прочности,
    # а МНОЖИТЕЛЬ входящего лечения (полученное лечение × Vitality/100,
    # база 100). «Живучесть» обещает совсем другое, поэтому термин остаётся
    # английским, а смысл объясняет справка по Shift.
    "Vitality",
    "Mining Speed", "Mining Spread", "Gemstone Spread", "Heat",
    # ⚠️ «Breaking Power» переводился как «Сила разрушения» — решение игрока
    # отменено 28.07. Слово вроде бы понятное, но механику НЕ передаёт: это
    # не «сила», а порог, ниже которого блок вообще не ломается, и он ещё
    # и не работает на части островов. Такому нужна справка, а не перевод, —
    # ровно как «Mining Speed», оставленному английским по той же причине.
    "Sea Creature Chance", "Trophy Fish Chance", "Bonus Pest Chance",
    # ⚠️ «Trophy Chance» добавлен 01.08 по решению игрока — по скриншоту, где
    # «Даёт +0❦ к шансу трофея» соседствовало с «к Fishing Speed». Рядом
    # с ним «Trophy Fish Chance» уже стоял английским, и разнобой был виден
    # в одной подсказке. Слово переводится легко, а механику не передаёт:
    # это шанс поймать ТРОФЕЙНУЮ РЫБУ, а не трофей вообще.
    "Trophy Chance",
    # ⚠️ «Swing Range» отсюда УБРАН 28.07 по решению игрока: переводим как
    # «Дальность удара». В жаргон он попал не решением, а самотёком — из
    # реестра характеристик Hypixel, куда генератор берёт всё подряд.
    # По правилу границы он на русской стороне: перевод слова и ЕСТЬ
    # объяснение механики (сравните с «удачей шахтёра», которая механику
    # не передаёт). Справка при этом заведена — она уточняет то, чего
    # из названия не видно: значение равно расстоянию в блоках.
    "Sweep", "Pull", "Tracking", "Respiration", "Fear",
    "Rift Time", "Rift Damage", "Rift Health", "Rift Intelligence",
    "Rift Mana Regen", "Rift Walk Speed", "Breaking Power",
}

# ⚠️ ПЕРЕВОДИМ, хотя это тоже характеристики: их суть передаётся одним словом.
# Держим списком, чтобы решение было видно, а не выводилось из умолчания.
#
#   Health, Defense, True Defense, Strength, Damage, Intelligence, Speed,
#   Mana, Crit Chance, Crit Damage, Attack Speed, Health Regen, Vitality,
#   Breaking Power, Fishing Speed, Mending, Ability Damage,
#   Heat/Cold/Pressure Resistance
#
# ⚠️ «Heat» (жар у дрелей) — В ЖАРГОНЕ, а «Heat Resistance» (сопротивление
# жаре) — переводим. Это разные вещи, и короткое имя нельзя выводить
# из длинного.
# ⚠️ «Mining Speed» оставлен английским НАРОЧНО, хотя «скорость добычи»
# понятна: у него есть справка про острова, где он не действует, а справка
# ищет термин по английскому написанию.

# ⚠️ «Mana» СЮДА НЕ ВХОДИТ, и это решение игрока, а не недосмотр.
# Я добавил её, увидев на полосе над хотбаром «83❈ Defense 105/105✎ Мана»
# и приняв разнобой за ошибку. Оказалось наоборот: над хотбаром мана должна
# оставаться русской. Слово это обиходное, гайды по нему не ищут, и в отличие
# от Mining Fortune никакой пользы от латиницы тут нет.
# ⚠️ Вместе с ней НЕЛЬЗЯ уносить «Mana Cost», «Mana Regen», «Mana Steal»:
# фильтр по вхождению слова захватывает и их, а это обычные подписи.

# Что мы про группу решили. «toggle» — решает игрок переключателем словаря.
#
# ⚠️ Это ПОЛИТИКА, а не свойство слова: «Magic Find» останется характеристикой,
# как бы мы ни решили его переводить. Поэтому лежит отдельной таблицей.
POLICY = {
    "npc":       ("не переводим", "имена персонажей: Ryan, Captain Baha"),
    "location":  ("не переводим", "места: Birch Park, The Catacombs"),
    "currency":  ("не переводим", "валюты Gems и Bits"),
    "brand":     ("не переводим", "сам сервер и его сервисы"),
    "item":      ("не переводим", "названия предметов — по ним ищут на аукционе"),
    "highlight": ("не переводим", "Hypixel подсветил как имя, но род неизвестен"),
    "enchant":     ("переключатель", "зачарования SkyBlock — словарь sb_enchants"),
    "stat_jargon": ("переключатель", "характеристики-жаргон — словарь sb_stats"),
    "stat":        ("переводим", "характеристики: Health, Defense, Attack Speed"),
    "mob":       ("переводим", "названия мобов в винительном падеже"),
    "material":  ("переводим", "материалы со строчной буквы"),
}


def _enchants_and_stats() -> tuple[set[str], set[str]]:
    """
    Зачарования и подписи характеристик из заготовки.

    ⚠️ Делит их ПОМЕТКА в заготовке, а не форма строки: «Growth V» и
    «Mending V» выглядят одинаково, и по одному виду зачарование от подписи
    характеристики не отличить. Этот же признак использует gen_enchants.py.
    """
    enchants: set[str] = set()
    stats: set[str] = set()
    if not ENCHANTS.exists():
        return enchants, stats
    try:
        data = json.loads(ENCHANTS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return enchants, stats
    contexts = data.get("_contexts") or {}
    for name, hint in contexts.items():
        if "зачарование" in hint:
            enchants.add(name)
        else:
            stats.add(name)
    return enchants, stats


def _stats_from_dictionary() -> set[str]:
    """Названия характеристик — из словаря, где они лежат парами «Имя: значение»."""
    names: set[str] = set()
    path = PACKS / "ru_ru" / "10-stats.json"
    if not path.exists():
        return names
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return names
    for key in (data.get("exact") or {}):
        head = key.split(":")[0].strip()
        if head and re.fullmatch(r"[A-Za-z][A-Za-z' -]{2,30}", head):
            names.add(head)
    return names


def _from_generator(attribute: str) -> set[str]:
    """Английские ключи из генератора словаря материалов (мобы, материалы)."""
    try:
        import gen_materials
    except ImportError:
        return set()
    table = getattr(gen_materials, attribute, None)
    return set(table) if isinstance(table, dict) else set()


_CACHE: dict[str, set[str]] | None = None


def all_groups() -> dict[str, set[str]]:
    """Весь реестр: группа -> слова."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    groups: dict[str, set[str]] = {k: set(v) for k, v in protected.collect_groups().items()}
    enchants, stat_labels = _enchants_and_stats()
    groups["enchant"] = enchants
    # Жаргон вынут из «stat» отдельной группой: запрет на характеристики целиком
    # накрыл бы и «Health», а нужны только эти семь.
    groups["stat_jargon"] = set(STAT_JARGON)
    groups["stat"] = (stat_labels | _stats_from_dictionary()) - STAT_JARGON
    groups["mob"] = _from_generator("MOBS")
    groups["material"] = _from_generator("MATERIALS")
    _CACHE = {name: words for name, words in groups.items() if words}
    return _CACHE


def of(group: str) -> set[str]:
    """Слова одной группы."""
    return set(all_groups().get(group, set()))


def group_of(term: str) -> list[str]:
    """
    В каких группах числится слово.

    Список, а не одна группа: «Auction House» — и место, и сервис сервера,
    и это правда. Придумывать единственный ответ значило бы врать.
    """
    return sorted(name for name, words in all_groups().items() if term in words)


def forbidden(extra: list[str] | tuple[str, ...] = ()) -> set[str]:
    """
    Что нельзя отдавать на перевод: группы «не переводим» плюс названные.

    Это и есть фильтр, ради которого затевался реестр: `forbidden(["enchant"])`
    вместо перечисления 93 названий, которые вдобавок разъедутся со словарём
    при первом же пополнении.
    """
    groups = all_groups()
    words: set[str] = set()
    for name, words_of_group in groups.items():
        if POLICY.get(name, ("", ""))[0] == "не переводим":
            words |= words_of_group
    for name in extra:
        words |= groups.get(name.strip(), set())
    return words


def main() -> int:
    parser = argparse.ArgumentParser(description="группы терминов проекта")
    parser.add_argument("--group", help="показать слова одной группы")
    parser.add_argument("--find", help="в какой группе это слово")
    parser.add_argument("--forbid", help="группы через запятую: что попадёт под запрет")
    args = parser.parse_args()

    groups = all_groups()

    if args.find:
        found = group_of(args.find)
        if found:
            for name in found:
                policy, about = POLICY.get(name, ("?", ""))
                print(f"  {args.find}  ->  {name}  [{policy}]  {about}")
        else:
            print(f"  {args.find} — ни в одной группе не числится")
        return 0

    if args.group:
        words = groups.get(args.group)
        if not words:
            print(f"группы «{args.group}» нет. Есть: {', '.join(sorted(groups))}")
            return 1
        policy, about = POLICY.get(args.group, ("?", ""))
        print(f"=== {args.group}: {len(words)} — {policy} ({about}) ===")
        for word in sorted(words):
            print(f"  {word}")
        return 0

    if args.forbid:
        names = [n for n in args.forbid.split(",") if n.strip()]
        base = forbidden()
        whole = forbidden(names)
        print(f"под запретом сейчас: {len(base)}")
        print(f"с группами {', '.join(names)}: {len(whole)}  (+{len(whole) - len(base)})")
        return 0

    total = sum(len(words) for words in groups.values())
    print(f"групп: {len(groups)}, слов: {total}")
    print()
    print("  группа      слов  что делаем      примеры")
    print("  " + "-" * 74)
    for name in sorted(groups, key=lambda key: -len(groups[key])):
        policy, _ = POLICY.get(name, ("?", ""))
        sample = ", ".join(sorted(groups[name])[:3])
        print(f"  {name:<11} {len(groups[name]):>5}  {policy:<15} {sample[:38]}")
    print()
    print(f"  запрещено к переводу: {len(forbidden())} слов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
