"""
Зачарования SkyBlock и подписи характеристик: сбор, заготовка, словарь.

Проблема. Зачарования Hypixel выводит СПИСКОМ через запятую:
    Wisdom V, Growth VI, Protection VI
А правила были привязаны ко всей строке (`^Growth ([IVXLC]+)$`), поэтому внутри
списка не срабатывали — на экране половина по-русски, половина нет. Плюс из 205
встреченных в игре зачарований в словаре лежало 79.

Решение двойное, и оба слоя нужны:
  regex    — на всю строку или сегмент, с необязательной запятой на конце.
             Точное и безопасное, срабатывает первым.
  glossary — подстановка ВНУТРИ незнакомой строки, с областью `item_lore`.
             Ловит любые сочетания в списке. Движок берёт только целые слова
             (isWordBoundary), так что «Luck» не испортит «Lucky».
Глоссарий — последняя попытка после точного поиска и правил, поэтому он не
перебивает то, что уже переведено лучше.

Порядок работы:
  1. python tools/gen_enchants.py --skeleton     -> data/work/enchants.json
  2. python tools/translate_ai.py data/work/enchants.json --sync
  3. python tools/gen_enchants.py                -> словарь в packs/<язык>/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
WORK = ROOT / "data" / "work"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")
LANG = "ru_ru"
OUT = PACKS / LANG / "76-enchant-names.json"
# Кастомные зачарования SkyBlock — отдельным ПЕРЕКЛЮЧАЕМЫМ словарём
OUT_EXT = PACKS / LANG / "77-sb-enchants.json"
# Старый рукотворный словарь: его правила перенесены в заготовку
OLD_HAND = PACKS / LANG / "75-sb-enchants.json"
INDEX = PACKS / "index.json"
SKELETON = WORK / "enchants.json"

# ⚠️ «Имя + УРОВЕНЬ и БОЛЬШЕ НИЧЕГО». Прежний шаблон обрывался на группе
# уровня и потому ловил ЧУЖИЕ правила с текстом после неё:
#   ^Tier ([IVXLC]+) Rewards$        -> «Награды $1 ступени»
#   ^Milestone ([IVXLC]+) in (…)$    -> «До вехи $1 — $2 $3»
# Их замены уезжали в подпись характеристики («^Tier:$» -> «Награды $1
# ступени:»), то есть на экран с живым «$1» посреди слова.
LEVEL_ONLY = re.compile(r"\^(.+?) \(\[IVXLC\][^)]*\)(?:\(,\?\\s\*\))?\$$")

# ⚠️ Бонусы за УРОВЕНЬ НАВЫКА — не зачарования, и в переключаемый словарь
# им нельзя. Выглядят они одинаково («Warrior XIII» против «Angler VI»),
# поэтому по форме их не отличить, и все восемь уезжали в sb_enchants —
# то есть выключались вместе с ним. Работали они лишь потому, что те же строки
# просочились ВТОРЫМ слоем в 90-from-game.json, минуя выключатель: 157 записей,
# оплаченных дважды. Список закрытый — навыков в SkyBlock фиксированное число,
# так что это перечисление известных сущностей, а не эвристика.
SKILL_BONUSES = {
    "Farmhand",    # Farming
    "Conjurer",    # Enchanting
    "Brewer",      # Alchemy
    "Warrior",     # Combat
    "Charming",    # Hunting
    "Zoologist",   # Taming
    "Logger",      # Foraging
    "Spelunker",   # Mining
}

# «Sharpness VII», «Bane of Arthropods VII», «Ultimate Wise V»
ITEM = re.compile(r"^([A-Z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*){0,3}) ([IVXLC]{1,6})$")

# Подпись характеристики: «Gear Score: 877 (1297)», «Gemstones: [x] [y]»
LABEL = re.compile(r"^([A-Z][A-Za-z' ]{2,26}):(?: |$)")

# Характеристика БЕЗ двоеточия: иконка, название, число. Так Hypixel пишет их
# на экране профиля и в меню — «(иконка) Health 1,234». Порога по частоте тут нет:
# форма сама по себе надёжный признак, в отличие от голого двоеточия.
#
# ⚠️ Число в конце обязательно: «(иконка) Foraging Camp» — это МЕСТО, таких строк
# в дампе 35, и переводить их нельзя.
ICON_LABEL = re.compile(
    "^[" + chr(92) + "ue000-" + chr(92) + "uf8ff] ?"
    r"([A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){0,2}) ?[+\-]?(?:\{n\}|[\d,.]+)%?$")

# Не зачарования и не характеристики — служебные слова, переводить их тут нечего
SKIP = {"Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Special", "Divine"}


def known_names() -> dict[str, str]:
    """
    Что уже переведено — из правил вида ^Name ([IVXLC]+)$ во всех словарях.

    ⚠️ ОБА СВОИХ ВЫХОДА пропускаем, а не один. Раньше исключался только `OUT`,
    а `OUT_EXT` (77-sb-enchants) читался — и генератор кормил сам себя: замена
    правила «{имя} $1$2» возвращалась сюда, снизу дописывался ещё один хвост,
    и так каждый прогон. Замер: у «Fishing Speed» накопилось ДЕСЯТЬ «$1»,
    у «Attack Speed» пять, у «Speed» два. На экране это дало бы
    «Скорость атаки VI VI VI VI VI».
    """
    found: dict[str, str] = {}
    for path in sorted(PACKS.rglob("*.json")):
        if path.name in ("index.json", OUT.name, OUT_EXT.name):
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for rule in pack.get("regex") or []:
            match = LEVEL_ONLY.match(rule.get("p", ""))
            if match:
                name = match.group(1).replace("\\", "")
                # ⚠️ Хвостов $N бывает НЕСКОЛЬКО («Шанс $1$2» — уровень
                # и запятая). Снимаем ВСЕ: снятие одного и было той дырой,
                # через которую накапливались лишние «$1».
                target = re.sub(r"(?:\s*\$\d)+\s*$", "", rule.get("r", "")).strip()
                if target:
                    found[name] = target
        for section in ("exact", "glossary"):
            for source, target in (pack.get(section) or {}).items():
                if target and not target.startswith("@") and ITEM.match(source + " I"):
                    found.setdefault(source, target)
    return found


def seen_names() -> tuple[Counter, Counter]:
    """Что реально встречается: зачарования и подписи характеристик."""
    enchants: Counter = Counter()
    labels: Counter = Counter()
    sure: Counter = Counter()
    sources: list[str] = []

    collected = DUMP / "collected.json"
    if collected.exists():
        data = json.loads(collected.read_text(encoding="utf-8"))
        for origin in ("item_lore", "screen"):
            sources += list((data.get("sources") or {}).get(origin, {}))
    for name in ("paragraphs.json", "lore_tooltips.json"):
        path = WORK / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for para in data.get("paragraphs") or []:
            sources.append(para["text"])
        for block in data.get("tooltips") or []:
            sources += block.get("lines") or []

    for line in sources:
        # Подпись характеристики: за двоеточием обязано быть значение,
        # иначе это просто фраза с двоеточием
        label = LABEL.match(line)
        if label and label.group(1) not in SKIP and len(line) > len(label.group(1)) + 1:
            if not re.fullmatch(r"[IVXLC]+", label.group(1)):
                labels[label.group(1)] += 1

        # Форма без двоеточия — сразу в надёжные, порог ей не нужен
        icon = ICON_LABEL.match(line)
        if icon and icon.group(1) not in SKIP:
            sure[icon.group(1)] += 1

        # ⚠️ Зачарования берём ТОЛЬКО из строк-списков через запятую.
        #
        # По одиночному «Sharpness I» их не отличить от имени предмета:
        # «Sheep Minion I», «Gold Ingot IX» выглядят точно так же, а их
        # переводить НЕЛЬЗЯ — по именам ищут на аукционе. Первый заход собрал
        # 399 «зачарований», и хвост оказался сплошь миньонами и коллекциями.
        # У списка через запятую такой формы не бывает — признак надёжный.
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        matched = [ITEM.match(p) for p in parts]
        if not all(matched):
            continue
        for item in matched:
            if item.group(1) not in SKIP:
                enchants[item.group(1)] += 1
    return enchants, labels, sure


def previous() -> dict[str, str]:
    """
    Уже сделанные переводы заготовки.

    ⚠️ Заготовка — ЕДИНСТВЕННОЕ место, где живут эти переводы: {@link known_names}
    нарочно не читает собранный словарь, иначе сборка кормила бы сама себя.
    Поэтому перезаписать заготовку пустыми значениями — значит стереть работу,
    и один раз это уже случилось. Берём старые значения из двух мест сразу:
    из самой заготовки и из собранного словаря, который из неё вырос.
    """
    done: dict[str, str] = {}
    if OUT.exists():
        pack = json.loads(OUT.read_text(encoding="utf-8"))
        for source, target in (pack.get("glossary") or {}).items():
            # ⚠️ Хвост $N снимаем И ЗДЕСЬ, а не только у правил ниже.
            # Без этого сборка КОРМИЛА САМА СЕБЯ: значение глоссария уходило
            # в `names`, оттуда в замену правила «{name} $1$2», а на следующем
            # прогоне возвращалось сюда уже с лишним «$1». Замер: у «Combo»
            # накопилось ДЕВЯТЬ хвостов, у «Fishing Speed» — девять, и на
            # экране в полном режиме вышло бы «Комбо VI VI VI VI…».
            # Прочие имена спасала только заготовка: она перебивает это
            # значение — а у кого записи в заготовке нет, тот и накапливал.
            target = re.sub(r"(?:\s*\$\d)+\s*$", "", str(target)).strip()
            if target:
                done[source] = target
        for rule in pack.get("regex") or []:
            match = re.match(r"\^(.+?) \(\[IVXLC\]", rule.get("p", ""))
            if match:
                # ⚠️ Хвостов $N бывает НЕСКОЛЬКО: «Шанс $1$2» — цифра уровня
                # и запятая. Снимали один — и в заготовку возвращалось
                # «Шанс $1», которое дальше уехало бы прямо на экран.
                target = re.sub(r"(?:\s*\$\d)+\s*$", "", rule.get("r", "")).strip()
                if target:
                    done.setdefault(match.group(1).replace("\\", ""), target)
    if SKELETON.exists():
        old = json.loads(SKELETON.read_text(encoding="utf-8")).get("exact") or {}
        done.update({k: v for k, v in old.items() if v})
    return done


def write_skeleton() -> int:
    enchants, labels, sure = seen_names()
    known = known_names()
    done = previous()
    pending = {}
    contexts = {}
    for name, count in enchants.most_common():
        if name not in known:
            pending[name] = done.get(name, "")
            contexts[name] = f"зачарование SkyBlock, встречается {count}x"
    # Подписи с порогом: у одиночных это чаще случайная фраза с двоеточием,
    # а не подпись характеристики. На пороге 3 остаётся 150 настоящих.
    for name, count in labels.most_common():
        if count >= 3 and name not in known and name not in pending:
            pending[name] = done.get(name, "")
            contexts[name] = f"подпись характеристики в подсказке, встречается {count}x"
    # Форма «иконка Имя число» порога не требует: у неё сам вид — признак.
    # Именно эти строки видно на экране профиля, с них и пришла жалоба.
    for name, count in sure.most_common():
        if name not in known and name not in pending:
            pending[name] = done.get(name, "")
            contexts[name] = f"характеристика SkyBlock, на экране пишется «(иконка) {name} 123»"

    SKELETON.parent.mkdir(parents=True, exist_ok=True)
    SKELETON.write_text(json.dumps({
        "id": "enchant_names",
        "_comment": "Заготовка: названия зачарований и подписи характеристик. "
                    "Перевести через tools/translate_ai.py, затем собрать словарь "
                    "через tools/gen_enchants.py.",
        "_contexts": contexts,
        "exact": pending,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"уже знаем: {len(known)}")
    print(f"встречено в игре и корпусе: зачарований {len(enchants)}, подписей {len(labels)}")
    print(f"уже переведено в заготовке: {sum(1 for v in pending.values() if v)}")
    print(f"НУЖЕН ПЕРЕВОД: {sum(1 for v in pending.values() if not v)}")
    print(f"записано: {SKELETON.relative_to(ROOT)}")
    print("\nдальше:  python tools/translate_ai.py data/work/enchants.json --sync")
    return 0


# Похоже на ТЕРМИН, а не на фразу: буквы, пробелы, апостроф, дефис — и коротко.
# Тот же признак, что в tools/gen_stat_forms.py, чтобы «термин» значил одно и то же.
TERM_LIKE = re.compile(r"[A-Za-z'\- ]{3,28}")


def all_known_terms() -> set[str]:
    """
    Термины ГЛОССАРИЯ из всех словарей — с ними наш термин и может соперничать.

    ⚠️ Соперник бывает только в глоссарии, и это следует из устройства движка:
    точную запись он ищет ПЕРВОЙ, а глоссарий применяет лишь к строке, которой
    в словаре нет вовсе. Значит запись из `exact` всегда обыгрывает глоссарий
    и отнимать у термина ничего не может. Опасен именно глоссарный сосед —
    живой случай из истории проекта: «Crit Chance» лежал в общем глоссарии без
    области (такие выключены флагом glossaryPass), а «Chance» — с областью,
    то есть включён всегда, и на экране вышло «Crit Шанс».

    Раньше сюда шли ключи `exact` тоже, и проверка выбрасывала работающие
    названия дважды:
      * целые фразы («…Requires Bane of Arthropods VI!») содержат любое слово,
        поэтому «кусок чужого термина» находился всегда — в глоссарии осталось
        0 названий из 69;
      * строки «Strong Vitality Enchantment» — записи `exact` из лора, они
        забирали ещё 47.
    Беда тихая и отложенная: счётчик выброшенных выглядит как работа защиты,
    а урон растёт вместе со словарём. Симптом на экране — список зачарований
    английский, хотя перевод каждого в словаре есть.
    """
    terms: set[str] = set()
    for path in sorted(PACKS.rglob("*.json")):
        if path.name in ("index.json", OUT.name, OUT_EXT.name):
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # ⚠️ ВЫКЛЮЧЕННЫЙ словарь соперником не считается: он не применяется,
        # пока игрок его не включит. Иначе «Angler» вылетал из глоссария из-за
        # «Angler Pottery Shard» — записи ванильных названий, которая по умолчанию
        # выключена, — и на удочке зачарование оставалось английским.
        if pack.get("default") is False:
            continue
        terms.update(k for k, v in (pack.get("glossary") or {}).items()
                     if v and TERM_LIKE.fullmatch(k))

    # ⚠️ Характеристики-жаргон считаем соперниками ВСЕГДА, хотя их словарь
    # выключен. Тут выключение значит не «перевода нет», а «оставляем
    # английским» — и подставить внутрь такого имени кусок перевода нельзя.
    # Живой случай: ванильное «Fortune» → «@enchantment.minecraft.fortune»
    # лезло в «Hunter Fortune» и давало «Hunter fortune» — смесь языков
    # там, где термин обязан остаться целым.
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    import terms as _terms
    terms.update(_terms.of("stat_jargon"))
    return terms


def swallows_longer(name: str, terms: set[str]) -> str | None:
    """
    Термин — КУСОК более длинного известного термина? Тогда в глоссарий нельзя.

    ⚠️ Живой случай. «Chance» попал в глоссарий с областью item_lore, а
    «Crit Chance» лежал в общем глоссарии БЕЗ области — такие выключены флагом
    glossaryPass. Длинный проиграл короткому не по длине, а потому что был
    выключен, и в профиле игрока появилось «Crit Шанс»: половина по-русски.
    Смесь языков хуже честного английского.

    Правило простое: если наш термин целым словом входит в другой известный,
    в глоссарий он не идёт. Правило-регулярка на всю строку остаётся — оно
    привязано к границам и такой беды не создаёт.
    """
    for term in terms:
        if term == name or len(term) <= len(name):
            continue
        if not re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", term):
            continue
        # ⚠️ ДВИЖОК САМ ЗАЩИЩАЕТ СОСТАВНОЕ ИМЯ, если длинный термин — это
        # «Заглавное слово + наш термин»: `Translator.insideProperName` видит
        # слева слово с заглавной и пропускает подстановку. Тогда запрет лишний,
        # а цена его высока — «Luck» не пускали из-за «Pet Luck», и списки
        # зачарований «Looting III, Luck V, Scavenger V» оставались английскими
        # (замер 26.08: 109 живых строк).
        #
        # ⚠️ Ослабление держится на ДАННЫХ, а не на доверии: короткий и длинный
        # не встречаются в ОДНОЙ строке ни разу (проверено по нашему дампу
        # и по строкам от игроков — 0 совпадений). Иначе сработала бы записанная
        # грабля: проверку движок делает по ПЕРВОМУ вхождению, а заменяет все.
        head = term[: -len(name)].rstrip()
        if head and head[:1].isupper() and " " not in head and not _seen_together(name, term):
            continue
        return term
    return None


_TOGETHER: dict[tuple[str, str], bool] = {}


def _seen_together(short: str, long_term: str) -> bool:
    """Короткий и длинный термин встречаются в ОДНОЙ живой строке?"""
    key = (short, long_term)
    if key in _TOGETHER:
        return _TOGETHER[key]
    import json as _json
    found = False
    for path in (DUMP / "collected.json", ROOT / "data" / "work" / "from_players.json"):
        if not Path(path).exists():
            continue
        try:
            data = _json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        groups = data.get("sources") or data.get("lines") or data
        if not isinstance(groups, dict):
            continue
        for lines in groups.values():
            if not isinstance(lines, dict):
                continue
            for line in lines:
                if long_term in line and re.search(
                        rf"(?<![A-Za-z]){re.escape(short)}(?![A-Za-z])",
                        line.replace(long_term, "")):
                    found = True
                    break
            if found:
                break
        if found:
            break
    _TOGETHER[key] = found
    return found


_MARKS: dict[str, str] | None = None


def marked_enchant(name: str) -> bool:
    """
    В заготовке имя помечено как ЗАЧАРОВАНИЕ, а не подпись характеристики?

    Пометку пишет сам сбор (`--skeleton`) и правит человек. Она и отличает
    «Angler» от «Charge»: первое можно класть в глоссарий, второе испортило бы
    прозу — «Charge» это обычное слово.
    """
    global _MARKS
    if _MARKS is None:
        _MARKS = {}
        if SKELETON.exists():
            _MARKS = json.loads(SKELETON.read_text(encoding="utf-8")).get("_contexts") or {}
    return "зачарование" in (_MARKS.get(name) or "")


def build_pack() -> int:
    base = known_names()
    names = dict(base)
    if SKELETON.exists():
        done = json.loads(SKELETON.read_text(encoding="utf-8")).get("exact") or {}
        names.update({k: v for k, v in done.items() if v})

    # ⚠️ Одно слово — два разных смысла, и перевод у них разный.
    #
    # «Mending V» на предмете — ванильное зачарование Minecraft, его переводит
    # сам клиент (@enchantment.minecraft.mending, «Починка»). А «Mending: 500»
    # у класса Лекарь — характеристика подземелий, и «Починка» там неверна:
    # это сила лечения. Различить строки механически можно (римская цифра
    # против числа), а вот ОДНО имя на оба случая — нельзя.
    #
    # Поэтому: если имя уже известно как ванильное зачарование (перевод пришёл
    # @ключом), правило зачарования и глоссарий оставляем ванильными, а подпись
    # характеристики берёт перевод из заготовки. Раньше заготовка перекрывала
    # оба — и ванильное зачарование поехало бы за статом.
    vanilla = {name for name, target in base.items() if target.startswith("@")}

    enchants, labels, sure = seen_names()
    # Длинные вперёд: «Bane of Arthropods» должен победить «Arthropods»
    ordered = sorted(names, key=len, reverse=True)

    rules = []
    glossary = {}
    swallowed = []
    terms = all_known_terms()
    # ⚠️ Переведённое в заготовке считаем зачарованием, даже если в дампе оно
    # ещё не попадалось. Сбор берёт зачарования ТОЛЬКО из строк-списков через
    # запятую — признак надёжный, но он видит лишь то, что игрок уже встретил.
    # «Last Stand» перевели руками, а правила ему не досталось: словарь знал
    # слово и не мог его применить.
    hand_made = set()
    if SKELETON.exists():
        hand_made = {k for k, v in
                     (json.loads(SKELETON.read_text(encoding="utf-8")).get("exact") or {}).items()
                     if v and ITEM.match(k + " I")}

    for name in ordered:
        target = names[name]
        # зачарованию — ванильный перевод, подписи — свой (см. про Mending выше)
        as_enchant = base[name] if name in vanilla else target
        if name in enchants or name in hand_made:
            # необязательная запятая на конце: Hypixel режет список на куски,
            # и в сегмент часто попадает «Growth VI, »
            # ⚠️ ДО ДЕСЯТИ ЗНАКОВ, а не шести: «XXXVII» — ровно шесть, а уже
            # «XXXVIII» (38) семь, и бонусы за уровень навыка доходят до 60+.
            # Прежний предел молча резал всё выше 37-го уровня.
            rules.append({"p": f"^{re.escape(name)} ([IVXLC]{{1,10}})(,?\\s*)$",
                          "r": f"{as_enchant} $1$2"})
            # ⚠️ В МЕНЮ ЗАЧАРОВАНИЯ УРОВЕНЬ АРАБСКИЙ: на предмете «Angler VI»,
            # а на кнопке «Angler 6» и «Big Brain 1-3» (вилка уровней). Правило
            # под римские цифры туда не достаёт, и заголовок кнопки оставался
            # английским при готовом переводе имени.
            # ⚠️ ЧИСЛО В ШАБЛОНЕ — РЕГУЛЯРКОЙ, А НЕ ДЫРКОЙ {n}. Движок гоняет
            # правила по СЫРОЙ строке (Translator.lookup -> matcher(source)),
            # а {n} бывает только в обобщённой — такое правило не совпадёт
            # НИКОГДА. Ловится только check_hole_rules.py.
            rules.append({"p": f"^{re.escape(name)} ([\\d,]+(?:-[\\d,]+)?)$",
                          "r": f"{as_enchant} $1"})
            # ⚠️ В глоссарий — ТОЛЬКО то, что ВИДЕЛИ в списке через запятую.
            #
            # Правило на всю строку туда не достаёт, поэтому списку нужен
            # глоссарий. А вот подписям он вреден: среди них «Water», «Note»,
            # «Effect», «Charge» — обычные слова, ими глоссарий испортил бы
            # прозу. Подпись и так всегда в начале строки, ей хватает правила.
            #
            # Именно поэтому hand_made даёт ПРАВИЛО, но не даёт глоссарий:
            # переведённое руками может оказаться подписью, а не зачарованием,
            # и проверить это нечем — в дампе его ещё не встречали. Первая
            # версия этой правки раздула глоссарий с 70 записей до 177.
            # ⚠️ …но заготовка — ОСОБЫЙ случай, и вот почему.
            #
            # Раньше hand_made не давал глоссарий вовсе, и на удочке половина
            # списка оставалась английской: «Flash V, Angler VI, Blessing VI» —
            # правило до них не достаёт, а в глоссарии их нет. При этом на дрели
            # те же зачарования переводились: там они идут ПО ОДНОМУ на строку,
            # и правила хватает. Со стороны это выглядит случайностью.
            #
            # Заготовка ведётся руками и помечает каждое имя: «зачарование
            # SkyBlock» или «подпись характеристики». Значит зачарование из неё —
            # такой же надёжный источник, как список через запятую из дампа.
            if name in enchants or (name in hand_made and marked_enchant(name)):
                longer = swallows_longer(name, terms)
                if longer:
                    swallowed.append((name, longer))
                else:
                    glossary[name] = as_enchant
        # ⚠️ И labels, и sure: без sure характеристика, встреченная ТОЛЬКО
        # в форме «иконка Имя число», не получала ни одного правила — перевод
        # лежал в заготовке и никуда не попадал. Так молча выпал «Mining Spread».
        if name in labels or name in sure:
            rules.append({"p": f"^{re.escape(name)}:(\\s*)$", "r": f"{target}:$1"})

    # ⚠️ ДВА файла, и деление не косметическое.
    #
    # Названия кастомных зачарований SkyBlock — вкусовое решение: по ним ищут
    # на аукционе и в фильтрах, поэтому игрок должен уметь их выключить. Значит
    # им место в переключаемом словаре («default»: false), как ванильным
    # названиям предметов.
    #
    # А вот ВАНИЛЬНЫЕ зачарования и подписи характеристик выключать нельзя:
    # первые и так приходят из самой игры (@ключ), и в клиенте игрока они уже
    # русские; вторые — обычные слова («Урон», «Скорость добычи»), без которых
    # подсказка станет наполовину английской.
    def is_vanilla(value: str) -> bool:
        return value.startswith("@")

    def is_skill_bonus(rule: dict) -> bool:
        """Бонус за уровень навыка — не зачарование, выключать его нельзя."""
        return any(rule["p"].startswith("^" + re.escape(name) + " ")
                   for name in SKILL_BONUSES)

    # ⚠️ Характеристики-жаргон сюда не попадают ВОВСЕ: их перевод живёт
    # в переключаемом sb_stats. Без этого «Overbloom:», «Ferocity:»
    # и «Pristine:» уезжали подписями в ядро, которое включено всегда, —
    # и выключатель не работал бы, как это уже было с «Lapidary V».
    # Проверять надо КАЖДЫЙ генератор, собирающий имена по всем словарям:
    # закрыть один слой мало.
    import terms
    jargon = terms.of("stat_jargon")
    rules = [rule for rule in rules
             if not any(rule["p"].startswith("^" + re.escape(name)) for name in jargon)]
    glossary = {name: value for name, value in glossary.items() if name not in jargon}

    core_rules = [r for r in rules
                  if is_vanilla(r["r"]) or r["p"].endswith(":(\\s*)$") or is_skill_bonus(r)]

    # ⚠️ ПРЕЖНИЕ ПОДПИСИ СОХРАНЯЕМ, а не выбрасываем.
    #
    # Список подписей собирается из того, что встречается в дампе и корпусе
    # СЕЙЧАС. Часть пришла из источников, которых уже нет: дамп чистился,
    # корпус пересобирался. Перезапуск такие правила молча стирал — замер
    # 26.08: «Enchanting:», «Difficulty:», «Dungeon:», «Boss:», «Combat:»
    # исчезали за один прогон и переставали переводиться ВООБЩЕ (спрошен
    # движок). В игре эти подписи есть — просто мимо них давно не ходили.
    #
    # Так же устроен `gen_stat_forms`: там разово потерялось 428 правил.
    # ⚠️ Мёртвое не переносим: дырка «{n}» в шаблоне не совпадёт с сырой
    # строкой НИКОГДА — движок гоняет правила ДО обобщения чисел.
    # ⚠️ Жаргон не переносим тоже: его перевод живёт в переключаемом
    # sb_stats, а ядро включено всегда — иначе выключатель снова сломается.
    kept = 0
    if OUT.exists():
        try:
            was = json.loads(OUT.read_text(encoding="utf-8")).get("regex") or []
        except (json.JSONDecodeError, OSError):
            was = []
        fresh = {r["p"] for r in core_rules}
        # ⚠️ ОДНА обратная косая: в файле лежит «\s», а json.loads отдаёт «\s».
        tail = ":(" + chr(92) + "s*)$"
        for rule in was:
            pattern = rule.get("p") or ""
            if not pattern.endswith(tail) or pattern in fresh:
                continue
            if chr(92) + "{n" in pattern or chr(92) + "{s" in pattern:
                continue
            if any(pattern.startswith("^" + re.escape(name)) for name in jargon):
                continue
            core_rules.append(rule)
            kept += 1
    if kept:
        print(f"перенесено прежних подписей: {kept}")
    ext_rules = [r for r in rules if r not in core_rules]
    core_gloss = {k: v for k, v in glossary.items()
                  if is_vanilla(v) or k in SKILL_BONUSES}
    ext_gloss = {k: v for k, v in glossary.items()
                 if not is_vanilla(v) and k not in SKILL_BONUSES}

    # ⚠️ ГОЛОЕ ИМЯ ЗАЧАРОВАНИЯ — ЭТО КНОПКА МЕНЮ, и правила его не ловят:
    # они писаны под «Имя УРОВЕНЬ» («^Cubism ([IVXLC]+)$»), а в меню Enchant
    # Item кнопка подписана просто «Cubism». Замер 24.08: 31 такая строка
    # в `menu_title` и 12 в `item_lore` — все кнопки, ни одной прозы.
    # Кладём ТОЧНОЙ записью: она срабатывает только на строку целиком,
    # поэтому «Critical» внутри фразы не тронет.
    # ⚠️ ГОЛОЕ ИМЯ БЫВАЕТ ЗАНЯТО ИМЕНЕМ ВЕЩИ, и в заголовке победит наше.
    # «Scuba» — это КРОЛИК Chocolate Factory (проверено по блоку подсказки:
    # «Grants +N Chocolate… You have not found this rabbit yet!»), а у нас
    # он же зачарование «Акваланг». Открыв область `item_name`, мы бы
    # подменили имя кролика: priority 13 против 61 у `81-item-names`,
    # а у `exact` побеждает МЕНЬШИЙ.
    # Расхождение считаем ПО ПЕРЕВОДУ, а не по совпадению имени: «Inferno»
    # и «Breeze» тоже носят и кролики, и зачарования — но переводятся
    # одинаково, и спорить там не о чем. Замер 25.08: спорных ровно одно.
    taken = {}
    names_file = ROOT / "data" / "work" / "item_names_ru.json"
    if names_file.exists():
        raw = json.loads(names_file.read_text(encoding="utf-8")).get("names") or {}
        for key, value in raw.items():
            text = value.get("ru") if isinstance(value, dict) else value
            if isinstance(text, str) and text and text != "-":
                taken[key] = text

    bare_core, bare_ext = {}, {}
    clashes = []
    for name, translation in glossary.items():
        if " " in name and len(name.split()) > 3:
            continue
        if name in taken and taken[name] != translation:
            clashes.append((name, translation, taken[name]))
            continue
        target = bare_core if (is_vanilla(translation) or name in SKILL_BONUSES) else bare_ext
        target[name] = translation
    if clashes:
        print(f"  голых имён отдано ВЕЩАМ: {len(clashes)}"
              f" (в заголовке это имя предмета, а не зачарование)")
        for name, ours, theirs in clashes:
            print(f"     {name}: зачарование {ours!r} против имени {theirs!r}")

    core = {
        "id": "enchant_names",
        "priority": 14,
        "_comment": "Подписи характеристик и ВАНИЛЬНЫЕ зачарования (их перевод "
                    "берётся у самой игры @ключом). Выключать нельзя: без подписей "
                    "подсказка станет наполовину английской. Собирается скриптом "
                    "tools/gen_enchants.py — правь заготовку data/work/enchants.json.",
        # ⚠️ `item_name` добавлен 25.08: в меню Enchant Item и в справочниках
        # имя зачарования стоит ЗАГОЛОВКОМ кнопки. Замер: так не доезжал
        # 91 готовый перевод. Спорное голое имя отсеяно выше (см. taken).
        # ⚠️ `chat` добавлен 26.08: БОНУСЫ ЗА УРОВЕНЬ НАВЫКА («Warrior II»,
        # «Zoologist I», «Farmhand VII») сервер объявляет в чат, а область
        # туда не пускала — 23 готовых перевода лежали мёртвым грузом.
        # Замер по 1548 живым строкам чата: новых 23, изменившихся 0.
        # ⚠️ `tab` добавлен 26.08: подпись виджета «Pet:» приходит строкой ТАБА.
        # Замер по 168 живым строкам таба: новых 1, изменившихся 0.
        "only": ["item_lore", "screen", "menu_title", "item_name", "chat", "tab"],
        "exact": bare_core,
        "regex": core_rules,
        "glossary": core_gloss,
    }
    ext = {
        "id": "sb_enchants",
        "priority": 13,
        "default": False,
        # ⚠️ ГРУППА ОБЯЗАТЕЛЬНА, иначе словарь выключен НАВСЕГДА. Он был
        # `default: false` без группы, и `/skyblockru full on` его не включал:
        # 417 записей лежали мёртвым грузом, а в режиме полного перевода
        # названия зачарований оставались английскими. Поимённо игрок включить
        # его может, но режим — не перечень файлов, и помнить он должен режим.
        "group": "full",
        "about": "Перевод названий зачарований SkyBlock: «Angler VI» -> «Рыболов VI». "
                 "Выключен по умолчанию: по английским названиям ищут вещи на аукционе "
                 "и настраивают фильтры.",
        "_comment": "Кастомные зачарования Hypixel SkyBlock. ПЕРЕКЛЮЧАЕМЫЙ словарь: "
                    "/skyblockru pack sb_enchants on. Два слоя: regex ловит строку "
                    "целиком («Angler VI» своей строкой у дрели), glossary — то же имя "
                    "ВНУТРИ списка через запятую («Flash V, Angler VI, Blessing VI» "
                    "у удочки), куда правило на всю строку не достаёт.",
        # ⚠️ `item_name` добавлен 25.08: в меню Enchant Item и в справочниках
        # имя зачарования стоит ЗАГОЛОВКОМ кнопки. Замер: так не доезжал
        # 91 готовый перевод. Спорное голое имя отсеяно выше (см. taken).
        "only": ["item_lore", "screen", "menu_title", "item_name"],
        "exact": bare_ext,
        "regex": ext_rules,
        "glossary": ext_gloss,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(core, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_EXT.write_text(json.dumps(ext, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.name}: правил {len(core_rules)}, терминов {len(core_gloss)}"
          f"  (подписи и ванильные — всегда включены)")
    print(f"{OUT_EXT.name}: правил {len(ext_rules)}, терминов {len(ext_gloss)}"
          f"  (зачарования SkyBlock — ПЕРЕКЛЮЧАЕМЫЕ, по умолчанию выключены)")
    if swallowed:
        print(f"НЕ пущено в глоссарий (кусок более длинного термина): {len(swallowed)}")
        for name, longer in swallowed:
            print(f"    {name!r} внутри {longer!r}")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    listing = index.setdefault("languages", {}).setdefault(LANG, [])
    changed = False
    for name in (OUT.name, OUT_EXT.name):
        if name not in listing:
            listing.append(name)
            changed = True
            print(f"добавил {name} в index.json")
    # ⚠️ Ручной 75-sb-enchants.json больше не нужен: его 36 правил перенесены
    # в заготовку, и генератор владеет ими один. Оставить оба — значит держать
    # два источника правды и однажды разойтись.
    if OLD_HAND.name in listing:
        listing.remove(OLD_HAND.name)
        changed = True
        print(f"убрал из index.json устаревший {OLD_HAND.name}"
              f" — его правила теперь в заготовке")
    if changed:
        listing.sort()
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


TRANSLATE_RULES = """Ты переводишь на русский НАЗВАНИЯ ЗАЧАРОВАНИЙ и ПОДПИСИ
характеристик из Hypixel SkyBlock.

