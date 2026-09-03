# -*- coding: utf-8 -*-
"""
Куда положить переведённую строку: в ОБЫЧНЫЙ словарь или в РЕЖИМНЫЙ.

⚠️ НА ГЛАЗ ЭТО НЕ ДЕЛАЕТСЯ, и замер 26.08 это показал: из 114 строк первой
пачки я бы отнёс к режиму только имена предметов, а режимными оказались 82.
Причина в том, что имена мобов, локаций и NPC переводятся ТОЛЬКО в режиме
(`85-mob-names`, `81-item-names`, `82-npc-places` — все с `group: full`),
и фраза с таким именем внутри в обычном режиме дала бы СМЕСЬ ЯЗЫКОВ.

Признак один и от ДВИЖКА: термин переводится с группой `full` и НЕ переводится
без неё — значит строка режимная. Спрашиваем две копии словаря.

⚠️ Спрашивать надо не только слово целиком, но и ПАРЫ-ТРОЙКИ соседних слов:
«Damage Treasure Hoarders {n} times.» — имя здесь «Treasure Hoarder», и по
одному слову оно не находится, а «Damage Treasure Hoarders» целиком словарю
неизвестно. Замер: без этого мимо проходили 3 строки из 28.

⚠️ Множественное число снимаем: сервер пишет «Goblins», а в словаре «Goblin».
"""
import re

CYR = re.compile("[а-яА-ЯёЁ]")
# ⚠️ БЕЗ re.I: регистр И ЕСТЬ признак имени собственного.
CAP = re.compile(r"[A-Z][A-Za-z'\-]*")
# Реплика NPC или моба: «Имя: текст». Класс букв ШИРЕ ASCII — Hypixel пишет
# «Cübe» с умлаутом, и ASCII-признак такую реплику пропускал.
SPEAKER = re.compile(r"^[^\W\d_][\w '\-]*(?:\{n\})?[\w '\-]*:", re.UNICODE)
# Источники, где строка ЦЕЛИКОМ является именем.
NAME_SOURCES = ("item_name", "name_tag")


def _russian(pair) -> bool:
    return bool(pair and pair[0] and CYR.search(pair[0]))


def terms_of(line: str, span: int = 3):
    """Слова с Заглавной и их сочетания по 2–3 подряд, длиннее — не бывает."""
    words = [(m.start(), m.group(0)) for m in CAP.finditer(line)]
    for i, (_, word) in enumerate(words):
        for take in range(1, span + 1):
            if i + take > len(words):
                break
            term = " ".join(w for _, w in words[i:i + take])
            yield term
            if term.endswith("s"):
                yield term[:-1]


def only_in_mode(term: str, origin: str, plain, full, lookup, translated=None):
    """
    Переводится в режиме и НЕ переводится без него.

    ⚠️ Мало знать, что термин РЕЖИМНЫЙ, — надо проверить, воспользовались ли мы
    этим. У «Grants +{n} Bonus Pest Chance.» термин `Pest` режимный, но в нашем
    переводе он оставлен АНГЛИЙСКИМ (жаргон по решению), и строка обычная.
    Поэтому при наличии перевода требуем, чтобы русское слово в нём БЫЛО.
    """
    if len(term) < 4:
        return False
    mode_ru = lookup(term, full, origin=origin)
    if not _russian(mode_ru) or _russian(lookup(term, plain, origin=origin)):
        return False
    if translated is None:
        return True
    # сравниваем по ОСНОВЕ: в строке слово стоит в падеже («Собирателям»)
    head = re.split(r"[\s\-]", mode_ru[0].strip())[0]
    stem = head[:-2] if len(head) > 5 else head
    return stem.lower() in translated.lower()


def decide(row: dict, plain, full, lookup, protected=None, known=None) -> str | None:
    """Причина, по которой строка режимная. None — обычная."""
    if row.get("src") in NAME_SOURCES:
        return "имя"
    if protected and known and protected.check_block([row["en"]], [row["ru"]], known):
        return "защита"
    if row.get("src") == "chat":
        said = SPEAKER.match(row["en"])
        # ⚠️ «Имя: текст» и «Подпись: значение» на вид одинаковы. Отличает то,
        # что ПОДПИСЬ обычный словарь знает («Runecrafting: +{n} XP»),
        # а имя моба или NPC — нет: их переводит только режим.
        if said and not _russian(lookup(said.group(0)[:-1], plain, origin="chat")):
            return "говорящий"
    for term in terms_of(row["en"]):
        if only_in_mode(term, row["src"], plain, full, lookup, row.get("ru")):
            return term
    return None
