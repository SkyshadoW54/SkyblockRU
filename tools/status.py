"""
СОСТОЯНИЕ строки: есть перевод, ждёт в очереди, «переводить нечего» или её нет вовсе.

Зачем отдельный инструмент. Пока беды находил игрок скриншотами, цикл был такой:
увидел английское — прислал картинку — я ищу, в каком слое дырка. Находки при этом
случайны, а мод свои промахи ЗНАЕТ: он сам пишет в дамп и непереведённое, и смесь
языков. Значит спрашивать надо не игрока, а дамп.

Два режима:
  python tools/status.py                     сводка по живому дампу: чего не хватает
  python tools/status.py "текст с экрана"    вердикт по одной строке (можно несколько)

Вердикт даётся по ТОМУ ЖЕ порядку, что у движка (Translator.lookup):
  точная запись -> обобщение по числам -> правило-регулярка -> глоссарий,
плюс проверка абзацев (мод склеивает соседние строки) и колонок (полоса над хотбаром).

⚠️ Правила примеряются Python-регулярками, а исполняет их Java. В мелочах движки
расходятся (живой случай: «\\uE000» с двумя косыми). Точная проверка шаблонов —
tools/check_rules.py, она гоняет настоящую Java.

⚠️ Глоссарий с областью ОТКАТЫВАЕТСЯ, если после подстановки английских слов
осталось больше, чем русских (Translator.applyGlossary). Из-за этого список
зачарований «Strong Vitality V, Sugar Rush III, Thorns III» остаётся целиком
английским, хотя два названия из трёх словарь знает: перевести часть — значит
сделать смесь языков, а она хуже. Инструмент это показывает отдельным статусом,
потому что лечится оно не переводом строки, а ДОБАВЛЕНИЕМ ТЕРМИНОВ в глоссарий.
"""

from __future__ import annotations

import argparse
import collections
import functools
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
WORK = ROOT / "data" / "work"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")

# Как обобщает числа сам движок (Translator.NUMBER)
# ⚠️ Обобщение чисел — из общего pkey: копий было шесть, и одна
# уже разошлась (в measure_color процент попадал внутрь числа).
from pkey import NUMBER  # noqa: E402
CODES = re.compile(r"§.")
ICONS = re.compile(r"[\ue000-\uf8ff]")
# Колонки полосы над хотбаром: разделитель — несколько пробелов
COLUMNS = re.compile(r"\s{3,}")

# Статусы, по убыванию «сделанности»
OK = "перевод есть"
BY_PARAGRAPH = "закрыто абзацем"
BY_COLUMNS = "закрыто по колонкам"
PARTIAL = "глоссарий откатится (вышла бы смесь языков)"
QUEUED = "ЖДЁТ В ОЧЕРЕДИ"
NOTHING = "переводить нечего (помечено)"
# ⚠️ Не «нечего», а «решено оставить английским»: к жаргону мы намерены
# вернуться, включив sb_stats. Отдельный статус — чтобы эти строки не мозолили
# глаза в списке работы, но и не потерялись, когда решим перевести всё.
JARGON = "оставлено английским (жаргон, sb_stats выключен)"
MISSING = "НЕТ НИГДЕ — даже не собрано"


def in_engine_order() -> list[tuple[Path, dict]]:
    """
    Словари в ТОМ ЖЕ порядке, в каком их перебирает мод.

    ⚠️ Раньше здесь стоял `sorted(PACKS.rglob("*.json"))` — то есть порядок
    по ИМЕНИ ФАЙЛА. А движок сортирует пакеты по `priority` по убыванию
    (`Translator.java`: PACKS.sort(comparingInt(priority).reversed())), и
    порядок решает, КАКОЙ перевод победит: у `exact` первый заполняет ключ
    (`putIfAbsent`), а правила перебираются подряд до первого совпадения.

    Расхождение делает инструмент бесполезным ровно там, где он нужен: на
    вопрос «что покажет игра» он отвечал `11-stat-forms.json` (имя «11» раньше),
    тогда как игра берёт `40-lore.json` — priority 25 против 12. Пока переводы
    в обоих совпадают, разницы не видно; разойдутся — инструмент назовёт
    не тот файл и не тот текст, причём уверенно.

    При равном priority мод сохраняет порядок загрузки (`List.sort` в Java
    устойчива), а грузит он по `index.json` — сперва `common`, потом язык.
    Повторяем и это, иначе ничью решал бы случай.
    """
    order: list[str] = []
    try:
        index = json.loads((PACKS / "index.json").read_text(encoding="utf-8"))
        order = list(index.get("common") or [])
        for names in (index.get("languages") or {}).values():
            order.extend(names)
    except (json.JSONDecodeError, OSError):
        pass

    packs: list[tuple[int, int, Path, dict]] = []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        place = order.index(path.name) if path.name in order else len(order)
        packs.append((-int(pack.get("priority") or 0), place, path, pack))
    return [(path, pack) for _, _, path, pack in sorted(packs, key=lambda r: r[:2])]


CONFIG = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/config.json")


@functools.lru_cache(maxsize=1)
def glossary_pass() -> bool:
    """
    Включена ли грубая подстановка терминов БЕЗ области.

    Умолчание `false` — как в `RuConfig.glossaryPass`. Спрашиваем конфиг ИГРОКА,
    а не держим свою копию: инструмент отвечает на вопрос «что покажет игра»,
    а игра смотрит именно туда.
    """
    try:
        return bool(json.loads(CONFIG.read_text(encoding="utf-8")).get("glossaryPass"))
    except (json.JSONDecodeError, OSError):
        return False


