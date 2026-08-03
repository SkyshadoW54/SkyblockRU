"""
Доехала ли правка до игры: jar в инстансах против собранных.

Зачем. 30.07 на этом потерян вечер. Игрок раз за разом говорил «перевода нет»,
я искал причину в коде, находил и чинил — а jar в инстансе оставался старым:
запущенная игра держала файл, `copy` проваливался МОЛЧА, и `install.cmd`
при этом печатал «==== DONE ====».

Хуже всего, что каждое звено выглядело исправным: gradle отчитывался
BUILD SUCCESSFUL, мод в игре работал, а СЛОВАРИ в jar были свежие — Loom
кладёт ресурсы заново, тогда как классы взял из кэша. То есть проверка
«словарь на месте» подтверждала ложное.

⚠️ 03.08 СТОРОЖ СОВРАЛ САМ, и дважды в одном ответе:

  * он сравнивал ЧЕТЫРЕ выбранных класса из сорока шести. Правка была
    в `Translator` — его в списке не было, и сторож бодро напечатал
    «правки доехали», когда в инстансах лежал jar двухчасовой давности;
  * он смотрел ОДИН инстанс (26.2), а их четыре — 1.21.11, 26.1.1, 26.1.2
    и 26.2, и в каждом свой jar.

Мораль та же, что записана про привратника миксинов: **сторож отвечает
на СВОЙ вопрос**. «Четыре класса совпали» и «правка доехала» — разные
утверждения, и первое выглядит как второе. Теперь сравниваются ВСЕ классы
мода во ВСЕХ инстансах, где он стоит.

Запуск:  python tools/check_installed.py
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTANCES = Path("C:/MultiMC/instances")
CLASS_PREFIX = "ru/skyblockru/"


def newest_jar(folder: Path) -> Path | None:
    """
    Самый свежий jar мода в папке.

    ⚠️ Версию НЕ зашиваем в имя: после первого же `--bump` сторож отвечал бы
    «нет собранного jar», то есть молча перестал бы стеречь. Уже было.
    """
    if not folder.is_dir():
        return None
    jars = [p for p in folder.glob("skyblockru-*.jar")
            if not p.name.endswith(("-sources.jar", "-dev.jar"))]
    return max(jars, key=lambda p: p.stat().st_mtime) if jars else None


def classes(path: Path) -> dict[str, int]:
    """
    Имя класса -> CRC содержимого.

    ⚠️ Берём ВСЕ классы мода, а не выбранные: правка может лечь в любой,
    и список «наблюдаемых» устаревает молча — ровно на этом сторож и соврал.
    ⚠️ CRC, а не размер: два разных класса одной длины сравнялись бы.
    ⚠️ Классы, а не словари: Loom кладёт ресурсы заново даже тогда, когда
    компиляцию взял из кэша, — на этом обожглись в первый раз.
    """
    out: dict[str, int] = {}
    try:
        with zipfile.ZipFile(path) as jar:
            for info in jar.infolist():
                if info.filename.startswith(CLASS_PREFIX) and info.filename.endswith(".class"):
                    out[info.filename] = info.CRC
    except (OSError, zipfile.BadZipFile) as error:
        print(f"не прочитал {path.name}: {error}")
    return out


def built_jars() -> dict[str, Path]:
    """Собранные jar по ИМЕНИ файла: versions/<версия>/build/libs."""
    found: dict[str, Path] = {}
    versions = ROOT / "versions"
    if not versions.is_dir():
        return found
    for folder in sorted(versions.iterdir()):
        jar = newest_jar(folder / "build" / "libs")
        if jar is not None:
            found[jar.name] = jar
    return found


def game_running() -> bool:
    """Держит ли кто-то jar: запущенная игра — самая частая причина."""
    try:
        done = subprocess.run(["tasklist"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    text = (done.stdout or "").lower()
    return "javaw.exe" in text or "java.exe" in text


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    built = built_jars()
    if not built:
        print("нет собранных jar в versions/*/build/libs")
        print("Сперва: gradlew build")
        return 1

    if not INSTANCES.is_dir():
        print(f"нет папки инстансов {INSTANCES}")
        return 1

    checked, stale_total, missing = 0, 0, []
    print("=== ЧТО СТОИТ У ИГРОКА ===")
    for instance in sorted(INSTANCES.iterdir()):
        mods = instance / ".minecraft" / "mods"
        installed = newest_jar(mods)
        if installed is None:
            continue
        checked += 1
        source = built.get(installed.name)
        if source is None:
            missing.append((instance.name, installed.name))
            print(f"  {instance.name:<10} {installed.name:<30} ?? такой сборки нет")
            continue

        want, have = classes(source), classes(installed)
        if not want:
            print(f"  {instance.name:<10} в собранном jar нет классов — сборка неполная?")
            stale_total += 1
            continue

        stale = [name for name, crc in want.items() if have.get(name) != crc]
        gone = [name for name in want if name not in have]
        if stale:
            stale_total += 1
            print(f"  {instance.name:<10} {installed.name:<30} "
                  f"!! СТАРЫЙ: расходится классов {len(stale)} из {len(want)}"
                  + (f", отсутствует {len(gone)}" if gone else ""))
            for name in stale[:4]:
                print(f"                 {name.split('/')[-1]}")
            if len(stale) > 4:
                print(f"                 ... ещё {len(stale) - 4}")
        else:
            print(f"  {instance.name:<10} {installed.name:<30} "
                  f"ок: все {len(want)} классов совпали")

    print()
    if checked == 0:
        print("мод не стоит ни в одном инстансе")
        return 1
    if missing:
        print("⚠️ jar есть, а сборки под него нет — версия убрана из settings.gradle.kts?")
    if stale_total == 0:
        print(f"СЛОМАНО: 0 — во всех {checked} инстансах лежит собранное")
        return 0

    print(f"=== СЛОМАНО: в {stale_total} инстансах СТАРЫЙ jar ===")
    print("  Правки собраны, но до игры не доехали.")
    if game_running():
        print("  ⚠️ Minecraft ЗАПУЩЕН — он держит файл, и copy проваливается молча.")
        print("     Закрыть игру ПОЛНОСТЬЮ (не выход на сервер), затем: python tools/build_all.py")
    else:
        print("  Игра не запущена — прогнать: python tools/build_all.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
