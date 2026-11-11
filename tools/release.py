# -*- coding: utf-8 -*-
"""
Собрать готовые jar всех версий в ОДНУ папку — то, что раздают игрокам.

    python tools/release.py           собрать в release/
    python tools/release.py --build   сперва пересобрать всё

⚠️ Зачем отдельный шаг. Сборки лежат по адресу
`versions/<версия>/build/libs/`, то есть в тринадцати разных папках. Пока
версия была одна, это не мешало; теперь взять «все jar для раздачи» стало
отдельной работой, а работа руками рано или поздно делается неверно —
кто-то заберёт вчерашний файл из папки, которую забыли пересобрать.

⚠️ В раздачу jar идёт БЕЗ режима полного перевода (решение игрока 03.10):
словари режима вырезаются при копировании (`copy_for_players`), а
`check_release` проверяет, что вырезаны и что команды `full` нет у игрока.

⚠️ Проверяем КАЖДЫЙ jar перед копированием: версия внутри должна совпасть
с папкой, а диапазон Minecraft — с версией сборки. Иначе повторится грабля
проекта: «версия в имени файла» уже однажды разошлась с содержимым,
и `build_all` разложил по инстансам старые сборки, отчитавшись «ок».
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "release"
MC_LIST = re.compile(r'mc\(\s*("[^)]*)\)')


def versions() -> list[str]:
    """Список версий — из settings.gradle.kts, копии не держим."""
    settings = ROOT / "settings.gradle.kts"
    found = MC_LIST.search(settings.read_text(encoding="utf-8"))
    return re.findall(r'"([^"]+)"', found.group(1)) if found else []


def newest_jar(version: str) -> Path | None:
    libs = ROOT / "versions" / version / "build" / "libs"
    if not libs.exists():
        return None
    jars = [p for p in libs.glob("skyblockru-*.jar")
            if not p.name.endswith(("-sources.jar", "-dev.jar"))]
    return max(jars, key=lambda p: p.stat().st_mtime) if jars else None


def copy_for_players(src: Path, dst: Path) -> list[str]:
    """Копия jar для раздачи БЕЗ словарей режима полного перевода.

    ⚠️ Решение игрока 03.10: режим full тестируется ТОЛЬКО на машине
    разработки. С 0.2.30 его словари ехали в jar раздачи вместе с командой,
    и любой скачавший включал сырой режим. Вырезаем ЗДЕСЬ, а не в сборке:
    jar в `versions/` и в инстансах остаётся полным — на нём режим и тестируют.

    ⚠️ Признак — `check_release.is_mode_pack` (тот же у `publish.py`).
    Из `index.json` вырезанные словари тоже убираем: объявленный, но
    отсутствующий файл — это жалоба загрузчика на пустом месте.
    ⚠️ Время файла копируем с исходного jar: `check_release` сверяет его
    с исходниками, и свежая по времени копия проходила бы проверку всегда.
    Возвращает имена вырезанных словарей.
    """
    import check_release  # ленивый импорт, как ниже в main

    index_name = check_release.PACKS_IN_JAR + "index.json"
    with zipfile.ZipFile(src) as zin:
        mode: set[str] = set()
        for name in zin.namelist():
            if (name.startswith(check_release.PACKS_IN_JAR) and name.endswith(".json")
                    and name != index_name):
                try:
                    meta = json.loads(zin.read(name))
                except ValueError:
                    continue
                if check_release.is_mode_pack(meta):
                    mode.add(name)
        short = {name.rsplit("/", 1)[-1] for name in mode}
        index = json.loads(zin.read(index_name))
        index["common"] = [x for x in index.get("common") or [] if x not in short]
        for lang, items in (index.get("languages") or {}).items():
            index["languages"][lang] = [x for x in items if x not in short]
        with zipfile.ZipFile(dst, "w") as zout:
            for info in zin.infolist():
                if info.filename in mode:
                    continue
                data = zin.read(info.filename)
                if info.filename == index_name:
                    data = json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8")
                zout.writestr(info, data)  # ZipInfo хранит сжатие и время записи
    shutil.copystat(src, dst)
    return sorted(short)


def describe(jar: Path) -> tuple[str, str]:
    """(версия мода, требуемая версия игры) из fabric.mod.json внутри jar."""
    with zipfile.ZipFile(jar) as z:
        meta = json.loads(z.read("fabric.mod.json"))
    return meta.get("version", "?"), (meta.get("depends") or {}).get("minecraft", "?")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Собрать jar всех версий в release/")
    parser.add_argument("--build", action="store_true", help="сперва пересобрать всё")
    args = parser.parse_args()

    if args.build:
        print("собираю все версии — это несколько минут...")
        done = subprocess.run([str(ROOT / "gradlew.bat"), "build", "--console=plain"],
                              cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if done.returncode != 0:
            print("СЛОМАНО: сборка не прошла — release не трогаю")
            for line in (done.stdout or "").splitlines():
                if "error:" in line or "FAILED" in line:
                    print("   ", line.strip()[:140])
            return 1
        print("собрано\n")

    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.jar"):
        old.unlink()

    rows, missing = [], []
    for version in versions():
        jar = newest_jar(version)
        if jar is None:
            missing.append(version)
            continue
        mod_version, needs = describe(jar)
        # ⚠️ Сверяем СОДЕРЖИМОЕ, а не имя файла: имя может совпасть с версией
        # папки при устаревшем jar внутри.
        if not mod_version.endswith("+" + version):
            print(f"   ⚠️ {version}: внутри jar версия {mod_version} — пропускаю")
            missing.append(version)
            continue
        cut = copy_for_players(jar, OUT / jar.name)
        rows.append((version, jar.name, needs, (OUT / jar.name).stat().st_size))
        if cut:
            print(f"   {version}: режим full вырезан из раздачи — {len(cut)} словарей "
                  f"(локальный jar в versions/ и инстансах остался полным)")

    print(f"=== release/  ({len(rows)} файлов) ===")
    print("%-9s %-30s %-16s %s" % ("версия", "файл", "требует игру", "размер"))
    for version, name, needs, size in rows:
        print("%-9s %-30s %-16s %.0f КБ" % (version, name, needs, size / 1024))
    if missing:
        print("\nНЕ СОБРАНЫ:", ", ".join(missing))
        print("   собрать: python tools/release.py --build")
    print(f"\nпапка: {OUT}")

    # ⚠️ Проверяем ТО, ЧТО УЕДЕТ ЛЮДЯМ, и делаем это ЗДЕСЬ, а не «потом».
    #
    # 04.08 в релиз v0.2.0 уехали чужие ники и тестовый словарь — не потому,
    # что их не вычистили, а потому что сборка была на три часа старше чистки.
    # Никакой сторож этого не спрашивал: check_nicknames смотрит исходники,
    # pack.verify — структуру архива. Раздача — последний момент, когда беду
    # ещё можно остановить, дальше файл уже у людей.
    import check_release  # ленивый импорт: тянет словари проекта
    print()
    if check_release.main_for(OUT) != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