class Rule(NamedTuple):
    """
    Правило-регулярка словаря.

    ⚠️ Поле `tg` тут не для полноты: без него инструмент разворачивает захват
    ДОСЛОВНО, тогда как движок переводит его по словарю (Translator.expandGroups).
    Одно правило с `tg` закрывает все навыки сразу — «+{n} Foraging ({n}/{n}k)»
    становится «+{n} Лесозаготовка ({n}/{n}k)», — а инструмент показывал прежний
    английский текст и объявлял колонку непереведённой. В отчёте она стояла
    ПЕРВОЙ, с 750 показами.
    """

    pattern: re.Pattern
    replacement: str
    where: str
    tg: bool


class Dictionaries:
    """Словари мода, разложенные так же, как их держит Translator."""

    def __init__(self, without: set[str] | None = None) -> None:
        """
        without — имена файлов словарей, которые НЕ учитывать.

        ⚠️ Нужно ГЕНЕРАТОРАМ, спрашивающим «а нет ли перевода уже».
        Генератор, который читает все словари и потом ПЕРЕЗАПИСЫВАЕТ свой,
        находит там собственные прошлые записи, считает работу сделанной
        и пишет пустоту. Ровно так `gen_headers.py` обнулил 41-headers.json:
        1385 записей -> 0, молча, с бодрым «записано». Та же беда уже была
        у `split_sb_stats` (242 записи), и чинили её тогда в одном месте,
        а не признаком — потому она и вернулась.
        """
        without = without or set()
        self.exact: dict[str, tuple[str, str]] = {}
        self.templates: dict[str, tuple[str, str]] = {}
        self.rules: list[Rule] = []
        self.glossary: dict[str, str] = {}
        # термины С областью: только они работают при выключенном glossaryPass
        self.scoped_terms: set[str] = set()
        self.paragraphs: dict[str, tuple[str, str]] = {}
        self.skipped: list[str] = []
        for path, pack in in_engine_order():
            if path.name in without:
                self.skipped.append(f"{path.name} (исключён вызвавшим)")
                continue
            # ⚠️ Словарь с «default»: false ВЫКЛЮЧЕН, пока игрок не включит его
            # через /skyblockru pack <id> on. Учитывать его — значит обещать
            # перевод, которого на экране нет: так «Sugar» из выключенных
            # ванильных названий выглядел рабочим термином глоссария.
            if pack.get("default") is False:
                self.skipped.append(f"{path.name} (id {pack.get('id')}, выключен)")
                continue
            for key, value in (pack.get("exact") or {}).items():
                if not value:
                    continue
                if "{n}" in key or "{s}" in key:
                    # Ручной шаблон — обычная запись словаря: движок кладёт её
                    # через put, значит побеждает ПОСЛЕДНИЙ пакет.
                    self.templates[key] = (value, path.name)
                else:
                    # ⚠️ ПОБЕЖДАЕТ ПОСЛЕДНИЙ, а не первый. Пакеты идут по priority
                    # ПО УБЫВАНИЮ, а движок раскладывает их через put — значит
                    # затирает предыдущего, и в живых словарях выигрывает пакет
                    # с МЕНЬШИМ priority («меньший priority — важнее», так и
                    # написано в Translator). Здесь стоял setdefault, то есть
                    # инструмент отвечал ровно наоборот: на вопрос «что покажет
                    # игра» называл проигравший словарь.
                    self.exact[key] = (value, path.name)
                    template = NUMBER.sub("{n}", key)
                    if template != key:
                        # ⚠️ А вот АВТОшаблон собирается через putIfAbsent —
                        # тут побеждает первый, и setdefault верен.
                        self.templates.setdefault(template, (value, path.name))
            for rule in pack.get("regex") or []:
                if not rule.get("r"):
                    continue
                try:
                    self.rules.append(Rule(re.compile(rule["p"]), rule["r"],
                                           path.name, bool(rule.get("tg"))))
                except re.error:
                    continue
            # Глоссарий и абзацы движок тоже кладёт через put — тот же порядок,
            # что у exact: последний пакет затирает предыдущего.
            #
            # ⚠️ ТЕРМИН БЕЗ ОБЛАСТИ ДВИЖОК НЕ ПРИМЕНЯЕТ, пока не включён
            # `glossaryPass` (`Translator.applyGlossary`: `only == null &&
            # !glossaryPass` → пропуск). А флаг выключен и в коде, и в конфиге
            # игрока. Инструмент этого не знал и подставлял ВСЕ термины: из 49
            # реально работает 21, а 28 он применял впустую — и показывал порчу,
            # которой на экране нет («Sheep Minion I» → «Sheep миньон I»,
            # хотя это имя предмета и движок его не трогает).
            for term, value in (pack.get("glossary") or {}).items():
                if value:
                    self.glossary[term] = value
                    if pack.get("only"):
                        self.scoped_terms.add(term)
            for key, value in (pack.get("paragraphs") or {}).items():
                if value:
                    self.paragraphs[key] = (value, path.name)
        # длинные термины вперёд — так же сортирует движок.
        # Безобластные берём, только если игрок включил glossaryPass.
        usable = (self.glossary if glossary_pass()
                  else {t: v for t, v in self.glossary.items() if t in self.scoped_terms})
        self.terms = sorted(usable, key=len, reverse=True)


# Дырки движка и то, чем он их заменяет при сборке правила из записи.
# Копия Translator.NAME_GROUP и NUMBER_GROUP — иначе инструмент не повторит мод.
NAME_HOLE = r"((?:\[[A-Za-z+]{2,10}\]\s*)?[A-Za-z0-9_]{3,16})"
NUMBER_HOLE = r"([\d,.]+)"


CHOICE = re.compile(r"\[[^\]]+\]")


def fill_choices(text: str, dic: "Dictionaries") -> str:
    """
    Подставляет переводы вариантов ответа — как это делает мод.

    Конечны сами варианты, а не их сочетания: наборов у каждого NPC свои,
    и ключом набор быть не может. Мод режет его и ищет каждый вариант
    отдельно (Translator.translateChoices), здесь повторяем то же.
    """
    def one(match: re.Match) -> str:
        found = dic.exact.get(match.group())
        return found[0] if found else match.group()

    return CHOICE.sub(one, text)


