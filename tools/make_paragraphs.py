"""
Собирает корпус АБЗАЦЕВ из корпуса подсказок.

Зачем: сервер режет описание на строки по ширине окна, а не по смыслу.
Переводя построчно, мы вынуждены повторять чужие границы — отсюда весь вечер
лезли одинаковые поломки (материал разорван пополам, фраза кончается посреди
строки) и заведомо худший перевод: русскую фразу приходилось втискивать
в границы английской.

⚠️ ГЛАВНОЕ: куски режутся ТОЧНО ТАК ЖЕ, как их режет мод (Paragraphs.runs) —
только по пустым строкам. Раньше скрипт резал ещё и по строкам-характеристикам,
а мод так не умеет: он вклеивает характеристику в абзац. Ключи расходились,
и 364 переведённых абзаца мод не спросил бы никогда — перевод за деньги в стол.

Строку-характеристику внутри куска обойти нельзя, но можно честно отказаться:
такой кусок в корпус НЕ попадает. Перекладывать его и не надо — перенос абзаца
смешал бы таблицу характеристик с прозой.

Одинаковые абзацы схлопываются: «Установи этого миньона…» встречается у сотни
миньонов, а перевести его надо один раз.

Готовые переводы (поле ru) при перезапуске СОХРАНЯЮТСЯ — иначе перегенерация
корпуса молча стирала бы оплаченную работу.

Источников может быть несколько, и они неравноценны:
  обычный аргумент  — выгрузка NEU: описания предметов, глубоко и надолго;
  --live            — дамп из игры: то, что игрок ВИДЕЛ своими глазами.

Сверено на живом дампе: корпус из одного NEU закрывает лишь 20% того, что мод
спрашивает во время игры — остального (меню, магазины, ивенты) в NEU нет вовсе.
Поэтому абзацы из дампа идут ПЕРВЫМИ: --limit у переводчика берёт начало списка,
и деньги уходят на то, что мозолит глаза, а не на предметы, которых никто не видел.

Запуск:
  python tools/make_paragraphs.py data/work/lore_tooltips.json
  python tools/make_paragraphs.py data/work/lore_tooltips.json --live "C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/tooltips.json"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ⚠️ Обобщение чисел берём ОБЩЕЕ, из pkey: копий этого правила в проекте было
# шесть, и одна успела разойтись. Заводить седьмую тут — верный способ снова
# развести ключ корпуса с ключом мода.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pkey import NUMBER  # noqa: E402

# Столько же, сколько MIN_LINES в Paragraphs.java: кусок короче двух строк
# склеивать не из чего.
MIN_LINES = 2

# Строки, которые в абзац попадать не должны: это не проза, а таблица.
# Признак не выдуман — сверен с корпусом: у таких строк своя строка на экране,
# и объединять их в абзац значило бы сломать вёрстку характеристик.
STRUCTURAL = re.compile(
    r"^(?:[A-Z][A-Z ]{2,}$"                 # РЕДКОСТЬ, ТИП ПРЕДМЕТА
    r"|[+\-]\s*\{n\}"                        # +{n} к характеристике
    r"|[A-Za-z' ]{3,28}: [+\-]?\{n\}"        # Ярлык: {n}
    r"|Time Between Actions|Max Storage|Resources Generated)"
)


HOLE = re.compile(r"\{[^{}]*\}|\{\{[^{}]*\}\}")


def has_foreign_hole(text: str) -> bool:
    """
    В тексте есть подстановка, которой движок НЕ ЗНАЕТ?

    Движок понимает ровно две: {n} — число, {s} — ник. Всё остальное в фигурных
    скобках приехало из выгрузки NEU, и в игре такой строки не бывает вовсе:
    ключ не совпадёт НИКОГДА, перевод уходит в стол.

    Пород две, и вторую я сперва не заметил:
      {INTELLIGENCE}  — именованная подстановка NEU;
      {{n}}           — её же {0}, внутрь которого попало наше обобщение чисел.
    Проверка «есть ли [A-Z_]» вторую не ловила: там внутри обычное {n}.
    Поэтому судим не по виду дырки, а по списку разрешённых.
    """
    return any(hole not in ("{n}", "{s}") for hole in HOLE.findall(text))


# ⚠️ СТРОКА, КОТОРАЯ ЯВНО ПРОДОЛЖАЕТСЯ, ХАРАКТЕРИСТИКОЙ НЕ БЫВАЕТ.
#
# Перенос режет фразу по ширине окна, и середина предложения запросто
# начинается с «+{n}»: «...Grants +12 Farming Fortune and / +6 Bonus Pest
# Chance, which / increases your chance...». Шаблон видел «+{n}» в начале,
# объявлял строку таблицей — и ВЕСЬ КУСОК не попадал в корпус.
#
# Цена была не в потерянном абзаце, а в СМЕСИ ЯЗЫКОВ на экране: раз абзаца
# нет, мод переводит построчно, первая строка находится («Даёт +12 Farming
# Fortune и»), остальные нет. Игрок прислал скриншотом ровно это.
#
# Признак тот же, что уже записан в проекте для хвостов переноса: фраза
# кончается СЛУЖЕБНЫМ словом или запятой. Замер по 29 429 строкам, которые
# шаблон зовёт характеристиками: продолжаются 91 (0.3%), и все до одной —
# настоящая середина предложения.
CONTINUES = re.compile(
    r"(?:,|\b(?:and|which|that|for|per|to|of|in|on|when|while|the|a|an|by|with|from"
    r"|every|each|your|you|or))\s*$",
    re.IGNORECASE)


# ⚠️ СТРОКА «+{n} … ПРЕДЛОГ … .» — ПРОДОЛЖЕНИЕ ФРАЗЫ, А НЕ ТАБЛИЦА (04.09).
#
# Предыдущий признак ловил только КОНЕЦ строки (служебное слово или запятая).
# А перенос режет и так: «Grants +86☘ Farming Fortune and / +30✿ Overbloom on
# ൠ Pests.» — вторая строка начинается с «+{n}», кончается точкой, и шаблон
# звал её характеристикой. Весь кусок не попадал в корпус, мод переводил
# построчно, и игрок видел «+30.1✿ Overbloom on Pests» — смесь языков.
# Прислано скриншотом 03.09 (питомец Hedgehog).
#
# Признак: строка с «+{n}» в начале, служебным словом ПОСРЕДИ и знаком конца
# предложения в хвосте. У таблицы характеристик посреди строки предлогов
# не бывает. Замер по 157 тысячам живых подсказок: признак отпускает
# 30 разных кусков, все 30 — проза («Each stack grants +5⚡ Swing Range,
# +3❁ Ferocity and +5% Damage.», «Deposit it in any Chum Bucket to earn
# +100 Coins and +25 Fishing XP!»), настоящих таблиц среди них ноль.
# ⚠️ ...И БЕЗ ТОЧКИ В КОНЦЕ ТОЖЕ (13.10). «These boots gain +{n}❈ Defense and /
# +{n}✦ Speed for every Farming Skill / level you have. …» — вторая строка
# начинается с «+{n}», кончается словом «Skill» (не служебным) и точки не
# имеет: фраза продолжается на третьей строке. Прежний признак требовал
# «.» или «!» в конце, строка шла за характеристику, весь кусок выпадал из
# корпуса, и мод переводил ботинки построчно: «+1☘ фермерской Fortune»,
# «навыка Farming уровня». Скриншот игрока 13.10 (Mantid Rancher's Boots).
# Теперь довольно предлога, за которым слово и ещё хоть что-то: у настоящей
# строки характеристики («+{n}% Damage to Zombies») после предлога слово
# одно. Строки таблиц — «- {n} coins each | {n}x in {n} order» (Bazaar),
# «+ {n}, {n} mins ago by Bank Interest» (банк) — отсекаются по запятой или
# черте сразу за числом и по «{n}» вместо слова за предлогом: это не проза.
# Старый признак (точка или «!» в конце) остаётся: «+{n}✦ Speed for {n}
# seconds.», «+{n}❀ Overbloom on ൠ Pests.» — после предлога стоит не слово.
PROSE_TAIL = re.compile(r"^[+\-]\s*\{n\}[^,|]*\S\s+(?:on|against|for|per|to|in|with|from|when"
                        r"|while|by|and|of)\s+(?:\S+.*[.!]|[A-Za-z]\S*\s+\S+.*)$")


def is_structural(line: str) -> bool:
    text = line.strip()
    if CONTINUES.search(text):
        return False
    if PROSE_TAIL.match(text):
        return False
    return bool(STRUCTURAL.match(text))


# ⚠️ ХВОСТ ЧУЖИХ МОДОВ В БЛОКЕ (04.09). REI/EMI дописывают в конец подсказки
# «Minecraft», клиент при F3+H — «minecraft:player_head» и число компонентов,
# Skyblocker — «skyblock:JAWBREAKER». Мод с 0.2.30 отрезает их ПО ЛОРУ
# предмета (core/TooltipTail) до сбора, и в новых блоках их нет. А в старых
# блоках от игроков они лежат (312 штук), и ключ «… Right-click to convert
# to an item! Minecraft» мод не спросит никогда. Здесь лора нет — только
# текст, поэтому режем по ФОРМЕ, и только то, что видели в данных.
FOREIGN_TAIL = re.compile(
    r"^(?:Minecraft|minecraft:[a-z0-9_/.]+|skyblock:[A-Za-z0-9_:.-]+"
    r"|(?:\{n\}|\d+) (?:компонент(?:ов|а)?|components?)|NBT: (?:\{n\}|\d+) tag\(s\))$")


def strip_foreign_tail(lines: list[str]) -> list[str]:
    """Снимает с конца блока строки чужих модов — см. FOREIGN_TAIL."""
    out = list(lines)
    while out and FOREIGN_TAIL.match(out[-1].strip()):
        out.pop()
    return out


# «Sharpness VII», «Bane of Arthropods VII», «Ultimate Wise V» — название и римская цифра
ENCHANT = re.compile(r"[A-Z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*){0,3} [IVXLC]{1,6}\b")

# ⚠️ Строка ЦЕЛИКОМ из имени и уровня — копия Paragraphs.ENCHANT_HEAD.
# Такую строку мод не считает именем предмета (у книги зачарования они
# совпадают), и корпус обязан вести себя так же — иначе ключи разойдутся.
ENCHANT_HEAD = re.compile(r"^[A-Z][A-Za-z' -]*\s[IVXLC]+$")


# Кириллица в ОРИГИНАЛЕ: строку уже перевёл кто-то другой — Minecraft или Hypixel
NOT_ENGLISH = re.compile(r"[А-Яа-яЁё]")

# Подстановка NEU: {INTELLIGENCE}, {FARMING_FORTUNE}. Движок знает только
# {n} и {s}, а в игре на этом месте стоит настоящее число — значит такой
# ключ не совпадёт НИКОГДА. Перевод в стол.


def is_enchant_list(text: str) -> bool:
    """
    Абзац на деле СПИСОК ЗАЧАРОВАНИЙ, а не проза.

    ⚠️ Переводить такие абзацами — выброшенные деньги. Набор зачарований
    у каждого предмета свой: из 147 таких абзацев в корпусе 143 встретились
    ровно ОДИН раз, и в живом дампе то же самое. Готовая запись «Legion V,
    Growth VI, Hardened Vitality X» не совпадёт больше никогда.

    Переводить надо сами названия зачарований (75-sb-enchants), тогда любая
    комбинация собирается сама и работает на всех предметах разом.

    Признак: если выкинуть из строки все «Название + римская цифра» и знаки
    списка, почти ничего не остаётся.
    """
    rest = ENCHANT.sub("", text)
    rest = re.sub(r"[,\s]+", "", rest)
    return len(ENCHANT.findall(text)) >= 2 and len(rest) <= len(text) * 0.15


# Строка-линия «--------------------------»: рамка перка министра. Hypixel
# ставит её БЕЗ пустых строк вокруг, и она склеивается с абзацем (дамп 18.10,
# «Minister Finnegan»: «Blooming Business» был куплен для меню мэра, а в
# подсказке министра ключ выходил с линиями по краям и не находился).
# Копия Paragraphs.SEPARATOR — сверяет check_contract.py.
SEPARATOR = re.compile(r"^-{5,}$")


def trim_separators(run: list[str]) -> list[str]:
    """
    Кусок без линий по краям — ровно как запасной ключ мода (Paragraphs.withoutSeparators).

    Мод сперва спрашивает кусок целиком (старые переводы с линиями в ключе —
    «Double Trouble», «GOATed» — остаются живыми), потом без линий. В корпус
    новый кусок кладём уже без них: так один купленный перевод служит и меню
    мэра, и подсказке министра. Внутренность короче MIN_LINES — режем нечего.
    """
    a, b = 0, len(run)
    while a < b and SEPARATOR.match(run[a].strip()):
        a += 1
    while b > a and SEPARATOR.match(run[b - 1].strip()):
        b -= 1
    if (a, b) == (0, len(run)) or b - a < MIN_LINES:
        return run
    return run[a:b]


def runs_of(lines: list[str]) -> list[list[str]]:
    """
    Куски подсказки ровно так, как их строит мод: режем ТОЛЬКО по пустым строкам.

    Точная копия Paragraphs.runs — если разойтись хоть в мелочи, ключ абзаца
    в корпусе не совпадёт с ключом, который мод построит в игре, и перевод
    не найдётся ни разу.
    """
    found: list[list[str]] = []
    run: list[str] = []
    for line in lines:
        if not line.strip():
            if len(run) >= MIN_LINES:
                found.append(list(run))
            run.clear()
        else:
            run.append(line.strip())
    if len(run) >= MIN_LINES:
        found.append(list(run))
    return found


def without_name(lines: list[str], item: str) -> list[str]:
    """
    Убирает первую строку, если это имя предмета.

    В подсказке имя стоит первой строкой и пустой строкой от описания не
    отделено, поэтому мод склеил бы его с первым абзацем — и перенос размазал
    бы имя по прозе. Мод делает то же самое (Paragraphs.nameAside), и если
    сделать иначе, ключи разойдутся.

    Для корпуса из NEU это пустая операция (там имени в строках нет вовсе),
    а для корпуса из живого дампа — обязательная: там имя первой строкой у 97%.
    """
    item = (item or "").strip()
    if not item or not lines:
        return lines
    first = lines[0].strip()
    # ⚠️ ИСКЛЮЧЕНИЯ ДЛЯ КНИГИ ЗАЧАРОВАНИЯ ЗДЕСЬ НЕТ — и это осознанно,
    # см. тот же комментарий в Paragraphs.nameAside. Признак «имя + римский
    # уровень» ловит предметы коллекций («Ice IV») и миньонов, и на замере
    # он оторвал 179 абзацев от их переводов.
    if first == item:
        return lines[1:]
    # ⚠️ Сравниваем ещё и ОБОБЩЁННЫЕ: строки в дампе записаны с дырками
    # («{n} Chocolate»), а имя предмета — сырым («6,805,377 Chocolate»).
    # Прямое сравнение их не сводит, имя остаётся в абзаце и уезжает в ключ.
    # Беда тихая и дорогая: перевод покупается, а мод спрашивает ключ БЕЗ
    # имени — и не находит его никогда.
    #
    # Это возврат уже записанной грабли с другой стороны: тогда обобщали
    # строку и забыли имя, теперь обобщение пришло из дампа, а сравнение
    # осталось сырым. Мораль та же: обобщение — часть ключа, и применять
    # его надо к ОБЕИМ сторонам.
    if NUMBER.sub("{n}", first) == NUMBER.sub("{n}", item):
        return lines[1:]
    return lines


def paragraphs_of(block: dict) -> tuple[list[dict], int]:
    """Абзацы одного блока и число кусков, отброшенных из-за характеристик."""
    out, skipped = [], 0
    for run in runs_of(without_name(strip_foreign_tail(block["lines"]), block.get("item", ""))):
        run = trim_separators(run)
        if any(is_structural(line) for line in run):
            # Мод склеит характеристику с прозой, и переложить такой кусок
            # значило бы размазать таблицу в текст. Честно не берём.
            skipped += 1
            continue
        text = " ".join(run)
        if is_enchant_list(text):
            # Список зачарований: у каждого предмета свой, перевод не переиспользуется
            skipped += 1
            continue
        if has_foreign_hole(text):
            # Чужая подстановка из выгрузки NEU: в игре такой строки не бывает,
            # мод её не спросит, а деньги за перевод ушли бы.
            skipped += 1
            continue
        if NOT_ENGLISH.search(text):
            # ⚠️ Кусок УЖЕ не английский — переводить нечего, а заплатили бы.
            #
            # Два честных источника такого: ванильные зачарования Minecraft
            # рисует сам на языке клиента («Эффективность X»), а лобби Hypixel
            # переводит сам по языку игрока («Нажмите, чтобы играть»). Это
            # не наш текст и не наша забота. Плюс ключ такого абзаца зависит
            # от языка клиента — сменит язык, и абзац не найдётся никогда.
            skipped += 1
            continue
        out.append({"lines": run, "text": text})
    return out, skipped


def read_blocks(name: str) -> list[dict]:
    path = Path(name)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"! нет файла: {path}")
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("tooltips") or []
    except (json.JSONDecodeError, OSError) as exception:
        print(f"! {path.name}: {exception}")
        return []


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Корпус абзацев из корпусов подсказок")
    parser.add_argument("files", nargs="*", help="выгрузки NEU (поле tooltips)")
    parser.add_argument("--live", nargs="*", default=[],
                        help="дампы из игры: эти абзацы игрок видел, они идут первыми")
    args = parser.parse_args()
    if not args.files and not args.live:
        print(__doc__)
        return 1

    sources = [(name, False) for name in args.files] + [(name, True) for name in args.live]

    out = ROOT / "data" / "work" / "paragraphs.json"

    # Уже сделанный перевод переносим по ключу. Без этого перезапуск скрипта
    # стирал весь оплаченный прогон — проверено, стирал молча и полностью.
    done: dict[str, str] = {}
    # Пометка «переводить нечего» переносится вместе с переводами: её ставит
    # translate_tooltips.py абзацам, где кроме имён предметов ничего нет
    # («▶ Snowball ▶ Snow Block»). Потеряем — и они снова поедут в запрос,
    # а это был почти весь последний заход: 36 бесполезных абзацев из 47.
    nothing: set[str] = set()
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8")).get("paragraphs") or []
            done = {p["text"]: p["ru"] for p in old if p.get("ru") and p.get("text")}
            nothing = {p["text"] for p in old if p.get("nothing") and p.get("text")}
        except (json.JSONDecodeError, OSError, KeyError):
            print("! старый корпус не прочитался — переводы перенести не смогу")

    # ⚠️ Абзац с полем `source` создан НАМЕРЕННО (варианты со значками сервера,
    # лор аукциона, возвращённое из словаря) — в источниках его нет и быть
    # не может. Пересборка молча выбрасывала такие записи: это пятое
    # повторение потери «корпус отстал от словаря». Переносим целиком.
    deliberate: list[dict] = []
    if out.exists():
        try:
            deliberate = [p for p in json.loads(out.read_text(encoding="utf-8")).get("paragraphs") or []
                          if p.get("source") and p.get("text")]
        except (json.JSONDecodeError, OSError, KeyError):
            deliberate = []

    seen: dict[str, dict] = {}
    skipped_total = 0
    blocks_total = 0
    for name, is_live in sources:
        blocks = read_blocks(name)
        blocks_total += len(blocks)
        print(f"  {'[из игры] ' if is_live else '[NEU]     '}{Path(name).name}: "
              f"подсказок {len(blocks)}")
        for block in blocks:
            found, skipped = paragraphs_of(block)
            skipped_total += skipped
            for para in found:
                key = para["text"]
                entry = seen.get(key)
                if entry is None:
                    entry = {
                        "text": key,
                        "lines": para["lines"],
                        "item": block.get("item", ""),
                        "count": 0,
                        # сколько раз абзац встретился В ИГРЕ, а не в выгрузке
                        "live": 0,
                    }
                    if key in done:
                        entry["ru"] = done[key]
                    if key in nothing:
                        entry["nothing"] = True
                    seen[key] = entry
                entry["count"] += 1
                if is_live:
                    entry["live"] += 1

    # ⚠️ Старый перевод С ЛИНИЯМИ в ключе переносим на ключ БЕЗ линий, если тот
    # ещё не переведён: текст тот же, линии из перевода снимаем. Иначе после
    # смены резки «GOATed» остался бы переведён только в старой записи, а
    # меню мэра с тем же текстом — нет (18.10).
    migrated = 0
    if out.exists():
        try:
            legacy = json.loads(out.read_text(encoding="utf-8")).get("paragraphs") or []
        except (json.JSONDecodeError, OSError, KeyError):
            legacy = []
        strip_lines = re.compile(r"\s*(?:§.)*-{5,}(?:§.)*\s*")
        for para in legacy:
            if not para.get("ru") or not para.get("lines"):
                continue
            inner = trim_separators([str(x) for x in para["lines"]])
            if inner == para["lines"]:
                continue
            target = seen.get(" ".join(x.strip() for x in inner).strip())
            if target is None or target.get("ru"):
                continue
            target["ru"] = strip_lines.sub(" ", para["ru"]).strip()
            migrated += 1
    if migrated:
        print(f"переводов снято с ключей с линиями по краям на ключ без линий: {migrated}")

    carried_deliberate = 0
    for para in deliberate:
        if para["text"] not in seen:
            seen[para["text"]] = para
            carried_deliberate += 1
    if carried_deliberate:
        print(f"перенесено абзацев с полем source (сделаны намеренно): {carried_deliberate}")

    # Сперва то, что игрок видел своими глазами, потом всё остальное по частоте.
    # На этом порядке держится --limit у переводчика: деньги идут сверху списка.
    ordered = sorted(seen.values(), key=lambda p: (-p.get("live", 0), -p.get("count", 0)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"paragraphs": ordered}, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    total_lines = sum(len(p["lines"]) for p in ordered)
    carried = sum(1 for p in ordered if p.get("ru"))
    lost = len(done) - carried
    # .get: у перенесённых абзацев с полем `source` поля `live` нет — на нём
    # refresh.py падал сразу после записи корпуса и дальше шаг 1 не шёл.
    live_count = sum(1 for p in ordered if p.get("live"))
    print(f"\nподсказок разобрано: {blocks_total}")
    print(f"РАЗНЫХ абзацев:   {len(ordered)}  (строк в них: {total_lines})")
    if args.live:
        print(f"из них ВИДЕЛИ в игре: {live_count} — они идут первыми в списке")
    print(f"кусков отброшено из-за характеристик внутри: {skipped_total}")
    if done:
        print(f"перенесено готовых переводов: {carried} из {len(done)}")
        if lost:
            print(f"⚠️ не нашли места {lost} переводам — абзац изменился или исчез")
    print(f"записано: {out}\n")
    print("самые частые:")
    for para in ordered[:5]:
        text = para["text"]
        print(f"  {para['count']:4}x  {text[:88]}{'…' if len(text) > 88 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
