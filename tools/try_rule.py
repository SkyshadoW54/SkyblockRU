"""
Примерка ПРАВИЛА до того, как оно попало в словарь.

Зачем отдельный инструмент. Семей почти одинаковых строк в очереди больше
четырёхсот (`find_families.py`), и каждая закрывается одним правилом вместо
покупки полусотни переводов. Но правило — самая опасная запись словаря:
оно ловит строки, которых мы не видели, и промах виден только на экране
у игрока. В этом файле записаны три случая подряд, когда правило испортило
работу: «Grants a {n}% chance to drop an» дало смесь языков, «^(.+) Collection$»
съело счётчик и апостроф, «^You bought (.+)!$» поймало «You bought back».

Инструмент отвечает на четыре вопроса, и все четыре — по ДАННЫМ:

  ЛОВИТ             сколько ждущих строк очереди закроется и что выйдет
  ЗАДЕНЕТ КУПЛЕННОЕ совпадёт ли результат с уже оплаченным переводом
  ЗАБЫТО В ЗАМЕНЕ   английские слова вне захватов — непереведённый кусок
  ЛАТИНИЦА ИЗ ЗАХВАТОВ  что осталось английским, списком и глазами
  УЖЕ ЗАКРЫТО       не ловит ли эти строки чужое правило (тогда работы нет)

⚠️ Примеряется строка С ПОДСТАВЛЕННЫМИ ЧИСЛАМИ. В очереди и дампе лежит
обобщённый вид («Skill {n}.»), а движок применяет правила ДО обобщения,
под живое число («Skill 22»). Прямое сравнение не совпадает НИКОГДА —
записанная грабля проекта, наступали четырежды. Образцы дырок берём
у очереди (`make_queue.HOLE_*`), своей копии не заводим.

⚠️ Шаблон Java и шаблон Python расходятся в мелочах, поэтому после примерки
всё равно нужен `python tools/check_rules.py` — он компилирует настоящей Java.

Запуск:
  python tools/try_rule.py "^Ты (.+)$" "Ты $1"
  python tools/try_rule.py ПАТТЕРН ЗАМЕНА --tg      захваты переводить словарём
  python tools/try_rule.py ПАТТЕРН ЗАМЕНА --show 25 сколько примеров печатать
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_queue  # noqa: E402  (образцы дырок и разбор словарей)

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "work" / "from_game.json"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")

ICON = re.compile("[\ue000-\uf8ff]")


def show(text: str, width: int = 76) -> str:
    """Значки нечитаемы в терминале и ломают ширину — меткой их."""
    text = ICON.sub("<>", text)
    return text if len(text) <= width else text[: width - 1] + "…"


def apply(pattern: re.Pattern, replacement: str, probe: str,
          tg: bool, engine) -> str | None:
    """
    Что выйдет на экране. Повторяет `Translator`: `$1` — номер группы,
    а при `tg` захват дополнительно переводится словарём.
    """
    match = pattern.fullmatch(probe)
    if not match:
        return None
    out: list[str] = []
    position = 0
    while position < len(replacement):
        symbol = replacement[position]
        if symbol == "$" and position + 1 < len(replacement) \
                and replacement[position + 1].isdigit():
            number = int(replacement[position + 1])
            position += 2
            if 1 <= number <= match.re.groups and match.group(number) is not None:
                piece = match.group(number)
                if tg and engine is not None:
                    status, dictionaries = engine
                    piece = status.translate_group(piece, dictionaries)
                out.append(piece)
            continue
        out.append(symbol)
        position += 1
    return "".join(out)


LATIN = re.compile(r"[A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*)*")

# ⚠️ Римская цифра — не английское слово: она одинакова на любом языке,
# ровно как число и значок. Записанная грабля проекта: у `stillEnglish`
# уровни «III» перевешивали чашу, и список зачарований оставался английским
# целиком, хотя две трети названий словарь знал.
ROMAN = re.compile(r"[IVXLCDM]+")


def forgotten_in_replacement(replacement: str) -> list[str]:
    """
    Английские слова в САМОЙ замене, вне захватов, — это забытый кусок.

    Признак точный: что стоит в замене, автор правила написал руками,
    и латиница там означает непереведённое слово. Единственное исключение —
    счётчик «x» («64x Bone»), он одинаков на любом языке.
    """
    text = re.sub(r"\$\d", " ", replacement)
    return [word for word in LATIN.findall(text) if word.strip() not in ("x",)]


def latin_from_groups(result: str, replacement: str) -> list[str]:
    """
    Что приходит латиницей ИЗ ЗАХВАТОВ.

    ⚠️ Машинного признака «это законное имя или забытый перевод» тут НЕТ,
    и заводить его я пробовал дважды. Список защищённых имён врёт в обе
    стороны сразу: `real_items` зовёт предметом кнопку меню «Instant Sell»
    (в `item_name` от сервера лежат и заголовки кнопок), а имён мобов
    бестиария — «Dumpster Diver» — в нём нет вовсе. Поэтому инструмент
    не судит, а ПОКАЗЫВАЕТ списком: имя предмета в захвате законно,
    а «Instant Sell» — забытое действие, и видно это глазами за секунду.
    """
    fixed = set(forgotten_in_replacement(replacement))
    return [word for word in LATIN.findall(result)
            if word not in fixed and not ROMAN.fullmatch(word)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pattern", help="шаблон правила (как в словаре)")
    parser.add_argument("replacement", help="замена (как в словаре, с $1)")
    parser.add_argument("--tg", action="store_true",
                        help="захваты переводить по словарю")
    parser.add_argument("--show", type=int, default=12,
                        help="сколько примеров печатать в каждом разделе")
    args = parser.parse_args()

    try:
        pattern = re.compile(args.pattern)
    except re.error as error:
        print(f"ШАБЛОН НЕ КОМПИЛИРУЕТСЯ: {error}")
        return 1

    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    exact = queue["exact"]
    contexts = queue.get("_contexts", {})

    import status  # ленивый: он сам берёт образцы дырок у очереди
    engine = (status, status.Dictionaries())
    known, guarded, covered = make_queue.already_translated()

    waiting: list[tuple[str, str]] = []
    paid: list[tuple[str, str, str]] = []
    latin: collections.Counter = collections.Counter()

    for key, translation in exact.items():
        probe = key.replace("{n}", make_queue.HOLE_NUMBER) \
                   .replace("{s}", make_queue.HOLE_NAME)
        result = apply(pattern, args.replacement, key, args.tg, engine)
        if result is None:
            result = apply(pattern, args.replacement, probe, args.tg, engine)
        if result is None:
            continue
        if translation:
            paid.append((key, translation, result))
        else:
            waiting.append((key, result))
        latin.update(latin_from_groups(result, args.replacement))

    print(f"=== ЛОВИТ В ОЧЕРЕДИ: {len(waiting) + len(paid)} строк "
          f"({len(waiting)} ждут, {len(paid)} уже куплены) ===")
    for key, result in waiting[: args.show]:
        note = contexts.get(key, "")
        print(f"   {show(key)}")
        print(f"     -> {show(result)}")
        if note:
            print(f"        [{note}]")
    if len(waiting) > args.show:
        print(f"   ... ещё {len(waiting) - args.show}")

    print()
    print(f"=== ЗАДЕНЕТ КУПЛЕННОЕ: {len(paid)} ===")
    if paid:
        print("   Точную запись движок ищет РАНЬШЕ правил, поэтому перевод")
        print("   не потеряется. Смотреть надо на РАЗНОБОЙ: если правило даёт")
        print("   не то же самое, соседние строки на экране разъедутся.")
        # ⚠️ Сравниваем ПОСЛЕ возврата образцов в дырки. Примерка идёт на строке
        # с подставленными числами, а купленный перевод хранит «{n}» — прямое
        # сравнение объявляло разными «Ты продал Gold Ore x{n}» и «...x1,234»,
        # то есть ровно совпадающие записи. Обобщение — часть ключа, и применять
        # его надо к ОБЕИМ сторонам сравнения: записанная грабля проекта.
        same = sum(1 for _, was, now in paid if was == status.unfill(now))
        print(f"   совпадает с купленным: {same} из {len(paid)}")
        for key, was, now in paid[: args.show]:
            now = status.unfill(now)
            mark = "  =" if was == now else "  ≠"
            print(f"   {mark} {show(key)}")
            print(f"        куплено: {show(was)}")
            if was != now:
                print(f"        правило: {show(now)}")
    else:
        print("   ничего — правило работает только на новых строках")

    print()
    forgotten = forgotten_in_replacement(args.replacement)
    print(f"=== ЗАБЫТО В САМОЙ ЗАМЕНЕ: {len(forgotten)} ===")
    if forgotten:
        print("   Это английские слова, которые ты написал руками вне захватов —")
        print("   то есть непереведённый кусок правила. Признак точный.")
        for word in forgotten:
            print(f"   {word!r}")
    else:
        print("   чисто — вне захватов английского нет")

    print()
    print(f"=== ЛАТИНИЦА ИЗ ЗАХВАТОВ: {len(latin)} разных ===")
    print("   Машина не знает, законное это имя или забытый перевод, и списка,")
    print("   который знал бы, в проекте НЕТ (см. комментарий в коде).")
    print("   Смотреть глазами: имя предмета законно, действие — забыто.")
    for word, count in latin.most_common(args.show):
        print(f"   {count:5}  {word}")
    if len(latin) > args.show:
        print(f"   ... ещё {len(latin) - args.show}")

    print()
    by_rule = [key for key, _ in waiting
               if make_queue.covered_by_rule(key, covered)]
    by_dict = [key for key, _ in waiting if key in known]
    by_off = [key for key, _ in waiting
              if make_queue.guarded_by_toggle(key, guarded)]
    print(f"=== УЖЕ ЗАКРЫТО БЕЗ НАС: правилом {len(by_rule)}, "
          f"словарём {len(by_dict)}, выключенным словарём {len(by_off)} ===")
    if by_rule or by_dict or by_off:
        print("   Эти строки правило не спасёт — их и так переводят")
        print("   (либо решено оставить английскими).")
        for key in (by_rule + by_dict + by_off)[: args.show]:
            print(f"   {show(key)}")
    else:
        print("   ни одной — работа настоящая")

    print()
    print("дальше: вписать в словарь и прогнать python tools/check_rules.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
