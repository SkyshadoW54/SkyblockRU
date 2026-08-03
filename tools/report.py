"""
Что в переводе не так ПРЯМО СЕЙЧАС — рабочий список, а не ожидание скриншота.

Зачем. Весь день ошибки находил игрок: замечал глазами, присылал скриншот,
я чинил. Схема плохая — находки случайны, а узнаю я о них с задержкой. При этом
мод свои промахи ЗНАЕТ, просто раскладывал их по четырём файлам, которые никто
не открывал.

Этот скрипт их читает и складывает в один список по убыванию важности:

  1. СМЕСЬ ЯЗЫКОВ — мод выдал строку наполовину по-русски. Худший вид ошибки:
     хуже и целиком английской строки, и отсутствия перевода. Законные случаи
     (имена предметов и NPC остаются английскими) отсеиваются по protected.py.
  2. ПЕРЕВОД ЕСТЬ, НО НЕ ПРИМЕНЁН — абзац нашёлся в словаре, а защита цвета
     не дала его склеить. Каждая такая запись — готовый перевод, лежащий
     мёртвым грузом.
  3. ЧАСТО СПРАШИВАЮТ, А НЕТ — непереведённое по убыванию частоты.

Запуск:
  python tools/report.py
  python tools/report.py --show 40
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")

ICONS = re.compile(r"[\ue000-\uf8ff]")
# \u26a0\ufe0f \u0426\u0438\u0444\u0440\u0430 \u0438 \u043f\u043e\u0434\u0447\u0451\u0440\u043a\u0438\u0432\u0430\u043d\u0438\u0435 \u2014 \u0427\u0410\u0421\u0422\u042c \u0441\u043b\u043e\u0432\u0430, \u0430 \u043d\u0435 \u0435\u0433\u043e \u043a\u043e\u043d\u0435\u0446. \u041f\u0440\u0435\u0436\u043d\u0438\u0439
# \u00ab\b[A-Za-z][A-Za-z'-]+\b\u00bb \u043d\u0430 \u00abboml9\u00bb \u0438 \u00abcherepahaHlov_\u00bb \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u043b \u0432\u043e\u0432\u0441\u0435:
# \u043f\u043e\u0441\u043b\u0435 \u0431\u0443\u043a\u0432 \u0438\u0434\u0451\u0442 word-\u0441\u0438\u043c\u0432\u043e\u043b, \u0433\u0440\u0430\u043d\u0438\u0446\u044b \b \u0442\u0430\u043c \u043d\u0435\u0442, \u0438 \u0441\u043b\u043e\u0432\u043e \u043d\u0435 \u043d\u0430\u0445\u043e\u0434\u0438\u043b\u043e\u0441\u044c.
# \u0412\u044b\u0433\u043b\u044f\u0434\u0435\u043b\u043e \u044d\u0442\u043e \u043a\u0430\u043a \u0440\u0430\u0431\u043e\u0442\u0430\u044e\u0449\u0438\u0439 \u043e\u0442\u0441\u0435\u0432 \u2014 \u0430 \u0431\u044b\u043b\u043e \u0441\u043b\u0435\u043f\u043e\u0442\u043e\u0439: \u043d\u0430\u0441\u0442\u043e\u044f\u0449\u0430\u044f \u0441\u043c\u0435\u0441\u044c
# \u0441 \u0442\u0430\u043a\u0438\u043c \u0441\u043b\u043e\u0432\u043e\u043c \u0442\u043e\u0436\u0435 \u043f\u0440\u043e\u0448\u043b\u0430 \u0431\u044b \u043c\u043e\u043b\u0447\u0430. \u041e\u0442\u0441\u0435\u0432 \u043d\u0438\u043a\u043e\u0432 \u0442\u0435\u043f\u0435\u0440\u044c \u0434\u0435\u043b\u0430\u0435\u0442 \u043f\u0440\u0438\u0437\u043d\u0430\u043a
# \u043d\u0438\u0436\u0435 (OWNER), \u0438 \u0440\u0430\u0441\u0448\u0438\u0440\u0435\u043d\u0438\u0435 \u0441\u0442\u0430\u043b\u043e \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u044b\u043c.
LATIN_WORD = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_'-]+(?![A-Za-z0-9_])")

# \u26a0\ufe0f \u0412\u041b\u0410\u0414\u0415\u041b\u0415\u0426: \u0441\u043b\u043e\u0432\u043e, \u0441\u0442\u043e\u044f\u0449\u0435\u0435 \u0432 \u043e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\u0435 \u0432 \u043f\u0440\u0438\u0442\u044f\u0436\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0439 \u0444\u043e\u0440\u043c\u0435 \u2014 \u00abguysgv's
# Profile\u00bb, \u00abnokliis' Profile\u00bb, \u00abTaylor's Cosmetics\u00bb. \u041f\u043e-\u0440\u0443\u0441\u0441\u043a\u0438 \u043f\u0440\u0438\u043d\u0430\u0434\u043b\u0435\u0436\u043d\u043e\u0441\u0442\u044c
# \u043f\u0435\u0440\u0435\u0434\u0430\u0451\u0442 \u041f\u0410\u0414\u0415\u0416, \u0438 \u00ab's\u00bb \u043e\u0442\u043f\u0430\u0434\u0430\u0435\u0442: \u00ab\u041f\u0440\u043e\u0444\u0438\u043b\u044c guysgv\u00bb \u2014 \u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u044b\u0439 \u043f\u0435\u0440\u0435\u0432\u043e\u0434,
# \u0430 \u043d\u0435 \u0441\u043c\u0435\u0441\u044c \u044f\u0437\u044b\u043a\u043e\u0432. \u0421\u0430\u043c\u043e \u0438\u043c\u044f \u043f\u0440\u0438 \u044d\u0442\u043e\u043c \u043e\u0431\u044f\u0437\u0430\u043d\u043e \u043e\u0441\u0442\u0430\u0442\u044c\u0441\u044f \u043b\u0430\u0442\u0438\u043d\u0438\u0446\u0435\u0439 \u2014 \u043f\u043e \u043d\u0438\u043a\u0443
# \u0438\u0449\u0443\u0442 \u0438\u0433\u0440\u043e\u043a\u0430, \u043f\u043e \u0438\u043c\u0435\u043d\u0438 NPC \u0438\u0449\u0443\u0442 \u043f\u0435\u0440\u0441\u043e\u043d\u0430\u0436\u0430.
#
# \u0421\u043f\u0438\u0441\u043a\u043e\u043c \u0442\u0430\u043a\u0438\u0445 \u043d\u0435 \u0437\u0430\u043a\u0440\u044b\u0442\u044c: \u043d\u0438\u043a\u043e\u0432 \u0441\u0442\u043e\u043b\u044c\u043a\u043e, \u0441\u043a\u043e\u043b\u044c\u043a\u043e \u043b\u044e\u0434\u0435\u0439 \u043d\u0430 \u0441\u0435\u0440\u0432\u0435\u0440\u0435. \u0417\u0430\u0442\u043e
# \u043f\u0440\u0438\u0437\u043d\u0430\u043a \u0431\u0435\u0440\u0451\u0442\u0441\u044f \u0438\u0437 \u0421\u0410\u041c\u041e\u0419 \u0421\u0422\u0420\u041e\u041a\u0418 \u0438 \u043f\u043e\u0442\u043e\u043c\u0443 \u043f\u043e\u043b\u043e\u043d \u2014 \u0442\u043e \u0436\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u0435, \u0447\u0442\u043e \u0443\u0436\u0435
# \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u043e \u0432 protected.from_wiki (\u00ab\u043f\u0440\u0438\u0442\u044f\u0436\u0430\u0442\u0435\u043b\u044c\u043d\u0443\u044e \u0444\u043e\u0440\u043c\u0443 \u043d\u0435 \u0437\u0430\u0449\u0438\u0449\u0430\u0435\u043c\u00bb).
#
# \u041e\u0431\u043b\u0430\u0441\u0442\u044c \u0443\u0437\u043a\u0430\u044f: \u043e\u0442\u0441\u0435\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0440\u043e\u0432\u043d\u043e \u0442\u043e \u0441\u043b\u043e\u0432\u043e, \u043a\u043e\u0442\u043e\u0440\u043e\u0435 \u0432 \u041e\u0420\u0418\u0413\u0418\u041d\u0410\u041b\u0415 \u0431\u044b\u043b\u043e
# \u0432\u043b\u0430\u0434\u0435\u043b\u044c\u0446\u0435\u043c, \u0438 \u0442\u043e\u043b\u044c\u043a\u043e \u0435\u0441\u043b\u0438 \u0432 \u043f\u0435\u0440\u0435\u0432\u043e\u0434\u0435 \u043e\u043d\u043e \u0441\u0442\u043e\u0438\u0442 \u0443\u0436\u0435 \u0431\u0435\u0437 \u00ab's\u00bb. \u041d\u0430\u0441\u0442\u043e\u044f\u0449\u0430\u044f
# \u0441\u043c\u0435\u0441\u044c \u00abDragon's Breath\u00bb \u2192 \u00abDragon's \u0434\u044b\u0445\u0430\u043d\u0438\u0435\u00bb \u043d\u0430\u0445\u043e\u0434\u043a\u043e\u0439 \u043e\u0441\u0442\u0430\u0451\u0442\u0441\u044f: \u0442\u0430\u043c \u0441\u043b\u043e\u0432\u043e
# \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u043b\u043e \u0430\u043f\u043e\u0441\u0442\u0440\u043e\u0444, \u0442\u043e \u0435\u0441\u0442\u044c \u043f\u0435\u0440\u0435\u0432\u0435\u0434\u0435\u043d\u043e \u043d\u0435 \u0431\u044b\u043b\u043e.
OWNER = re.compile(r"([A-Za-z][A-Za-z0-9_-]*)'(?:s(?![A-Za-z0-9_])|(?![A-Za-z0-9_]))")

# \u0410\u0434\u0440\u0435\u0441 \u0441\u0430\u0439\u0442\u0430: \u00abMC.HYPIXEL.NET\u00bb, \u00abSTORE.HYPIXEL.NET\u00bb. \u041b\u0430\u0442\u0438\u043d\u0438\u0446\u0430 \u0432 \u043d\u0451\u043c \u0437\u0430\u043a\u043e\u043d\u043d\u0430
# \u0432\u0441\u0435\u0433\u0434\u0430 \u0438 \u043f\u0435\u0440\u0435\u0432\u043e\u0434\u0438\u0442\u044c \u0435\u0451 \u043d\u0435\u0447\u0435\u0433\u043e, \u0430 \u043f\u043e \u0441\u043b\u043e\u0432\u0430\u043c \u043e\u043d \u0440\u0430\u0441\u043f\u0430\u0434\u0430\u043b\u0441\u044f \u043d\u0430 \u00abMC\u00bb, \u00abHYPIXEL\u00bb,
# \u00abNET\u00bb \u2014 \u0438 \u043a\u0430\u0436\u0434\u0430\u044f \u0447\u0430\u0441\u0442\u044c \u0432\u044b\u0433\u043b\u044f\u0434\u0435\u043b\u0430 \u043a\u0430\u043a \u043d\u0435\u043f\u0435\u0440\u0435\u0432\u0435\u0434\u0451\u043d\u043d\u043e\u0435 \u0441\u043b\u043e\u0432\u043e. \u0421\u043f\u0438\u0441\u043a\u043e\u043c \u0438\u043c\u0451\u043d
# \u0442\u0430\u043a\u043e\u0435 \u043d\u0435 \u0437\u0430\u043a\u0440\u044b\u0442\u044c: \u0441\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u0435 \u0438\u0434\u0451\u0442 \u043f\u043e \u0441\u043b\u043e\u0432\u0430\u043c, \u0430 \u0434\u043e\u043c\u0435\u043d \u0441\u043b\u043e\u0432\u043e\u043c \u043d\u0435 \u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f.
DOMAIN = re.compile(r"\b[A-Za-z][A-Za-z-]*(?:\.[A-Za-z][A-Za-z-]*)+\b")


def load(name: str) -> dict:
    path = DUMP / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def show(text: str) -> str:
    return ICONS.sub("◇", text)


def mixed_lines(guarded: set[str]) -> list[tuple[str, str, list[str]]]:
    """
    Смесь языков за вычетом ЗАКОННОЙ.

    Английское слово в русской фразе законно в двух случаях, и оба — решения,
    а не промахи:
      * это защищённое имя (NPC, локация, валюта) — их мы нарочно не переводим;
      * это ВЛАДЕЛЕЦ из притяжательной формы оригинала («guysgv's Profile» →
        «Профиль guysgv»). Ник списком не закрыть, признак берётся из строки.

    Всё остальное — ошибка, и её надо чинить.
    """
    out = []
    # Регистр не в счёт: «Hypixel» в списке, а в строке «HYPIXEL» — то же имя.
    parts = {part.lower() for name in guarded for part in name.split()}
    for source, result in (load("mixed.json").get("lines") or {}).items():
        # владельцы берутся из ОРИГИНАЛА: в переводе «'s» уже отпало
        owners = {w.lower() for w in OWNER.findall(source)}
        rest = [w for w in LATIN_WORD.findall(DOMAIN.sub(" ", result))
                if w.lower() not in parts and w.lower() not in owners]
        if rest:
            out.append((source, result, rest))
    return out


PREP = "(?:на|в|к|с|до|от|за|по|из|у|о|об|для|при|над|под|про|через|со|ко)"
TAIL = re.compile(r"" + PREP + r"\s*$", re.I)
HEAD = re.compile(r"^\s*" + PREP + r"", re.I)


def bad_joins() -> list[tuple[str, str, str, str]]:
    """
    Соседние строки, чьи переводы вместе читаются плохо.

    Перенос режет фразу пополам, а построчный переводчик берёт куски порознь
    и не видит соседа. Порознь оба выглядят прилично: «Телепортируйся
    к выбранному блоку на» и «до 61 блоков». Вместе — «на до 61 блоков».

    Признак механический: перевод первого куска кончается предлогом, а второго
    с предлога начинается. Двух предлогов подряд в русском не бывает.
    """
    done = json.loads((ROOT / "data" / "work" / "from_game.json")
                      .read_text(encoding="utf-8")).get("exact") or {}
    blocks = (load("tooltips.json").get("tooltips") or [])
    seen, out = set(), []
    for block in blocks:
        lines = block.get("lines") or []
        for first, second in zip(lines, lines[1:]):
            ru_a, ru_b = done.get(first), done.get(second)
            if not ru_a or not ru_b or (first, second) in seen:
                continue
            seen.add((first, second))
            if TAIL.search(ru_a) and HEAD.match(ru_b):
                out.append((first, second, ru_a, ru_b))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", type=int, default=15, help="сколько строк на раздел")
    args = parser.parse_args()

    if not DUMP.exists():
        print(f"нет папки дампа: {DUMP}")
        return 1

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from protected import collect, resolve_collisions
    guarded = resolve_collisions(collect(), quiet=True)

    problems = 0

    # --- 1. смесь языков ---
    mixed = mixed_lines(guarded)
    print(f"=== СМЕСЬ ЯЗЫКОВ: {len(mixed)} ===")
    if not mixed:
        print("  чисто\n")
    else:
        print("  Мод выдал строку наполовину по-русски. Это хуже, чем не переводить.")
        for source, result, rest in mixed[:args.show]:
            print(f"\n  EN {show(source)[:88]}")
            print(f"  RU {show(result)[:88]}")
            print(f"     осталось английским: {', '.join(rest[:6])}")
        if len(mixed) > args.show:
            print(f"\n  ... ещё {len(mixed) - args.show}")
        print()
        problems += len(mixed)

    # --- 1b. плохая склейка соседних строк ---
    glued = bad_joins()
    print(f"=== ПЛОХАЯ СКЛЕЙКА СОСЕДНИХ СТРОК: {len(glued)} ===")
    if not glued:
        print("  чисто")
        print()
    else:
        print("  Строку разрезал перенос, и куски переведены порознь.")
        print("  По отдельности читаются, вместе — нет.")
        for first, second, ru_a, ru_b in glued[:args.show]:
            print()
            print(f"EN {show(first)[:44]} | {show(second)[:40]}")
            print(f"  RU {show(ru_a)[:44]} | {show(ru_b)[:40]}")
        print()
        problems += len(glued)

    # --- 2. перевод есть, но не применён ---
    #
    # ⚠️ СПИСКИ отсюда исключены, и это не смягчение отчёта. Отказ склеить
    # список больше не означает, что перевод пропал: `Paragraphs.listed` режет
    # найденный перевод по маркерам и выкладывает пункты своими строками
    # (см. ParagraphColors.listCuts). То есть для списка отказ — штатный путь,
    # а не потеря. Оставь их здесь — и раздел снова станет тем, чем был раздел
    # «часто встречается»: списком уже сделанного, из-за которого не видно
    # настоящих бед.
    cases = load("color-cases.json").get("cases") or []
    blocked = [c for c in cases if not c.get("merged")]
    lists = [c for c in blocked if "список" in (c.get("reason") or "")]
    blocked = [c for c in blocked if c not in lists]
    print(f"=== ПЕРЕВОД ЕСТЬ, НО ЗАЩИТА ЦВЕТА НЕ ДАЛА ЕГО ПРИМЕНИТЬ: {len(blocked)} ===")
    if not blocked:
        print("  таких нет")
        if lists:
            print(f"  (списков: {len(lists)} — их перевод режется по пунктам,"
                  " это штатный путь)")
        print()
    else:
        print("  Абзац нашёлся в словаре, но склеить его не дали цвета.")
        print("  Проверять правило: python tools/check_colors.py")
        for case in blocked[:args.show]:
            print(f"\n  цвета: {case['colors']}")
            print(f"     {case.get('reason', '')}")
            if case.get("sample"):
                print(f"     {show(case['sample'])[:78]}")
        if len(blocked) > args.show:
            print(f"\n  ... ещё {len(blocked) - args.show}")
        print()

    # --- 3. чего мод НЕ переведёт: спрашиваем движок, а не свой список ---
    #
    # ⚠️ Раньше этот раздел читал словари сам и брал из них только секции
    # `exact` и `paragraphs`. Значит он не знал ни про правила (2095 штук),
    # ни про то, что полосу над хотбаром мод переводит ПО КОЛОНКАМ, — и
    # объявлял непереведённым то, что переводится.
    #
    # Стоило это дорого, потому что раздел стоит ПЕРВЫМ в работе новой сессии.
    # Верхушку списка держало «SHIFT to DISMOUNT   RIGHT-CLICK to FIRE»
    # с 766 показами: обе колонки лежат в 20-ui.json переведёнными, а мод
    # честно режет строку по колонкам. Настоящая работа тонула под сделанной.
    #
    # Считать частоту по СТРОКАМ полосы нельзя и по второй причине: Hypixel
    # обновляет её несколько раз в секунду, пока надпись висит на экране.
    # Игрок сел за снежную пушку ОДИН раз — счётчик показал 1116. Поэтому
    # частота тут говорит «долго висело», а не «часто встречается», и
    # сортировка по ней уводит не туда.
    #
    # Разбор по колонкам, отсев непереводимого по замыслу и чтение всех секций
    # уже написаны в status.py и проверены на живых данных. Зовём их, а не
    # переписываем: вторая копия признака в этом проекте разъезжалась трижды.
    from status import Dictionaries, load_corpus, load_queue, survey
    survey(Dictionaries(), load_queue(), load_corpus(), args.show)

    print(f"\nитого требует внимания: {problems + len(blocked)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
