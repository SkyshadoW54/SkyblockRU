"""
Слова, которые переводить НЕЛЬЗЯ: имена NPC, названия локаций, валюты.

Зачем отдельный список, а не «нейросеть сама поймёт»: она видит голый текст.
Цвет, которым Hypixel подсвечивает такие слова, до неё не доходит — §-коды
снимаются раньше, иначе не совпал бы словарь. А по одному тексту «Foraging»
не отличить от «Foraging Camp»: первое — навык (переводим), второе — локация
(не трогаем). Догадка тут не работает, нужен явный список.

Список собирается ИЗ ЖИВЫХ ДАННЫХ — того, что мод записал в игре:
  [NPC] Имя:      -> имя NPC
  <значок> Место  -> локация из боковой панели
плюс горстка констант, которых в дампе может ещё не быть.

Тут же лежит проверка: после перевода защищённое слово обязано остаться
в строке. Спорить с моделью бесполезно (проверено на иконках) — дешевле
поймать механически.

Запуск:  python tools/protected.py
"""

from __future__ import annotations

import functools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Дамп из игры: там живые имена и места, а не мои догадки.
DUMPS = [
    Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json"),
    ROOT / "data" / "work" / "collected.json",
]

# Имена, которые Hypixel ПОДСВЕТИЛ СВОИМ ЦВЕТОМ. Собирает мод (Highlights.java),
# потому что в дампе строк §-коды уже сняты и признак пропадает.
#
# Это лучший источник из всех: цвет — данные от сервера, а не догадка по виду
# текста. В реплике «go and find <жёлтым>Captain Baha<белым> in the
# <голубым>Fishing Outpost<белым>!» сервер сам показал, где имена.
HIGHLIGHTS = [
    Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/highlighted.json"),
    ROOT / "data" / "work" / "highlighted.json",
]

# Полные списки с вики: места и говорящие. Собираются отдельными инструментами
# (fetch_places.py, fetch_dialogues.py) и обновляются вручную — это данные,
# а не результат каждого прогона.
WIKI_PLACES = ROOT / "data" / "work" / "places_wiki.json"
WIKI_DIALOGUES = ROOT / "data" / "work" / "npc_dialogues.json"

# Порог для ОДНОСЛОВНЫХ имён с вики: сколько раз слово встречается со строчной
# в наших же текстах, чтобы считать его обычным существительным, а не именем.
# Выше штатного ORDINARY_MIN намеренно — списки с вики авторитетны, и резать
# их надо только там, где слово явно живёт двойной жизнью (Mayor, Museum).
WIKI_LOWERCASE = 10

# Должности перед именем: по-русски они переводятся («мэр Finnegan»), поэтому
# связку целиком защищать нельзя. Список закрытый — это те слова, которыми
# Hypixel помечает роль персонажа.
TITLE_PREFIX = re.compile(r"^(Mayor|Captain|King|Queen|Lord|Sir|Master|Chief"
                          r"|Professor|Doctor|Elder)\s", re.I)

# ⚠️ ДВОЙСТВЕННЫЕ СЛОВА: на вики они значатся именами (место или персонаж),
# но в прозе Hypixel употребляет их как обычные существительные, и там их
# ПЕРЕВОДЯТ правильно: «elected as Mayor of SkyBlock» → «избран мэром
# SkyBlock», «Museum Donations» → «пожертвования в музей».
#
# Защитив такое слово, мы объявляем правильный перевод порчей имени —
# на живом корпусе это дало 18 ложных «поломок» разом.
#
# ⚠️ Список ЯВНЫЙ, а не признак, и это осознанно. Признак я подбирал трижды,
# и каждый раз он врал:
#   * «часто пишется со строчной» — Mayor и Museum в оригинале ВСЕГДА
#     с заглавной, счётчик нулевой, и они проходят как имена;
#   * «стоит с артиклем» — ловит Mayor и Museum, но заодно Jerry и Taylor,
#     а Frosty и Coral пропускает;
#   * «переведено хотя бы раз в корпусе» — считает и настоящие промахи
#     перевода, и законную двойственность, не различая их.
# Слов таких десятки, а не сотни, и каждое видно глазами — перечислить
# честнее, чем гадать.
AMBIGUOUS = {
    # должности и роли
    "Mayor", "King", "Queen", "Wizard", "Alchemist", "Blacksmith", "Builder",
    "Baker", "Librarian", "Banker", "Farmer", "Hunter", "Merchant", "Guard",
    # места, которые бывают и просто словом
    "Museum", "Forest", "Carnival", "Graveyard", "Village", "Wilderness",
    "Bank", "Farm", "Hub", "Library", "Jungle", "Barn", "Mine", "Mountain",
    "Park", "End", "Castle", "Church", "Camp",
    # предметы и существа
    "Rock", "Chicken", "Sheep", "Coral", "Bone", "Gemstone", "Apple", "Carrot",
    "Bingo", "Frosty",
    # ⚠️ ПОДПИСИ, а не имена. Hypixel подсветил их в чате («убедись, что ты
    # Fishing Level 6»), и подсветка записала их в защиту — но словарь их
    # переводит сам: «Fishing Level II» -> «Уровень рыбалки II». Без этой
    # строки проверка бракует ПРАВИЛЬНЫЙ перевод и останавливает сборку.
    "Fishing Level",
}