⚠️ Главное: это НЕ имена собственные, их НУЖНО переводить. Общее правило
«названия не трогаем» тут не действует — зачарование это свойство предмета,
и игрок должен понимать, что оно делает. «Lethality» -> «Смертоносность»,
«Drain» -> «Вытягивание», «Gear Score» -> «Оценка снаряжения».

Правила:
1. Коротко: это подписи в тесной подсказке, а не проза.
2. С заглавной буквы, как в оригинале.
3. Без пояснений в скобках и без точки в конце.
4. Термины из глоссария ниже соблюдай: если «Vitality» там «Vitality»,
   то «Strong Vitality» — «Сильная живучесть», а не «Крепкое здоровье».
5. Если слово и правда непереводимо (выдуманное имя собственное) — верни его
   без изменений, но это редкий случай, а не отговорка.

Отвечай только переводом."""


def translate_pending() -> int:
    """Переводит то, что осталось в заготовке, отдельным запросом."""
    from anthropic import Anthropic

    data = json.loads(SKELETON.read_text(encoding="utf-8"))
    exact, contexts = data["exact"], data.get("_contexts") or {}
    pending = [k for k, v in exact.items() if not v]
    if not pending:
        print("всё уже переведено")
        return 0

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from apikey import check as check_key
    if not check_key():
        return 1
    from translate_tooltips import glossary

    schema = {"type": "object", "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"en": {"type": "string"}, "ru": {"type": "string"}},
        "required": ["en", "ru"], "additionalProperties": False}}},
        "required": ["items"], "additionalProperties": False}

    listing = "\n".join(f"{name}   [{contexts.get(name, '')}]" for name in pending)
    client = Anthropic()
    response = client.messages.create(
        model="claude-opus-5", max_tokens=16000,
        system=[{"type": "text", "text": TRANSLATE_RULES + "\n\n" + glossary(),
                 "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "high"},
        messages=[{"role": "user", "content": "Переведи каждое название:\n\n" + listing}],
    )
    if response.stop_reason == "refusal":
        print("модель отказалась")
        return 1
    payload = json.loads("".join(b.text for b in response.content if b.type == "text"))

    filled = 0
    for item in payload.get("items") or []:
        name, target = item.get("en"), (item.get("ru") or "").strip()
        if name in exact and target:
            exact[name] = target
            filled += 1
    SKELETON.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    usage = response.usage
    cost = ((getattr(usage, "input_tokens", 0) / 1e6 * 5)
            + (getattr(usage, "output_tokens", 0) / 1e6 * 25)
            + (getattr(usage, "cache_read_input_tokens", 0) / 1e6 * 0.5)
            + (getattr(usage, "cache_creation_input_tokens", 0) / 1e6 * 6.25))
    print(f"переведено: {filled} из {len(pending)}   (${cost:.3f})")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Зачарования и подписи характеристик")
    parser.add_argument("--skeleton", action="store_true", help="собрать заготовку к переводу")
    parser.add_argument("--translate", action="store_true", help="перевести остаток заготовки")
    args = parser.parse_args()
    if args.skeleton:
        return write_skeleton()
    if args.translate:
        return translate_pending()
    return build_pack()


if __name__ == "__main__":
    raise SystemExit(main())
