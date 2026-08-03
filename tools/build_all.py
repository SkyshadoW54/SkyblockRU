"""
Собрать ВСЕ версии мода и разложить по инстансам — одной командой.

⚠️ Зачем. Со Stonecutter сборок несколько, и «поправил, собрал, поставил»
перестало быть одним действием. Стоит забыть одну версию — и у части игроков
останется старый перевод, причём МОЛЧА: jar на месте, мод грузится, просто
半 правок в нём нет. Это ровно та беда, что уже стоила проекту вечера
(«запущенная игра держит jar, copy проваливается молча»), только теперь
она умножается на число версий.

Что делает:
  1. читает список версий из settings.gradle.kts — не держит копию;
  2. собирает каждую;
  3. СВЕРЯЕТ РЕСУРСЫ всех сборок между собой: словари, справка и локализация
     обязаны совпадать побайтово. Разошлись — значит какая-то версия собрана
     из старого исходника, и это надо увидеть СЕЙЧАС, а не от игрока;
  4. раскладывает jar по инстансам MultiMC и сверяет размер.

Запуск:
  python tools/build_all.py            собрать, сверить, разложить
  python tools/build_all.py --dry      только собрать и сверить
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "settings.gradle.kts"
INSTANCES = Path("C:/MultiMC/instances")

# ⚠️ Куда какую версию ставить. Инстанс может называться иначе, чем версия
# (26.1.2 играет на сборке 26.2 — они совместимы), поэтому карта явная.
TARGETS = {
    "26.2": ["26.2", "26.1.2", "26.1.1"],
    "1.21.11": ["1.21.11"],
}


def versions() -> list[str]:
    """Версии из settings.gradle.kts — источник правды один."""
    if not SETTINGS.exists():
        return []
    text = SETTINGS.read_text(encoding="utf-8")
    # ⚠️ Берём ВЫЗОВ, а не объявление: `fun mc(vararg versions: String)`
    # подходит под наивный шаблон и даёт пустой список — то есть сборку
    # «ни одной версии», и это выглядело бы как поломка настроек.
    call = re.search(r'mc\(\s*("[^)]*")\s*\)', text)
    if not call:
        return []
    return re.findall(r'"([^"]+)"', call.group(1))


def mod_version() -> str:
    """Наша версия — из gradle.properties, единственного места, где она живёт."""
    found = re.search(r"^mod_version=(.+)$",
                      (ROOT / "gradle.properties").read_text(encoding="utf-8"), re.M)
    return found.group(1).strip() if found else ""


def jar_of(version: str) -> Path:
    """
    Собранный jar нужной версии игры.

    ⚠️ Версию мода НЕ ЗАШИВАТЬ в имя. Первый заход держал здесь «0.1.0», и при
    первом же поднятии версии инструмент собрал 0.2.0, а разложил по инстансам
    старый 0.1.0 — молча, отчитавшись «ок». Ровно та беда, от которой уже
    предостерегает комментарий в install.cmd: «жёстко зашитая версия молча
    перестаёт работать, как только версия меняется». Поймал `version.py`,
    который сравнивает установленное с исходниками.
    """
    libs = ROOT / "versions" / version / "build" / "libs"
    exact = libs / f"skyblockru-{mod_version()}+{version}.jar"
    if exact.exists():
        return exact
    # версия поднята, но сборки ещё нет — пусть вызывающий увидит отсутствие
    return exact


def resources(jar: Path) -> dict[str, str]:
    """Ресурсы сборки: словари, справка, локализация — то, что общее для всех."""
    with zipfile.ZipFile(jar) as z:
        return {n: hashlib.sha256(z.read(n)).hexdigest()[:16]
                for n in z.namelist() if n.startswith("assets/")}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="не раскладывать по инстансам")
    args = parser.parse_args()

    targets = versions()
    if not targets:
        print("СЛОМАНО: не разобрал список версий из settings.gradle.kts")
        return 1
    print(f"версий в сборке: {len(targets)} — {', '.join(targets)}\n")

    gradle = ROOT / "gradlew.bat"
    tasks = [f":{v}:build" for v in targets]
    done = subprocess.run([str(gradle), *tasks, "--console=plain"],
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.returncode != 0:
        print("СЛОМАНО: сборка не прошла")
        for line in done.stdout.splitlines():
            if ": error:" in line or "What went wrong" in line:
                print("   " + line.strip()[:140])
        return 1
    print("собрано: все версии\n")

    # --- сверка ресурсов ---
    print("=== СВЕРКА РЕСУРСОВ (словари, справка, локализация) ===")
    base_version = targets[0]
    base = resources(jar_of(base_version))
    bad = 0
    for version in targets[1:]:
        other = resources(jar_of(version))
        only_a = sorted(set(base) - set(other))
        only_b = sorted(set(other) - set(base))
        diff = sorted(k for k in set(base) & set(other) if base[k] != other[k])
        if only_a or only_b or diff:
            bad += 1
            print(f"  СЛОМАНО {base_version} vs {version}:"
                  f" только в первой {len(only_a)}, только во второй {len(only_b)},"
                  f" различаются {len(diff)}")
            for name in (only_a + only_b + diff)[:6]:
                print(f"      {name}")
        else:
            print(f"  ок  {base_version} vs {version}: {len(base)} файлов совпадают")
    if bad:
        print("\nСЛОМАНО: сборки разошлись по ресурсам —"
              " какая-то версия собрана из старого исходника")
        return 1

    if args.dry:
        print("\nсухой прогон: по инстансам не раскладываю")
        return 0

    # --- раскладка ---
    print("\n=== УСТАНОВКА ===")
    for version, instances in TARGETS.items():
        if version not in targets:
            continue
        src = jar_of(version)
        for name in instances:
            mods = INSTANCES / name / ".minecraft" / "mods"
            if not mods.exists():
                print(f"  {name:9} нет такого инстанса — пропускаю")
                continue
            dst = mods / src.name
            try:
                # ⚠️ Спрашиваем ФАЙЛ, а не список процессов: занятый jar
                # copy перезапишет молча и оставит старый (см. install.cmd).
                if dst.exists():
                    with open(dst, "r+b"):
                        pass
                for old in mods.glob("skyblockru-*.jar"):
                    old.unlink()
                dst.write_bytes(src.read_bytes())
            except OSError as error:
                print(f"  {name:9} ЗАНЯТ — игра запущена? ({error.strerror})")
                bad += 1
                continue
            ok = dst.stat().st_size == src.stat().st_size
            print(f"  {name:9} {src.name}  {'ок' if ok else 'РАЗМЕР НЕ СОШЁЛСЯ'}")
            bad += not ok

    print()
    if bad:
        print(f"СЛОМАНО: {bad}")
        return 1
    print("СЛОМАНО: 0 — все версии собраны, сверены и разложены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