# ⚠️ Порога по числу встреч тут НЕТ, и это осознанно.
#
# Сначала брали только слова, встреченные дважды. Но цена ошибки несимметрична:
# не защитили имя — его переведут, и «Captain Baha» станет «Капитаном Бахой»,
# по которому не найти ни NPC, ни вещь на аукционе. Защитили лишнее — слово
# осталось английским, что неприятно, но безобидно. А «Captain Baha» в логах
# встретился ровно один раз.
#
# Вместо порога — два признака по СМЫСЛУ:
#   имя из двух слов и больше     -> берём всегда;
#   одно слово                    -> берём, если оно почти не встречается
#                                    СО СТРОЧНОЙ в наших же текстах.
# Второй признак механический и проверяемый: «bring» со строчной попадается
# 28 раз, «awesome» 3, а «baha», «atoll», «seraphine» — ни одного.
ORDINARY_MIN = 3

# Хвост с римским уровнем: «Level IX», «Growth VI»
ROMAN_TAIL = re.compile(r"\s+[IVXLC]{1,6}$")

# Служебные слова: внутри имени они пишутся со строчной и признак заглавной
# буквы не портят — «Trial of Fire», «Bank of Hypixel», «Cult of the Fallen Star».
SERVICE_WORDS = {"of", "the", "a", "an", "and", "to", "in", "on", "at", "for",
                 "from", "with", "by", "de", "la", "el"}

NPC_LINE = re.compile(r"^\[NPC\]\s+([A-Z][A-Za-z' ]{1,24}):")

# Надпись над головой: имя NPC целой строкой, без чисел и двоеточий.
#
# ⚠️ Третий источник, и он ловит то, чего нет в двух других: цветом NPC
# выделяют не всегда («[NPC] Talbot: Hey, I'm Talbot!» — имя внутри реплики
# белое), а в префиксе он появляется, только если с ним заговорили. А над
# головой имя висит всегда, стоит пройти мимо.
NAME_TAG = re.compile(r"^[A-Z][A-Za-z'-]+(?: [A-Z][A-Za-z'-]+){0,3}$")

# Значок локации в боковой панели (приватная зона Unicode).
LOCATION_LINE = re.compile(r"^[-]\s*([A-Z][A-Za-z' ]{2,28})$")

# То, чего в дампе может не оказаться, а защищать надо.
#
# ⚠️ Разложено ПО ГРУППАМ, а не одним списком. Раньше тут лежало плоское
# множество, и вместе с ним терялось то, что мы про каждое слово знаем:
# «Gems» — валюта, «Birch Park» — место, «Lumber Merchant» — торговец.
# Знание было, но выбрасывалось по дороге — а без него нельзя ни взять
# группу целиком, ни запретить к переводу что-то одно.
ALWAYS_GROUPS = {
    # Валюты — по прямой просьбе: Gems (за деньги) и Bits не переводим,
    # иначе их не отличить от Gemstones (самоцветы с добычи).
    "currency": {"Gems", "Bits"},
    # Сам сервер и его сервисы: имена собственные, вдобавок по ним ищут гайды.
    "brand": {"SkyBlock", "Hypixel", "Bazaar", "Auction House"},
    "location": {
        "Foraging Camp", "Birch Park",
        # Подземелья: локация называется «The Catacombs», и по этому имени
        # игрок ищет сведения о ней. Переводим только слово РЯДОМ:
        # «Floor VII» -> «этаж VII».
        "The Catacombs", "Catacombs",
        # Локации, которые в дампе попадаются только внутри фраз, а не строкой
        "Spider's Den", "The End", "Dungeon Hub",
        # ⚠️ Решение игрока 01.08: «Mining Island на английском должно быть
        # ВСЕГДА». Это не одно место, а группа островов (Dwarven Mines,
        # Crystal Hollows и прочие), и по имени её ищут в гайдах. Перевод
        # «острова добычи» звучал прилично, но искать по нему нечего.
        # ⚠️ ТОЛЬКО множественное число. «Mining Island» в единственном ловит
        # ложно: в абзаце «Main skill: Mining / Island tier: I» это ДВЕ разные
        # строки, склеенные подряд, и защита объявляла верный перевод порчей.
        "Mining Islands",
    },
    # ⚠️ Собирательное имя набора характеристик, а не отдельная характеристика:
    # в реестре Hypixel его нет, поэтому в STAT_JARGON ему не место. Решение
    # игрока — оставить английским, как и сами характеристики боя.
    "stat": {"Combat Stats"},
    "npc": {"Lumber Merchant"},
    # Предмет из общественного магазина: Hypixel пишет его и со строчной
    # («obtain booster cookies»), но имя предмета остаётся именем.
    "item": {"Booster Cookie", "Booster Cookies"},
}

