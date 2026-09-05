# -*- coding: utf-8 -*-
"""Имя способности и бонуса в ЗАГОЛОВКЕ режимного абзаца — по-русски.

Режим full переводит ВСЁ (решение игрока 28.08), но `gen_full_paragraphs`
менял только ТЕРМИН («Farming Fortune» -> «Удача фермера»), а имя способности
оставлял английским:

    было:  §6Способность: Cropshot§7 Даёт §6+{n}☘ к Удаче фермера§7 …
    стало: §6Способность: Урожайный выстрел§7 Даёт §6+{n}☘ к Удаче фермера§7 …

⚠️ ТОЛЬКО ИМЕНИТЕЛЬНЫЙ, и это не осторожность, а падеж. Подставить механически
можно там, где имя стоит в именительном; в прозе оно требует падежа
(«урон Cropshot», «обменяй Dragon Essence»), а падеж машинно не выводится —
записанное правило проекта.

⚠️⚠️ ПРИЗНАК «ЭТО ЗАГОЛОВОК» ПРОТЕКАЛ, И ЧЕРЕЗ НЕГО ШЛА ПОРЧА ПАДЕЖА.
`heading()` берёт кусок до возврата к цвету тела, а если разметки НЕТ —
брал первые 70 знаков, то есть кусок ПРОЗЫ. Замер 28.08: из 95 правок
52 шли этой веткой, и 18 из них портили падеж:

    Обменяй Dragon Essence на перки  ->  Обменяй Драконья эссенция на перки
    Поговори с Bulvar ...            ->  Поговори с Булвар ...

Поэтому позиция каждого имени теперь проверяется отдельно (`nominative_at`):
именительный стоит в начале строки, после двоеточия и после конца
предложения. Слева предлог или глагол — подстановки НЕ делаем вовсе.
⚠️ Несклоняемое имя после предлога («с Джонси») законно, но склоняемость
машинно не выводится — отказываем и здесь. Потерять правку дешевле, чем
вписать неверный падеж: он выглядит готовым текстом и живёт сессиями.

⚠️ ИМЯ ЦЕЛИКОМ, а не по словам. Иначе выходит «Благословение from the Dark» —
смесь языков в чистом виде: так уже испорчены записи, где подстановка взяла
первое слово составного имени.

⚠️ Правим ЗАГОТОВКУ (data/work/full_paragraphs_ru.json), а не собранный
словарь: словарь автосборный, и следующий `--write` стёр бы правку.

    python tools/fix_full_headings.py          сухой прогон
    python tools/fix_full_headings.py --yes    применить
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import status  # noqa: E402

SKELETON = ROOT / "data" / "work" / "full_paragraphs_ru.json"
CYR = re.compile("[а-яА-ЯёЁ]")
CODES = re.compile("§.")
# заголовок: до первого возврата к цвету тела (§7) после цветного куска
HEAD = re.compile(r"^((?:§.)*[^§]*)")
# имя целиком: слова с Заглавной подряд, служебные внутри допускаются
NAME = re.compile(r"(?<![A-Za-z])([A-Z][A-Za-z']*(?:[ -](?:of|the|from|and|in|on|to|"
                  r"[A-Z][A-Za-z']*))*)(?![A-Za-z])")


# ⚠️ Решения проекта: эти слова остаются английскими В ЛЮБОМ режиме, и
# подставлять их русский перевод нельзя, даже когда он в словаре есть.
KEEP_ENGLISH = {
    "Bits", "Gems",              # валюты — решение проекта
    "Combat",                    # навык — решение игрока 01.08
    "Shift",                     # имя клавиши одинаково в любом языке (27.08)
    "SkyBlock", "Hypixel", "Bazaar",   # бренды
    "Respiration",               # ванильное зачарование: имя даёт КЛИЕНТ
}

# слева от имени: слово, после которого именительного не бывает
CASE_LEFT = re.compile(
    r"(?:в|во|на|из|с|со|у|к|ко|для|от|про|при|над|под|за|об?|"
    r"время|используя|этой|этим|этого|помощью|"
    r"обменяй|улучш\w+|купи|открой|употреби|поставь|убей|собери|получ\w+|"
    r"найди|поговори|установи|падает|получено)\s*$",
    re.IGNORECASE,
)
# слева от имени: подлежащее в именительном — «Твой X даёт …»
# ⚠️ ПОРЯДКОВОЕ ЧИСЛИТЕЛЬНОЕ СЛЕВА — тоже именительный: «{n}-й Сезон Джерри»,
# «3-я Ярмарка». Оно согласуется с именем, а не управляет им, поэтому падежа
# не меняет. Без этого ходовая форма события («{n}th Season of Jerry», 208
# установок у игроков) оставалась английской.
NOMINATIVE_LEFT = re.compile(r"(?:тво[йяёе]|тво[иё]|наш\w*|эт[оаи]?т?|"
                             r"(?:\{n\}|\d+)-[йяое])\s*$",
                             re.IGNORECASE)


def heading(text: str) -> str:
    """Строка целиком: резать её по «заголовку» больше не нужно.

    ⚠️ Прежде тут стоял кусок до возврата к цвету тела, а при отсутствии
    разметки — первые 70 знаков, то есть кусок ПРОЗЫ (см. шапку). Обрезка
    и защищала слабо, и теряла работу: у размеченной строки имя за первым
    §7 не подставлялось вовсе («установить этот Sinker на удочку»).
    Позицию каждого имени теперь проверяют `nominative_at`, `standalone`
    и `gender_safe` — по отдельности и на месте.
    """
    return text


def nominative_at(text: str, at: int) -> bool:
    """Стоит ли имя на позиции `at` в ИМЕНИТЕЛЬНОМ падеже.

    Признак от соседа слева, а не от вида имени: начало строки, двоеточие
    и конец предложения именительного не меняют, а предлог и глагол —
    меняют. Сомнительное считаем падежом и не трогаем.
    """
    left = CODES.sub("", text[:at]).rstrip()
    # ⚠️ ВЕДУЩИЙ ЗНАЧОК — ЭТО НАЧАЛО СТРОКИ, а не сосед, меняющий падеж.
    # Hypixel метит им заголовок («<знак> Hotspot Hook Grants …»), и признак,
    # не знавший об этом, отказывал: слева не пусто и не двоеточие. Из-за
    # этого заголовок части удочки оставался английским при купленном
    # переводе имени. Значок опознаём тем же признаком, что `gen_full_icons`
    # (копию не заводим): свой список алфавитов отстал бы от новой вещи.
    if left:
        import gen_full_icons
        if all(gen_full_icons._icon_char(c) or c.isspace() for c in left):
            # ⚠⚠ ...НО ПОВТОРЯЮЩИЙСЯ ЗНАК — ЭТО СПИСОК, а не заголовок.
            # У «▶ Spooky ▶ Winter ▶ Минералы» каждый пункт свой, и подстановка
            # брала имя ПРЕДМЕТА там, где стоит КАТЕГОРИЯ: выходило «Спуки»
            # рядом с «Жуткий» в соседней строке. Признак тот же, что в моде
            # (`ColorLayout.repeatedMarker`): знак встречается дальше — список.
            mark = left.strip()
            if mark and CODES.sub("", text).count(mark) > 1:
                return False
            return True
    if not left:
        return True
    if left.endswith((":", ".", "!", "?", "—", "-", "•", "▪")):
        return True
    if NOMINATIVE_LEFT.search(left):
        return True
    # ⚠️ Всё прочее — НЕИЗВЕСТНО, и это отказ, а не «наверное, именительный».
    # Замер 28.08: у 60% мест сосед слева падежа не выдаёт вовсе
    # («используя [Salts]», «пойманные этой [Black Hole]»).
    return False


# слева стоит слово, согласуемое по РОДУ с именем
AGREE_LEFT = re.compile(r"(?:эт[оаи]?[тй]?|тво[йяёе]|нов[ыаоя]\w*|перв[ыаоя]\w*|"
                        r"как[оаи]\w*|сам[оаи]?\w*)\s*$", re.IGNORECASE)


def gender_safe(text: str, start: int) -> bool:
    """Не разойдётся ли РОД с согласованным словом слева.

    ⚠️ Подстановка меняет род: «этот Sinker» -> «этот Грузило» (средний!).
    Английское имя рода не имеет, поэтому согласованное слово рядом написано
    наугад, и после перевода оно врёт. Род по окончанию не выводим —
    записанная грабля проекта: мягкий знак его НЕ выдаёт («дрель» женского,
    «трюфель» мужского), а явный список ради двух случаев не окупается.
    Поэтому просто отказ: замер 28.08 — таких мест 2 из 29.
    """
    left = CODES.sub("", text[:start]).rstrip()
    return not AGREE_LEFT.search(left)


# английское слово с Заглавной — сосед, который выдаёт составное имя
NEIGHBOUR = re.compile(r"[A-Z][A-Za-z']*")
ROMAN = re.compile(r"^[IVXLCDM]+$")


def standalone(text: str, start: int, end: int) -> bool:
    """Целое ли это имя, а не кусок составного.

    ⚠️ Записанная грабля проекта: подстановка по ЧАСТИ имени даёт смесь
    языков — «Нежить Fortune», «Йети Tracker», «Мастерство Moonglade».
    Признак от соседа: английское слово с Заглавной вплотную слева или
    справа значит, что имя длиннее найденного куска.
    ⚠️ Римский уровень соседом НЕ считается: «Гекатомба I» законна.
    """
    right = CODES.sub("", text[end:]).strip().split()
    if right:
        word = NEIGHBOUR.fullmatch(right[0].strip(".,!?:;()"))
        if word and not ROMAN.match(word.group(0)):
            return False
    # ⚠️ ПОДПИСЬ ОТДЕЛЯЕТ ИМЯ, и сосед за ней в счёт не идёт. У «Счётчик RNG:
    # Crystal Nucleus» слева стоит аббревиатура «RNG», признак принимал её за
    # часть названия и отказывал — 65 показов. Двоеточие тут говорит прямо:
    # слева подпись, справа значение, и они разные вещи.
    left_raw = CODES.sub("", text[:start]).rstrip()
    if left_raw.endswith((":", "—", "|")):
        return True
    left = left_raw.strip().split()
    if left:
        word = NEIGHBOUR.fullmatch(left[-1].strip(".,!?:;()"))
        if word and not ROMAN.match(word.group(0)):
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--show", type=int, default=10)
    args = ap.parse_args()

    if not SKELETON.exists():
        print("нет заготовки:", SKELETON)
        return 1
    data = json.loads(SKELETON.read_text(encoding="utf-8"))
    rows = data.get("rows") or {}
    full = status.Dictionaries(groups={"full"})

    fixed, shown, skipped, held = 0, 0, 0, 0
    for key, row in rows.items():
        ru = row.get("ru") or ""
        if not ru:
            continue
        # ⚠️ Берём и НЕГОТОВЫЕ записи: заготовка пополняется абзацами, чей
        # ЗАГОЛОВОК расходится с режимным переводом (см. `clashing_heading`
        # в gen_full_paragraphs). У них `ru` предзаполнен обычным переводом,
        # и подставить имя — это вся работа. Готовой такая запись становится
        # только когда в ней нет и английских ТЕРМИНОВ: те правятся руками.
        fresh_row = not row.get("done")
        if fresh_row and row.get("terms"):
            continue
        head = heading(ru)
        plain = CODES.sub("", head)
        new_head = head
        for name in sorted(set(NAME.findall(plain)), key=len, reverse=True):
            if len(name) < 4 or name in KEEP_ENGLISH:
                continue
            got = status.lookup(name, full, origin="item_lore")
            if not got or not CYR.search(got[0]):
                continue
            # имя обязано стоять ЦЕЛИКОМ и отдельным словом
            pattern = r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])"
            # ⚠️ Позицию проверяем У КАЖДОГО вхождения по отдельности: одно
            # и то же имя в одной строке бывает и подлежащим, и после предлога.
            out, last, touched = [], 0, False
            for m in re.finditer(pattern, new_head):
                if not nominative_at(new_head, m.start()):
                    held += 1
                    continue
                if not standalone(new_head, m.start(), m.end()):
                    held += 1
                    continue
                if not gender_safe(new_head, m.start()):
                    held += 1
                    continue
                out.append(new_head[last:m.start()])
                out.append(got[0])
                last, touched = m.end(), True
            if touched:
                out.append(new_head[last:])
                new_head = "".join(out)
        if new_head == head:
            continue
        # ⚠️ Прежде тут стоял откат «в заголовке осталось английское слово».
        # Он был рассчитан на ЗАГОЛОВОК; со строкой целиком он откатывает
        # каждую запись, где в теле есть непереведённое имя, — то есть почти
        # все (замер: 8 правок вместо 29). От полуперевода теперь защищает
        # `standalone` — точечно, у места вставки, а не по всей строке.
        if shown < args.show:
            print(f"  было : {head[:74]}")
            print(f"  стало: {new_head[:74]}\n")
            shown += 1
        row["ru"] = new_head + ru[len(head):]
        if fresh_row:
            row["done"] = True
        fixed += 1

    print(f"поправлено заголовков: {fixed}")
    print(f"пропущено (осталось бы английское слово): {skipped}")
    print(f"НЕ ТРОНУТО (нужен падеж либо неясно): {held}")
    if not args.yes:
        print("\nсухой прогон. Применить: --yes")
        return 0
    SKELETON.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("записано. Дальше: python tools/gen_full_paragraphs.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
