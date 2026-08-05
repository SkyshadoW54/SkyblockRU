"""
Имена, ВНУТРИ которых термин справки термином не является.

Беда, ради которой написано (05.08). Игрок прислал Green Candy:

    Конфеты можно обменять у Fear
    Mongerer во время Spooky Festival!

и рядом развёрнутую справку про характеристику «Fear». Никакого Fear
в предмете нет — есть NPC «Fear Mongerer», торговец конфетами, и его имя
разрезано переносом.

⚠️ Правило «слово с Заглавной справа — продолжение имени» тут бессильно
ПО УСТРОЙСТВУ: между «Fear» и «Mongerer» прошла граница строки, а на границе
защита намеренно отключается (иначе пропадает справка там, где следующая
строка просто начинается с заглавной). Замер по 9150 живым подсказкам:
снять эту границу стоило бы **51 законного показа** — «Magic Find /
Increases the chance…», «Budget Hopper / Minion Shipping». Дорого и мимо.

⚠️ Чиним ДАННЫМИ, а не догадкой. Список имён у проекта есть (protected.py),
и пересечение с терминами справки оказалось крошечным — **10 пар на 1049
имён**: Fear Mongerer, Angler Angus, Dragontail Bank, Feast Chef Ted,
Scuba Simulator, Smoldering Tomb и ещё несколько. Перечислить их честнее,
чем гадать по форме текста.

Имена кладутся В САМУ СТАТЬЮ (поле «names»), а не общим списком: мод ищет
термин по одной статье за раз, и лишние имена ему не нужны.

Запуск:
  python tools/gen_wiki_names.py          покажет
  python tools/gen_wiki_names.py --write  впишет в справку
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

WIKI = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "wiki"
FILES = ("ru_ru.json", "enchants_ru_ru.json")


def blockers(terms: list[str], names: set[str]) -> dict[str, list[str]]:
    """Для каждого термина — имена, внутри которых он стоит целыми словами.

    ⚠️ Сравниваем ПО СЛОВАМ, а не подстрокой: иначе «Bank» нашёлся бы внутри
    «Bankrupt», а это другое слово. Тот же признак, что у `protected.mentions`.
    """
    out: dict[str, list[str]] = {}
    split = {name: name.split() for name in names if " " in name}
    for term in terms:
        words = term.split()
        size = len(words)
        found = []
        for name, parts in split.items():
            if len(parts) <= size:
                continue
            for i in range(len(parts) - size + 1):
                if parts[i:i + size] == words:
                    found.append(name)
                    break
        if found:
            out[term] = sorted(found)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="вписать в файлы справки")
    args = parser.parse_args()

    import protected

    names = protected.collect()
    total = 0
    for file in FILES:
        path = WIKI / file
        if not path.is_file():
            continue
        data = json.load(io.open(path, encoding="utf-8"))
        terms = data.get("terms") or {}
        found = blockers(sorted(terms), names)

        print(f"=== {file} ===")
        if not found:
            print("   имён-помех нет")
        for term, inside in sorted(found.items()):
            print(f"   {term:<22} внутри  {', '.join(inside)}")

        changed = 0
        for term, entry in terms.items():
            want = found.get(term)
            # ⚠️ Поле УБИРАЕМ, когда помех не осталось: иначе имя, выпавшее
            # из защиты, продолжало бы гасить справку — молча и навсегда.
            if want:
                if entry.get("names") != want:
                    entry["names"] = want
                    changed += 1
            elif "names" in entry:
                del entry["names"]
                changed += 1
        total += changed
        if args.write and changed:
            with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            print(f"   вписано: {changed} статей")
        elif changed:
            print(f"   изменится: {changed} статей (--write впишет)")

    # ⚠️ БЕЗ --write это СТОРОЖ, а не показ: несовпадение значит, что справка
    # отстала от списка защищённых имён. Появился новый NPC с термином внутри
    # имени — и мод снова покажет чужую справку, молча. Поэтому ненулевой код
    # возврата и место в круге сборки: инструмент, который надо ВСПОМНИТЬ,
    # защитой не является.
    if not args.write and total:
        print(f"\nСЛОМАНО: справка отстала от списка имён на {total} статей")
        print("    Впиши: python tools/gen_wiki_names.py --write")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