ALWAYS = {name for names in ALWAYS_GROUPS.values() for name in names}

# Ложные срабатывания: слова, которые ВЫГЛЯДЯТ как имя, но ими не являются.
NOT_NAMES = {
    "None", "You", "Your Island", "The", "A", "An",
    # Пришли из подсветки цветом, но именами не являются:
    # Hypixel красит и восклицания. Ловится только глазами —
    # признак «не пишется со строчной» их пропускает.
    "Congrats", "Goofy", "Timber", "Awesome", "Welcome", "Hooray",
    # ⚠️ Профессия, а не имя. В дампе есть предмет «Wizard», поэтому слово
    # попадало в защищённые, — а во фразе «A famous Wizard used a wand made
    # out of these» это обычный волшебник, и оставлять его латиницей значит
    # выдать «Один известный Wizard сделал жезл». Абзац при этом вообще
    # не переводился: любой осмысленный перевод браковался как «испортил имя».
    "Wizard",
    # ⚠️ Пришли из подсветки в СВЕЖЕМ дампе и именами не являются:
    # «(No Pearls, No Rushing)» — это УСЛОВИЯ забега, Hypixel красит их как
    # предупреждение; «Timer» в списке возможностей — обычное слово. Оставь
    # их в защите, и правильный перевод («без жемчуга», «Таймер») пойдёт
    # в СЛОМАНО, а круг сборки встанет на ровном месте.
    "No Pearls", "No Rushing", "Timer",
}


_ORDINARY: dict[str, int] | None = None


def ordinary_words() -> dict[str, int]:
    """
    Сколько раз слово встречается СО СТРОЧНОЙ буквы в наших текстах.

    Источник — корпус описаний и логи чата, то есть настоящий английский язык
    этой игры, а не словарь общей лексики. Имя собственное со строчной
    не пишут никогда, обычное слово — постоянно. Признак дешёвый и честный.
    """
    global _ORDINARY
    if _ORDINARY is not None:
        return _ORDINARY
    import collections
    import gzip
    counter: collections.Counter = collections.Counter()

    def feed(text: str) -> None:
        counter.update(re.findall(r"\b[a-z][a-z'-]{2,}\b", text))

    for name in ("lore_tooltips.json", "paragraphs.json"):
        path = ROOT / "data" / "work" / name
        if path.exists():
            feed(path.read_text(encoding="utf-8", errors="replace"))
    logs = Path("C:/MultiMC/instances/26.2/.minecraft/logs")
    if logs.exists():
        for path in list(logs.glob("*.log")) + list(logs.glob("*.log.gz")):
            opener = gzip.open if path.suffix == ".gz" else open
            try:
                with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
                    feed(handle.read())
            except OSError:
                continue
    _ORDINARY = dict(counter)
    return _ORDINARY


def looks_like_name(name: str) -> bool:
    """Кусок текста — имя собственное, а не выделенное обычное слово?"""
    name = name.strip()
    if len(name) < 4:
        return False
    if ROMAN_TAIL.search(name):
        # «Level IX», «Trial of Fire III» — хвост с уровнем делает именем что
        # угодно, а «Level» это обычное слово. Уровень отбрасываем и судим
        # по тому, что осталось.
        return looks_like_name(ROMAN_TAIL.sub("", name))
    if name.upper() == name:
        # ЗАГЛАВНЫМИ Hypixel набирает кнопки и выделение, а не имена:
        # «CLICK TO BUY», «COMMUNITY SHOP», «NEW RABBIT».
        return False
    if name.split() and name.split()[-1].lower() in SERVICE_WORDS:
        # ⚠️ Имя не КОНЧАЕТСЯ служебным словом. «Use the» — обрывок фразы,
        # который подсветка выхватила вместе с артиклем: «Use the button on
        # the right…». По правилу заглавной буквы он проходил как имя («Use»
        # с большой, «the» служебное и не в счёт) — и запрещал переводить
        # начало любой такой фразы. Настоящее имя оканчивается значимым
        # словом: «Heart of the Mountain», «Trial of Fire».
        return False
    if " " in name:
        # ⚠️ Двух слов НЕ ДОСТАТОЧНО: Hypixel красит и АКЦЕНТ, а не только имена.
        #
        # В реплике Croesus подсвечены и «The Catacombs», «Kuudra», «Treasure
        # Chests» (имена, не переводим), и «don't open» — обычные слова, которые
        # переводить как раз нужно, да ещё и цвет им сохранить. Правило «два слова
        # и больше — имя» брало за имена «don't open», «collect and hoard»,
        # «not ready», «before talking to me again»: пять акцентов из девяти.
        # Цена такой ошибки высока — одно подсвеченное «open any» запретило бы
        # переводить эти слова по ВСЕМУ проекту.
        #
        # Различает их то самое правило заглавной буквы, на котором стоит проект:
        # имя Hypixel пишет с большой, обычное слово во фразе — с маленькой.
        # Служебные слова внутри имени («Trial of Fire») в счёт не идут.
        significant = [w for w in re.findall(r"[A-Za-z][A-Za-z']*", name)
                       if w.lower() not in SERVICE_WORDS]
        if not significant:
            return False
        return all(word[0].isupper() for word in significant)
    return ordinary_words().get(name.lower(), 0) < ORDINARY_MIN


