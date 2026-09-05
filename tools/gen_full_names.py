# -*- coding: utf-8 -*-
"""Имена NPC и локаций, оставшиеся английскими ВНУТРИ русского перевода.

    python tools/gen_full_names.py            покажет
    python tools/gen_full_names.py --write    соберёт 02-full-names.json

⚠️ ЗАЧЕМ. Строка переведена ЦЕЛИКОМ вместе с английским именем внутри
(«Мэр Diana», «Отправься в Savanna Woodland»), и такая точная запись лежит
в ОБЫЧНОМ словаре. `exact` движок ищет раньше правил, а у `exact` побеждает
МЕНЬШИЙ priority — значит режимный `82-npc-places` (62) до дела не доходит,
хотя «Диана» и «Саванновый лес» лежат в нём готовыми. Замер 25.08: 1464 строки.

⚠️ PRIORITY 2 — НИЖЕ ВСЕХ, включая `03-full-jargon` (3) и `42-checklist` (5).
Иначе режимная версия снова проиграет обычной записи.

⚠️ ПАДЕЖ МАШИНОЙ НЕ ВЫВОДИТСЯ — записанное правило проекта. Поэтому берём
ТОЛЬКО позиции, где имя стоит в ИМЕНИТЕЛЬНОМ, и это видно по соседу:
  * префикс реплики «[NPC] Имя:» — 499 строк;
  * имя в САМОМ начале строки («Scorpius избран мэром») — 96;
  * сразу после двоеточия или должности («Область: Hub», «Мэр Diana») — 92.
Всё остальное («в Savanna Woodland», «с Blacksmith», «рецепт X») требует
падежа и сюда НЕ БЕРЁТСЯ — там нужен человек.
"""
import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import status  # noqa: E402
import check_nicknames  # noqa: E402
# ⚠️⚠️ КОСВЕННЫЕ ПАДЕЖИ БЕРЁМ У СОСЕДА, А НЕ ПИШЕМ СВОИ. Признак «какой падеж
# требует слово слева» живёт в `gen_full_places` (предлог, глагол движения,
# существительное перед именем) и там же выверен на обоих краях. Копия
# признака в этом проекте расходилась трижды и всегда МОЛЧА.
import gen_full_places as places  # noqa: E402

OUT = ROOT / "src/main/resources/assets/skyblockru/packs/ru_ru/02-full-names.json"
PACKS = ROOT / "src/main/resources/assets/skyblockru/packs"
DUMP = pathlib.Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")
CYR = re.compile("[а-яА-ЯёЁ]")
# именительный виден по соседу слева
# ⚠️ ТИТУЛ СЛЕВА — тоже признак именительного. Без «Король» в списке
# режимное имя не подставлялось, и на экране оставалось «Король Brammor»:
# половина по-русски, половина нет. Нашёл сторож check_mode_wins.
NOM_AFTER = re.compile(r"(?::|\||—|Мэр|Министр|Кандидат|Область|Событие|Король|Королева|Царь|Капитан|Мастер|Старейшина)\s*$")
NUM_HOLE = re.compile(r"\{i?\d*\}|\{n\d*\}")
NO_WORDS = re.compile("^[^A-Za-z\u0410-\u044f\u0401\u0451]*$")


LAT_WORD = re.compile(r"\b[A-Za-z][A-Za-z']+\b")


def english_words(text: str) -> int:
    """Сколько АНГЛИЙСКИХ слов осталось в тексте (римские цифры не в счёт)."""
    return sum(1 for w in LAT_WORD.findall(text)
               if not re.fullmatch(r"[IVXLCDM]+", w))


