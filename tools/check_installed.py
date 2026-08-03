"""
Доехала ли правка до игры: jar в инстансе против собранного.

Зачем. 30.07 на этом потерян вечер. Игрок раз за разом говорил «перевода нет»,
я искал причину в коде, находил и чинил — а jar в инстансе оставался старым:
запущенная игра держала файл, `copy` проваливался МОЛЧА, и `install.cmd`
при этом печатал «==== DONE ====».

Хуже всего, что каждое звено выглядело исправным: gradle отчитывался
BUILD SUCCESSFUL, мод в игре работал, а СЛОВАРИ в jar были свежие — Loom
кладёт ресурсы заново, тогда как классы взял из кэша. То есть проверка
«словарь на месте» подтверждала ложное.

Сошлось только на сравнении БАЙТОВ скомпилированного класса в двух местах.
Этот инструмент делает ровно это, чтобы вопрос «а правка вообще в игре?»
закрывался одной командой, а не вечером поисков.

Запуск:  python tools/check_installed.py
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# ⚠️ Со Stonecutter сборок несколько — по одной на версию игры, каждая в своей
# папке versions/<версия>/build/libs. Старый путь build/libs остаётся от
# прежних сборок и молча показывал бы вчерашний jar как «собранный».
TARGET = "26.2"


def newest_jar(folder: Path) -> Path | None:
    """
    Самый свежий jar мода в папке.

    ⚠️ ВЕРСИЮ В ИМЯ ФАЙЛА НЕ ЗАШИВАТЬ — этот сторож на том и умер молча.
    Пути были прописаны как `skyblockru-0.1.0+26.2.jar`, и первый же
    `version.py --bump` сделал 0.2.0: сторож перестал находить оба jar
    и на каждый запуск отвечал «нет собранного jar, сперва install.cmd».
    В круге сборки это значит, что САМАЯ ДОРОГАЯ беда проекта (запущенная
    игра держит файл, copy проваливается молча) больше не проверялась вовсе.

    ⚠️ Ровно эта грабля уже записана про `build_all.py` — и повторилась,
    потому что чинили ТО МЕСТО, а не признак. Версию спрашиваем у файловой
    системы, как это делает `version.py`.
    """
    if not folder.exists():
        return None
    jars = sorted(folder.glob("skyblockru-*.jar"), key=lambda p: p.stat().st_mtime)
    return jars[-1] if jars else None


BUILT = newest_jar(ROOT / "versions" / TARGET / "build" / "libs")
INSTALLED = newest_jar(Path(f"C:/MultiMC/instances/{TARGET}/.minecraft/mods"))

# Классы, по которым судим: если они совпали, совпало и остальное.
# Берём именно КЛАССЫ, а не словари: ресурсы Loom обновляет и тогда, когда
# компиляцию взял из кэша, — на этом и обожглись.
WATCH = [
    "ru/skyblockru/core/ColorLayout.class",
    "ru/skyblockru/core/Paragraphs.class",
    "ru/skyblockru/core/Wiki.class",
    "ru/skyblockru/core/UnknownStrings.class",
]


def entries(path: Path) -> dict[str, int]:
    """Имя -> размер для наблюдаемых классов."""
    out: dict[str, int] = {}
    try:
        with zipfile.ZipFile(path) as jar:
            names = set(jar.namelist())
            for name in WATCH:
                if name in names:
                    out[name] = jar.getinfo(name).file_size
    except (OSError, zipfile.BadZipFile) as error:
        print(f"не прочитал {path.name}: {error}")
    return out


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
    if BUILT is None:
        print(f"нет собранного jar в versions/{TARGET}/build/libs")
        print("Сперва: install.cmd")
        return 1
    if INSTALLED is None:
        print(f"в инстансе {TARGET} jar мода нет")
        return 1

    built, installed = entries(BUILT), entries(INSTALLED)
    if not built:
        print("в собранном jar нет наблюдаемых классов — сборка неполная?")
        return 1

    stale = [name for name, size in built.items() if installed.get(name) != size]
    print(f"собран:    {BUILT.stat().st_size} б, {BUILT.stat().st_mtime_ns // 10**9}")
    print(f"в инстансе:{INSTALLED.stat().st_size} б")
    print()
    for name in WATCH:
        mark = "!!" if name in stale else "ok"
        print(f"  [{mark}] {name.split('/')[-1]:24} "
              f"собран {built.get(name, '-')}, в игре {installed.get(name, '-')}")

    if not stale:
        print("\njar в инстансе совпадает с собранным — правки доехали")
        return 0

    print(f"\n=== СЛОМАНО: в игре СТАРЫЙ jar ({len(stale)} классов расходятся) ===")
    print("  Правки собраны, но до инстанса не доехали.")
    if game_running():
        print("  ⚠️ Minecraft ЗАПУЩЕН — он держит файл, и copy проваливается молча.")
        print("     Закрыть игру ПОЛНОСТЬЮ (не выход на сервер), затем install.cmd")
    else:
        print("  Игра не запущена — просто прогнать install.cmd заново.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
