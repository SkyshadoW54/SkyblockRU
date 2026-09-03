"""
Чек-листы Hypixel: знак состояния ✔/✖ входит в КЛЮЧ, и это удваивало покупку.

Беда, которую это лечит. Hypixel помечает выполненные пункты значком ✔,
а невыполненные ✖ — задания, настройки, виджеты таба, требования музея:

    ✔ Собери Birch Logs. ({n}/{n})
    ✖ Collect Dark Oak Logs. ({n}/{n})      <- та же фраза, английская

Строка приходит СО ЗНАКОМ, поэтому «✔ X» и «✖ X» для словаря — две разные
записи. Их и покупали по отдельности, в разные вечера и разными словами:

    ✔ Пройди Campfire Trials. ({n}/{n})
    ✖ Заверши Campfire Trials. ({n}/{n})    <- соседняя строка того же списка

Замер 17.08 по дампу и строкам игроков: 1144 строки семьи, 978 разных хвостов,
у 166 встречены ОБА знака. Из них 30 оплачены наполовину, а 13 переведены
по-разному — то есть игрок видит разнобой столбиком.

Что делает этот скрипт: собирает переводы, ОТРЫВАЕТ от них знак и выдаёт
обе формы разом. Одна покупка — обе половины, и разнобоя больше не будет.

⚠️ ПОЧЕМУ НЕ ОДНО ПРАВИЛО «^([✔✖]) (.+)$» с tg, хотя оно напрашивается.
Проверено по коду: `Translator.lookup` возвращает совпадение, КАК ТОЛЬКО
правило подошло, — даже если текст не изменился ни на знак. А раз перевод
«найден», `TextTranslator` не зовёт `UnknownStrings.record`, и строка
перестаёт попадать в дамп. Широкое правило сделало бы невидимыми 709
непереведённых строк семьи: работы не видно ни в отчёте, ни в очереди.
Это записанная грабля проекта про фильтр, который прячет работу, — здесь
она стоила бы вчетверо дороже. Точные записи такого не делают: не нашлось —
строка честно уходит в дамп.

⚠️ РАЗНОБОЙ СВОДИМ ПО ДАННЫМ, а не на вкус. Механически решается только
точка в конце (её берём по ОРИГИНАЛУ). Остальное решено голосованием
по всем 41 041 паре словаря — какой глагол проект уже выбрал:
    Complete -> «Пройди»    58 против 28 «Выполняй» и 4 «Заверши»
    Reach    -> «Достигни»  95 против 5 «Дойди»
    Coins    -> «монеты»    118 против 15 (там имена предметов)

⚠️ Словарь идёт с ПРИОРИТЕТОМ 5, то есть ВЫИГРЫВАЕТ у 90-from-game (10):
у секции `exact` побеждает МЕНЬШИЙ priority. Так и задумано — иначе
сведённый разнобой не доехал бы до экрана. Печатается, что именно
перебивается и чем: пересборка обязана давать тот же текст.

⚠️ Источник правды — ЭТОТ СКРИПТ, а не собранный json: пополнил очередь
переводами, перезапусти его, иначе словарь отстанет.

Запуск:
  python tools/gen_checklist.py            сухой прогон (по умолчанию)
  python tools/gen_checklist.py --write    записать словарь
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

PACK = (ROOT / "src" / "main" / "resources" / "assets" / "skyblockru"
        / "packs" / "ru_ru" / "42-checklist.json")
INDEX = (ROOT / "src" / "main" / "resources" / "assets" / "skyblockru"
         / "packs" / "index.json")
QUEUE = ROOT / "data" / "work" / "from_game.json"
ARCHIVE = ROOT / "data" / "work" / "queue_archive.json"
PLAYERS = ROOT / "data" / "work" / "from_players.json"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")

DONE = "\u2714"   # ✔ выполнено
TODO = "\u2716"   # ✖ не выполнено
MARKS = (DONE, TODO)
ENDS = (".", "!", "?")

PRIORITY = 5

# ⚠️ Разнобой, который машиной не разрешить: разошлись СЛОВА, а не пунктуация.
# Каждый выбор подтверждён голосованием по словарю (см. шапку) либо
# согласием с уже купленным АБЗАЦЕМ, где эта строка стоит в составе.
DECISIONS = {
    # Complete -> «Пройди»: 58 против 28 и 4
    "Complete Campfire Trials. ({n}/{n})": "Пройди Campfire Trials. ({n}/{n})",
    "Complete The Woods Race in {n}m.": "Пройди The Woods Race за {n} мин.",
    # Reach -> «Достигни»: 95 против 5
    "Reach checkpoint {n}.": "Достигни контрольной точки {n}.",
    # Coins -> «монеты» (118 против 15), глагол — как в купленном абзаце
    # «✔ Поговори с Banker. ✔ Внеси монеты в Bank.»
    "Deposit Coins in the Bank.": "Внеси монеты в Bank.",
    # то же: строка стоит внутри купленного абзаца про кузнеца
    "Mine coal. ({n}/{n})": "Добудь уголь. ({n}/{n})",
    # ⚠️ имя не склоняется, падеж берёт русская подпорка — правило проекта
    "Travel to The Park behind the Forest.":
        "Отправляйся в The Park за локацией Forest.",
    # обрывок фразы «to the Redstone Merchant»: слова, которого на строке нет,
    # не выдумываем
    "Give {n} Redstone to the Redstone": "Отдай {n} Redstone для Redstone",
    # ⚠️ категории существ — как в 46-mob-categories: там 19 согласованных
    # записей в единственном числе, у нас было 3 разрозненных во множественном.
    # Большинство и однородность за соседним словарём.
    # ⚠️ разнобой 25.08 — оба варианта я завёл сам при ручном переводе.
    # Берём тот, что уже стоял в соседнем словаре: его игрок видит
    # на кнопках меню, и он старше.
    "Leave the area.": "Покинь область.",
    # Garden — защищённое имя, падеж берёт русская подпорка «уровня»
    "Reach Garden Level IV. ({n}/{n})":
        "Достигни уровня Garden IV. ({n}/{n})",
    "\ue074 Arthropod": "\ue074 Членистоногий",
    "\ue076 Cubic": "\ue076 Кубический",
    "\ue081 Skeletal": "\ue081 Костяной",
    " Ender": " Эндерский",
}


# ⚠️ Хвосты, которых в очереди НЕТ и не будет в ближайшее время: строку
# прислали меньше трёх человек, и порог `make_queue` её не пускает. Порог
# верный (строка от одного человека — чаще его собственная комбинаторика),
# но эти два виджета законны и переведены заодно с двадцатью четырьмя
# соседями — держать их английскими значило бы завести разнобой в одном
# столбце меню.
EXTRA = {
    "Essence Widget": "Виджет эссенции",
    "Slayer Widget": "Виджет истребителя",
    # ⚠️ Эти две — НАСТРОЙКИ, а не характеристики, но `split_sb_stats`
    # утащил их в выключенный 78-sb-stats: в ключе стоит жаргонное слово
    # («Pristine», «Ferocity»). Оттуда мы их не берём (см. collect), поэтому
    # перевод стоит здесь. ⚠️ «Чистый чат» из того словаря НЕВЕРЕН по смыслу:
    # это чат о срабатывании Pristine, а сам термин везде английский.
    "Pristine Chat": "Чат Pristine",
    "Ferocity Sounds": "Звуки Ferocity",
}


def marked(text: object) -> bool:
    return isinstance(text, str) and text[:1] in MARKS


def tail_of(text: str) -> str:
    return text[1:].lstrip()


def seen_lines() -> set[str]:
    """Все строки семьи, которые МОД РЕАЛЬНО ВИДЕЛ — наш дамп и строки игроков."""
    out: set[str] = set()
    for path in (DUMP / "collected.json", PLAYERS):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for items in (data.get("sources") or data).values():
            if isinstance(items, dict):
                out |= {s for s in items if marked(s)}
    return out


def pick(tail: str, variants: list[str]) -> str:
    """Один перевод на обе половины.

    Решаем в три шага, и первые два — по данным:
      1. руками (DECISIONS) — там, где разошлись СЛОВА;
      2. точка в конце — по ОРИГИНАЛУ: есть у него, есть и у нас;
      3. иначе первый по порядку (переводы совпадают, выбирать нечего).
    """
    if tail in DECISIONS:
        return DECISIONS[tail]
    uniq = list(dict.fromkeys(variants))
    if len(uniq) == 1:
        return uniq[0]
    want_dot = tail.rstrip().endswith(ENDS)
    for variant in uniq:
        if variant.rstrip().endswith(ENDS) == want_dot:
            return variant
    return uniq[0]


def collect() -> tuple[dict[str, str], list[tuple[str, list[str]]]]:
    """Хвост -> перевод. Второй список — разнобой, который решать глазами."""
    import status

    # ⚠️ СВОЙ ВЫХОД НЕ СПРАШИВАЕМ. Иначе генератор находит там собственные
    # прошлые записи, считает их источником и застывает: правка в очереди
    # перестаёт доезжать, а ошибочная запись поддерживает сама себя.
    # Ровно так `gen_headers` обнулил 1385 заголовков, а `split_sb_stats` —
    # 242 характеристики. Замер здесь: без исключения «перевод знал голый
    # хвост» падало с 71 до 0 — то есть шаг 3 переставал работать вовсе.
    dic = status.Dictionaries(without={PACK.name})
    variants: dict[str, list[str]] = {}

    def note(key: str, value: str) -> None:
        if not marked(key) or not isinstance(value, str) or not value.strip():
            return
        if not marked(value):
            return          # знак в переводе битый — такую запись не берём
        variants.setdefault(tail_of(key), []).append(tail_of(value))

    # 1. записи со знаком из словарей мода, кроме своего (см. выше)
    #
    # ⚠️⚠️ И КРОМЕ КОРПУСА АБЗАЦЕВ — иначе выходит КРУГ, который съедает
    # переводы. `merge_paragraphs` не кладёт в `96-paragraphs.exact` ключи,
    # которые уже лежат точной записью в ДРУГОМ словаре. Стоит нам забрать
    # оттуда склеенный абзац («✖ Requirement {n}/{n} Find {n} duplicate
    # Rabbits.» — это ДВЕ строки подсказки), и следующая пересборка корпуса
    # выбросит его как «есть у соседа», а мы к тому времени соберёмся заново
    # уже без него. Замер: так пропало 55 переводов, и заметила это только
    # сверка с git — сторожа на «словарь вдруг похудел» в проекте нет.
    #
    # Наше дело — ПОСТРОЧНЫЕ записи; абзацы живут своим путём и знак ✔/✖
    # внутри них не мешает: мод спрашивает корпус целым ключом.
    SKIP = {PACK.name, "96-paragraphs.json"}
    import packs
    for pack in packs.load():
        if pack.path.name in SKIP:
            continue
        # ⚠️ ВЫКЛЮЧЕННЫЙ СЛОВАРЬ НЕ ЧИТАЕМ. «Выключен» — это решение игрока
        # НЕ ПЕРЕВОДИТЬ, а не «перевода нет»: вытащив запись оттуда, мы
        # проводим её в обход решения. Замер поймал две («Pristine Chat»,
        # «Ferocity Sounds»): их утащил в 78-sb-stats `split_sb_stats`,
        # потому что в ключе стоит жаргонное слово, — и мой генератор
        # вынес их обратно наружу. Записанная грабля проекта, повторённая
        # уже в четвёртом инструменте.
        if not pack.enabled:
            continue
        for key, value in (pack.exact or {}).items():
            note(key, value)

    # 2. и из рабочих файлов очереди: там перевод появляется раньше словаря
    for path in (QUEUE, ARCHIVE):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for section in ("exact", "ru"):
            for key, value in (data.get(section) or {}).items():
                note(key, value)

    pairs: dict[str, str] = {}
    clashes: list[tuple[str, list[str]]] = []
    for tail, found in variants.items():
        uniq = list(dict.fromkeys(found))
        chosen = pick(tail, found)
        if len(uniq) > 1 and tail not in DECISIONS:
            same_but_dot = len({v.rstrip(".") for v in uniq}) == 1
            if not same_but_dot:
                clashes.append((tail, uniq))
                continue
        pairs[tail] = chosen

    # 3. хвост, чей перевод словарь знает БЕЗ знака: «✔ Defense» -> «✔ Защита».
    #    Тут знак просто мешал совпасть, покупать было нечего.
    #
    # ⚠️ Сюда попадает и результат ПРАВИЛ («Combat Skill IV» -> «Навык Combat IV»),
    # то есть он застывает точной записью. Поправят правило — запись отстанет,
    # поэтому генератор и надо гонять в круге сборки, а не «когда вспомню».
    global FROM_BARE
    FROM_BARE = 0
    for line in seen_lines():
        tail = tail_of(line)
        if tail in pairs:
            continue
        # ⚠️ РЕШЕНИЕ СИЛЬНЕЕ НАХОДКИ. Раньше DECISIONS спрашивался только
        # в pick() — то есть на шаге 1, где вариантов несколько. А хвост,
        # у которого перевод ровно один, приходил сюда и молча побеждал:
        # 25.08 так «Эндерский» из 46-mob-categories заменялся на «Эндер».
        if tail in DECISIONS:
            pairs[tail] = DECISIONS[tail]
            continue
        hit = status.lookup(tail, dic)
        if hit and hit[0] and hit[0] != tail:
            pairs[tail] = hit[0]
            FROM_BARE += 1

    # 4. ГОЛЫЕ переводы КНОПОК из очереди и архива.
    #
    # ⚠️ Без этого шага выходит круг, и он уже съел две строки. Заголовок
    # кнопки («Inventory Full Notifications») знака не имеет вовсе, поэтому
    # шаги 1–3 его не видят: они ищут записи СО ЗНАКОМ либо хвосты семьи.
    # А как только мы кладём его голой формой, `make_queue` считает строку
    # закрытой и убирает ключ из очереди — и на следующей пересборке брать
    # перевод уже неоткуда. Спасает АРХИВ: он не чистится по построению,
    # ровно для таких случаев и заведён.
    keys = buttons()
    for path in (QUEUE, ARCHIVE):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for section in ("exact", "ru"):
            for key, value in (data.get(section) or {}).items():
                if not isinstance(key, str) or marked(key):
                    continue
                if key not in keys or not isinstance(value, str) or not value.strip():
                    continue
                pairs.setdefault(key, value)

    for tail, ru in EXTRA.items():
        pairs.setdefault(tail, ru)

    return pairs, clashes


FROM_BARE = 0


# ⚠️ ЖЕЛЕЗНЫЙ ПРИЗНАК НАСТРОЙКИ, и его даёт САМ СЕРВЕР: Hypixel пишет
# «X is now enabled!» только про ПЕРЕКЛЮЧАЕМЫЕ настройки. Имени предмета
# в такой строке не бывает по построению.
#
# Понадобился, потому что одного `menu_title` мало: он набирается медленно
# (у нас 10 строк), и «Play Music» в него не попал — перевод куплен, а на
# экране английский. А снять признак совсем НЕЛЬЗЯ: замер показал, что тогда
# голой формой уехали бы «Bee Pet» -> «Питомец Bee» и «Common Dolphin Pet»,
# то есть ИМЕНА, по которым ищут на аукционе. Каталог сервера их не знает,
# так что второй признак («не имя») их не ловит.
TOGGLED = re.compile(r"^(.+) is now (?:enabled|disabled)!$")


def buttons() -> set[str]:
    """Заголовки, которые ТОЧНО не имя вещи, а подпись кнопки.

    Два источника, и оба от сервера:
      * `menu_title` — `core/Titles.java` назвал строку кнопкой (у вещи
        в блоке подсказки есть строка редкости, у кнопки нет);
      * имя из «X is now enabled!» — так Hypixel сообщает о переключении
        настройки, и вещей там не бывает.
    """
    out: set[str] = set()
    for path in (DUMP / "collected.json", PLAYERS):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        sources = data.get("sources") or data
        out |= {s for s in (sources.get("menu_title") or {}) if isinstance(s, str)}
        for items in sources.values():
            if not isinstance(items, dict):
                continue
            for line in items:
                if not isinstance(line, str):
                    continue
                found = TOGGLED.match(line)
                if found:
                    out.add(found.group(1))
    return out


def build(pairs: dict[str, str]) -> dict[str, str]:
    """Каждому хвосту — ОБЕ формы со знаком, а кнопке ещё и ГОЛУЮ.

    ⚠️ ЗАЧЕМ ГОЛАЯ. Пункт меню приходит ДВАЖДЫ: строкой списка со знаком
    («✔ Player Trading») и ЗАГОЛОВКОМ подсказки без него («Player Trading»).
    Мы закрывали только первую — игрок открыл настройки и увидел русский
    список над английским заголовком. Нашёл это он, а не сторож.

    ⚠️ Голую форму кладём ТОЛЬКО кнопкам, и признаков нужно ДВА. Одного
    «встретилось как menu_title» мало: `Titles` ошибается в безопасную
    сторону, и ванильная вещь без строки редкости («Crafting Table»,
    «Booster Cookie») тоже зовётся кнопкой. Голая запись перевела бы ИМЯ,
    по которому ищут на аукционе, — поэтому второй признак снимает всё,
    что каталог сервера знает как предмет либо что лежит в защищённых.
    Замер: из 10 заголовков экрана настроек 4 закрылись даром, 3 имени
    отсеяны, 3 остались работой.
    """
    import protected

    keys = buttons()
    known = protected.real_items() | protected.collect()

    exact: dict[str, str] = {}
    for tail, ru in sorted(pairs.items()):
        if ru == tail:
            continue                      # тождественная запись бесполезна
        for mark in MARKS:
            exact[f"{mark} {tail}"] = f"{mark} {ru}"
        if tail in keys and tail not in known:
            exact[tail] = ru
    return exact


def overrides(exact: dict[str, str]) -> list[tuple[str, str, str, str]]:
    """Что мы перебиваем у соседей (priority 5 выигрывает) и чем именно."""
    import packs

    out = []
    for pack in packs.load():
        if pack.path.name in (PACK.name, "96-paragraphs.json"):
            continue
        for key, value in (pack.exact or {}).items():
            if key in exact and value != exact[key]:
                out.append((key, value, exact[key], pack.path.name))
    return out


def register() -> bool:
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    files = data["languages"]["ru_ru"]
    if PACK.name in files:
        return False
    files.append(PACK.name)
    files.sort()
    INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true",
                        help="записать словарь (по умолчанию сухой прогон)")
    parser.add_argument("--show", type=int, default=12)
    args = parser.parse_args()

    pairs, clashes = collect()
    exact = build(pairs)
    seen = seen_lines()

    print("хвостов с переводом: %d  (из них %d — перевод знал ГОЛЫЙ хвост,"
          " знак просто мешал совпасть)" % (len(pairs), FROM_BARE))
    print("записей в словаре:   %d  (по две на хвост)" % len(exact))
    covered = sum(1 for line in seen if line in exact)
    print("строк семьи из игры: %d, закрывается словарём: %d"
          % (len(seen), covered))

    hits = overrides(exact)
    print("\n=== ПЕРЕБИВАЕТ соседей: %d ===" % len(hits))
    print("    Тут и сводится разнобой. Каждая строка обязана быть осознанной:")
    for key, was, now, where in hits[:args.show]:
        print("   %r  [%s]" % (key, where))
        print("      было:  %r" % was)
        print("      стало: %r" % now)
    if len(hits) > args.show:
        print("   ... ещё %d" % (len(hits) - args.show))

    if clashes:
        print("\n=== РЕШИТЬ ГЛАЗАМИ (разошлись слова): %d ===" % len(clashes))
        print("    Впиши выбор в DECISIONS — машина тут не судья.")
        for tail, uniq in clashes[:args.show]:
            print("   %r" % tail)
            for variant in uniq:
                print("      %r" % variant)

    if not args.write:
        print("\nсухой прогон: ничего не записано (--write запишет)")
        return 1 if clashes else 0

    pack = {
        "id": "checklist",
        "priority": PRIORITY,
        "_comment": (
            "Чек-листы Hypixel: знак состояния ✔/✖ входит в КЛЮЧ, поэтому "
            "«✔ X» и «✖ X» — две разные записи, и покупались они порознь "
            "(13 пар успели разъехаться в переводе). Собирается "
            "tools/gen_checklist.py: он снимает знак, сводит разнобой и "
            "выдаёт ОБЕ формы разом — править надо СКРИПТ, а не этот файл. "
            "priority 5 ниже, чем у 90-from-game (10), нарочно: у exact "
            "побеждает МЕНЬШИЙ, иначе сведённый разнобой не доехал бы "
            "до экрана. Одним широким правилом это не делается — совпавшее "
            "правило гасит запись строки в дамп, и 709 непереведённых строк "
            "стали бы невидимы."
        ),
        "exact": exact,
    }
    PACK.parent.mkdir(parents=True, exist_ok=True)
    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print("\nзаписано: %s (%d записей)" % (PACK.name, len(exact)))
    if register():
        print("вписан в index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
