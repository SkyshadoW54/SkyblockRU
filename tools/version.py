"""
Версия мода: какая у нас, какая собрана, какая стоит у игрока.

⚠️ Зачем. До 02.08 версия была ВСЕГДА `0.1.0` — все сборки за все месяцы
назывались одинаково. Пока мод стоял у одного человека, это было терпимо:
свежесть определяли по времени сборки. С раздачей чужим людям так нельзя —
ни игрок не поймёт, что у него старое, ни мод не сможет сравнить себя
с выложенным и предложить обновиться.

Схема: `МАЖОР.МИНОР.ПАТЧ`, растёт при каждом выпуске.
  ПАТЧ  — пополнение перевода, правки цвета и разметки (самое частое);
  МИНОР — новые возможности мода, поддержка новой версии игры;
  МАЖОР — перелом, после которого старые словари или конфиг несовместимы.

⚠️ Полная версия jar выглядит как `0.2.0+26.2`: слева наша, справа версия
игры. Сравнивать надо ЛЕВУЮ часть — правая у сборок разная по построению.

Запуск:
  python tools/version.py                показать всё
  python tools/version.py --bump patch   поднять патч
  python tools/version.py --bump minor   поднять минор
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROPS = ROOT / "gradle.properties"
SETTINGS = ROOT / "settings.gradle.kts"
INSTANCES = Path("C:/MultiMC/instances")


def current() -> str:
    found = re.search(r"^mod_version=(.+)$", PROPS.read_text(encoding="utf-8"), re.M)
    return found.group(1).strip() if found else "?"


def versions() -> list[str]:
    text = SETTINGS.read_text(encoding="utf-8") if SETTINGS.exists() else ""
    call = re.search(r'mc\(\s*("[^)]*")\s*\)', text)
    return re.findall(r'"([^"]+)"', call.group(1)) if call else []


def bump(kind: str) -> str:
    parts = current().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        print(f"СЛОМАНО: версия «{current()}» не вида МАЖОР.МИНОР.ПАТЧ — не трогаю")
        raise SystemExit(1)
    major, minor, patch = (int(p) for p in parts)
    if kind == "major":
        major, minor, patch = major + 1, 0, 0
    elif kind == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    new = f"{major}.{minor}.{patch}"
    text = PROPS.read_text(encoding="utf-8")
    PROPS.write_text(re.sub(r"^mod_version=.+$", f"mod_version={new}", text, flags=re.M),
                     encoding="utf-8")
    return new


def in_jar(path: Path) -> tuple[str, str]:
    """Версия и время сборки прямо из jar — правда, а не догадка по имени."""
    try:
        with zipfile.ZipFile(path) as z:
            meta = json.loads(z.read("fabric.mod.json"))
        built = (meta.get("custom") or {}).get("skyblockru:built", "?")
        return meta.get("version", "?"), built
    except (zipfile.BadZipFile, OSError, KeyError, json.JSONDecodeError):
        return "?", "?"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--bump", choices=("major", "minor", "patch"),
                        help="поднять версию перед выпуском")
    args = parser.parse_args()

    if args.bump:
        was = current()
        print(f"версия поднята: {was} -> {bump(args.bump)}")
        print("⚠️ пересобери и разложи: python tools/build_all.py")
        return 0

    print(f"=== В ИСХОДНИКАХ: {current()} ===\n")

    print("=== СОБРАНО ===")
    for version in versions():
        jar = ROOT / "versions" / version / "build" / "libs" / f"skyblockru-{current()}+{version}.jar"
        if not jar.exists():
            # версию могли поднять, а собрать ещё нет — ищем что есть
            libs = ROOT / "versions" / version / "build" / "libs"
            found = sorted(libs.glob("skyblockru-*.jar")) if libs.exists() else []
            jar = found[-1] if found else None
        if jar is None:
            print(f"  {version:9} не собрано")
            continue
        mod, built = in_jar(jar)
        stale = "  ⚠️ СТАРЕЕ ИСХОДНИКОВ" if not mod.startswith(current() + "+") else ""
        print(f"  {version:9} {mod:18} собран {built}{stale}")

    print("\n=== СТОИТ У ИГРОКА (инстансы MultiMC) ===")
    if not INSTANCES.exists():
        print("  папки инстансов нет")
        return 0
    for inst in sorted(p for p in INSTANCES.iterdir() if p.is_dir()):
        mods = inst / ".minecraft" / "mods"
        jars = sorted(mods.glob("skyblockru-*.jar")) if mods.exists() else []
        if not jars:
            continue
        if len(jars) > 1:
            print(f"  {inst.name:9} ⚠️ ДВА JAR СРАЗУ: {[j.name for j in jars]}")
        for jar in jars:
            mod, built = in_jar(jar)
            stale = "  ⚠️ СТАРЕЕ ИСХОДНИКОВ" if not mod.startswith(current() + "+") else ""
            print(f"  {inst.name:9} {mod:18} собран {built}{stale}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