def no_words_left(before: str) -> bool:
    """Слева от имени НЕТ СЛОВА — значит и падежа нет.

    ⚠️ Прежний признак требовал `at <= 2`, и подпись бестиария
    «+{n} Arachne ⸎ Сила» уходила в «нужен падеж»: слева пять знаков.
    Падежа там нет вовсе — управлять именем нечем, слева одни числа и значки.

    ⚠️ Дырку {n} СНИМАЕМ, а {s} НЕТ. В {n} стоит латинская «n», и без
    снятия признак видит слева «слово» (записанная грабля проекта, четвёртый
    случай). А {s} — это НИК, и что стоит за ним, мы не знаем: в 37 строках
    вида «{s} Adventurer:» проверить по логам не удалось, и трогать их нельзя.
    """
    return bool(NO_WORDS.match(NUM_HOLE.sub("", before)))


NPC_PREFIX = re.compile(r"^(?:§.)*\[NPC\]\s*(?:§.)*$")


CODES = re.compile("§.")
WORDS = re.compile(r"[A-Za-z][A-Za-z']*")
PLAYER_SOURCES = {"name_tag", "menu_title", "screen", "title",
                  "boss_bar", "scoreboard", "tab", "action_bar",
                  # ⚠️⚠️ ЛОР И ЧАТ ДОБАВЛЕНЫ 05.09, и прежний довод против них
                  # УСТАРЕЛ В ТОТ ДЕНЬ, когда появились падежи. Он звучал так:
                  # «там проза, имя в косвенном падеже, механика бессильна —
                  # в именительный не попало НИ ОДНОЙ строки». Верно для
                  # именительного и неверно теперь: `places.substitute` берёт
                  # падеж у слова слева. Замер: «Портал в Логово пауков»,
                  # «Дойди до Лазуритового карьера», «Мешок Хрустальных
                  # пустот» — это как раз лор и чат.
                  "item_lore", "chat"}
# ⚠️ Наш дамп берётся ЦЕЛИКОМ — реплики NPC оттуда, и 489 записей словаря
# держатся именно на них.
PLAYERS_MIN = 3   # сколько установок должны прислать строку, чтобы ей верить

# Сколько имён подставляем в одну строку. Предел, а не догадка: строка
# с шестью именами не встречалась ни разу, а бесконечный цикл на правке
# подстановки обошёлся бы дороже пропущенной записи.
MAX_NAMES = 6
# маска той же ДЛИНЫ, что §-код: позиции в тексте не съезжают
MASK = chr(0) * 2

# ⚠️ ЭТИ СЛОВА ОСТАЮТСЯ АНГЛИЙСКИМИ ПО РЕШЕНИЮ, и «остатком» их звать нельзя:
# иначе откат срубит законные записи вроде «[NPC] Киша: Привет!».
KEEP_ENGLISH = {"NPC", "SKYBLOCK", "MVP", "VIP", "SLAYER", "Pests", "Combat",
                "Gems", "Bits", "Bazaar", "Hypixel", "SkyBlock"}


def russian_names() -> dict[str, str]:
    """Английское имя -> русское. Берём у РЕЖИМНОГО словаря, не выдумываем."""
    src = json.loads((PACKS / "ru_ru" / "82-npc-places.json").read_text(encoding="utf-8"))
    out = {}
    for key, value in (src.get("exact") or {}).items():
        if not CYR.search(value):
            continue
        if not re.fullmatch(r"[A-Za-z'’ .-]+", key) or len(key) <= 4:
            continue
        out[key] = value
    return out


def fix_halves(text: str, names: dict[str, str]) -> str:
    """Починить половинную подстановку: «Mayor Диана» -> «Мэр Диана».

    ⚠️ Такие записи РОЖДАЛИСЬ ЗДЕСЬ ЖЕ и переезжали из сборки в сборку.
    Пока составного имени не было в словаре, подстановка брала личное
    («Diana» -> «Диана») и оставляла должность английской. Имя добавили —
    а перенос по-прежнему возвращал старое значение, потому что строки
    в НАШЕМ дампе нет: она приходит только от игроков.

    Чиним, а не выбрасываем: выбросить — значит потерять перевод строки
    целиком, а смесь языков хуже и того и другого.
    """
    for english, russian in names.items():
        head, _, last = english.rpartition(" ")
        if not head:
            continue
        tail = names.get(last)
        if not tail:
            continue
        broken = f"{head} {tail}"
        if broken in text:
            text = text.replace(broken, russian)
    return text


