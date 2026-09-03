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
from gen_stat_forms import ICON, NUMBER, VALUE, without_icons  # noqa: E402

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
    "Melon Slice Fortune": "Удача ломтиков арбуза",
    "Mushroom Fortune": "Удача грибов",
    "Cactus Fortune": "Удача кактусов",
    "Sugar Cane Fortune": "Удача тростника",
    "Cocoa Beans Fortune": "Удача какао",
    "Nether Stalk Fortune": "Удача адского нароста",
    "Fig Fortune": "Удача инжира",
    "Mangrove Fortune": "Удача мангров",
    # «Helix» в именах предметов — «Спиральный» («Helix Log» ->
    # «Спиральное бревно»), значит и удача по дереву называется так же.
    "Helix Fortune": "Удача спирали",
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
    # ⚠️ Терминов БЕЗ русской формы в режиме оставалось три, и это дырка
    # именно ПОЛНОГО перевода: в обычном режиме они английские по решению
    # игрока, а включивший режим видел бы их английскими вопреки обещанию.
    # `Respiration` в список НЕ входит: у него в словаре стоит @ключ,
    # и клиент сам подставляет «Подводное дыхание» — это точнее нашего слова.
    "Charm Chance": "Шанс очарования",
    # ⚠️ «Pristine Procs» лежал в словаре ДВАЖДЫ: «Срабатываний Pristine»
    # (перенесено из общих словарей, где термин английский по решению)
    # и «Срабатываний Чистоты». Побеждал первый — то есть в РЕЖИМЕ, который
    # включают ради русского слова, оставалось английское.
    "Pristine Procs": "Срабатываний Чистоты",
    "Vitality": "Живучесть",
    # `Fishing Speed` в STAT_JARGON не значится (он английский по отдельному
    # решению 29.07), но форма нужна по той же причине — иначе в режиме
    # «Даёт +5 Fishing Speed» остаётся посреди русской фразы.
    "Fishing Speed": "Скорость рыбалки",
    # ⚠️ Дырки, найденные ПО РЕЖИМНЫМ АБЗАЦАМ: эти четыре в обычном режиме
    # переводятся (`11-stat-forms`), а в режимном словаре их не было — и
    # абзац показывал бы «+5 Treasure Chance» рядом с подписью «Шанс
    # сокровищ: +5». Формы взяты у обычных словарей, чтобы не разойтись.
    "Treasure Chance": "Шанс сокровищ",
    "Double Hook Chance": "Шанс двойной поклёвки",
    "Swing Range": "Размах удара",
    "Hunting Fortune": "Удача охоты",
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


def stays_english(rule: dict) -> bool:
    """Правило, которое оставляет ЖАРГОННЫЙ термин английским.

    ⚠️ В общих словарях такая запись — РЕШЕНИЕ игрока (жаргон английский),
    а здесь она бессмысленна: словарь включают, чтобы термин стал русским.
    Попадает сюда переносом (`split_sb_stats` тащит записи из общих словарей)
    и живёт молча — а если встанет РАНЬШЕ русского правила, включивший режим
    увидит английское слово вопреки обещанию.
    """
    match = re.match(r"\^([A-Za-z' " + "\\" * 2 + r"]{3,32})[:( ]", rule.get("p", ""))
    if not match:
        return False
    name = match.group(1).replace("\\", "").strip()
    if name not in terms.STAT_JARGON:
        return False
    replacement = rule.get("r", "")
    return any(re.search(r"(?<![A-Za-z])" + re.escape(word) + r"(?![A-Za-z])",
                         replacement)
               for word in re.findall(r"[A-Za-z]{3,}", name))


def shadowing_exact(names: dict[str, str]) -> dict[str, str]:
    """Русские ТОЧНЫЕ записи взамен тождественных из обычных словарей.

    ⚠️ `exact` движок ищет РАНЬШЕ правил, а формы режима лежат правилами.
    Значит тождественная точная запись обычного словаря («Vitality: +{n}» ->
    то же самое) ГАСИТ режим по этой строке целиком: словарь загружен,
    правило есть, команда говорит «режим включён», а на экране английское
    слово. Тень видна только замером — сторожа на неё нет.

    Для обычного режима такая запись законна (жаргон английский по решению),
    поэтому её не трогаем, а кладём рядом РУССКУЮ в режимный словарь: у него
    priority меньше, а у `exact` выигрывает МЕНЬШИЙ.
    """
    out: dict[str, str] = {}
    for path in sorted(PACK.parent.parent.rglob("*.json")):
        if path.name in ("index.json", PACK.name):
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if pack.get("group") == "full":
            continue
        for key, value in (pack.get("exact") or {}).items():
            if not isinstance(value, str) or key != value:
                continue
            match = LABEL.match(key)
            if not match:
                continue
            name = match.group(1)
            russian = names.get(name)
            if russian:
                out[key] = russian + key[len(name):]
    return out



