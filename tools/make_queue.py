"""
Очередь на перевод для строк, которые НЕ абзацы: чат, меню, панель.

Зачем отдельный инструмент. `merge_dump.py` сваливает всё непереведённое
в один плоский файл — 10887 записей без источника и без частоты. Переводить
это целиком нельзя и не нужно:

  item_name (2909)   названия предметов, их не переводят ПО ЗАМЫСЛУ —
                     по ним ищут на аукционе;
  item_lore (8626)   описания, их закрывают абзацы и шаблоны;
  action_bar         полоса над хотбаром переводится ПО КОЛОНКАМ, целой
                     строки в словаре быть не должно вовсе.

Остаётся то, что действительно требует перевода строкой целиком: чат, экраны
меню, боковая панель, список игроков, заголовки, полоса босса.

Строки идут ПО УБЫВАНИЮ ЧАСТОТЫ — как и корпус абзацев, чтобы `--limit`
покупал самое ходовое, а не случайное.

Запуск:
  python tools/make_queue.py
  python tools/make_queue.py --sources chat screen
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pkey  # noqa: E402

DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")
OUT = ROOT / "data" / "work" / "from_game.json"

# ⚠️ АРХИВ ПЕРЕВОДОВ — не то же самое, что файл очереди.
#
# Очередь ПЕРЕСОБИРАЕТСЯ: состав строк берётся заново из дампа, а готовые
# переводы подхватываются из неё же самой. Значит стоит строке на одном
# прогоне выпасть из дампа — перевод уходит вместе с ней, и взять его негде.
# Ровно так пропало вписанное руками «Pristine Procs: {n}»: ключ исчез
# из очереди целиком, а следующая пересборка вернула его с ПУСТЫМ значением.
#
# Архив живёт отдельно и составом очереди НЕ чистится: он только пополняется.
# Вернулась строка в дамп — перевод найдётся здесь и встанет на место.
# У корпуса абзацев такая защита есть с самого начала (make_paragraphs
# переносит `ru` и `nothing` по ключу), у очереди её не было.
ARCHIVE = ROOT / "data" / "work" / "queue_archive.json"

# Что переводим строкой целиком. Порядок = приоритет при равной частоте.
WORTH = ["chat", "screen", "scoreboard", "tab", "title", "boss_bar", "item_lore"]

# Названия предметов и полосу над хотбаром не берём ВООБЩЕ:
# первые не переводятся по замыслу, вторую мод переводит по колонкам.
NEVER = {"item_name", "action_bar"}

# Список зачарований через запятую — его держат правила, а не точные записи
ENCHANT_LIST = re.compile(
    r"^[A-Z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*){0,3} [IVXLC]{1,6}"
    r"(?:, [A-Z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*){0,3} [IVXLC]{1,6})+,?$")

# Одиночная характеристика: её закрывает tools/gen_stat_forms.py
# ⚠️ Значение обязано начинаться с ЦИФРЫ или с дырки {n}.
#
# Было «[\d,.]+», а этот класс допускает строку ИЗ ОДНОЙ ТОЧКИ — значит любое
# предложение из букв, начатое с заглавной и законченное точкой, считалось
# «строкой характеристики» и молча выбрасывалось из очереди. На живом дампе
# так пропали 824 строки: «Straight from the spider's mouth.», «You don't have
# any coins to claim.», «Donate Spider Sword to your Museum.» — их не переводили
# НИ РАЗУ, и не потому что не дошли руки, а потому что инструмент их не показывал.
# Проверено: настоящие характеристики («Health: +293 (+40)», «Defense: +100»,
# «Health: +{n} (+{n})») ловятся по-прежнему, ни одна не потерялась.
STAT_LINE = re.compile(r"^[ -￿]? ?[A-Z][A-Za-z' ]+:? ?[+\-]?(?:\d[\d,.]*|\{n\})%?")

# Строка целиком из чисел, знаков и подстановок — переводить нечего
ICONS = re.compile(r"[-]")

NOTHING_TO_DO = re.compile(r"^[\W\d\s]*$")

# ⚠️ Ник игрока с боковой панели. Мод обобщает ник до {s} только когда перед
# ним стоит ранг («[VIP] Usairim»), а голый ник в начале строки — нет. Значит
# КАЖДЫЙ новый игрок плодит «уникальную непереведённую строку», и в очередь
# их набежало 899 из 999 остатка. Переводить их нельзя и не нужно.
#
# Признак: одно слово без пробелов, в котором есть цифра, подчёркивание,
# заглавная В СЕРЕДИНЕ или просто длина больше двенадцати. У настоящих
# надписей панели («Ruins», «Bank», «Arcade Games») такого не бывает.
#
# Ник вида «Axototel» так не поймать — он выглядит обычным словом. Это
# осознанный предел: такие доедут до модели, она вернёт их без изменений,
# и они отсеются как «переводить нечего». Стоит это копейки, а гнаться
# за полнотой признака здесь значит начать выбрасывать настоящие надписи.
NICKNAME = re.compile(
    r"^(?:[A-Za-z]*[\d_]|[A-Za-z]+\{n\}|[A-Za-z][a-z]+[A-Z]|[A-Za-z]{13,})[A-Za-z\d_{}n]*$")


# Запись СПИСКА ИГРОКОВ на панели: «[123] Ник», «Ник [GUILD]», «Ник ✿».
# Их набежало 837 из 947 строк панели — то есть панель почти целиком занята
# людьми, а не текстом. Мод обобщает ник до {s} только при ранге впереди
# («[VIP] Usairim»), поэтому каждый новый игрок плодит «уникальную строку».
#
# ⚠️ ТЕГ ГИЛЬДИИ пишут как хотят, и «[A-Z]{2,6}» его не описывает. В живом
# дампе: «[CHIMKAN]» (семь букв), «[S]» (одна), «[✿UHG✿]» и «[NOVERA❤]»
# (значки), «[A{n}]» (цифра, обобщённая модом). Семь таких строк дошли
# до очереди и попросили денег за перевод чужих ников — а гильдий столько,
# сколько их создали игроки, то есть список пополнялся бы вечно.
# Поэтому после «{s} » берём ЛЮБОЙ тег: перед скобкой уже стоит обобщённый
# ник, а надпись панели с ника не начинается.
PLAYER_ROW = re.compile(
    r"^(?:\[\{n\}\]|\[\d+\])\s*\S+|^\S+\s+\[[A-Z]{2,6}\]$|^\{s\}\s+\[[^\]]{1,12}\]$")

# Дата и номер сервера в подвале панели: «07/25/26 m12AB». Букв там всего
# пара, и те — идентификатор, а не слово. Таких набежало 41: каждый новый
# сервер плодит «уникальную непереведённую строку», ровно как ники.
SERVER_LINE = re.compile(r"^\{n\}/\{n\}/\{n\}\s+[a-zA-Z]?\{n\}[A-Z]{0,3}$")

# «Oak Log x{n}» — название предмета со счётчиком. Названия не переводим.
ITEM_COUNT = re.compile(r"^[A-Z][A-Za-z' ]+ x\{n\}$")


def nick_free(line: str) -> str:
    """Строка с чужим ником, обобщённым в «{s}».

    ⚠️ Ленивый импорт: `check_nicknames` сам тянет `protected`, а тот —
    рабочие файлы. Наверху это замкнуло бы круг импортов.
    """
    try:
        import check_nicknames
    except ImportError:
        return line
    return check_nicknames.generalized(line)


def worth_translating(line: str, source: str) -> bool:
    """Строку вообще есть смысл отдавать модели?"""
    if NOTHING_TO_DO.match(line):
        return False
    if PLAYER_ROW.match(line) or ITEM_COUNT.match(line) or SERVER_LINE.match(line):
        return False
    if " " not in line:
        # ⚠️ Одно слово на боковой панели — это НИК. Проверено: из 100 таких
        # ни одного настоящего текста. А названия мест, которые там тоже
        # бывают одним словом, мы и так не переводим.
        if source == "scoreboard":
            return False
        if NICKNAME.match(line):
            return False
    # ⚠️ СПИСОК ГОСТЕЙ: «- Ник» одним словом. Записанная открытая грабля —
    # структурный признак ников такую форму не ловил, и чужие имена уезжали
    # в ПЛАТНУЮ покупку. Замер 08.08 по данным от игроков: 16 таких строк
    # из 104 отобранных.
    #
    # ⚠️ Отсеиваем, а не обобщаем: «- {s}» переводить не во что, это просто
    # ник в столбце. Обобщение полезно там, где вокруг ника есть ТЕКСТ
    # («RARE REWARD! {s} found …»), а здесь текста нет вовсе.
    #
    # ⚠️ Пробел в остатке разделяет ник и ПРЕДМЕТ: «- Melon Juice ({n}/{n})» —
    # ингредиент рецепта, его переводить надо. Поэтому берём только строки
    # без пробелов после дефиса.
    if GUEST_ROW.match(line):
        return False
    return True


# «- Ник» из списка гостей: дефис, пробел и ОДНО слово (цифры в нике уже
# обобщены в «{n}», поэтому фигурные скобки тоже допустимы).
GUEST_ROW = re.compile(r"^-\s+[A-Za-z0-9_{}]{3,20}$")


# Знак списка в начале строки — тот же признак, по которому мод отказывается
# склеивать список (ColorLayout.repeatedMarker).
#
# ⚠️ Набор ОБЯЗАН совпадать с `ColorLayout.CHOICE_MARKS`, и он уже разъезжался:
# здесь не было «✖», «◆» и «»». Замер на корпусе — 130 абзацев (527 строк),
# которые мод списком считает, а очередь не считала: их строки не попадали
# в очередь как «закрытые абзацем», а сам абзац на экран не выкладывался.
# У 108 из них перевод был КУПЛЕН и лежал мёртвым грузом — игрок видел
# английский текст, за который заплачено.
#
# Это ровно та беда, что уже записана в граблях («строки списка выпадали МЕЖДУ
# двумя системами»), и чинили её тогда добавлением этой самой строки. Но набор
# знаков ВЫПИСАЛИ ЗАНОВО вместо того, чтобы сверить с модом, — и он разошёлся
# снова, молча. Сторожит теперь `check_contract.py`.
#
# ⚠️ Значков приватной зоны (❈ ⚔ ☘) тут нет НАМЕРЕННО, хотя мод их тоже считает
# списочными. У него для них порог выше (4 строки против 3), потому что ими
# начинается обычная проза про характеристики. Взяв их без порога, мы объявили
# бы несписком кучу описаний и отправили их строки в очередь — то есть платили
# бы за то, что и так закрыто абзацем. Ошибаться тут лучше в эту сторону:
# лишняя строка в очереди стоит копейки, пропавшая не найдётся никак.
LIST_MARK = re.compile(r"^[▶▸➤✔✖◼◆‣•▪»○✓⋗⁍]")


def in_paragraphs(known_keys: set[str] = frozenset(),
                  keep: dict[str, str] | None = None) -> set[str]:
    """
    Строки лора, которые уже закрыты корпусом абзацев.

    ⚠️ Обратное неверно: НЕ каждая строка лора попадает в абзацы. Кусок, рядом
    с которым стоит строка-характеристика, в корпус не берётся вовсе — иначе
    перенос размазал бы таблицу в прозу. А в очередь построчного перевода лор
    тоже не брали, считая, что «его закрывают абзацы». Такие строки проваливались
    между двумя системами: на живом дампе их 2532, и «Multiple sacks sum their
    capacity!» — как раз одна из них.

    @param known_keys ключи абзацев, перевод которых есть у мода. Нужны для
                      блока зачарований: он закрывается ПОСЕКЦИОННО, и знать,
                      какая секция переведена, можно только по словарю.
    @param keep       строки, за перевод которых УЖЕ заплачено. Закрытыми их
                      не объявляем: новое покупать не надо, но и выбрасывать
                      оплаченное незачем — построчный перевод остаётся
                      подстраховкой на случай, когда у игрока другая ширина
                      подсказки и абзац разрезан иначе.
    """
    path = ROOT / "data" / "work" / "paragraphs.json"
    if not path.exists():
        return set()
    lines: set[str] = set()
    for para in json.loads(path.read_text(encoding="utf-8")).get("paragraphs") or []:
        rows = para.get("lines") or []
        # ⚠️ Абзац-СПИСОК мод не склеит НИКОГДА (ColorLayout бережёт структуру),
        # значит его перевод до экрана не дойдёт, и строки надо переводить
        # построчно. Считая их «закрытыми», мы теряли их дважды: абзац не
        # применяется, а в очередь они не попадают — так «Highest Price»
        # и «Ending soon» остались английскими при купленном переводе.
        if any(LIST_MARK.match(str(row).strip()) for row in rows):
            continue
        # ⚠️ У списка знаки бывают РАЗНЫЕ у каждого пункта, и LIST_MARK их
        # не знает: Hypixel помечает крючок, леску и грузило удочки тремя
        # разными буквами чужих алфавитов. Мод такой абзац не склеивает
        # (ColorLayout: «у каждой строки свой знак»), а очередь считала строки
        # закрытыми — и оплаченный перевод исчезал при первой же пересборке.
        # Игрок присылал эту удочку трижды.
        if pkey.every_line_marked(rows):
            continue
        # ⚠️ БЛОК ЗАЧАРОВАНИЙ закрывается ПОСЕКЦИОННО, а не целиком или никак.
        #
        # Такой абзац склеивается из НАБОРА, который стоит на предмете:
        # «Bank V + Growth VI + Protection VI» — один ключ, «Bank V + Aqua
        # Affinity I + Growth V» — уже другой. Наборов столько, сколько игроки
        # собрали, поэтому целиком абзац почти никогда не совпадёт.
        #
        # Раньше отсюда следовал вывод «считать блок незакрытым и переводить
        # построчно», и он был верен — ПОКА мод не умел резать абзац сам.
        # Теперь умеет: `Paragraphs.bySections` делит абзац по заголовкам
        # и ищет перевод КАЖДОЙ секции отдельно. Значит секция с переводом
        # до экрана доходит, и платить за её строки второй раз незачем,
        # а секция без перевода честно идёт в очередь.
        #
        # Замер по живому дампу: 716 абзацев с заголовками зачарований,
        # секций с описанием закрыто 62, не закрыто 7 разных (20 вхождений).
        # Считая блок незакрытым целиком, очередь просила купить строки,
        # которые на экране уже по-русски.
        heads = [i for i, row in enumerate(rows)
                 if ENCHANT_HEAD.match(str(row).strip())]
        if len(heads) >= 2:
            paid = keep or {}
            if pkey.key_of(rows) in known_keys:
                lines.update(row for row in rows if not paid.get(str(row)))
                continue
            for h, start in enumerate(heads):
                end = heads[h + 1] if h + 1 < len(heads) else len(rows)
                # ⚠️ Ключ секции строим ТЕМ ЖЕ pkey, что и мод, — иначе
                # «закрыто» здесь и «нашлось» там разойдутся молча.
                if pkey.key_of(rows[start:end]) in known_keys:
                    lines.update(row for row in rows[start:end]
                                 if not paid.get(str(row)))
            continue
        lines.update(rows)
    return lines


# Строка-заголовок зачарования: имя и римский уровень, больше ничего.
# Копия признака из Paragraphs.ENCHANT_HEAD — засчитывается только при ДВУХ
# и более таких строках в абзаце, иначе под него попадают имена предметов
# («Sheep Minion I» неотличим от «Sharpness I»).
ENCHANT_HEAD = re.compile(r"^[A-Z][A-Za-z' -]*\s[IVXLC]+$")


def already_translated() -> tuple[set[str], list, list]:
    """
    Строки, для которых перевод УЖЕ есть в словарях мода.

    ⚠️ Без этой проверки очередь предлагала перевести заново то, что переведено
    год назад, — и модель, понятно, писала иначе. В словаре оказывались две
    записи на одну строку: «Кошелёк: §6{n}» с цветом и «Кошелёк: {n}» без него.
    Побеждает та, у которой приоритет выше, то есть исход зависел от номера
    файла, а не от качества. Деньги за такой перевод тоже платятся дважды.

    ⚠️ **ВЫКЛЮЧЕННЫЙ словарь — это решение НЕ ПЕРЕВОДИТЬ, а не отсутствие
    перевода.** Инструменты считали его «неучтённым», и строка уходила в очередь
    как непереведённая: `Lapidary V` перевели вторично в 90-from-game.json,
    где выключателя нет, — и на дрели появилась «Огранка V», хотя игрок
    кастомные зачарования отключил. Поэтому у переключаемых словарей
    (`"default": false`) берём ВСЁ: exact, paragraphs, весь глоссарий и ШАБЛОНЫ.
    Раньше из глоссария брались только «@»-записи (ванильные названия), а секция
    regex не читалась вовсе — а `sb_enchants` держит зачарования именно в ней.

    ⚠️ **А у ВКЛЮЧЁННЫХ словарей секция regex не читалась ВООБЩЕ, и это та же
    беда с другой стороны.** Правил там 1984, и очередь их не видела ни одного:
    из 144 «ждущих перевода» строк 139 уже переводились правилами
    (`Progress to Milestone XXV`, `Your Wither Essence`, `Blocks Mined`).
    Тихо это потому, что счётчик очереди выглядит осмысленно, а проверить его
    можно было только прогнав каждую строку через `status.py` руками.

    Цена не в одних деньгах ($0.21 за прогон, и так каждый раз). Купленный
    вторично перевод ложится в `90-from-game.json` секцией `exact`, а движок
    ищет `exact` РАНЬШЕ правил (`Translator.lookup`) — и перебивает их
    независимо от priority. То есть семья, аккуратно закрытая одним правилом,
    разъезжается обратно на отдельные записи, переведённые в разные вечера
    и разными словами.

    @return точные строки, шаблоны ВЫКЛЮЧЕННЫХ словарей, правила ВКЛЮЧЁННЫХ
    """
    packs = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
    known: set[str] = set()
    guarded: list = []
    covered: list = []
    for path in packs.rglob("*.json"):
        # ⚠️ СВОЙ ЖЕ словарь (90-from-game) не читаем ВООБЩЕ, даже ради шаблонов.
        #
        # Пробовал брать оттуда записи с дырками — «движок ведь строит из них
        # правило, пусть очередь тоже видит». Итог: 1096 переводов выпали
        # из словаря за один прогон. Шаблон, собранный из очереди, накрывает
        # СОСЕДНИЕ записи той же очереди («+{n} SkyBlock XP», «You have {n}
        # material stashed away!»), они объявляются закрытыми, выпадают
        # из состава — и export_pack уносит их из словаря.
        #
        # Ради одной строки «This gift is for JustMrwxw, sorry!» такое не
        # делается: пусть лучше она лишний раз побудет в очереди.
        if path.name in ("index.json", "90-from-game.json"):
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        known.update(k for k, v in (pack.get("exact") or {}).items() if v)
        known.update(k for k, v in (pack.get("paragraphs") or {}).items() if v)
        optional = pack.get("default") is False
        # ⚠️ Ванильные названия (значение вида «@block.minecraft.anvil») живут
        # в ПЕРЕКЛЮЧАЕМОМ словаре и подчиняются его выключателю. Переведи такое
        # слово ещё и в общем словаре — и выключатель перестанет работать:
        # игрок отключил перевод ванильных названий, а наковальня всё равно
        # русская. Фильтр читал только exact, а этот словарь хранит записи
        # в glossary — так «Наковальня» и просочилась дважды.
        known.update(k for k, v in (pack.get("glossary") or {}).items()
                     if isinstance(v, str) and (optional or v.startswith("@")))
        if not optional:
            # ⚠️ ТОЧНАЯ ЗАПИСЬ С ДЫРКОЙ — это тоже правило, просто движок
            # собирает его сам при загрузке (`Translator.templateRule`).
            # Очередь же сверяла такие записи буквально, и строка с настоящим
            # ником («…Season of Jerry, Player_123!») не совпадала с шаблоном
            # («…Season of Jerry, {s}!») — то есть просилась в перевод, хотя
            # на экране уже русская. Повторяем движок, а не сверяем по-своему.
            for key, value in (pack.get("exact") or {}).items():
                if not value or not HOLES.search(key):
                    continue
                pattern = ""
                last = 0
                for hole in HOLES.finditer(key):
                    pattern += re.escape(key[last:hole.start()])
                    pattern += NAME_HOLE if hole.group() == "{s}" else NUMBER_HOLE
                    last = hole.end()
                pattern += re.escape(key[last:])
                try:
                    covered.append(re.compile("^" + pattern + "$"))
                except re.error:
                    continue
            # ⚠️ Правило с «tg» переводит захваченный кусок по словарю, и если
            # куска там нет — на экране выйдет смесь языков, то есть строку
            # всё-таки надо переводить. Раньше отсюда следовал вывод «такие
            # правила закрывающими не считать вовсе», и он был ОСТОРОЖНЫМ,
            # но неверным: опасение проверялось рассуждением, а не данными.
            #
            # Замер 31.07 по живой очереди: из 49 строк, закрытых tg-правилами,
            # чистый перевод дают 48 («Ням-ням! Ты обновил +{n} Ferocity
            # на {n} ч.!», «Нужен навык Фермерство {n}.»), и лишь одна выглядит
            # смесью — «Нужна ступень Heart of the Forest {n}», где латиницей
            # осталось ЗАЩИЩЁННОЕ имя локации, то есть ровно как задумано.
            # Отбрасывая их скопом, очередь просила деньги за сделанное.
            #
            # Поэтому решение принимается ПО ФАКТУ: правило разворачивается
            # с переводом захватов, и строка считается закрытой, только если
            # смеси не вышло (`covered_by_rule`). Осторожность при этом
            # сохранена — сомнительная строка остаётся в очереди, а лишняя
            # строка в очереди стоит копейки, тогда как пропавшая не найдётся
            # ничем (на этом проект уже потерял 1639 строк).
            #
            # ⚠️ ИСКЛЮЧЕНИЕ: правило, помеченное «toggle», закрывает строку
            # без всякой проверки. У уровней коллекций («Bone V», «Coal VII»)
            # захват — ванильное имя, а ванильные названия лежат в ПЕРЕКЛЮЧАЕМОМ
            # словаре, выключенном по решению игрока. Значит строка останется
            # английской целиком, ровно как решено; проверять там нечего.
            # Пометку ставит генератор правила, а не догадка по виду шаблона.
            for rule in pack.get("regex") or []:
                if not rule.get("r"):
                    continue
                try:
                    pattern = re.compile(rule.get("p", ""))
                except re.error:
                    continue
                if rule.get("tg") and not rule.get("toggle"):
                    covered.append(TgRule(pattern, rule.get("r", "")))
                else:
                    covered.append(pattern)
            continue
        for rule in pack.get("regex") or []:
            try:
                guarded.append(re.compile(rule.get("p", "")))
            except re.error:
                continue
    return known, guarded, covered


def guarded_by_toggle(line: str, guarded: list) -> bool:
    """Закрыта ли строка ВЫКЛЮЧЕННЫМ словарём — тогда переводить её не надо."""
    return any(rule.search(line) for rule in guarded)


# Образцы для дырок: в дампе числа уже обобщены в «{n}», а правила писаны под
# НАСТОЯЩУЮ строку — движок применяет их до обобщения. Чтобы сравнивать то же,
# что сравнит игра, дырки заполняем правдоподобным значением.
# ⚠️ Ник с рангом: «[VIP] Matthewthe69». Голый ник под шаблон {s} тоже подходит,
# но проверять надо тот вид, который Hypixel шлёт чаще, иначе правило с рангом
# покажется несовпадающим.
HOLE_NUMBER = "1,234"
HOLE_NAME = "[VIP] Player"

# Дырки в точных записях и то, чем их подменяет движок. Группы взяты
# из Translator.NAME_GROUP и NUMBER_GROUP — копия признака, но иначе
# очередь не повторит поведение мода.
HOLES = re.compile(r"\{[ns]\}")
NAME_HOLE = r"((?:\[[A-Za-z+]{2,10}\]\s*)?[A-Za-z0-9_]{3,16})"
NUMBER_HOLE = r"([\d,.]+)"


class TgRule(NamedTuple):
    """
    Правило с «tg»: захваченные куски переводятся по словарю.

    Хранится отдельно от обычных, потому что совпадения шаблона тут НЕ ХВАТАЕТ.
    Закрыта ли строка, видно только по результату: если словарь знает захват,
    на экране чистый русский, а если нет — смесь языков, и строку надо
    переводить. Проверяет `covered_by_rule`.
    """
    pattern: re.Pattern
    replacement: str


_ENGINE: tuple | None = None


def _engine():
    """
    Движок глазами `status.py` — словари в порядке перебора мода.

    ⚠️ Импорт ЛЕНИВЫЙ и это важно: `status` сам берёт у нас образцы дырок
    (`HOLE_NUMBER`, `HOLE_NAME`), и импорт на верхнем уровне замкнул бы круг.
    Своей копии разворачивания правил здесь не заводим намеренно: копия
    признака в этом проекте расходилась с движком трижды, и каждый раз молча.
    """
    global _ENGINE
    if _ENGINE is None:
        import status
        _ENGINE = (status, status.Dictionaries())
    return _ENGINE


def tg_closes(rule: TgRule, line: str, probe: str) -> bool:
    """
    Закрывает ли tg-правило строку — по РЕЗУЛЬТАТУ, а не по совпадению.

    Смесь языков считаем незакрытой строкой: пусть лучше она лишний раз
    побудет в очереди, чем станет невидимой для всех отчётов сразу.
    """
    match = rule.pattern.fullmatch(line) or rule.pattern.fullmatch(probe)
    if not match:
        return False
    try:
        status, dictionaries = _engine()
    except Exception:
        return False
    out: list[str] = []
    text, position = rule.replacement, 0
    while position < len(text):
        symbol = text[position]
        if symbol == "$" and position + 1 < len(text) and text[position + 1].isdigit():
            number = int(text[position + 1])
            position += 2
            if 1 <= number <= match.re.groups and match.group(number) is not None:
                out.append(status.translate_group(match.group(number), dictionaries))
            continue
        out.append(symbol)
        position += 1
    result = "".join(out)
    return status.latin_words(result) <= status.cyrillic_words(result)


def covered_by_rule(line: str, covered: list) -> bool:
    """
    Переводится ли строка ПРАВИЛОМ включённого словаря.

    ⚠️ Совпадение проверяется ЦЕЛИКОМ (`fullmatch`), как в движке
    (`Translator.lookup` зовёт `matcher.matches()`). Поиск внутри строки
    (`search`, как у `guarded_by_toggle`) тут неверен: там речь о глоссарии,
    который подставляет термин ВНУТРЬ, а правило либо берёт строку целиком,
    либо не берёт вовсе.

    ⚠️ Список `covered` разнороден: обычные правила лежат скомпилированным
    шаблоном, а правила с «tg» — записью `TgRule`, потому что у них решает
    результат. Чужие списки (у `merge_tooltips` он свой) состоят из одних
    шаблонов и работают как раньше.
    """
    probe = line.replace("{n}", HOLE_NUMBER).replace("{s}", HOLE_NAME)
    for rule in covered:
        if isinstance(rule, TgRule):
            if tg_closes(rule, line, probe):
                return True
            continue
        if rule.fullmatch(line) or rule.fullmatch(probe):
            return True
    return False


STAT_LABEL = re.compile(r"^[^A-Za-z]*([A-Za-z][A-Za-z' ]*?)\s*:")

RARITY = re.compile(r"^(COMMON|UNCOMMON|RARE|EPIC|LEGENDARY|MYTHIC|DIVINE|SPECIAL"
                    r"|VERY SPECIAL|SUPREME|ADMIN|ULTIMATE)\b")
TOOLTIPS = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/tooltips.json")


# Знаки, которыми Hypixel метит ВЕЩИ: не хватает (✖), звёзды и улучшения
# («✿ Shiny Necrotic Storm's Leggings ✪✪✪✪✪➎»), уровень питомца.
ITEM_MARKS = re.compile(r"[✖✪✿➊-➓⭐★]|^\[Lvl")

# Имя ЗАЧАРОВАННОЙ КНИГИ: название зачарования и уровень АРАБСКОЙ цифрой,
# иногда диапазоном — «Angler 6», «Feast 1-5», «Critical 6-7».
ENCHANT_BOOK = re.compile(r"^([A-Z][A-Za-z' \-]+?) "
                          r"(?:\d+(?:-\d+)?|\{n\}(?:-\{n\})?)$")

_ENCHANT_NAMES: frozenset[str] | None = None


def enchant_names() -> frozenset[str]:
    """
    Названия зачарований — СПИСКОМ, а не признаком по форме.

    ⚠️ Список берётся у `terms`, где он собран из словарей и сверен с NBT
    сервера. Признак по одной лишь форме тут не годится и это уже проверено
    дорого: «Имя + уровень» ловит коллекции и миньонов («Sheep Minion I»),
    и правка, сделанная по форме, разом сломала 179 абзацев.
    """
    global _ENCHANT_NAMES
    if _ENCHANT_NAMES is None:
        try:
            import terms
            _ENCHANT_NAMES = frozenset(n.lower() for n in terms.of("enchant"))
        except Exception:
            _ENCHANT_NAMES = frozenset()
    return _ENCHANT_NAMES


def looks_like_item(line: str, headers: set[str]) -> bool:
    """Заголовок принадлежит ВЕЩИ, а не кнопке меню."""
    head = line.strip()
    if head in headers:
        return True
    # ⚠️ ЗАЧАРОВАННАЯ КНИГА — тоже вещь, и её имя переводить нельзя: по нему
    # ищут на аукционе и в базаре. Ни один прежний признак её не опознавал:
    # в меню базара у подсказки нет строки редкости, а чужие репозитории
    # не знают книг с ДИАПАЗОНОМ уровней («Feast 1-5»). Оттого 15 таких имён
    # просились в перевод, и купленный «Рыболов 6» лёг бы в 90-from-game.json,
    # у которого выключателя нет, — то есть в обход решения игрока держать
    # зачарования английскими. Ровно так уже появлялась «Огранка V».
    #
    # ⚠️ Уровень тут АРАБСКИЙ, поэтому правила `sb_enchants` (они писаны
    # под римский, «^Angler ([IVXLC]+)$») строку не ловят и выключенный
    # словарь её не закрывает.
    book = ENCHANT_BOOK.match(head)
    if book and book.group(1).lower() in enchant_names():
        return True
    # ⚠️ Знак предмета решает сам по себе: подсказка вещи бывает без строки
    # редкости (у требований «✖ Cactus Armor» её нет вовсе), и по одному
    # списку такие уезжали в перевод.
    return bool(ITEM_MARKS.search(head))


def real_item_headers() -> set[str]:
    """
    Заголовки, которые ДЕЙСТВИТЕЛЬНО принадлежат предмету, а не кнопке меню.

    ⚠️ Мод пишет в `item_name` заголовок ЛЮБОЙ подсказки, в том числе кнопки:
    «Green Thumb», «Claim All Coins», «Sell Stash Now». Очередь отсеивала их все
    как имена предметов — и категории оставались английскими рядом с
    переведённым «Столярное дело».

    Признаков два, и по отдельности каждый врёт:
      * список предметов из чужих репозиториев не знает вещей с префиксом ковки
        и звёздами («Ancient Maxor's Boots ✪✪✪») — 1669 ложных из 3383;
      * строка редкости надёжнее, но её нет у некоторых настоящих предметов.
    Поэтому берём ОБА: предмет — то, у чьей подсказки есть строка редкости,
    либо то, что знают репозитории. Всё прочее — кнопка, её переводим.
    """
    headers: set[str] = set()
    try:
        from protected import real_items, collect
        headers |= {name for name in real_items() if name}
        # ⚠️ И защищённые имена: среди заголовков попадаются NPC («Elle»),
        # питомцы («Rat») и мобы («☠ Sven Packmaster») — их переводить нельзя
        # ровно так же, как имена вещей.
        headers |= {name for name in collect() if name}
    except Exception:
        pass
    if not TOOLTIPS.exists():
        return headers
    try:
        data = json.loads(TOOLTIPS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return headers
    tips = data.get("tooltips") or data.get("cases") or data
    for tip in tips if isinstance(tips, list) else []:
        lines = tip.get("lines") or tip.get("lore") or []
        if not lines:
            continue
        body = [re.sub(r"[^A-Z ]", "", str(line)).strip() for line in lines]
        if any(RARITY.match(text) for text in body):
            headers.add(str(lines[0]).strip())
    return headers


def known_stats() -> set[str]:
    """Названия характеристик, которые мы знаем. Пустое множество — не беда."""
    try:
        from gen_stat_forms import collect_stats
        return set(collect_stats())
    except Exception:
        return set()


def is_stat_line(line: str, stats: set[str], covered: list | None = None) -> bool:
    """
    Строка характеристики — та, у которой ПОДПИСЬ есть в нашем списке.

    ⚠️ Раньше судили по одной форме «Слово: число», и под неё попадала обычная
    речь: «You earn: {n} coins», «Price paid: {n} Coins», «You have {n}
    unclaimed rewards!» На живом дампе из 963 отсеянных строк характеристиками
    были 148, а 815 — фразы, которые надо переводить. Форма одинаковая
    у обеих, поэтому признак взят по СУЩЕСТВУ: подпись сверяется со списком
    характеристик, собранным из наших же словарей.

    Если список пуст (запуск без словарей), ведём себя как раньше — по форме:
    лучше лишний раз не заплатить, чем сломать поведение молча.
    """
    if not STAT_LINE.match(line):
        return False
    if not stats:
        return True
    label = STAT_LABEL.match(line)
    if not (label and label.group(1).strip() in stats):
        return False
    # ⚠️ ПОДПИСЬ ИЗ СПИСКА — ЕЩЁ НЕ ПОВОД ВЫБРОСИТЬ СТРОКУ.
    #
    # Отбраковка держится на обещании «эту строку закроет правило из
    # gen_stat_forms». Обещание проверяемое — так и проверим. Правило ждёт
    # ЧИСЛОВОЕ значение, а Hypixel пишет после той же подписи что угодно:
    # «Ends in: {n}d», «Date: {n}nd Early Winter {n}», «Price: {n} coins»,
    # «Health: +{n} (+{n}) [+{n}] (+{n})» — квадратные скобки правило не берёт.
    #
    # Замер на живом дампе: из 115 отсеянных строк правилом закрыты 43,
    # а 72 не закрыты НИЧЕМ — они не переводились и не попадали ни в один
    # отчёт. Ровно тот случай, что записан в граблях: фильтр «переводить
    # не надо» опаснее отсутствия перевода, потому что делает строку невидимой.
    if covered:
        return covered_by_rule(line, covered)
    return True


def load(name: str) -> dict:
    path = DUMP / name
    if not path.exists():
        print(f"! нет файла: {path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def archive_read() -> tuple[dict[str, str], set[str]]:
    """Переводы и пометки «нечего», пережившие все прошлые пересборки."""
    if not ARCHIVE.exists():
        return {}, set()
    data = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    return dict(data.get("ru") or {}), set(data.get("asis") or [])


def archive_write(ru: dict[str, str], asis: set[str]) -> None:
    """
    Сохранить архив. Он ТОЛЬКО пополняется: удалять отсюда нечего, а вот
    потерять — можно навсегда, второго источника у ручного перевода нет.
    """
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE.write_text(json.dumps({
        "_comment": "Архив переводов очереди: ключ -> перевод. Пополняется при "
                    "каждой пересборке и НЕ чистится составом очереди. Нужен "
                    "потому, что from_game.json пересобирается из дампа: выпала "
                    "строка — перевод исчез бы вместе с ней. Правится руками.",
        "ru": {k: ru[k] for k in sorted(ru)},
        "asis": sorted(asis),
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", nargs="*", default=WORTH)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    collected = load("collected.json")
    sources = collected.get("sources") or {}
    if not sources:
        print("дамп пуст — поиграй и попробуй снова")
        return 1

    # Уже сделанные переводы не теряем: файл переживает пересборку очереди.
    # ⚠️ Это третье место в проекте, где скрипт мог бы затереть ручную работу,
    # и в первых двух он её затирал. Читаем старое ДО записи нового.
    out_path = Path(args["out"] if isinstance(args, dict) else args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    done: dict[str, str] = {}
    # ⚠️ Пометку «переводить нечего» переносим вместе с переводами. Её ставит
    # tools/translate_ai.py тем строкам, которые модель вернула как есть (имена
    # предметов, ники, технические метки). Потеряем её при пересборке — и все
    # они снова поедут в запрос: 472 строки за прогон, оплаченные впустую.
    asis: list[str] = []
    if out_path.exists():
        old = json.loads(out_path.read_text(encoding="utf-8"))
        done = {k: v for k, v in (old.get("exact") or {}).items() if v}
        asis = list(old.get("_asis") or [])

    # ⚠️ Архив пополняем СЕЙЧАС, до пересборки состава: то, что лежит в очереди
    # прямо сейчас, может не попасть в новый состав, и это последний момент,
    # когда перевод ещё виден. Пополнение одностороннее — архив не забывает.
    arch_ru, arch_asis = archive_read()
    was = len(arch_ru), len(arch_asis)
    arch_ru.update(done)
    arch_asis |= set(asis)
    archive_write(arch_ru, arch_asis)
    # Готовые переводы берём из архива, а не только из текущего файла: строка,
    # выпадавшая из дампа и вернувшаяся обратно, получит свой перевод назад.
    in_file = set(done)
    done = {**arch_ru, **done}
    asis = sorted(arch_asis)
    added = len(arch_ru) - was[0], len(arch_asis) - was[1]

    known, guarded, covered = already_translated()
    # ⚠️ Ключи абзацев нужны ДО фильтра: блок зачарований закрывается
    # посекционно, и какая секция переведена — знает только словарь.
    known |= in_paragraphs(known, done)
    skipped_toggle = 0
    skipped_rule = 0
    stats = known_stats()
    real_headers = real_item_headers()
    item_names = {s.strip() for s in (sources.get("item_name") or {})}
    skipped_known = 0
    # ⚠️ Имя предмета для строк лора: его переводить нельзя НИГДЕ, в том числе
    # внутри собственного описания. Иначе в одной подсказке вещь называется
    # двумя именами: заголовок «Sea Creature Chance», а под ним «Шанс морских
    # существ — это твой шанс…». Абзацный переводчик имя знает и правило
    # соблюдает, а построчный не знал его вовсе — мод пишет имя в contexts,
    # мы его просто не читали.
    contexts = collected.get("contexts") or {}
    picked: dict[str, int] = {}
    origin: dict[str, str] = {}
    for source in args.sources:
        if source in NEVER:
            print(f"  пропускаю {source}: такие строки переводить нельзя")
            continue
        for line, count in (sources.get(source) or {}).items():
            # ⚠️ ЧУЖОЙ НИК ОБОБЩАЕМ, А НЕ ПЕРЕВОДИМ ПОШТУЧНО.
            #
            # «RARE REWARD! sentiences found a Fuming Potato Book…» — это
            # тринадцать отдельных строк на тринадцать игроков, и каждая
            # бесполезна остальным. Обобщённая «RARE REWARD! {s} found…»
            # работает у всех и никого не называет. Замер 05.08: из 151 строки,
            # отобранной к покупке, около 60 были такими.
            #
            # ⚠️ Признак берётся ПО СТРУКТУРЕ строки (check_nicknames.STRUCTURAL),
            # а не по виду ника: у половины игроков ник — обычное слово
            # (zuhnia, sentiences, nograssbro), и признак «есть цифра или
            # подчёркивание» их не видит. Своей копии тут не заводим.
            line = nick_free(line)
            if not worth_translating(line, source):
                continue
            if line in known:
                skipped_known += 1
                continue
            # ⚠️ Строку закрывает ВЫКЛЮЧЕННЫЙ словарь — значит перевод для неё
            # уже куплен и осознанно отключён. Отправить её в очередь значит
            # заплатить второй раз И обойти решение игрока.
            if guarded_by_toggle(line, guarded):
                skipped_toggle += 1
                continue
            # ⚠️ Строку уже переводит ПРАВИЛО включённого словаря. Точной
            # записи для неё нет и не будет — семьи вроде «Progress to …»
            # закрываются одной формой, — но на экране она русская, и платить
            # за неё второй раз незачем.
            if covered_by_rule(line, covered):
                skipped_rule += 1
                continue
            if source == "item_lore":
                # Имя предмета попадает и в лор (первой строкой подсказки),
                # а имена не переводят. Источник item_name говорит это прямо,
                # гадать по виду не нужно.
                # имя НАСТОЯЩЕГО предмета не переводим, а заголовок кнопки —
                # переводим: «Green Thumb» в меню Строителя это категория
                if line.strip() in item_names and looks_like_item(line, real_headers):
                    continue
                if ENCHANT_LIST.match(line) or is_stat_line(line, stats, covered):
                    continue
            number = count if isinstance(count, int) else 1
            if number > picked.get(line, 0):
                picked[line] = number
                origin.setdefault(line, source)

    ordered = sorted(picked, key=lambda s: (-picked[s], s))
    exact = {line: done.get(line, "") for line in ordered}
    hints = {}
    for line in ordered:
        hint = f"{origin[line]}, встречается {picked[line]}x"
        # ⚠️ Значок с имени снимаем: Hypixel пишет «◇ Sea Creature Chance»,
        # а в самой строке значка нет — сравнение по сырому имени не совпадало,
        # и подсказка не доезжала именно там, где нужнее всего.
        item = ICONS.sub("", contexts.get(line) or "").strip()
        if item and len(item) > 2 and item in line:
            hint += f". НЕ ПЕРЕВОДИТЬ имя предмета: {item}"
        hints[line] = hint
    contexts = hints

    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept_asis = sorted(s for s in asis if s in exact and not exact[s])
    out_path.write_text(json.dumps({
        "id": "from_game",
        "priority": 10,
        "_comment": "Очередь на перевод: чат, меню, панель. Собрана "
                    "tools/make_queue.py по убыванию частоты. Названия предметов "
                    "и полоса над хотбаром сюда НЕ попадают. В _asis лежат строки, "
                    "которые модель признала непереводимыми — их больше не спрашивают, "
                    "убери строку оттуда, чтобы спросить снова.",
        "_contexts": contexts,
        "_asis": kept_asis,
        "exact": exact,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ⚠️ Три разных числа, и складывать их в два нельзя: помеченные «переводить
    # нечего» — это НЕ переведённое, просто спрашивать их больше не нужно.
    # Один счётчик на два события в этом проекте уже врал (см. colorLoss).
    ready = sum(1 for v in exact.values() if v)
    left = len(exact) - ready - len(kept_asis)
    print(f"\nисточники: {', '.join(args.sources)}")
    print(f"уже переведено в других словарях, не берём: {skipped_known}")
    print(f"закрыто ПРАВИЛОМ включённого словаря, не берём: {skipped_rule}")
    print(f"закрыто ВЫКЛЮЧЕННЫМ словарём (решение игрока), не берём: {skipped_toggle}")
    rescued = sum(1 for line in ordered if exact[line] and line not in in_file)
    print(f"архив переводов: {len(arch_ru)} строк, {len(arch_asis)} пометок "
          f"(+{added[0]}/+{added[1]} за прогон)")
    if rescued:
        print(f"  ВЕРНУЛОСЬ ИЗ АРХИВА: {rescued} "
              f"(перевод пропал бы вместе с выпавшей строкой)")
    print(f"строк в очереди: {len(exact)}")
    print(f"  уже переведено: {ready}")
    print(f"  переводить нечего (_asis): {len(kept_asis)}")
    print(f"  ЖДУТ ПЕРЕВОДА:  {left}")
    print(f"записано: {out_path.relative_to(ROOT)}")
    print("\nсамое ходовое:")
    for line in ordered[:8]:
        clean = re.sub(r"[\ue000-\uf8ff]", "◇", line)
        print(f"  {picked[line]:4}x [{origin[line]}] {clean[:74]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
