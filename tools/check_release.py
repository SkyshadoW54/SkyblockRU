"""
Что уезжает ЛЮДЯМ: проверка собранных файлов перед раздачей.

Заведено 04.08 по факту: в релиз v0.2.0 уехали ЧУЖИЕ НИКИ и тестовый словарь.
Не потому, что их забыли вычистить — вычистили, — а потому что релиз собрали
в 14:12, а чистка была в 16:12 и 17:29. `release.py` и `pack.py` берут то,
что лежит в сборке НА МОМЕНТ ЗАПУСКА, и трёхчасовой разрыв никто не заметил.

⚠️ Сторожа на это не было ни одного, хотя по отдельности всё проверялось:
`check_nicknames` смотрит ИСХОДНИКИ, `pack.verify` — структуру архива,
`check_installed` — классы в инстансах. Никто не спрашивал про то, что реально
лежит в раздаваемом файле. Это записанная мораль проекта: сторож отвечает
на СВОЙ вопрос, и «исходники чистые» ≠ «чистое уедет людям».

Проверяем пять вещей, и каждая ловит свою беду:

  1. СВЕЖЕСТЬ   нет ли в src/ файлов новее сборки. Корень беды: правка есть,
                а в jar её нет.
  2. НИКИ       ищем прямо в словарях СОБРАННОГО jar, признак берём
                у check_nicknames (своя копия разошлась бы).
  3. ЛИШНЕЕ     словари, объявленные в jar, но отсутствующие в исходниках —
                так ловится тестовый словарь, удалённый уже после сборки.
  4. БИБЛИОТЕКА чужой jar, вложенный в наш (08.08 ронял чужую сборку).
  5. РЕЖИМ FULL словари режима полного перевода и команда `full` в ветке
                игрока (решение 03.10: режим тестируется только локально,
                а с 0.2.30 и то и другое уезжало в раздачу незамеченным).

Запуск:
  python tools/check_release.py                проверить всё в release/
  python tools/check_release.py --jar FILE     проверить один файл
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
SRC = ROOT / "src"
PACKS_IN_JAR = "assets/skyblockru/packs/"

sys.path.insert(0, str(Path(__file__).resolve().parent))


def newest_source() -> tuple[float, Path | None]:
    """Самый свежий файл исходников: время и путь."""
    best, where = 0.0, None
    for path in SRC.rglob("*"):
        if not path.is_file():
            continue
        stamp = path.stat().st_mtime
        if stamp > best:
            best, where = stamp, path
    return best, where


def declared_in_jar(zf: zipfile.ZipFile) -> set[str]:
    """Словари, объявленные в index.json внутри jar — их мод и грузит."""
    try:
        index = json.loads(zf.read(PACKS_IN_JAR + "index.json"))
    except (KeyError, json.JSONDecodeError):
        return set()
    names = set(index.get("common") or [])
    for _lang, items in (index.get("languages") or {}).items():
        names.update(items)
    return names


def is_mode_pack(meta: dict) -> bool:
    """Словарь режима полного перевода — в раздачу НЕ идёт.

    ⚠️ Признак — поля самого словаря, а не список имён: поля ставит
    генератор, за ними следит `check_full_mode` (`"group": "full"`,
    `"default": false`). Список пополняли бы руками и однажды забыли.
    Тот же признак держит `publish.py` для облака — он зовёт эту функцию,
    чтобы облако и jar раздачи не разошлись в том, что считать режимом.
    """
    return bool(meta.get("group")) or meta.get("default") is False


PLAYER_BRANCH = "addPlayerCommands"
COMMAND_CLASS = "ru/skyblockru/command/RuCommand.class"


def player_branch_strings(zf: zipfile.ZipFile) -> set[str] | None:
    """Строковые константы в ветке команд ИГРОКА — по байткоду собранного jar.

    ⚠️ Спрашиваем jar, а не исходник: проверять надо то, что уедет людям.
    `literal("full")` компилируется в `ldc "full"` прямо в теле
    `addPlayerCommands`, лямбды `.executes(...)` живут отдельно и сюда не
    попадают. None — проверить нечем (нет javap или класса).
    """
    import subprocess
    import tempfile
    from check_mixin_gate import find_java  # одна копия поиска JDK, не своя

    javap = find_java("javap")
    if javap is None or COMMAND_CLASS not in zf.namelist():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "RuCommand.class"
        target.write_bytes(zf.read(COMMAND_CLASS))
        done = subprocess.run([javap, "-c", "-p", str(target)], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        return None
    found: set[str] = set()
    inside = False
    for line in done.stdout.splitlines():
        if line.startswith("  ") and not line.startswith("   ") and line.strip():
            # заголовок члена класса: ровно два пробела отступа (метод, поле,
            # `static {}`) — любой из них закрывает предыдущий метод
            inside = f" {PLAYER_BRANCH}(" in line
            continue
        if inside and "// String " in line:
            found.add(line.split("// String ", 1)[1].strip())
    return found


def source_pack_names() -> set[str]:
    """Словари, которые есть в исходниках прямо сейчас."""
    base = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
    return {p.name for p in base.rglob("*.json")}


def check_jar(jar: Path, source_names: set[str], newest: float,
              newest_path: Path | None) -> list[str]:
    import check_nicknames  # ленивый импорт: тянет словари проекта

    problems: list[str] = []
    known = check_nicknames.known_names()

    # 1. Свежесть: сборка не должна быть старше исходников.
    built = jar.stat().st_mtime
    if newest > built:
        gap = int((newest - built) / 60)
        problems.append(
            f"СБОРКА СТАРШЕ ИСХОДНИКОВ на {gap} мин — правка есть, а в файле её нет"
            + (f" (свежее всех: {newest_path.relative_to(ROOT)})" if newest_path else ""))

    with zipfile.ZipFile(jar) as zf:
        declared = declared_in_jar(zf)
        names = [n for n in zf.namelist()
                 if n.startswith(PACKS_IN_JAR) and n.endswith(".json")]

        # 2. Ники — в том, что реально уедет людям.
        for name in names:
            short = name.rsplit("/", 1)[-1]
            if short not in check_nicknames.FROM_GAME:
                continue  # в прочих словарях латиница — это текст Hypixel
            try:
                pack = json.loads(zf.read(name))
            except json.JSONDecodeError:
                continue
            found: set[str] = set()
            for section in ("exact", "paragraphs", "glossary"):
                for key, value in (pack.get(section) or {}).items():
                    if isinstance(value, str):
                        found |= check_nicknames.nicks_in(key + " " + value, known)
            if found:
                shown = ", ".join(sorted(found)[:6])
                problems.append(f"НИКИ ИГРОКОВ в {short}: {len(found)} — {shown}")

        # 3. Лишнее: объявлено в jar, но в исходниках такого файла уже нет.
        for short in sorted(declared):
            if short not in source_names:
                problems.append(
                    f"ПОСТОРОННИЙ СЛОВАРЬ {short}: объявлен в index.json, "
                    f"но в исходниках его нет — похоже, тестовый")

        # 4. ⚠️ ЧУЖАЯ БИБЛИОТЕКА ВНУТРИ НАШЕГО JAR — самая дорогая беда,
        # какая тут бывает: она роняет НЕ наш перевод, а ВСЮ ИГРУ, ещё на
        # загрузке, и виноватым выглядит наш мод (он и виноват).
        #
        # Так и случилось 08.08: мы вкладывали `mod-api-1.0.2.jar`, Fabric
        # считал нашу версию лучшей и подсовывал её всем — а мод-обёртка
        # `hypixel-mod-api 1.0.1` из сборки игрока собрана под 1.0.1 и звала
        # `setPacketSender(Predicate)`, которого в 1.0.2 больше нет.
        # NoSuchMethodError на старте, игра не запускается вовсе.
        #
        # Правило простое: чужую библиотеку раздаёт её собственный мод,
        # а не мы. Вкладывать можно только своё.
        nested = [n for n in zf.namelist()
                  if n.endswith(".jar") and not n.startswith("assets/")]
        for name in nested:
            problems.append(
                f"ЧУЖАЯ БИБЛИОТЕКА В JAR: {name} — Fabric раздаст нашу версию "
                f"всем модам, и собранный под другую версию сосед упадёт "
                f"с NoSuchMethodError, уронив игру на старте")

        # 5. ⚠️ РЕЖИМ ПОЛНОГО ПЕРЕВОДА В РАЗДАЧЕ (решение игрока 03.10).
        #
        # Режим тестируется ТОЛЬКО на машине разработки. А с 0.2.30 его
        # словари ехали в jar раздачи, и команда `/skyblockru full` стояла
        # в ветке игрока: любой скачавший видел её в подсказке команд и
        # включал сырой режим. Облако всё это время придерживало словари
        # правильно — утечка шла через jar, и его про режим никто не спрашивал.
        # Вырезает словари `release.py`; здесь — проверка, что вырезал.
        for name in names:
            short = name.rsplit("/", 1)[-1]
            if short == "index.json":
                continue
            try:
                meta = json.loads(zf.read(name))
            except json.JSONDecodeError:
                continue
            if is_mode_pack(meta):
                problems.append(
                    f"РЕЖИМ FULL В РАЗДАЧЕ: словарь {short} — режим тестируется "
                    f"только локально; jar для раздачи собирает release.py")
        strings = player_branch_strings(zf)
        if strings is None:
            problems.append(
                "КОМАНДЫ НЕ ПРОВЕРЕНЫ: нет javap или класса команд — "
                "не знаю, видна ли игроку команда full")
        elif "full" in strings:
            problems.append(
                "РЕЖИМ FULL В РАЗДАЧЕ: команда /skyblockru full стоит в ветке "
                "игрока — её место за devCommands")
    return problems


def jars_to_check(explicit: str | None) -> list[Path]:
    if explicit:
        return [Path(explicit)]
    found = sorted(RELEASE.glob("skyblockru-*.jar"))
    return found


def main_for(folder: Path) -> int:
    """Проверить всё, что лежит в папке раздачи. Зовётся из release.py."""
    return run(sorted(folder.glob("skyblockru-*.jar")))


def run(jars: list[Path]) -> int:
    if not jars:
        print("в release/ нет собранных jar — сперва: python tools/release.py")
        return 1
    source_names = source_pack_names()
    newest, newest_path = newest_source()

    total = 0
    for jar in jars:
        problems = check_jar(jar, source_names, newest, newest_path)
        mark = "ок " if not problems else "!! "
        print(f"{mark}{jar.name}")
        for problem in problems:
            print(f"     {problem}")
        total += len(problems)

    print()
    if total:
        print(f"=== РАЗДАВАТЬ НЕЛЬЗЯ: {total} ===")
        print("    Пересобрать: python tools/build_all.py && python tools/release.py")
        return 1
    print("СЛОМАНО: 0 — в файлах нет ни ников, ни посторонних словарей,")
    print("          ни режима полного перевода, и собраны они не раньше")
    print("          последней правки исходников")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", help="проверить один файл, а не всю папку release/")
    args = parser.parse_args()
    return run(jars_to_check(args.jar))


if __name__ == "__main__":
    raise SystemExit(main())