def clean(text: str) -> str:
    """Строка как её видит словарь: без §-кодов, с обрезкой краёв."""
    return CODES.sub("", text).strip()


# Римская цифра — не английское слово: она одинакова на любом языке. Тот же
# признак, что в Translator.isRoman; без него уровни «III» в списке зачарований
# перевешивают русский перевод, и движок откатывает подстановку целиком.
ROMAN = re.compile(r"[IVXLC]+")


def latin_words(text: str) -> int:
    return len([w for w in re.findall(r"[A-Za-z][A-Za-z']+", text)
                if len(w) > 1 and not ROMAN.fullmatch(w)])


def cyrillic_words(text: str) -> int:
    return len([w for w in re.findall(r"[А-Яа-яЁё][А-Яа-яЁё]+", text) if len(w) > 1])


def try_glossary(line: str, dic: Dictionaries) -> tuple[str | None, bool]:
    """
    Подстановка терминов внутри незнакомой строки.

    Возвращает (что получится, применится ли). Второе — та самая проверка из
    Translator.applyGlossary: если английских слов в результате больше, чем
    русских, движок откатывает подстановку целиком.
    """
    result = line
    touched = False
    for term in dic.terms:
        if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", result):
            value = dic.glossary[term]
            if value.startswith("@"):
                # Ванильный ключ разворачивает САМА ИГРА, и в подсчёт слов он
                # войдёт русским (Translator.applyGlossary разворачивает его ДО
                # проверки на смесь). Показываем это явно, а не латинским хвостом
                # ключа: иначе инструмент считал бы «Шипы» английским словом.
                value = "⟨из игры: " + value.rsplit(".", 1)[-1] + "⟩"
            result = re.sub(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", value, result)
            touched = True
    if not touched:
        return None, False
    return result, cyrillic_words(result) >= latin_words(result)


# Глубже одного уровня перевод захвата не пускает и движок
# (Translator.MAX_GROUP_DEPTH): правило, поймавшее собственный результат,
# зациклится.
MAX_GROUP_DEPTH = 1


def hole_samples() -> tuple[str, str] | None:
    """
    Чем заполнять дырки `{n}` и `{s}`, чтобы примерить правило.

    Образцы берём У ОЧЕРЕДИ (`make_queue.HOLE_*`), а не заводим свои: копия
    признака в этом проекте расходилась трижды, и каждый раз молча.
    Нет очереди — заполненную форму просто не примеряем: лучше не проверить,
    чем проверить своей копией.
    """
    try:
        from make_queue import HOLE_NAME, HOLE_NUMBER
        return HOLE_NUMBER, HOLE_NAME
    except ImportError:
        return None


def probes(line: str) -> list[str]:
    """
    Виды строки, которые надо примерить к правилу.

    ⚠️ В ДАМПЕ ЧИСЛА УЖЕ ОБОБЩЕНЫ («+{n} Foraging ({n}/{n}k)»), а правила
    писаны под ЖИВУЮ строку («\\+([\\d,]+)»): движок применяет их ДО обобщения.
    Прямое сравнение не совпадёт НИКОГДА — и отчёт объявлял непереведённой
    колонку с 750 показами, хотя правило её закрывает.

    ⚠️ Ровно эта грабля уже записана про `covered_by_rule`, и она повторилась
    потому, что чинили ТО МЕСТО, а не признак. Здесь признак один на оба
    места инструмента (вердикт и колонки полосы).
    """
    seen = [line]
    template = NUMBER.sub("{n}", line)
    if template not in seen:
        seen.append(template)
    samples = hole_samples()
    if samples:
        number, name = samples
        for form in list(seen):
            filled = form.replace("{n}", number).replace("{s}", name)
            if filled not in seen:
                seen.append(filled)
    return seen


def unfill(text: str) -> str:
    """Вернуть образцы обратно в дырки: показываем строку в том виде, в каком спросили."""
    samples = hole_samples()
    if not samples:
        return text
    number, name = samples
    return text.replace(number, "{n}").replace(name, "{s}")


def expand(rule: Rule, match: re.Match, dic: Dictionaries, depth: int) -> str:
    """
    Подставить захваты в замену — как Translator.expandGroups.

    ⚠️ Веток две, и они разные в самом движке: без `tg` идёт обычная
    подстановка (`matcher.replaceFirst`), а с `tg` каждый захват переводится
    по словарю. Инструмент знал только первую, поэтому показывал английский
    результат там, где игра даёт русский.
    """
    if not rule.tg:
        # показываем ГОТОВЫЙ вид, а не шаблон с $1 — иначе непонятно,
        # что именно игрок увидит на экране
        try:
            return match.expand(rule.replacement.replace("$", "\\"))
        except (re.error, IndexError):
            return rule.replacement

    out: list[str] = []
    text = rule.replacement
    position = 0
    while position < len(text):
        symbol = text[position]
        if symbol == "$" and position + 1 < len(text) and text[position + 1].isdigit():
            number = int(text[position + 1])
            position += 2
            if 1 <= number <= match.re.groups:
                raw = match.group(number)
                if raw is not None:
                    out.append(translate_group(raw, dic, depth))
            continue
        out.append(symbol)
        position += 1
    return "".join(out)


def translate_group(raw: str, dic: Dictionaries, depth: int = 0) -> str:
    """
    Перевод одного ЗАХВАЧЕННОГО куска — как Translator.translateGroup.

    Порядок движка: полный поиск (с ограничением глубины) → набор вариантов
    ответа → глоссарий → как есть.
    """
    if depth < MAX_GROUP_DEPTH:
        found = lookup(raw, dic, depth + 1)
        if found:
            return found[0]
    # ⚠️ Набор вариантов режем ТОЛЬКО здесь, как и движок
    # (translateChoices зовётся из translateGroup, а не из lookup).
    # Раньше инструмент резал его после ЛЮБОГО правила — то есть обещал
    # перевод вариантов там, где правило стоит без `tg` и движок их не тронет.
    choices = fill_choices(raw, dic)
    if choices != raw:
        return choices
    partial, applies = try_glossary(raw, dic)
    if partial and applies:
        return partial
    return raw


def lookup(line: str, dic: Dictionaries, depth: int = 0) -> tuple[str, str] | None:
    """
    Что движок вернёт для этой строки: (перевод, где лежит) либо ничего.

    Повторяет Translator.lookup по порядку: точная запись → шаблон по числам
    → правило-регулярка. Глоссарий сюда НЕ входит — движок применяет его
    отдельно и только к строке, которой в словаре нет вовсе.
    """
    template = NUMBER.sub("{n}", line)

    if line in dic.exact:
        return dic.exact[line]
    if template in dic.templates:
        return dic.templates[template]
    if template in dic.exact:
        return dic.exact[template]
    # ⚠️ ЗАПИСЬ С ДЫРКОЙ — ЭТО ТОЖЕ ПРАВИЛО. Движок собирает из неё регулярку
    # при загрузке (Translator.templateRule): «…Season of Jerry, {s}!» ловит
    # строку с настоящим ником. Без этого инструмент уверенно отвечал «НЕТ
    # НИГДЕ» про реплики, которые на экране давно по-русски.
    for key, (value, where) in dic.templates.items():
        if "{s}" not in key:
            continue
        pattern = re.escape(key)
        pattern = pattern.replace(re.escape("{s}"), NAME_HOLE)
        pattern = pattern.replace(re.escape("{n}"), NUMBER_HOLE)
        match = re.fullmatch(pattern, line)
        if match:
            result = value
            for group in match.groups():
                result = result.replace("{s}", group, 1)
            return result, where

    rule, match = rule_hit(line, dic)
    if rule and match:
        return unfill(expand(rule, match, dic, depth)), rule.where
    return None


def rule_hit(line: str, dic: Dictionaries) -> tuple[Rule | None, re.Match | None]:
    """
    Правило, которое возьмёт строку, — в порядке движка.

    Внешний цикл по ПРАВИЛАМ, а не по видам строки: движок перебирает их
    подряд до первого совпадения (`Translator.lookup`), и порядок в файле
    словаря решает, кто победит.
    """
    forms = probes(line)
    for rule in dic.rules:
        for probe in forms:
            match = rule.pattern.fullmatch(probe)
            if match:
                return rule, match
    return None, None


def verdict(raw: str, dic: Dictionaries, queue: dict, corpus: dict) -> dict:
    """Что мод сделает с этой строкой и в каком она состоянии."""
    line = clean(raw)
    template = NUMBER.sub("{n}", line)

    found = lookup(line, dic)
    if found:
        value, where = found
        return {"status": OK, "where": where, "result": value}

    # абзац: мод склеивает соседние строки, и наша строка может быть его куском
    for key, (value, where) in dic.paragraphs.items():
        if len(line) > 6 and (line in key or template in key):
            return {"status": BY_PARAGRAPH, "where": where, "result": value,
                    "hint": "⚠️ применится ТОЛЬКО если склейка разрешена по цветам"
                            " (ColorLayout): у заголовка с полями и у списка"
                            " со значками мод склеивать не станет —"
                            " проверить python tools/check_colors.py"}

    # полоса над хотбаром собрана колонками, каждая переводится отдельно
    if COLUMNS.search(line):
        parts = [p for p in COLUMNS.split(line) if p.strip()]
        if parts and all(
                clean(p) in dic.exact or NUMBER.sub("{n}", clean(p)) in dic.templates
                for p in parts):
            return {"status": BY_COLUMNS, "where": "по колонкам", "result": ""}

    partial, applies = try_glossary(line, dic)
    if partial and not applies:
        # что именно осталось английским: римские уровни в счёт не идут
        left = [word for word in re.findall(r"[A-Za-z][A-Za-z']*(?: [A-Z][A-Za-z']*)*", partial)
                if not re.fullmatch(r"[IVXLC]{1,6}", word) and len(word) > 2]
        return {"status": PARTIAL, "where": "glossary", "result": partial,
                "hint": "не хватает терминов: " + ", ".join(sorted(set(left))[:6])
                        + " — их надо завести в data/work/enchants.json,"
                          " а в глоссарий они попадут, когда встретятся в списке"
                          " через запятую в дампе (gen_enchants)"}
    if partial and applies:
        return {"status": OK, "where": "glossary", "result": partial}

    # перевода нет: в каком состоянии очередь?
    for key in (line, template):
        if key in queue["asis"]:
            return {"status": NOTHING, "where": "_asis", "result": ""}
        if key in queue["waiting"]:
            return {"status": QUEUED, "where": "from_game.json", "result": ""}
    for key in (line, template):
        if key in corpus["nothing"]:
            return {"status": NOTHING, "where": "paragraphs.json: nothing", "result": ""}
        if key in corpus["waiting"]:
            return {"status": QUEUED, "where": "paragraphs.json", "result": ""}

    # ⚠️ ЖАРГОН — это РЕШЕНИЕ, а не пробел. Все `*Fortune` и `*Wisdom`,
    # «Magic Find», «Pristine» и прочее из terms.STAT_JARGON оставлены
    # английскими намеренно: перевод слова механику не объясняет, а по этим
    # названиям читают гайды. Перевод для них лежит в выключенном sb_stats.
    #
    # Отчёт об этом не знал и показывал их как «НЕТ НИГДЕ» — то есть звал
    # чинить решённое. Это ровно то, на что жаловался игрок: список работы
    # мозолит глаза тем, что работой не является.
    #
    # ⚠️ Отдельный статус, а НЕ «переводить нечего»: разница в том, что
    # к жаргону мы намерены вернуться. Захотим перевести всё — включим
    # sb_stats, и эти строки снова станут работой, видной по своему статусу.
    label = STAT_LABEL.match(line)
    if label and label.group(1).strip() in jargon_names():
        return {"status": JARGON, "where": "terms.STAT_JARGON", "result": ""}
    return {"status": MISSING, "where": "", "result": ""}


# Подпись характеристики в начале строки: «Gemstone Fortune: +12 (+3)»
STAT_LABEL = re.compile(r"^([A-Z][A-Za-z' ]{2,30}?): *[+\-]?[\d,.{-]")

_JARGON: frozenset[str] | None = None


def jargon_names() -> frozenset[str]:
    """Характеристики, оставленные английскими по решению игрока."""
    global _JARGON
    if _JARGON is None:
        try:
            import terms
            _JARGON = frozenset(terms.STAT_JARGON)
        except (ImportError, OSError):
            _JARGON = frozenset()
    return _JARGON


def load_queue() -> dict:
    """Очередь построчного перевода: кто ждёт, кому «нечего»."""
    path = WORK / "from_game.json"
    if not path.exists():
        return {"waiting": set(), "asis": set()}
    data = json.loads(path.read_text(encoding="utf-8"))
    exact = data.get("exact") or {}
    asis = set(data.get("_asis") or [])
    # ⚠️ Три состояния, а не два: помеченные «переводить нечего» лежат в exact
    # с пустым значением, но ЖДУЩИМИ не являются. Сложишь их вместе — и очередь
    # покажет 472 вместо одной строки.
    return {
        "waiting": {k for k, v in exact.items() if not v and k not in asis},
        "asis": asis,
    }


def load_corpus() -> dict:
    """Корпус абзацев: что ждёт перевода, что помечено «нечего»."""
    path = WORK / "paragraphs.json"
    if not path.exists():
        return {"waiting": set(), "nothing": set()}
    data = json.loads(path.read_text(encoding="utf-8"))
    waiting, nothing = set(), set()
    for para in data.get("paragraphs") or []:
        if para.get("ru"):
            continue
        (nothing if para.get("nothing") else waiting).add(para["text"])
    return {"waiting": waiting, "nothing": nothing}


def show(text: str, width: int = 74) -> str:
    return ICONS.sub("◇", clean(text))[:width]


def why_missing(raw: str) -> list[str]:
    """
    Путь строки от дампа до очереди: где именно она потерялась.

    Отвечает на «почему нет перевода» по шагам, теми же функциями, какими
    очередь и решает, — чтобы ответ не расходился с делом.
    """
    out: list[str] = []
    try:
        import make_queue as mq
    except ImportError:
        return ["что делать: сыграть с этой строкой на экране,"
                " потом python tools/make_queue.py"]

    dump = ROOT / "data" / "work" / "collected.json"
    live = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")
    path = live if live.exists() else dump
    try:
        sources = (json.loads(path.read_text(encoding="utf-8")).get("sources") or {})
    except (json.JSONDecodeError, OSError):
        return ["дамп не читается: " + str(path)]

    # ⚠️ В ДАМПЕ ЧИСЛА УЖЕ ОБОБЩЕНЫ. Мод пишет туда «Убито Magma Cubes: {n}»,
    # а игрок спрашивает про строку с настоящим числом — и поиск по сырому виду
    # не находил ничего. Инструмент уверенно отвечал «мод эту строку ещё
    # не видел» и советовал идти играть, хотя строка в дампе лежала.
    probe = NUMBER.sub("{n}", clean(raw))
    where = [name for name, lines in sources.items()
             if isinstance(lines, dict) and (raw in lines or probe in lines)]
    if not where:
        return ["в дампе её НЕТ: мод эту строку ещё не видел",
                "что делать: открыть её в игре, потом python tools/refresh.py"]
    # Дальше работаем с тем видом, который РЕАЛЬНО лежит в дампе: фильтры
    # очереди смотрят именно на него.
    stored = raw
    for name in where:
        if raw not in sources.get(name, {}) and probe in sources.get(name, {}):
            stored = probe
            break
    raw = stored
    out.append(f"в дампе есть — источник: {', '.join(where)}")

    taken = [name for name in where if name in mq.WORTH]
    if not taken:
        out.append(f"⚠️ источник {where[0]} мы НЕ переводим намеренно (NEVER/не в WORTH)")
        return out

    source = taken[0]
    if not mq.worth_translating(raw, source):
        out.append("⚠️ отсеяно: worth_translating() — числа, ник или техническая метка")
        return out
    known, guarded, covered = mq.already_translated()
    if raw in known:
        out.append("⚠️ отсеяно: уже переведено в другом словаре")
        return out
    if raw in mq.in_paragraphs():
        out.append("⚠️ отсеяно: строка входит в абзац корпуса (его и применят)")
        return out
    if mq.guarded_by_toggle(raw, guarded):
        out.append("⚠️ отсеяно: закрыто ВЫКЛЮЧЕННЫМ словарём — это решение игрока")
        return out
    if mq.covered_by_rule(raw, covered):
        out.append("отсеяно осознанно: строку переводит ПРАВИЛО включённого словаря")
        return out
    if source == "item_lore":
        names = {s.strip() for s in (sources.get("item_name") or {})}
        if raw.strip() in names and mq.looks_like_item(raw, mq.real_item_headers()):
            out.append("⚠️ отсеяно: это имя НАСТОЯЩЕГО предмета, их не переводим")
            return out
        if mq.ENCHANT_LIST.match(raw):
            out.append("⚠️ отсеяно: похоже на список зачарований")
            return out
        if mq.is_stat_line(raw, mq.known_stats()):
            out.append("⚠️ отсеяно: строка характеристики (подпись есть в списке)")
            return out
    out.append("фильтры проходит — значит очередь просто устарела")
    out.append("что делать: python tools/refresh.py")
    return out


def one_line(raw: str, dic: Dictionaries, queue: dict, corpus: dict) -> None:
    answer = verdict(raw, dic, queue, corpus)
    print(f"  {show(raw)}")
    print(f"     {answer['status']}" + (f"   [{answer['where']}]" if answer["where"] else ""))
    if answer["result"]:
        print(f"     -> {show(answer['result'], 84)}")
    if answer.get("hint"):
        print(f"     {answer['hint']}")
    if answer["status"] == MISSING:
        # ⚠️ «Нет нигде» — это не ответ, а вопрос. За вечер он прозвучал семь раз,
        # и каждый раз причина была РАЗНАЯ: строки не было в дампе; она была,
        # но её выбросил фильтр характеристик; её отсеяли как имя предмета;
        # очередь собиралась раньше, чем игрок открыл меню. Разбираться
        # приходилось одноразовыми скриптами. Теперь путь строки печатается сам.
        for line in why_missing(raw):
            print("     " + line)
    elif answer["status"] == QUEUED:
        print("     что делать: python tools/translate_ai.py data/work/from_game.json --sync")


# Ник с тегом гильдии в боковой панели: «{s} [ZOMB]». Переводить нечего.
NICK_ROW = re.compile(r"^\{s\}(\s*\[[A-Za-z0-9]{1,8}\])?\s*$")
# Совсем ничего переводимого: числа, значки, дырки, разметка
NO_LETTERS = re.compile(r"^[\W\d_]*$")
# Ведущий маркер списка: «▶ Titanic Experience Bottle» — имя предмета со значком
LIST_MARK = re.compile(r"^[^\w\s]+\s*")
# ⚠️ НАРЯД ПРОКАЧКИ в конце имени: «Aurora Chestplate ✪✪✪», «Waxed Bone Necklace
# ✪✪✪✪✪➎», «Ancient Maxor's Helmet ✪✪✪✪✪ ✦». Звёзды ставит сервер за ковку
# и звёздность, а ИМЯ от них не меняется — по нему всё так же ищут на аукционе.
# Без снятия каждый вариант прокачки выглядел новой непереведённой строкой:
# замер 01.08 — 294 таких в отчёте, и все до одной ложные.
UPGRADE_MARKS = re.compile(r"[\s✪✦✧➀-➓❶-❿]+$")


def worth_counting(line: str, source: str, items: set[str]) -> bool:
    """
    Строку СТОИТ считать непереведённой?

    ⚠️ Без этого отбора сводка врёт втрое и становится бесполезной. Ровно так
    метрика покрытия однажды показала 25% вместо правды: в «непереведённое»
    попали имена предметов, ники из боковой панели и строки из одних чисел —
    всё то, что мы не переводим ПО ЗАМЫСЛУ.
    """
    clean_line = clean(line)
    # дырки убираем ДО проверки: «{n}/{n}» — это числа, а не текст, но буквы
    # «n» и «s» внутри них счётчик сбивают
    bones = clean_line.replace("{n}", " ").replace("{s}", " ")
    if not clean_line or NO_LETTERS.match(bones):
        return False
    if NICK_ROW.match(clean_line):
        return False
    # ⚠️ Признаки «это ник / список игроков / номер сервера» НЕ пишем заново:
    # они уже отобраны на живых данных в tools/make_queue.py, и вторая копия
    # разошлась бы с первой. Одна беда — один признак, в одном месте.
    try:
        from make_queue import worth_translating
        if not worth_translating(clean_line, source):
            return False
    except ImportError:
        pass
    # имя предмета: по нему ищут на аукционе. Ведущий маркер снимаем — «▶ Bottle»
    # это то же имя, что «Bottle», просто со значком от Hypixel. Наряд прокачки
    # в хвосте снимаем по той же причине: «Aurora Chestplate ✪✪✪» — тот же предмет.
    bare = LIST_MARK.sub("", clean_line).strip()
    plain = UPGRADE_MARKS.sub("", bare).strip()
    if clean_line in items or bare in items or plain in items:
        return False
    # ⚠️ Имя, защищённое ЦЕЛИКОМ (NPC, локация, бренд), работой не является:
    # это решение не переводить, а не пропуск. Отсев уже стоял в разборе колонок
    # полосы, но не в общем счёте — и «Elle», «Foxy», «Vargul» попадали в список
    # работы наравне с настоящими промахами (55 строк на замере 01.08).
    #
    # ⚠️ Сравниваем строку ЦЕЛИКОМ, а не по вхождению слова: вхождением проект
    # обжигался дважды («Gems» внутри «Gemstones», «Heat» внутри «Heat
    # Resistance»). Двойственные слова («Bank», «Farm», «Village») в защиту
    # не входят намеренно — см. protected.AMBIGUOUS, — и здесь останутся.
    return plain.lower() not in guarded_names()


@functools.lru_cache(maxsize=1)
def guarded_names() -> frozenset[str]:
    """Имена, которые мы не переводим по замыслу: локации, NPC, валюты, бренды."""
    try:
        from protected import collect
        return frozenset(name.lower() for name in collect())
    except (ImportError, OSError):
        return frozenset()


def uncovered_columns(line: str, dic: Dictionaries, items: set[str],
                      source: str = "action_bar") -> list[str]:
    """
    Непереведённые КОЛОНКИ полосы над хотбаром.

    Полоса собрана колонками через несколько пробелов, и мод переводит каждую
    отдельно (TextTranslator.translateColumns). Считать всю строку
    непереведённой из-за одной колонки — то же завышение: в середине там стоит
    название локации или события, которое мы не переводим.

    ⚠️ Отсев защищённых имён сравнивает колонку ЦЕЛИКОМ, а не по вхождению
    слова. Вхождением проект уже обжигался дважды: «Gems» находилось внутри
    «Gemstones», а sb_stats утаскивал подпись «Heat Resistance» из-за слова
    «Heat». Целая колонка «◇ Trials of Fire» — это название события, а вот
    строка, где имя лишь упомянуто, переводиться обязана.

    ⚠️ Правило примеряем через общий `rule_hit`, а не своей проверкой. Здесь
    стояла вторая копия, и она была слепа к обобщению: колонка приходит
    из дампа как «+{n} Foraging ({n}/{n}k)», а правило писано под живое число.
    Отчёт держал её ПЕРВОЙ строкой работы с 750 показами — при том, что
    правило с `tg` переводит её целиком.

    ⚠️ ДВОЙСТВЕННОЕ СЛОВО В ПОЛОСЕ ДВОЙСТВЕННЫМ НЕ БЫВАЕТ — и это ОБЛАСТЬ,
    а не пополнение списка. Общая защита нарочно не берёт `Village`,
    `Mountain`, `The Barn` (`protected.AMBIGUOUS`): по-русски это и место,
    и обычное слово, и защитив их, мы сломали бы прозу. Но колонку полосы
    целиком занимает МЕТКА ЛОКАЦИИ — второго смысла у неё там нет, — поэтому
    в этой области сверяемся со ВСЕМ списком мест с вики (275 названий).
    Тот же приём, что «цвет — признак имени ТОЛЬКО В ЧАТЕ».

    Замер 01.08: «◇ Village» держало первую строку отчёта с 242 показами —
    91% всего раздела, — и настоящей работы за ним было не видно.

    ⚠️ Область проверяется по ИСТОЧНИКУ, а не по виду строки. Раздел колонок
    считается для любой строки с двойным пробелом, и туда попадает чат:
    варианты ответа диалога («➜ [Nah.]») и вопросы викторины Hypixel про
    безопасность. Там «Village» осталось бы обычным словом, и отсев по месту
    был бы неверен.
    """
    parts = [part for part in COLUMNS.split(clean(line)) if part.strip()]
    guarded = guarded_names()
    places = bar_places() if source == "action_bar" else frozenset()
    left = []
    for part in parts:
        probe = clean(part)
        if probe in dic.exact or NUMBER.sub("{n}", probe) in dic.templates:
            continue
        if rule_hit(probe, dic)[0]:
            continue
        # значок Hypixel («◇ Village») именем не является — снимаем его,
        # как это уже делает worth_counting для маркеров списка
        bare = LIST_MARK.sub("", probe).strip()
        if bare.lower() in guarded or bare.lower() in places:
            continue
        if worth_counting(part, "action_bar", items):
            left.append(probe)
    return left


@functools.lru_cache(maxsize=1)
def bar_places() -> frozenset[str]:
    """
    Названия мест для КОЛОНКИ ПОЛОСЫ — берём у protected, копии не заводим.

    Список живёт в `data/work/places_wiki.json`, и читает его `protected.py`.
    Вторая копия чтения разошлась бы с первой при первом же пополнении —
    в этом проекте копии признаков расходились трижды, и всякий раз молча.
    """
    try:
        from protected import wiki_places
        return wiki_places()
    except (ImportError, OSError):
        return frozenset()


def show_by_layer(rows: list[tuple[int, str, str]], limit: int) -> int:
    """
    Разложить «НЕТ НИГДЕ» по слоям и показать списком ТОЛЬКО настоящую работу.

    ⚠️ Зачем. Раздел стоит первым в работе новой сессии, и 01.08 в нём лежало
    1144 строки, из которых работой не была НИ ОДНА: наборы зачарований
    (sb_enchants выключен решением), варианты предметов со звёздами, обрывки
    фраз, имена NPC. Настоящий промах в таком списке не разглядеть, а отчёт,
    показывающий наши РЕШЕНИЯ бедой, приучает в него не смотреть — это уже
    записанная беда, стоившая проекту двух вечеров на scan.py и scan_all.py.
    Числа при этом не прячем: каждый слой печатается своей строкой.

    ⚠️ Слои спрашиваем у `pick_queue.classify`, а не пишем заново: он отбирает
    то, за что СТОИТ платить, и признаки в нём выверены на живой очереди.
    Копия признака в этом проекте расходилась с оригиналом трижды, и всякий
    раз молча. Импорт ленивый — `pick_queue` сам импортирует `status`,
    и на верхнем уровне вышел бы круг.
    """
    try:
        from pick_queue import classify
        import terms
        enchants = {name.lower() for name in terms.of("enchant")}
    except (ImportError, OSError):
        for times, source, line in rows[:limit]:
            print(f"   {times:5}x [{source}] {show(line)}")
        return len(rows)

    layers: dict[str, list[tuple[int, str, str]]] = collections.defaultdict(list)
    for times, source, line in rows:
        layers[classify(clean(line).strip(), enchants)].append((times, source, line))

    # почему слой НЕ работа — говорим прямо, иначе число выглядит долгом
    why = {
        "зачарование": "решение игрока: sb_enchants выключен, наборов бесконечно много",
        "обрывок": "полфразы от переноса — покупать вредно, лечится абзацем",
        "техническое": "ники, адреса серверов, метки",
        "жаргон": "terms.STAT_JARGON — остаётся английским по решению",
    }
    for name, group in sorted(layers.items(), key=lambda kv: -len(kv[1])):
        if name == "покупка":
            continue
        print(f"   {len(group):5}  {name} — {why.get(name, '')}")

    work = layers.get("покупка") or []
    print(f"   {len(work):5}  ПОКУПКА — вот это и есть работа")
    for times, source, line in work[:limit]:
        print(f"        {times:4}x [{source}] {show(line)}")
    if len(work) > limit:
        print(f"        ... ещё {len(work) - limit}")
    return len(work)


def survey(dic: Dictionaries, queue: dict, corpus: dict, limit: int) -> int:
    """Сводка по живому дампу: чего не хватает, по важности."""
    collected = DUMP / "collected.json"
    if not collected.exists():
        print(f"нет дампа: {collected}")
        return 1
    data = json.loads(collected.read_text(encoding="utf-8"))
    sources = data.get("sources") or {}

    # ⚠️ Имена предметов не переводим ПО ЗАМЫСЛУ, а список игроков и надписи над
    # головами — это ники. Считать их «непереведёнными» значит завышать беду
    # втрое: именно так метрика покрытия однажды показала 25% вместо правды.
    skip_sources = {"item_name", "tab", "name_tag"}

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from protected import real_items
        items = real_items()
    except (ImportError, OSError):
        items = set()

    buckets: dict[str, list[tuple[int, str, str]]] = collections.defaultdict(list)
    columns: collections.Counter = collections.Counter()
    col_source: dict[str, str] = {}
    jargon_left = 0
    for source, entries in sources.items():
        if source in skip_sources:
            continue
        for line, count in entries.items():
            times = count if isinstance(count, int) else 1
            if not worth_counting(line, source, items):
                continue
            # строка, разделённая двойным пробелом: считаем КУСКИ, а не её целиком
            if COLUMNS.search(clean(line)):
                for part in uncovered_columns(line, dic, items, source):
                    columns[part] += times
                    col_source.setdefault(part, source)
                continue
            answer = verdict(line, dic, queue, corpus)
            # ⚠️ JARGON тоже пропускаем: это решение оставить строку английской,
            # а не работа. Показывать её в списке «что не переведено» значит
            # звать чинить решённое — и топить в этом шуме настоящие беды.
            if answer["status"] in (OK, BY_PARAGRAPH, BY_COLUMNS, NOTHING, JARGON):
                jargon_left += answer["status"] == JARGON
                continue
            buckets[answer["status"]].append((times, source, line))

    order = [PARTIAL, QUEUED, MISSING]
    total = 0
    for status in order:
        rows = sorted(buckets.get(status, []), reverse=True)
        if not rows:
            continue
        shown = sum(times for times, _, _ in rows)
        print(f"=== {status}: {len(rows)} строк, {shown} показов ===")
        if status == PARTIAL:
            print("    Словарь знает ЧАСТЬ терминов строки, и движок нарочно"
                  " откатывает подстановку:")
            print("    половина по-русски хуже, чем честный английский."
                  " Лечится добавлением терминов.")
        elif status == QUEUED:
            print("    Уже в очереди — нужен только прогон переводчика.")
        else:
            print("    Мод показывал это на экране, но ни в очередь, ни в корпус"
                  " строка не попала.")
        if status == MISSING:
            total += show_by_layer(rows, limit)
        else:
            total += len(rows)
            for times, source, line in rows[:limit]:
                print(f"   {times:5}x [{source}] {show(line)}")
            if len(rows) > limit:
                print(f"   ... ещё {len(rows) - limit}")
        print()

    if columns:
        # ⚠️ Заголовок раньше говорил «полоса над хотбаром», и это было
        # НЕВЕРНО: по колонкам режется любая строка с двойным пробелом,
        # а такие шлёт и чат — наборы вариантов ответа («➜ [Nah.]») и вопросы
        # викторины Hypixel про безопасность. Замер 01.08: из 18 кусков
        # раздела к полосе относился ОДИН, остальные 17 пришли из чата.
        # Отчёт называл источник неверно и уводил искать беду не туда.
        print(f"=== КУСКИ строк, разделённых пробелами, без перевода: {len(columns)} ===")
        print("    Так собрана полоса над хотбаром и наборы вариантов в чате —"
              " мод переводит каждый кусок отдельно.")
        print("    Тут только те, что не нашлись; источник указан в скобках.")
        for part, times in columns.most_common(limit):
            print(f"   {times:5}x [{col_source.get(part, '?')}] {show(part, 60)}")
        if len(columns) > limit:
            print(f"   ... ещё {len(columns) - limit}")
        print()
        total += len(columns)

    if jargon_left:
        print(f"=== оставлено английским по решению: {jargon_left} строк ===")
        print("    Жаргон из terms.STAT_JARGON — все *Fortune и *Wisdom,"
              " Magic Find, Pristine и прочее.")
        print("    Это НЕ работа: перевод для них лежит в выключенном sb_stats."
              " Захотим перевести всё — включим его.")
        print()

    if not total:
        print("мод переводит всё, что собрал")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Состояние строки: перевод, очередь или ничего")
    parser.add_argument("lines", nargs="*", help="строки с экрана")
    parser.add_argument("--limit", type=int, default=15, help="сколько показывать в разделе")
    args = parser.parse_args()

    dic = Dictionaries()
    queue = load_queue()
    corpus = load_corpus()
    print(f"словари: {len(dic.exact)} точных, {len(dic.templates)} шаблонов, "
          f"{len(dic.rules)} правил, {len(dic.glossary)} терминов, "
          f"{len(dic.paragraphs)} абзацев")
    for name in dic.skipped:
        print(f"  не учитываю: {name}")
    print(f"очередь строк: {len(queue['waiting'])} ждут, {len(queue['asis'])} «нечего»")
    print(f"корпус абзацев: {len(corpus['waiting'])} ждут, {len(corpus['nothing'])} «нечего»")
    print()

    if args.lines:
        for raw in args.lines:
            one_line(raw, dic, queue, corpus)
        return 0
    return survey(dic, queue, corpus, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
