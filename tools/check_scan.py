# -*- coding: utf-8 -*-
"""
СКАНЕР ЭКРАНА — проверка НА УМЕНИЕ НАХОДИТЬ.

`scan.py` смотрит подсказки до и после перевода и ищет то, что игрок замечает
глазами. Но у такого инструмента два способа соврать, и оба тихие:

  * ОСЛЕПНУТЬ — «находок нет» тогда читается как «всё хорошо». Ровно так
    в проекте уже обжигались: `swallows_longer` выбрасывал вообще всё
    и выглядел работающим;
  * ЗАШУМЕТЬ — показывать наши же решения бедой. Отчёт, который всегда
    красный, приучает в него не смотреть.

Поэтому проверяем ОБА края: подсаживаем каждую беду, которую игрок реально
присылал скриншотами, и следом прогоняем заведомо здоровую подсказку.

    python tools/check_scan.py
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan  # noqa: E402

# Здоровая заготовка: заголовок своим цветом, описание серым, подпись
# со значением на одной строке.
BASE = {
    "item": "Проверка",
    "before": [
        [["green", "Class Passive: Taunt"]],
        [["gray", "Increases the chance for mobs to target you"]],
        [["gray", "when you are above "], ["green", "25%"], ["gray", " HP."]],
        [["dark_gray", "Cooldown: "], ["green", "90s"]],
    ],
    "after": [
        [["green", "Пассивка класса: Taunt"]],
        [["gray", "Повышает шанс того, что мобы выберут целью тебя"]],
        [["gray", "когда у тебя выше "], ["green", "25%"], ["gray", " ХП."]],
        [["dark_gray", "Перезарядка: "], ["green", "90 с"]],
    ],
}


def cases():
    """Каждая беда — из настоящей находки игрока, а не выдумана."""
    out = []

    # «часть переведена, часть нет» — 31.07, Ghost Abilities и Tank Level
    bad = copy.deepcopy(BASE)
    bad["after"][1] = [["gray", "Increases the chance for mobs to target you"]]
    out.append(("ЛОСКУТ", bad))

    # заголовки пассивок уезжали в фиолетовый от редкости предмета
    bad = copy.deepcopy(BASE)
    bad["after"][0] = [["dark_purple", "Пассивка класса: Taunt"]]
    out.append(("ЦВЕТ", bad))

    # «Перезарядка:» одной строкой, «90 с» на следующей
    bad = copy.deepcopy(BASE)
    bad["after"][3] = [["dark_gray", "Перезарядка:"]]
    bad["after"].append([["green", "90 с"]])
    bad["before"].append([["gray", ""]])
    out.append(("ПОДПИСЬ", bad))

    # «…и даёт щит» / «щит на 5 с» — Hyperion
    bad = copy.deepcopy(BASE)
    bad["after"][1] = [["gray", "Повышает шанс и даёт щит"]]
    bad["after"][2] = [["gray", "щит на 5 с"]]
    out.append(("ПОВТОР", bad))

    # заголовок вобрал начало описания — способности сферы подземелья
    bad = copy.deepcopy(BASE)
    bad["after"][0] = [["green", "Пассивка класса: Taunt Повышает шанс того"]]
    out.append(("СЛИПЛОСЬ", bad))

    return out


def main():
    filters = scan.load_filters()
    missed = []

    print("%-12s %s" % ("подсажено", "что нашёл сканер"))
    for want, case in cases():
        kinds = [kind for kind, _note in scan.scan_case(case, filters)]
        ok = want in kinds
        if not ok:
            missed.append(want)
        print("  %-10s %s  %s" % (want, "[ok]  " if ok else "[СЛЕП]",
                                  ", ".join(kinds) or "ничего"))

    # ⚠️ Второй край: на здоровой подсказке находок быть не должно.
    kinds = [kind for kind, _note in scan.scan_case(BASE, filters)]
    clean = not kinds
    print("  %-10s %s  %s" % ("(здоровая)", "[ok]  " if clean else "[ЛОЖНО]",
                              ", ".join(kinds) or "чисто"))

    print()
    if missed or not clean:
        print("СЛОМАНО: пропущено %s%s" % (
            ", ".join(missed) or "нет",
            "" if clean else "; шумит на здоровой"))
        return 1
    print("сканер ловит все подсаженные беды и не шумит на здоровой")
    return 0


if __name__ == "__main__":
    sys.exit(main())
