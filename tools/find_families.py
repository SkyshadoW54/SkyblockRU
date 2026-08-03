"""
Ищет СЕМЬИ почти одинаковых записей — те, что должны быть одним правилом.

Зачем. За вечер трижды всплыло одно и то же: точная запись покрывает ОДИН
вариант строки, а Hypixel меняет в ней уровень, число, знак препинания или имя
предмета — и остальные варианты тихо остаются английскими.

    Level VII Rewards:      Acacia Log III Rewards:     Spruce Log IV Rewards:
    Level X Rewards:        Birch Log III Rewards:      Pufferfish I Rewards:
    ...двадцать записей, а голого «Rewards:» среди них нет

Беда двойная:
  * НЕПОЛНОТА — вариантов всегда больше, чем успели собрать;
  * РАЗНОБОЙ — каждую строку модель переводила отдельно, не видя соседей,
    и вышло «Награды ЗА Acacia Log III» рядом с «Награды Birch Log III».

Плюс деньги: за каждый вариант платили как за отдельную строку.

Скрипт сводит записи к скелету (уровень, число, имя -> метка) и показывает
семьи, которые стоит заменить правилом. Сортировка по размеру: сверху то,
где выгода больше всего.

Запуск:
  python tools/find_families.py
  python tools/find_families.py --min 3 --show 20
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

ICONS = re.compile(r"[-]")

# Изменчивые куски: то, ради чего и заводится правило
ROMAN = re.compile(r"(?<![A-Za-z])[IVXLC]{1,6}(?![A-Za-z])")
# ⚠️ Обобщение чисел — из общего pkey: копий было шесть, и одна
# уже разошлась (в measure_color процент попадал внутрь числа).
from pkey import NUMBER  # noqa: E402
# Имя собственное: два и больше слова с заглавной подряд
NAME = re.compile(r"[A-Z][A-Za-z'-]+(?: [A-Z][A-Za-z'-]+)+")
# Одно слово с заглавной посреди строки (не в начале)
LONE_NAME = re.compile(r"(?<=[a-z,] )[A-Z][A-Za-z'-]{2,}")

# Замеренная цена строки на прогоне до оптимизации кэша
PRICE_PER_LINE = 0.0079

# ⚠️ Эти словари ПЕРЕЧИСЛЯЮТ ОСОЗНАННО, и правилом их не заменить.
#
# «50-rarity» — строка редкости есть у каждого предмета, и комбинации
# «редкость + тип» перебираются целиком нарочно: забудешь одну, она полезет
# в игре на самом видном месте. «26-time» — время суток, где перевод зависит
# от значения («10:00 утра» против «22:00 вечера»), то есть правилом это
# как раз НЕ выражается. Их собирают генераторы, и это правильно.
GENERATED = {"50-rarity.json", "26-time.json", "45-materials.json",
             "80-vanilla-names.json", "70-enchants.json"}

# Скелет короче этого — не семья, а совпадение формы
MIN_SKELETON_WORDS = 3


def skeleton(text: str) -> str:
    """Строка без изменчивых частей. Одинаковый скелет = одна семья."""
    s = ICONS.sub("◇", text)
    s = NAME.sub("<имя>", s)
    s = ROMAN.sub("<ур>", s)
    s = NUMBER.sub("<n>", s)
    s = s.replace("{n}", "<n>").replace("{s}", "<ник>")
    s = LONE_NAME.sub("<имя>", s)
    return re.sub(r"\s{2,}", " ", s).strip()


QUEUE = ROOT / "data" / "work" / "from_game.json"


def queue_waiting() -> dict[str, tuple[str, str]]:
    """
    Строки, за которые очередь ПРОСИТ ДЕНЬГИ, — источник семей вместо словаря.

    Зачем отдельный режим. Обычный поиск смотрит УЖЕ КУПЛЕННОЕ и говорит, где
    мы переплатили в прошлом. А очередь — счёт, который ещё не оплачен, и та же
    комбинаторика видна в нём ДО траты: 52 имени коллекций по десятку уровней
    каждое — «Coal VII», «Carrot IX», «Lapis Lazuli VI» — это 331 строка,
    которую закрывает ОДНО правило.

    ⚠️ Переводов у этих строк нет по определению, поэтому признак «разнобой
    внутри семьи» здесь неприменим: разъезжаться пока нечему. Зато признак
    «правило УЖЕ есть» становится важнее — он означает, что очередь просит
    денег за сделанное.
    """
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    exact = data.get("exact") or {}
    asis = set(data.get("_asis") or [])
    return {key: ("", "очередь") for key, value in exact.items()
            if not value and key not in asis}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--min", type=int, default=3, help="от скольких записей считать семьёй")
    parser.add_argument("--show", type=int, default=12)
    parser.add_argument("--queue", action="store_true",
                        help="искать семьи среди ЖДУЩИХ строк очереди, а не в словарях")
    args = parser.parse_args()

    entries: dict[str, tuple[str, str]] = {}
    rules: list[re.Pattern] = []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # ⚠️ Правила собираем ИЗ ВСЕХ словарей, включая генерируемые: семья,
        # закрытая правилом, — это сделанная работа, и показывать её как долг
        # нельзя. Раньше список шёл вперемешку, и первые пять семей в нём были
        # уже закрыты («✖ Talk to», «This skin can only be applied to»).
        for rule in pack.get("regex") or []:
            if not rule.get("r"):
                continue
            try:
                rules.append(re.compile(rule["p"]))
            except re.error:
                continue
        if path.name in GENERATED or args.queue:
            continue
        for source, target in (pack.get("exact") or {}).items():
            if target and source not in entries:
                entries[source] = (target, path.name)

    # ⚠️ Правила собраны выше по ВСЕМ словарям — их нужно знать в обоих
    # режимах, иначе семья, давно закрытая правилом, снова покажется работой.
    if args.queue:
        entries = queue_waiting()

    families: dict[str, list[tuple[str, str, str]]] = collections.defaultdict(list)
    for source, (target, pack) in entries.items():
        families[skeleton(source)].append((source, target, pack))

    big = [(sk, rows) for sk, rows in families.items()
           if len(rows) >= args.min and len(sk.split()) >= MIN_SKELETON_WORDS]

    def covered(rows: list[tuple[str, str, str]]) -> bool:
        """Семью уже держит правило? Проверяем на КАЖДОЙ записи, не на первой.

        Правило, поймавшее только часть семьи, работу не закрывает: остальные
        варианты по-прежнему держатся точными записями, а новых мы не увидим.

        ⚠️ Примеряем ОБЕ формы: как есть и с заполненными дырками. В очереди
        строка лежит ОБОБЩЁННОЙ («Big Yum! You refresh +{n} Pet Luck for {n}
        hours!»), а правило писано под живую («\\+([\\d,.]+)») — движок применяет
        его ДО обобщения, и прямое сравнение не совпадёт НИКОГДА. Из-за этого
        инструмент звал писать правило, которое давно стоит.

        ⚠️ Это ТРЕТЬЕ место с одной и той же слепотой (были `status.verdict`
        и `uncovered_columns`). Образцы берём у очереди — `make_queue.HOLE_*`,
        свою копию не заводим: копия признака в этом проекте расходилась молча
        уже трижды.
        """
        try:
            from make_queue import HOLE_NAME, HOLE_NUMBER
        except ImportError:
            HOLE_NUMBER = HOLE_NAME = None

        def hit(source: str) -> bool:
            probes = [source]
            if HOLE_NUMBER:
                probes.append(source.replace("{n}", HOLE_NUMBER).replace("{s}", HOLE_NAME))
            return any(rx.search(probe) for rx in rules for probe in probes)

        return all(hit(source) for source, _, _ in rows)

    # Непокрытые вперёд: это и есть работа. Внутри — по размеру семьи.
    marked = [(sk, rows, covered(rows)) for sk, rows in big]
    marked.sort(key=lambda item: (item[2], -len(item[1])))

    todo = [item for item in marked if not item[2]]
    waste = sum(len(rows) - 1 for _, rows, done in marked if not done)
    covered_rows = sum(len(rows) for _, rows, done in marked if done)
    what = "строк ждёт в очереди" if args.queue else "точных записей всего"
    print(f"{what}: {len(entries)}")
    print(f"семей от {args.min} записей: {len(big)}")
    if args.queue:
        # ⚠️ У очереди «правило УЖЕ есть» — не отчёт о сделанном, а НАХОДКА:
        # значит она просит денег за строки, которые движок и так переводит.
        print(f"  правило УЖЕ есть: {len(marked) - len(todo)} семей"
              f" ({covered_rows} строк) — ПРОСЯТ ДЕНЕГ ЗРЯ")
        print(f"  правила НЕТ:      {len(todo)} семей")
        print(f"строк уйдёт, если закрыть правилами: {waste + covered_rows}"
              f"  (~${(waste + covered_rows) * PRICE_PER_LINE:.2f})\n")
    else:
        print(f"  правило УЖЕ есть: {len(marked) - len(todo)} — это сделанная работа")
        print(f"  правила НЕТ:      {len(todo)}")
        print(f"лишних записей в непокрытых: {waste}"
              f"  (~${waste * PRICE_PER_LINE:.2f} по цене прогона)\n")

    for sk, rows, done in marked[:args.show]:
        if done:
            continue
        # разнобой внутри семьи: одинаковый скелет перевода — признак
        # единообразия. У очереди переводов нет, разъезжаться нечему.
        if args.queue:
            mark = "к покупке"
        else:
            shapes = {skeleton(target) for _, target, _ in rows}
            mark = "РАЗНОБОЙ" if len(shapes) > 1 else "единообразно"
        print(f"=== {len(rows)} записей, {mark}")
        print(f"    скелет: {sk[:88]}")
        for source, target, pack in sorted(rows)[:4]:
            print(f"      {source[:52]}")
            if target:
                print(f"        -> {target[:52]}   [{pack}]")
        if len(rows) > 4:
            print(f"      ... ещё {len(rows) - 4}")
        print()

    print("Каждая такая семья должна быть ОДНИМ правилом с захватом:")
    print("  вариантов всегда больше, чем успели собрать, а перевод не разъезжается.")
    print("⚠️ Правило ставим ЗАПАСНЫМ путём: точные записи движок ищет первыми,")
    print("  купленные переводы остаются, а правило подхватывает новые варианты.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
