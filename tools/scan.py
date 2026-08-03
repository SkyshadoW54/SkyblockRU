# -*- coding: utf-8 -*-
"""
СКАНЕР ЭКРАНА — всё, что игрок увидел бы глазами, но считает машина.

Беда, ради которой написано. Игрок водит курсором по предметам, замечает
«тут русский, а строкой ниже английский», «заголовок слипся», «откуда
фиолетовый» — присылает скриншот, я чиню, через минуту он находит следующее.
Находки случайны, узнаём с задержкой, а он работает сканером.

⚠️ При этом ДАННЫЕ ДЛЯ ПОИСКА У НАС УЖЕ ЕСТЬ: мод пишет в `dump/preview.json`
каждую подсказку ДО и ПОСЛЕ перевода, с цветами. То есть у нас ровно то,
что видит игрок, ПЛЮС оригинал для сравнения. Всё, что он замечает глазами,
из этой пары вычислимо.

Признаки (каждый выведен из настоящей находки, а не придуман):

  ЛОСКУТ     строка осталась английской, а соседние переведены
  ЦВЕТ       в переводе появился цвет, которого нет в оригинале
             (заголовки пассивок уезжали в фиолетовый от редкости предмета)
  ПОДПИСЬ    строка кончается подписью с двоеточием, значение уехало вниз
             («Перезарядка:» / «90 с»)
  ЧИСЛО      строка кончается голым числом, единица уехала вниз
             («в радиусе 10» / «блоков»)
  СЛИПЛОСЬ   строка была ОТДЕЛЬНОЙ, а в переводе вошла в состав соседней
             (заголовок «Ability: X» с описанием)
  ПОВТОР     на стыке двух строк повторяется слово («и даёт щит» / «щит на 5 с»)

⚠️ ГРАНИЦА: сканер видит только те подсказки, которые игрок ОТКРЫВАЛ.
Данные приходят из игры, и про предмет, на который не наводились, знать
неоткуда. Но это уже не «ищи глазами» — достаточно походить по меню.

    python tools/scan.py                 сводка по видам
    python tools/scan.py --kind ЦВЕТ     только один вид
    python tools/scan.py --item Танк     только одна подсказка
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/preview.json")

CODES = re.compile(r"\u00a7.")
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
WORD = re.compile(r"[А-Яа-яЁёA-Za-z]+")
SENTENCE_END = (".", "!", "?", ":", ";")

# ⚠️ Цвета, которые в переводе появляются ЗАКОННО. Наши правила несут §-коды
# нарочно: «§4❣ §cНужна ступень §dHeart of the Mountain §a{n}§c.» — там и
# dark_red, и light_purple, и green приходят ИЗ ПРАВИЛА, а не от поломки.
# Первый прогон без этого списка выдал их как находки — то есть показывал
# нашу же разметку бедой.
EXPECTED_NEW = {"dark_red", "red", "light_purple", "green", "yellow", "gold"}


def text_of(row) -> str:
    if isinstance(row, str):
        return CODES.sub("", row)
    return CODES.sub("", "".join(p[1] for p in row if len(p) > 1))


def colors_of(row) -> set:
    if isinstance(row, str):
        return set()
    return {p[0] for p in row if len(p) > 1 and p[1].strip()}


def stem(word: str) -> str:
    return word.lower().replace("ё", "е")[:5]


def ends_with_label(text: str) -> bool:
    """Кончается подписью «Перезарядка:» — значение уехало на другую строку.

    ⚠️ Перед двоеточием годится и ЦИФРА: «Прогресс до уровня 4:» — подпись,
    просто её последнее слово число. Требуя букву, признак не узнавал такую
    строку и печатал находку с пустым примером — беда есть, а какая, непонятно.
    Java (`ParagraphColors.endsWithLabel`) принимает букву ИЛИ цифру, и копия
    здесь обязана совпадать с ней: разошедшиеся копии признака — отдельная
    болезнь этого проекта, каждый раз тихая.
    """
    tail = text.rstrip()
    if not tail.endswith(":"):
        return False
    last = tail.split()[-1] if tail.split() else ""
    return len(last) > 1 and any(ch.isalnum() for ch in last[:-1])


def has_pair(text: str) -> bool:
    """Стоят ли подпись и её значение на ОДНОЙ строке — «Перезарядка: 90 с».

    ⚠️ Считаем пару, а не двоеточие: строка «Цена продажи:» без хвоста парой
    не является, и именно поэтому признак не срабатывает там, где двоеточие
    добавил наш перевод, а значение и в оригинале стояло ниже.
    """
    head, sep, tail = text.strip().partition(":")
    return bool(sep and tail.strip() and any(ch.isalpha() for ch in head))


def torn_label(rows: list[str]) -> list[str]:
    """Места, где подпись разорвана переносом: «Цена» / «продажи:».

    Возвращает описания найденных мест — сравнивать надо ЧИСЛО таких мест
    в оригинале и в переводе, иначе признак ловит обычную вёрстку Hypixel,
    где подпись просто идёт следом за прозой.
    """
    out = []
    for index in range(len(rows) - 1):
        now, nxt = rows[index].strip(), rows[index + 1].strip()
        if not now or not nxt or now.endswith((".", "!", "?", ":", "»")):
            continue
        head = nxt.split()[0]
        if head.endswith(":") and len(head) > 1 and any(ch.isalpha() for ch in head):
            out.append(f"«{now[-18:]}» / «{head}»")
    return out


def dangling_number(rows: list[str], index: int) -> bool:
    """Строка кончается голым числом, а под ней есть НЕПУСТАЯ строка.

    Единица измерения уехала вниз только тогда, когда ей есть куда уезжать:
    у последней строки подсказки и перед пустой строкой числу стоять законно.
    """
    if index + 1 >= len(rows) or not rows[index + 1].strip():
        return False
    return ends_with_number(rows[index])


def ends_with_number(text: str) -> bool:
    """Кончается голым числом — единица измерения уехала вниз.

    ⚠️ Точка в конце ОТМЕНЯЕТ находку: «Heart of the Mountain 7.» — это
    законченное предложение, а не оторванное число. Без этой проверки
    первый прогон выдал девять таких строк, и все были ложными.
    """
    tail = text.rstrip()
    if tail.endswith((".", "!", "?", ":", ";", ",")):
        return False
    words = tail.split()
    if not words:
        return False
    last = words[-1]
    return any(ch.isdigit() for ch in last) and not any(ch.isalpha() for ch in last)


def load_filters():
    import protected
    import terms
    guarded = {n.lower() for n in protected.collect()}
    jargon = {n.lower() for n in terms.STAT_JARGON}
    decided, rules = set(), []
    try:
        import make_queue
        known, _g, covered = make_queue.already_translated()
        decided = {k.lower() for k in known}
        rules = covered
    except Exception as failure:
        print(f"не смог прочитать решения по словарям: {failure}")
    return guarded, jargon, decided, rules


def still_english(line, guarded, jargon, decided, rules) -> bool:
    if not LATIN_WORD.search(line):
        return False
    stripped = line.strip()
    if stripped.lower() in decided:
        return False
    for rule in rules:
        try:
            if rule.search(stripped):
                return False
        except AttributeError:
            continue
    clean = line.lower()
    for name in guarded | jargon:
        if name in clean:
            clean = clean.replace(name, " ")
    return bool(LATIN_WORD.search(clean))


def scan_case(case, filters):
    """Все находки одной подсказки: список (вид, пояснение)."""
    guarded, jargon, decided, rules = filters
    before_rows = case.get("before") or []
    after_rows = case.get("after") or []
    before = [text_of(r) for r in before_rows]
    after = [text_of(r) for r in after_rows]
    item = (case.get("item") or "?").strip()
    found = []

    # --- ЛОСКУТ: часть строк переведена, часть нет
    if len(before) == len(after):
        translated, english = 0, []
        for index, (was, now) in enumerate(zip(before, after)):
            if not was.strip():
                continue
            if index == 0 and now.strip() == item:
                continue          # имя предмета не переводим нарочно
            if was != now:
                translated += 1
            elif still_english(now, guarded, jargon, decided, rules):
                english.append(now)
        if translated and english:
            found.append(("ЛОСКУТ", f"{len(english)} строк англ. при {translated} рус.: "
                                    f"{english[0][:52]}"))

    # --- ЦВЕТ: в переводе есть цвет, которого не было в оригинале
    was_colors = set()
    for row in before_rows:
        was_colors |= colors_of(row)
    for row in after_rows:
        new = colors_of(row) - was_colors - EXPECTED_NEW
        if new:
            found.append(("ЦВЕТ", f"взялся {', '.join(sorted(new))}: "
                                  f"{text_of(row)[:48]}"))
            break

    # --- ПОДПИСЬ, ЧИСЛО и РАЗРЫВ: сверяем СТРУКТУРУ подсказки целиком
    #
    # ⚠️ Раньше строка перевода сверялась с оригинальной ПО ИНДЕКСУ, и это
    # давало 29 ложных находок из 58 (замер 31.07 по 137 живым подсказкам).
    # Причина одна на оба признака: русский текст занимает больше строк,
    # индексы разъезжаются — и `before[index]` оказывается уже другой строкой.
    # Так «Ступенчатый бонус: Squashbuckle (0/4)» объявлялось оторванным
    # числом, хотя счётчик и в оригинале стоит там же: это НАША правка,
    # и она работает верно.
    #
    # Второй источник вранья — двоеточие, которого у Hypixel не было:
    # «Sell Price» / «92 Coins» мы переводим как «Цена продажи:» / «92 монет».
    # Значение как стояло на своей строке, так и стоит, а признак видел бедой
    # саму подпись. Отчёт, показывающий наши РЕШЕНИЯ бедой, приучает в него
    # не смотреть — это в проекте уже записано дважды.
    #
    # Теперь считаем ПАРЫ «подпись + значение на одной строке»: беда, если
    # их стало меньше, чем прислал Hypixel. Признак не зависит ни от сдвига
    # строк, ни от того, добавили ли мы двоеточие от себя.
    pairs_before = sum(1 for row in before if has_pair(row))
    pairs_after = sum(1 for row in after if has_pair(row))
    if pairs_after < pairs_before:
        torn = next((row for row in after if ends_with_label(row)), "")
        found.append(("ПОДПИСЬ", f"значение уехало вниз: {torn[-40:]}"))

    bare_before = sum(1 for i, row in enumerate(before) if dangling_number(before, i))
    bare_after = sum(1 for i, row in enumerate(after) if dangling_number(after, i))
    if bare_after > bare_before:
        torn = next((row for i, row in enumerate(after) if dangling_number(after, i)), "")
        found.append(("ЧИСЛО", f"единица уехала вниз: {torn[-40:]}"))

    # ⚠️ РАЗРЫВ ПОДПИСИ — беда, которой прежний сканер не видел вовсе, хотя
    # она и была единственной настоящей находкой того прогона:
    #     Hypixel:  «Sell Price» / «6 Coins»
    #     на экране: «Цена» / «продажи:» / «6 монет»
    # Русская подпись длиннее английской, а ширину мод берёт по самой длинной
    # строке ОРИГИНАЛА, чтобы не двигать окно, — в узкой подсказке подпись
    # перестаёт помещаться и рвётся посередине. Признак: следующая строка
    # НАЧИНАЕТСЯ хвостом подписи, а текущая знаком конца не завершена.
    # ⚠️ И тут признак сверяется с ОРИГИНАЛОМ, а не берётся сам по себе:
    # «проза без точки, а следом подпись» — обычная вёрстка Hypixel, и такой
    # структуры в подсказках полно. Бедой это становится, только когда разрывов
    # стало БОЛЬШЕ, чем прислал сервер. Без сверки признак давал 36 находок
    # вместо одной настоящей.
    torn_before = torn_label(before)
    torn_after = torn_label(after)
    if len(torn_after) > len(torn_before):
        found.append(("РАЗРЫВ", f"подпись разорвана: {torn_after[0]}"))

    # --- СЛИПЛОСЬ: заголовок был ОТДЕЛЬНОЙ строкой, а в переводе вошёл
    # в состав соседней.
    #
    # ⚠️ Признак строгий НАРОЧНО. Первая версия сравнивала длины строк
    # и давала 13 находок, из которых половина — обычный перенос («Купить
    # сейчас: …монет»). Смотрим по СМЫСЛУ: заголовок в оригинале выделен
    # цветом и стоит один в строке, а в переводе после него на ТОЙ ЖЕ
    # строке идёт начало следующей.
    if len(before) == len(after):
        for index in range(len(before) - 1):
            head = before[index].strip()
            if not head or len(head) > 56 or head.endswith((".", "!", "?")):
                continue
            own = colors_of(before_rows[index])
            below = colors_of(before_rows[index + 1])
            # заголовок ОДНОЦВЕТНЫЙ и цвет у него свой, отличный от описания
            if len(own) != 1 or not below or own == below:
                continue
            now = after[index].strip()
            # первые слова описания оказались в строке заголовка
            first_words = " ".join(before[index + 1].split()[:2])
            translated_below = after[index + 1].strip() if index + 1 < len(after) else ""
            if not first_words or not now:
                continue
            piece = " ".join(translated_below.split()[:2])
            if piece and piece.lower() in now.lower():
                found.append(("СЛИПЛОСЬ", f"заголовок вошёл в описание: {now[:52]}"))
                break

    # --- ПОВТОР на стыке строк
    for index in range(len(after) - 1):
        a_line, b_line = after[index], after[index + 1]
        if not a_line.strip() or not b_line.strip():
            continue
        if a_line.rstrip().endswith(SENTENCE_END):
            continue
        left, right = WORD.findall(a_line), WORD.findall(b_line)
        if not left or not right:
            continue
        if left[-1].lower() == right[0].lower() and len(left[-1]) > 2:
            found.append(("ПОВТОР", f"«{left[-1]}» дважды: …{a_line[-28:]} | {b_line[:28]}…"))
            break

    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kind", help="только один вид находок")
    parser.add_argument("--item", help="только подсказки с этим именем")
    parser.add_argument("--show", type=int, default=8, help="сколько показать в каждом виде")
    args = parser.parse_args()

    if not DUMP.exists():
        print(f"нет файла: {DUMP}")
        print("Он появляется, когда игрок наводит курсор на предметы в игре.")
        return 0

    cases = json.loads(DUMP.read_text(encoding="utf-8")).get("cases") or []
    filters = load_filters()

    by_kind = defaultdict(list)
    for case in cases:
        item = (case.get("item") or "?").strip()
        if args.item and args.item.lower() not in item.lower():
            continue
        for kind, note in scan_case(case, filters):
            by_kind[kind].append((item, note))

    print(f"подсказок просмотрено: {len(cases)}")
    total = sum(len(v) for v in by_kind.values())
    print(f"находок: {total}")
    print()

    # ⚠️ Признак, забытый здесь, СЧИТАЕТСЯ, но не печатается — то есть находки
    # пропадают молча, а итог «находок 70» перестаёт сходиться с показанным.
    # Добавил признак в scan_case — добавь и сюда.
    order = ["ЛОСКУТ", "СЛИПЛОСЬ", "ЦВЕТ", "ПОВТОР", "РАЗРЫВ", "ПОДПИСЬ", "ЧИСЛО"]
    for kind in order:
        rows = by_kind.get(kind) or []
        if not rows or (args.kind and args.kind.upper() != kind):
            continue
        print(f"=== {kind}: {len(rows)} ===")
        for item, note in rows[:args.show]:
            print(f"  {item[:30]:<30} {note[:78]}")
        if len(rows) > args.show:
            print(f"   ... ещё {len(rows) - args.show}")
        print()

    if not total:
        print("на просмотренных подсказках беды не видно")
    return 0


if __name__ == "__main__":
    sys.exit(main())