def nominative(before: str, at: int) -> bool:
    """Имя стоит в ИМЕНИТЕЛЬНОМ — по тому, что слева."""
    if at == 0 or not re.search(r"[А-Яа-яЁё]", before):
        # начало строки либо только служебное слева
        return bool(at <= 2 or no_words_left(before)
                    or NPC_PREFIX.match(before.strip()) or "[NPC]" in before)
    return bool(NOM_AFTER.search(before.rstrip()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--show", type=int, default=8)
    args = ap.parse_args()

    if not DUMP.exists():
        print("нет дампа:", DUMP)
        return 1
    names = russian_names()
    order = sorted(names, key=len, reverse=True)
    # ⚠️ ДЛИННЫЕ ИМЕНА ПЕРВЫМИ: иначе «Catacombs» успеет забрать место
    # у «The Catacombs», и артикль останется английским посреди русского.
    # Третий элемент пары — первое слово, оно нужно для дешёвого отсева.
    place_forms = [(n, f, n.split(" ")[0])
                   for n, f in sorted(places.PLACES.items(),
                                      key=lambda kv: -len(kv[0]))]
    # ⚠️ ИНДЕКС ПО ПЕРВОМУ СЛОВУ ОКАЗАЛСЯ ДЫРЯВЫМ: пропускал 46% строк.
    # Первые слова имён частые («Minion», «The», «Zombie», «Ancient»), и
    # признак «в строке есть слово, с которого начинается какое-то имя»
    # истинен почти всегда. Отсев не отсеивал, прогон не укладывался в лимит.
    #
    # Теперь индекс отвечает на НУЖНЫЙ вопрос: какие имена вообще могут
    # встретиться в этой строке. Кандидатов обычно единицы, и у них
    # проверяется ПОЛНОЕ вхождение — то есть отсев точный, а не приблизительный.
    by_word: dict[str, list[str]] = {}
    for n in names:
        for w in WORDS.findall(n):
            by_word.setdefault(w, []).append(n)
    # ⚠️ СЕБЯ ИЗ ОПРОСА ИСКЛЮЧАЕМ: на втором прогоне генератор нашёл бы свои же
    # записи (там имена уже русские), решил бы, что работы нет, и записал пустой
    # словарь. Ровно так съели себя gen_headers, split_sb_stats и gen_full_jargon.
    full = status.Dictionaries(without={OUT.name}, groups={"full"})
    dump = json.loads(DUMP.read_text(encoding="utf-8"))

    # ⚠️⚠️ СТРОКИ ОТ ИГРОКОВ — ВТОРОЙ ИСТОЧНИК, и он БОЛЬШЕ нашего.
    #
    # Генератор читал только НАШ дамп (21 642 строки), а от игроков приходит
    # 74 661. Из-за этого «King Brammor» не подставлялся ГОДАМИ: у нас на
    # экране такой строки нет, она встречается только у других людей.
    # Замер 28.08: строк с переводимым именем ТОЛЬКО от игроков — 18 536,
    # то есть в 22 раза больше, чем видел генератор.
    #
    # Формат другой: там сразу {источник: {строка: сколько установок}},
    # без обёртки "sources". Приводим к общему виду, а не заводим второй цикл.
    sources = dict(dump.get("sources") or {})
    players = ROOT / "data" / "work" / "from_players.json"
    if players.exists():
        for origin, lines in json.loads(players.read_text(encoding="utf-8")).items():
            if not isinstance(lines, dict) or origin not in PLAYER_SOURCES:
                continue
            merged = dict(sources.get(origin) or {})
            for line, freq in lines.items():
                # ⚠️ ПОРОГ «строку прислали МНОГИЕ» — записанное правило проекта
                # (поднят 1 -> 3, когда установок стало 73). Строка от одного
                # человека чаще всего его собственная комбинаторика, а не
                # надпись Hypixel. Наш дамп порогу не подчиняется: там показы.
                if isinstance(freq, int) and freq < PLAYERS_MIN:
                    continue
                merged.setdefault(line, freq)
            sources[origin] = merged

    exact, skipped, possessive, nicknamed, handmade = {}, 0, 0, 0, 0
    by_case = 0   # взято КОСВЕННЫМ падежом (gen_full_places.substitute)
    halfway = 0
    covered = 0
    # ручные переводы режима: они полнее нашей подстановки
    hand_pack = PACKS / "ru_ru" / "04-full-strings.json"
    by_hand = set()
    if hand_pack.exists():
        by_hand = set(json.loads(hand_pack.read_text(encoding="utf-8"))
                      .get("exact", {}))
    known_names = check_nicknames.known_names()
    for origin, lines in sources.items():
        rows = lines.items() if isinstance(lines, dict) else ((x, 1) for x in lines)
        for line, _ in rows:
            # ⚠️ ДЕШЁВЫЙ ОТСЕВ ПЕРЕД ДОРОГИМ. `status.lookup` при промахе
            # перебирает три тысячи правил — замер 26.08: 16 мс на строку,
            # то есть 7.6 минуты на 28 578 строк дампа. А подставить имя мы
            # можем, только если оно ЕСТЬ В ОРИГИНАЛЕ: перевод английского
            # имени из ниоткуда не возьмётся. Проверка вхождения подстрокой
            # стоит микросекунды и отбрасывает подавляющее большинство строк.
            # Тот же приём, каким `protected.check_block` ускорен в 74 раза.
            # ⚠️ ОТСЕВ ПО ИНДЕКСУ, а не перебором 1526 имён на каждую строку.
            # Со вторым источником строк стало 96 тысяч, и перебор давал
            # 146 млн проверок — прогон не укладывался в 28 минут (код 124).
            # Индекс по ПЕРВОМУ СЛОВУ имени сводит это к числу слов в строке.
            maybe = {n for w in WORDS.findall(line) for n in by_word.get(w, ())}
            if not any(n in line for n in maybe):
                continue
            found = status.lookup(line, full, origin=origin)
            if not found or not CYR.search(found[0]):
                continue
            text = found[0]
            # ⚠️⚠️ ИЩЕМ ПО ТЕКСТУ С ЗАМАСКИРОВАННЫМИ §-КОДАМИ.
            #
            # Код кончается ЛАТИНСКОЙ БУКВОЙ («§b»), и просмотр назад
            # `(?<![A-Za-z])` считает её частью слова: в «§bBanker Barry»
            # длинное имя не находится, а короткое «Barry» — находится.
            # Подставлялось оно, и на экране выходило «§bBanker Барри» —
            # СМЕСЬ ЯЗЫКОВ, худший вид ошибки. Замер 27.08: так испорчены
            # 8 записей («Mayor Диана», «Mayor Марина»).
            #
            # Записанная грабля проекта («замена по `\b` не поймала
            # `§bЛесозаготовка`: латинская «b» кода и кириллическая «Л» обе
            # буквенные»), всплывшая с другой стороны.
            #
            # Маска СОХРАНЯЕТ ДЛИНУ (§ + знак = два знака), поэтому позиции
            # в маскированном и настоящем тексте совпадают, и подставлять
            # можно прямо по ним.
            masked = CODES.sub("\x00\x00", text)
            hit = next((n for n in order
                        if re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])",
                                     masked)), None)
            if not hit:
                continue
            # ⚠️⚠️ ПОДСТАВЛЯЕМ ВСЕ ИМЕНА, А НЕ ПЕРВОЕ. Раньше менялось одно,
            # и составная строка выходила ПОЛУПЕРЕВОДОМ:
            #   «Glacite Tunnels - Dwarven Base Camp»
            #   -> «Глацитовые туннели - Dwarven Base Camp»
            # Замер 28.08: из 936 живых записей чисто подставлялись 129,
            # у 807 оставалось английское слово. Смесь языков хуже английского
            # целиком — записанное правило проекта.
            # Предел витков нужен: текст меняется по ходу, и без него поиск
            # мог бы зациклиться на своём же результате.
            new, turns = text, 0
            need_case = False
            placed: list[str] = []   # какие русские имена реально подставили
            while turns < MAX_NAMES:
                turns += 1
                probe = CODES.sub(MASK, new)
                found = next((n for n in order
                              if re.search(r"(?<![A-Za-z])" + re.escape(n)
                                           + r"(?![A-Za-z])", probe)), None)
                if not found:
                    break
                at = probe.find(found)
                if re.match(r"['’]s(?![A-Za-z])", new[at + len(found):]):
                    possessive += 1
                    break
                if not nominative(new[:at], at):
                    # ⚠️ СЧИТАЕМ ПОЗЖЕ: падежная подстановка идёт СЛЕДОМ, и
                    # строка может быть взята ею. Инкремент прямо здесь давал
                    # «оставляем человеку: 504» на строках, которые генератор
                    # на самом деле брал, — отчёт врал о размере работы.
                    need_case = True
                    break
                placed.append(names[found])
                new = new[:at] + names[found] + new[at + len(found):]
            # ⚠️⚠️ КОСВЕННЫЕ ПАДЕЖИ — второй заход, ПОСЛЕ именительного.
            # Цикл выше берёт имя, только когда слева двоеточие или титул;
            # а «Портал в Spider's Den», «Дойди до Lapis Quarry», «Мешок
            # Crystal Hollows» требуют винительного и родительного, и их он
            # оставлял английскими. Замер 05.09 по 130 237 живым парам:
            # имя локации стоит в 3074 строках, русским выходило 53%.
            # ⚠️ ДЕШЁВЫЙ ОТСЕВ ПЕРЕД ДОРОГИМ: substitute гоняет по нескольку
            # регулярок на имя, а имён 181 — без отсева это сотни тысяч
            # прогонов на строку. Проверяем ПЕРВОЕ СЛОВО: оно целое даже
            # тогда, когда Hypixel разорвал имя §-кодом между словами.
            before_case = new
            # ⚠️ КНОПКА НАВИГАЦИИ — ЭТО НАПРАВЛЕНИЕ, и предлог «в/на» требует
            # винительного: «To Backwater Bayou» -> «В Затонную заводь», а не
            # «В Затонной заводи». Видно это только в АНГЛИЙСКОМ ключе —
            # русский текст сам по себе неотличим от заголовка места, поэтому
            # признак берём здесь и передаём вниз. Поймано выборкой глазами:
            # 4 записи из 575 вышли с предложным.
            motion = bool(re.match(r"^(?:§.)*(?:To|Back to)\s+[A-Z]",
                                   CODES.sub("", line)))
            for _pname, _pforms, _pfirst in place_forms:
                if _pfirst not in new:
                    continue
                new = places.substitute(new, _pname, _pforms, motion=motion)
            if new != before_case:
                by_case += 1
            elif need_case:
                skipped += 1
            if new == text:
                continue
            # ⚠️ ОТКАТ ПРИ ОСТАТКЕ: осталось английское слово — вышел
            # полуперевод, такую запись не заводим. Метки не в счёт:
            # «[NPC]», «Pests», «Combat» английские ПО РЕШЕНИЮ.
            rest = [w for w in re.findall(r"(?<![A-Za-z])[A-Za-z]{3,}(?![A-Za-z])",
                                          CODES.sub("", new))
                    if w not in KEEP_ENGLISH]
            if rest:
                halfway += 1
                continue
            # ⚠️ ИМЕНИТЕЛЬНЫЙ ПЕРЕД «нельзя» — ВСЕГДА НЕВЕРЕН: там винительный
            # («Чёрную дыру нельзя ставить»), а признак видел начало строки
            # и считал падеж именительным. Поймано выборкой глазами.
            #
            # ⚠️ Спрашиваем ИМЕННО подставленное имя, а не «есть ли слово
            # нельзя в строке»: широкий признак выбрасывал заодно законную
            # реплику «[NPC] Лорас: Такую возможность нельзя сбрасывать».
            # Отказываемся молча: потерять правку дешевле, чем вписать
            # неверный падеж — он выглядит готовым текстом и живёт сессиями.
            plain_new = CODES.sub("", new)
            if any(re.search(r"%s\s+(?:\w+\s+){0,1}(?:нельзя|невозможно|запрещено)\b"
                             % re.escape(put), plain_new) for put in placed):
                skipped += 1
                continue
            # ⚠️⚠️ КЛЮЧ — ЭТО ЖИВАЯ СТРОКА ДАМПА, И В НЕЙ БЫВАЕТ ЧУЖОЙ НИК.
            # Перевод пришёл ПРАВИЛОМ («☠ {s} was killed by …»), то есть общим
            # для всех, а точная запись замораживает его на одном человеке:
            # «☠ Omega_Dynasty was killed by Old Wolf.» не совпадёт больше
            # ни у кого на свете, зато чужое имя уедет в раздачу.
            # Чиним ОБОБЩЕНИЕМ, а не пропуском (записанное правило проекта):
            # обобщённая запись работает у всех и никого не называет.
            key = check_nicknames.safe_key(line, new, known_names)
            if key is None:
                nicknamed += 1
                continue
            # ⚠️⚠️ РУЧНОЙ ПЕРЕВОД СИЛЬНЕЕ МАШИННОЙ ПОДСТАНОВКИ, и без этой
            # проверки он ПЕРЕБИВАЕТСЯ: у нас priority 2, у ручного словаря 4,
            # а у `exact` побеждает МЕНЬШИЙ. Замер 26.08 движком: 28 записей,
            # и в режиме игрок видел «дружок Blacksmith из Village» вместо
            # «дружок Кузнеца из Деревни» — то есть режим работал наполовину.
            # Мы подставляем имя ТОЛЬКО в именительном (иначе падеж), а руками
            # переведено всё вместе с падежами. Спорить тут не о чем.
            if key in by_hand:
                handmade += 1
                continue
            exact[key] = new

    # ⚠️⚠️ ПЕРЕНОС ПРЕЖНИХ ЗАПИСЕЙ ОБЯЗАТЕЛЕН, и без него пересборка съедает
    # работу: генератор видит только то, что лежит в ДАМПЕ СЕЙЧАС, а дамп
    # чистится и редеет. Замер 26.08: словарь усох 549 -> 198, и сторож
    # `check_shrink` показал 295 строк, переставших переводиться ВООБЩЕ.
    # Ровно та же семья, что у `gen_enchants` и `gen_stat_forms`, — там
    # перенос завели после такой же потери.
    #
    # ⚠️ Переносим НЕ ВСЁ: запись, которую сегодня закрывает ручной перевод
    # либо у которой в ключе чужой ник, возвращать нельзя — иначе правка
    # отменится сама собой при первой же пересборке.
    # ⚠️⚠️ ОБЩЕЕ ПРАВИЛО СИЛЬНЕЕ НАШЕЙ ПОДСТАНОВКИ, и проверять это надо
    # НА ИТОГОВОМ НАБОРЕ, а не в цикле по дампу: там сотни тысяч строк,
    # и лишний `lookup` на каждую сделал сборку 16-минутной (замер 26.08).
    #
    # Если движок уже даёт по КЛЮЧУ русский текст, работу делает правило либо
    # чужая запись — а они закрывают ВСЕ варианты строки, тогда как наша точная
    # запись только один. У «Bestiary Milestone I» правило даёт «Веха бестиария
    # I», а мы замораживали «Бестиарий: веха I» (priority 2 против 20, у `exact`
    # побеждает МЕНЬШИЙ) — игрок видел ДВЕ формы: наши 20 записей и правило
    # на остальных 1131.
    for key in list(exact):
        already = status.lookup(key, full, origin="item_name")
        # ⚠️ «ЕСТЬ КИРИЛЛИЦА» — СЛИШКОМ СЛАБЫЙ ПРИЗНАК: он считает работу
        # сделанной у ПОЛУПЕРЕВОДА. «King Brammor» движок отдаёт как
        # «Король Brammor» (кириллица есть, имя английское), и пять королей
        # молча выпадали из режима — нашёл это `check_mode_wins`.
        # Спрашиваем по существу: наше значение ПОЛНЕЕ, если английских слов
        # в нём меньше. Подстановка имени их только убирает.
        if already and CYR.search(already[0])                 and english_words(already[0]) <= english_words(exact[key]):
            del exact[key]
            covered += 1
    if covered:
        print(f"уже закрыто правилом или чужой записью: {covered}")
    carried = 0
    if OUT.exists():
        before = json.loads(OUT.read_text(encoding="utf-8")).get("exact", {})
        for key, value in before.items():
            if key in exact or key in by_hand:
                continue
            if check_nicknames.nicks_in(key, known_names):
                continue
            # ⚠️ ПЕРЕНОС ТОЖЕ ОБЯЗАН СПРАШИВАТЬ, НЕ ЗАКРЫТО ЛИ УЖЕ. Иначе он
            # возвращает записи, которые новый набор отбросил осознанно:
            # 26.08 защита `covered` выбросила 20 вех бестиария (их закрывает
            # общее правило), а перенос вернул все двадцать — и словарь
            # не изменился вовсе.
            covers = status.lookup(key, full, origin="item_name")
            if covers and CYR.search(covers[0]):
                covered += 1
                continue
            # ⚠️ Прежняя сборка могла содержать половинную подстановку —
            # чиним её ЗДЕСЬ, иначе смесь языков переезжает вечно.
            exact[key] = fix_halves(value, names)
            carried += 1
    if carried:
        print(f"перенесено из прежней сборки: {carried}")

    print(f"строк с английским именем в русском переводе: {len(exact) + skipped}")
    print(f"  ИМЕНИТЕЛЬНЫЙ — берём: {len(exact) - by_case}")
    print(f"  КОСВЕННЫЙ ПАДЕЖ — берём: {by_case}")
    print(f"  нужен падеж — оставляем человеку: {skipped}")
    if possessive:
        print(f"  притяжательная форма («X's») — тоже человеку: {possessive}")
    if nicknamed:
        print(f"  чужой ник в строке — обобщено либо отброшено: {nicknamed}")
    if handmade:
        print(f"  переведено РУКАМИ — не трогаем: {handmade}")
    if halfway:
        # ⚠️ Это НЕ потеря, а защита: подстановка дала бы смесь языков.
        print(f"  откат: остался бы английский хвост — {halfway}")
    for key, value in list(exact.items())[:args.show]:
        print(f"   {key[:44]!r}")
        print(f"      -> {value[:64]!r}")
    if not args.write:
        print("\nСУХОЙ ПРОГОН. Записать: --write")
        return 0
    if not exact:
        print("ПУСТО — файл НЕ переписан (скорее всего прочитан свой выход)")
        return 1

    pack = {
        "id": "full_names",
        "priority": 2,
        "default": False,
        "group": "full",
        "about": "Имена NPC и локаций внутри строк: «Мэр Diana» -> «Мэр Диана». "
                 "Часть полного перевода.",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_full_names.py — правь СКРИПТ. "
                    "Берутся только позиции ИМЕНИТЕЛЬНОГО падежа (префикс [NPC], "
                    "начало строки, после двоеточия/должности): падеж машиной "
                    "не выводится, а «в Savanna Woodland» требует винительного.",
        "exact": dict(sorted(exact.items())),
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано: {OUT.name} ({len(exact)} записей)")
    index = PACKS / "index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    files = data["languages"]["ru_ru"]
    if OUT.name not in files:
        files.append(OUT.name)
        files.sort()
        index.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print("вписан в index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