# ⚠️⚠️ ГЛОССАРИЙ ЖАРГОНА — просьба игрока 27.08: «мне для режима full нужен
# перевод жаргонов». Точные формы («Magic Find: +{n}») закрывают ПОДПИСИ,
# а термин ВНУТРИ фразы («Grants +5 Ferocity to your pet») закрывает только
# глоссарий — и в нём было 10 терминов из 59.
#
# ⚠️ ОДНОСЛОВНЫЕ ПУСКАЕМ НЕ ВСЕ, и это замер по живым строкам, а не осторожность:
#   Heat        73 строки, из них 64 — ИМЕНА ПРЕДМЕТОВ («Titanic Heat Helmet»)
#   Vitality   307 строк, 276 — ЗАЧАРОВАНИЕ («Hardened Vitality V»)
#   Respiration 98 строк, 80 — ванильное зачарование, его даёт клиент
#   Sweep      120 строк, 39 — имена предметов («Common Sweep Booster»)
#   Fear        23 строки, 20 — имя NPC «Fear Mongerer» и метка чек-листа
# Подстановка внутри них дала бы смесь языков в ИМЕНИ, а имя мы не переводим.
# Прочие однословные (`Pull`, `Tracking`, `Overbloom`) встречаются только
# как характеристика — их пускаем.
UNSAFE_ALONE = frozenset({"Heat", "Vitality", "Respiration", "Sweep", "Fear"})


def glossary_terms(names: dict) -> dict:
    """Термины, которые можно подставлять ВНУТРИ строки."""
    out = {}
    for term in terms.STAT_JARGON:
        russian = names.get(term)
        if not russian:
            continue
        if " " not in term and term in UNSAFE_ALONE:
            continue
        # ⚠️ КУСОК ДЛИННОГО ТЕРМИНА НЕ ПУСКАЕМ: «Fortune» внутри «Hunter
        # Fortune» однажды дал «Mining Удача» — записанная грабля проекта.
        longer = any(term != other and _inside(term, other)
                     for other in terms.STAT_JARGON)
        if longer:
            continue
        out[term] = russian
    return out


def _inside(short: str, long: str) -> bool:
    return re.search(r"(?<![A-Za-z])" + re.escape(short) + r"(?![A-Za-z])", long) is not None


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
        # ⚠️ ЗНАЧОК ПОСЛЕ ЗНАЧЕНИЯ: «Carrot Fortune: +{n}<значок>».
        # Форма выше ловит значок ПЕРЕД числом (список игроков), а Hypixel
        # ставит его и в хвосте — у подписей урожайных удач. Замер 26.08:
        # 15 живых строк не переводились, при том что БЕЗ значка перевод
        # есть у 14 из них. Записанная грабля «значок вплотную к числу».
        rules.append({"p": f"^{source}: ({NUMBER}{ICON})$", "r": f"{target}: $1"})
        # ⚠️ ПЯТАЯ ФОРМА: «Breaking Power 4» — имя и число БЕЗ значка и без
        # двоеточия. Так Hypixel пишет подзаголовок под названием вещи, и её
        # не ловила ни одна из четырёх: те все требуют либо двоеточия, либо
        # значка. Нашёл игрок на экране, а не сторож.
        rules.append({"p": f"^{source} ({NUMBER})$", "r": f"{target} $1"})
        # ⚠️ ЗАГОЛОВОК подсказки: « Health» — значок и имя, БЕЗ числа
        # и БЕЗ двоеточия. Ни одна из прежних форм его не ловила, и меню
        # «Настройка характеристик» стояло с английскими заголовками при
        # русском теле — нашёл игрок на экране. Значок ОБЯЗАТЕЛЕН: без него
        # правило поймало бы обычное слово («Speed» отдельной строкой).
        rules.append({"p": f"^({ICON} ?){source}$", "r": f"$1{target}"})

    pack = json.loads(PACK.read_text(encoding="utf-8"))
    # ⚠️ ДОПОЛНЯЕМ, а не переписываем. split_sb_stats однажды обнулил этот
    # словарь на втором запуске (242 записи исчезли молча), и грабля записана.
    old = pack.get("regex") or []
    # ⚠️ Сверяем БЕЗ набора значков: иначе расширение ICON раздваивает
    # каждое правило — новое с широким классом и мёртвое старое с узким.
    fresh = {without_icons(rule["p"]) for rule in rules}
    kept = [rule for rule in old
            if rule.get("p") and without_icons(rule["p"]) not in fresh
            and not stays_english(rule)]
    pack["regex"] = rules + kept

    shadow = shadowing_exact(names)
    if shadow:
        exact = pack.get("exact") or {}
        exact.update(shadow)
        pack["exact"] = dict(sorted(exact.items()))
        print(f"точных записей поверх тождественных: {len(shadow)}")
        for key, value in list(shadow.items())[:6]:
            print(f"    {key!r} -> {value!r}")
    print()
    print(f"правил: было {len(old)}, стало {len(pack['regex'])} "
          f"(новых {len(rules)}, сохранено прежних {len(kept)})")

    gloss = dict(pack.get("glossary") or {})
    before = len(gloss)
    gloss.update(glossary_terms(names))
    pack["glossary"] = dict(sorted(gloss.items()))
    print(f"глоссарий: было {before}, стало {len(gloss)}")

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