@functools.lru_cache(maxsize=1)
def wiki_places() -> frozenset[str]:
    """
    ВСЕ названия мест с вики, в нижнем регистре и БЕЗ отсева двойственных.

    ⚠️ Это НЕ защита, и путать их дорого. `collect_groups` прогоняет список
    через `from_wiki`, и оттуда законно выпадают `Village`, `Mountain`,
    `The Barn` — слова, которые бывают и именем места, и обычным
    существительным (`AMBIGUOUS`). Защищать их по всему проекту нельзя:
    «избран мэром SkyBlock» сломалось бы в шестнадцати местах.

    Но у двойственности есть ОБЛАСТЬ. Там, где строку целиком занимает метка
    локации — колонка полосы над хотбаром, — второго смысла у слова нет,
    и сверяться можно со всем списком. Тот же приём, что «цвет — признак
    имени ТОЛЬКО В ЧАТЕ»: признак верен не всюду, а в своей области.

    Цена молчания видна на замере 01.08: «◇ Village» держало ПЕРВУЮ строку
    отчёта с 242 показами — 91% всего раздела колонок, — и настоящей работы
    (17 колонок, 24 показа) за ним было не разглядеть.
    """
    if not WIKI_PLACES.exists():
        return frozenset()
    try:
        data = json.loads(WIKI_PLACES.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return frozenset()
    return frozenset(str(name).strip().lower()
                     for name in (data.get("locations") or []) if str(name).strip())


def collect() -> set[str]:
    """Все защищённые слова одним множеством — как читали до появления групп."""
    return {name for names in collect_groups().values() for name in names}


def collect_groups() -> dict[str, set[str]]:
    """
    То же самое, но С ГРУППАМИ: кто это — NPC, место, валюта, подсветка.

    <p>⚠️ Группа известна В МОМЕНТ СБОРА и раньше терялась: строку «[NPC] Ryan:»
    приносит источник chat, локацию — боковая панель, и оба клали слово в общую
    кучу. Из-за этого нельзя было ни взять категорию целиком, ни запретить
    к переводу что-то одно — приходилось перечислять слова руками.

    <p>Группа «highlight» — честное «не знаю»: Hypixel подсветил слово своим
    цветом, значит это имя собственное, но место оно или персонаж, из цвета
    не следует. Врать точной категорией тут хуже, чем признаться.
    """
    groups: dict[str, set[str]] = {key: set(value) for key, value in ALWAYS_GROUPS.items()}

    def add(group: str, name: str) -> None:
        # ⚠️ «ДОЛЖНОСТЬ + ИМЯ» защищаем НЕ ЦЕЛИКОМ: должность переводится,
        # имя нет — «Mayor Finnegan» → «мэра Finnegan». Иначе правильный
        # перевод объявляется порчей имени, и круг сборки встаёт: ровно так
        # «Mayor Scorpius» заблокировал jar (2 записи в СЛОМАНО).
        #
        # ⚠️ Фильтр стоял ТОЛЬКО на именах с вики, а имена приходят ещё
        # из префикса «[NPC] Имя:», надписи над головой и подсветки в чате.
        # Записанная грабля повторилась: «завёл ворота — проведи через них
        # ВСЕ пути». Теперь ворота одни — эта функция.
        #
        # ⚠️ Голую часть ОБЯЗАТЕЛЬНО добавляем взамен. У шести «Mayor X»
        # имя защищено и само по себе, а у «Captain Baha» и «Master Tactician
        # Funk» — НЕТ, и простое снятие пары открыло бы путь к «Капитану Бахе»,
        # по которому не найти ни NPC, ни вещь.
        title = TITLE_PREFIX.match(name)
        if title:
            bare = name[title.end():].strip()
            if bare:
                groups.setdefault(group, set()).add(bare)
            return
        groups.setdefault(group, set()).add(name)

    # ⚠️ Полные списки с вики — они ПОЛНЕЕ собранного модом по определению.
    #
    # Всё, что ниже, собиралось из дампа: локация попадала в защиту, только
    # если игрок мимо неё ходил, а имя NPC — если он с ним говорил. Место,
    # где игрок не был, оставалось беззащитным, и очередной прогон мог его
    # перевести: «Birch Park» → «Берёзовый парк» ломает и поиск варпа,
    # и понимание гайдов.
    #
    # Вики знает все места (шаблон {{Zone|…}} на странице Locations) и всех
    # говорящих (реплики «[NPC] Имя:» на тысяче страниц с диалогами).
    # Собирают их `tools/fetch_places.py` и `tools/fetch_dialogues.py`;
    # файлы лежат в data/work и обновляются вручную, а не при каждом запуске:
    # ходить в сеть ради списка имён на каждый прогон незачем.
    # ⚠️ Однословные имена с вики пропускаем через тот же признак, что и
    # локации из боковой панели: слово, которое в НАШИХ текстах постоянно
    # встречается со строчной, — обычное существительное, а не имя.
    #
    # Без этого проверка перевода дала 18 «испорченных имён» на ровном месте:
    # «Mayor of SkyBlock» → «мэром SkyBlock» и «Museum Donations» →
    # «Пожертвования в музей» — правильные переводы, забракованные потому,
    # что «Mayor» и «Museum» пришли с вики как имена. Та же беда, что была
    # с «Farm», оказавшимся глаголом «выращивай».
    def from_wiki(name: str) -> bool:
        # ⚠️ Берём ТОЛЬКО составные имена. Однословные с вики защищать нельзя:
        # надёжного признака «имя или обычное слово» для них не нашлось.
        #
        # Пробовал два, оба врут:
        #   * «часто пишется со строчной» — «Mayor» и «Museum» в оригинале
        #     ВСЕГДА с заглавной, счётчик нулевой, и они проходят как имена;
        #   * «стоит с артиклем» — ловит Mayor и Museum, но заодно Jerry (14
        #     совпадений) и Taylor (13), а Frosty и Coral пропускает.
        #
        # Цена ошибки тут высокая и односторонняя: защитив «Mayor», мы ломаем
        # правильный перевод «избран мэром SkyBlock» в 16 местах сразу.
        # А однословные имена и так попадают в защиту из дампа, когда игрок
        # заговорит с персонажем: источник «[NPC] Имя:» однозначен, в отличие
        # от списка на вики.
        # ⚠️ Притяжательную форму не защищаем: «Taylor's Cosmetics» по-русски
        # становится «косметикой Taylor» — имя на месте, а окончание 's
        # отпадает, потому что в русском притяжательность передаёт падеж.
        # Защитив «Taylor's», мы объявили бы правильный перевод порчей имени.
        if name.endswith("'s") or name.endswith("s'"):
            return False
        if name in AMBIGUOUS:
            return False
        # ⚠️ «ДОЛЖНОСТЬ + Имя» не защищаем целиком: по-русски должность
        # переводится, а имя остаётся — «Mayor Finnegan» → «мэра Finnegan»,
        # и это правильно. Защищённой связкой мы объявили бы такой перевод
        # порчей имени. Само имя при этом защищено отдельно.
        return not TITLE_PREFIX.match(name)

    for path, group, key in ((WIKI_PLACES, "location", "locations"),
                             (WIKI_DIALOGUES, "npc", None)):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if key:
            for name in data.get(key) or []:
                if from_wiki(name):
                    add(group, name)
        else:
            # Имя говорящего берём из самих реплик: там оно названо прямо,
            # без догадок по колонкам таблицы.
            #
            # ⚠️ Но чистим: в разметке вики попадаются обрывки — «&Pearl Dealer»
            # (недоснятый цветовой код), «----» (линия таблицы), «Einary§f».
            # Защитив такое, мы завели бы в списке слова, которых в игре нет,
            # а «----» ещё и совпал бы с разделителем в подсказках.
            for item in (data.get("lines") or {}).values():
                who = (item or {}).get("npc", "").strip()
                if (who and re.fullmatch(r"[A-Za-z][A-Za-z0-9 '\-.]{1,32}", who)
                        and from_wiki(who)):
                    add(group, who)

    for dump in DUMPS:
        if not dump.exists():
            continue
        try:
            data = json.loads(dump.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # ⚠️ Берём строки ПО ИСТОЧНИКУ, а не по форме.
        # Сперва я ловил локации по виду «значок + Слово» во всех источниках —
        # и нахватал типов мобов (Undead, Arthropod, Animal): в описаниях
        # предметов они пишутся так же. А их переводить как раз нужно.
        # Источник записан в дампе явно, гадать по форме незачем.
        sources = data.get("sources") or {}
        for line in sources.get("chat", {}):
            npc = NPC_LINE.match(line)
            if npc:
                add("npc", npc.group(1).strip())
        for line in sources.get("scoreboard", {}):
            place = LOCATION_LINE.match(line)
            # ⚠️ Локацию проверяем `looks_like_name`, как имена из name_tag
            # и из подсветки. Без этого в защищённые попадали ОБЫЧНЫЕ СЛОВА:
            # Bank, Farm, Village, Mountain, Blacksmith — по-английски это
            # и места, и просто существительные.
            #
            # Ломается на них тот самый признак заглавной буквы, на котором
            # стоит проект: в НАЧАЛЕ ПРЕДЛОЖЕНИЯ с большой пишется любое слово.
            # «Farm in-season crops to help season the Communal Stew» — тут
            # «Farm» глагол «выращивай», а проверка `check_block` объявляла
            # правильный перевод порчей имени и браковала абзац целиком.
            #
            # Замер: из 50 локаций отсеиваются ровно 5, и все пятеро в наших
            # же текстах чаще пишутся со строчной (Bank 28 раз, Farm 13).
            # Настоящие места — Birch Park, Catacombs, Coal Mine — остаются,
            # их со строчной не пишут никогда.
            #
            # ⚠️ К группе `npc` тот же фильтр применять НЕЛЬЗЯ: он режет всё
            # короче четырёх букв, а среди NPC есть Sam, Pat, Liz, Zog —
            # настоящие имена, и потерять их дороже. Там источник и надёжнее:
            # «[NPC] Имя:» прямо говорит, что это персонаж, тогда как локация
            # опознана ПО ФОРМЕ надписи в боковой панели.
            if place and looks_like_name(place.group(1).strip()):
                add("location", place.group(1).strip())
        for line in sources.get("name_tag", {}):
            # Мобов отсекаем по «[Lv..]» и по числам: у них уровень и здоровье,
            # у NPC — только имя. Переводить типы мобов как раз нужно.
            tag = line.strip()
            if NAME_TAG.match(tag) and looks_like_name(tag):
                add("npc", tag)

    known = translated_terms()
    for file in HIGHLIGHTS:
        if not file.exists():
            continue
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for name, count in (data.get("names") or {}).items():
            if not looks_like_name(name) or name in known:
                # ⚠️ Уже переводится словарём — значит это НЕ имя, а термин,
                # который Hypixel просто выделил цветом. Свой словарь важнее:
                # иначе одно подсвеченное «Defense» запретило бы переводить
                # характеристику по всему проекту.
                continue
            # ⚠️ ДВОЙСТВЕННЫЕ СЛОВА не защищаем и здесь. Список AMBIGUOUS
            # заводился ровно против этой беды, но стоял только на именах
            # с вики — а «Museum» пришло ПОДСВЕТКОЙ и защиту всё равно
            # получило: `looks_like_name` его пропускает (Hypixel пишет
            # такие слова всегда с заглавной, счётчик «часто со строчной»
            # нулевой — это в комментарии к AMBIGUOUS и записано).
            #
            # Итог: правильные переводы «Museum Donations» → «Пожертвования
            # в музей» шли в СЛОМАНО, и круг сборки вставал на них.
            #
            # ⚠️ Из групп фильтруем ТОЛЬКО подсветку: она говорит «это имя
            # собственное», но не говорит чьё, — источник самый слабый.
            # У «[NPC] Frosty:» источник однозначен, и там AMBIGUOUS не
            # применяется: настоящий Frosty остаётся защищённым.
            if name in AMBIGUOUS:
                continue
            add("highlight", name)

    # ⚠️ Имя, встреченное двумя путями, принадлежит БОЛЕЕ ТОЧНОМУ источнику.
    #
    # Названное в ALWAYS_GROUPS руками — точнее всего: там мы знаем, что это.
    # Надпись над головой (name_tag) висит и над NPC, и над табличкой места,
    # поэтому «Birch Park» приезжал оттуда как NPC, хотя он локация. Пока всё
    # лежало общей кучей, ошибка была не видна вовсе — группы её показали.
    for group, names in ALWAYS_GROUPS.items():
        for other in groups:
            if other != group:
                groups[other] -= names

    # Подсветка цветом говорит «это имя собственное», но не говорит, чьё.
    # Поэтому «highlight» уступает любой группе, где слово уже названо.
    named = {name for group, names in groups.items() if group != "highlight"
             for name in names}
    groups["highlight"] = {name for name in groups.get("highlight", set())
                           if name not in named}

    return {group: {name for name in names if name and name not in NOT_NAMES}
            for group, names in groups.items()}


# Разбор шаблона на составные части: группа, экранированный символ, чистый термин
GROUP = re.compile(r"\((?:[^()\\]|\\.)*\)")
ESCAPED = re.compile(r"\\(.)")
PLAIN_TERM = re.compile(r"[A-Za-z][A-Za-z' ]{1,40}")


def term_of_rule(pattern: str) -> str | None:
    """
    Вытаскивает термин из шаблона правила: получить «Held Item» из шаблона,
    который матчит строку «Held Item:».

    ВНИМАНИЕ. Без этого список «что уже переводится» был неполон, и половина
    характеристик считалась именами собственными. Подписи и зачарования живут
    ИМЕННО в секции regex, а фильтр читал только exact и glossary — поэтому
    «Held Item», «Fishing Wisdom», «Aquatic» попадали в защищённые, и хороший
    перевод отбраковывался как «испортил имя». 190 таких на корпусе.
    """
    text = pattern[1:] if pattern.startswith("^") else pattern
    text = GROUP.sub("", text)          # выкидываем скобочные группы
    text = ESCAPED.sub('\\1', text)      # снимаем экранирование
    text = text.rstrip("$").strip().rstrip(":").strip()
    return text if PLAIN_TERM.fullmatch(text) else None


# Строка редкости в подсказке: «COMMON RABBIT», «✿ SHINY MYTHIC HELMET».
# Hypixel печатает её заглавными у КАЖДОГО настоящего предмета.
RARITY_LINE = re.compile(
    r"^(?:✿ )?(?:SHINY )?(?:COMMON|UNCOMMON|RARE|EPIC|LEGENDARY|MYTHIC"
    r"|DIVINE|SPECIAL|VERY SPECIAL|ADMIN)\b")

# Списки имён из чужих репозиториев (tools/fetch_items.py, fetch_neu.py)
ITEM_LISTS = [
    ROOT / "data" / "en" / "item_names.txt",
    ROOT / "data" / "en" / "neu_names.txt",
]

# Подсказки блоками: заголовок + строки. Оттуда берём признак редкости.
TOOLTIPS = [
    Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/tooltips.json"),
    ROOT / "data" / "work" / "lore_tooltips.json",
]

_REAL_ITEMS: set[str] | None = None


def real_items() -> set[str]:
    """
    Имена НАСТОЯЩИХ предметов — тех, что ищут на аукционе и в базаре.

    ⚠️ Заголовок подсказки — это НЕ всегда имя предмета. У кнопки в меню
    заголовок тоже есть: «Weapons», «Shards», «Enchantments», «Personal Bests»,
    «Slayer». Такие слова переводить как раз нужно, а защита имени бракует
    хороший перевод — 8 абзацев из 47 в одном заходе.

    Признаков два, и по отдельности каждый врёт:
      * список предметов из чужих репозиториев знает «Enchanted Book»
        и «Diamond Sword», но НЕ знает кроликов Chocolate Factory — а «Dash»
        защищать обязательно, иначе он станет «Рывком», то есть другим кроликом;
      * строка редкости в подсказке («COMMON RABBIT») ловит кроликов и почти
        всё остальное, но её нет у ванильной «Anvil».
    Вместе они дают полное покрытие: предмет — если хоть один признак сработал.

    ⚠️ Приём «словарь его переводит — значит не имя» (как в resolve_collisions)
    тут НЕ годится: словарь переводит и «Enchanted Book» (935 абзацев корпуса),
    и «Diamond Sword» — через переключаемый словарь ванильных названий. Снять
    с них защиту значило бы перевести имена, по которым ищут на аукционе.
    """
    global _REAL_ITEMS
    if _REAL_ITEMS is not None:
        return _REAL_ITEMS
    names: set[str] = set()
    for path in ITEM_LISTS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            cleaned = re.sub(r"[\ue000-\uf8ff]", "", line).strip()
            if cleaned:
                names.add(cleaned)
    for path in TOOLTIPS:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for block in _tooltip_blocks(data):
            title = (block.get("item") or "").strip()
            lines = block.get("lines") or []
            if title and any(RARITY_LINE.match(str(line).strip()) for line in lines):
                names.add(title)
    # ⚠️ КАНОНИЧЕСКИЙ список от самого Hypixel — каталог предметов плюс NBT
    # живых аукционов (`tools/fetch_item_names.py`). Он не эвристика, в отличие
    # от двух признаков выше: сервер прямо говорит, что это предмет.
    #
    # Замер 29.07: 6227 имён, из них защита не знала 367 — прокачанные варианты
    # («Ancient Burning Crimson Boots ✪✪✪✪✪», «Absolutely Perfect Boots -
    # Tier XII»). Собранные признаки их не видели, потому что мод такие вещи
    # на экране не встречал: они лежат у других игроков.
    names.update(_names_from_server())
    _REAL_ITEMS = names
    return names


def _names_from_server() -> set[str]:
    """Имена предметов из каталога Hypixel и NBT аукциона."""
    path = ROOT / "data" / "work" / "item_names.json"
    if not path.exists():
        return set()
    try:
        rows = json.loads(path.read_text(encoding="utf-8")).get("names") or {}
    except (json.JSONDecodeError, OSError):
        return set()
    return {name for name in rows.values() if isinstance(name, str) and name.strip()}


def _tooltip_blocks(data) -> list[dict]:
    """Блоки подсказок из файла любой из двух раскладок (дамп и корпус NEU)."""
    found: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("lines"), list):
                found.append(node)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                if isinstance(value, (dict, list)):
                    walk(value)

    walk(data)
    return found


def translated_terms() -> set[str]:
    """Что УЖЕ переводится словарём — источник правды о переводимом."""
    packs = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
    terms = set()
    for path in packs.rglob("*.json"):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for section in ("exact", "glossary"):
            terms.update(k for k, v in (pack.get(section) or {}).items() if v)
        for rule in pack.get("regex") or []:
            term = term_of_rule(rule.get("p", ""))
            if term:
                terms.add(term)
    return terms


def resolve_collisions(words: set[str], quiet: bool = False) -> set[str]:
    """
    Убирает из защиты слова, которые словарь переводит.

    Живой пример: «Foraging» — навык, и он переводится («Лесозаготовка»),
    а «Foraging Camp» — локация, и её трогать нельзя. Одно слово внутри
    другого, правила противоположные. Разводим по явному признаку: есть
    запись в словаре — значит переводится, защите там делать нечего.
    Слова из ALWAYS сильнее словаря: их защищали по прямой просьбе.
    """
    dictionary = translated_terms()
    clashing = {w for w in words if w in dictionary and w not in ALWAYS}
    if clashing and not quiet:
        print("не защищаю (словарь их переводит): " + ", ".join(sorted(clashing)))
    return words - clashing


def as_prompt(words: set[str]) -> str:
    """Кусок запроса к модели со списком неприкосновенных слов."""
    listed = ", ".join(sorted(words))
    return ("НЕ ПЕРЕВОДИТЬ (имена NPC, названия мест, валюты) — переносить в перевод\n"
            "БУКВА В БУКВУ, даже если рядом стоит переводимое слово:\n" + listed)


def mentions(text: str, word: str) -> bool:
    """
    Слово встречается как ОТДЕЛЬНОЕ слово, а не куском другого.

    ⚠️ Раньше тут была простая подстрока — и она врала в обе стороны.
    «Gems» находится внутри «Gemstones», поэтому правильный перевод
    «Gemstone Collection» → «Коллекция самоцветов» считался порчей
    защищённого имени и блок отбраковывался целиком. Та же беда у NPC
    Sam внутри «Same color» и Pat внутри «Pathfinder»: на корпусе абзацев
    это 33 записи, выброшенные ни за что.

    Границу проверяем по латинским буквам, а не через \\b: имена бывают
    из двух слов («Foraging Camp»), а после имени легко идёт апостроф
    или кириллица — и то и другое границей быть обязано.
    """
    return re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", text) is not None


def check_block(source: list[str], translated: list[str], words: set[str]) -> list[str]:
    """
    Какие защищённые слова пропали при переводе.

    Ищем только те, что реально были в оригинале: список общий на весь корпус,
    и требовать наличия всех слов в каждой строке бессмысленно.
    """
    lost = []
    src = "\n".join(source)
    ru = "\n".join(translated)
    for word in words:
        # ⚠️ ДЕШЁВЫЙ ОТСЕВ ПЕРЕД ДОРОГИМ. `mentions` — регулярка с проверкой
        # границ, и она вызывалась для КАЖДОГО из 991 защищённого имени
        # на каждый абзац: 6.4 млн запусков regex. На корпусе из 6418 абзацев
        # это 394 секунды — 94% всего времени `check_translation` и почти весь
        # круг сборки (6 минут).
        #
        # Логику это не меняет: `mentions` ищет слово с границами, а значит
        # без вхождения ПОДСТРОКОЙ оно найтись не может. Проверка `in` идёт
        # в C и отсеивает подавляющее большинство имён сразу.
        if word not in src:
            continue
        if mentions(src, word) and not mentions(ru, word):
            lost.append(word)
    return lost


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    words = resolve_collisions(collect())
    print(f"защищённых слов: {len(words)}")
    for word in sorted(words):
        print(f"  {word}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
