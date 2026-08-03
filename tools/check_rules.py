"""
Проверка правил-регулярок НАСТОЯЩЕЙ Java, до запуска игры.

Зачем отдельный инструмент. Правила пишет Python, а исполняет Java, и в мелочах
движки расходятся. Живой случай: в шаблоне «[\\uE000-\\uF8FF]» оказалось две
обратные косые вместо одной. Python такой шаблон принимает, Java видит букву «u»
после косой — и правило не совпадает НИКОГДА. Ошибки не видно нигде: словарь
грузится, счётчики растут, просто перевода нет. Тут это ловится за три секунды.

Заодно примерка: `--line` прогоняет строку с экрана через все правила и говорит,
какое сработало и из какого словаря. Дополняет tools/find_text.py — тот ищет
готовый текст в словарях, а этот отвечает «что мод сделает вот с этой строкой».

Запуск:
  python tools/check_rules.py                      только компиляция
  python tools/check_rules.py --dump               плюс строки из живого дампа
  python tools/check_rules.py --line "Health: +293 (+40)"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")
CHECKER = Path(__file__).resolve().parent / "RuleCheck.java"

# Иконки в выводе не видны и ломают ширину — показываем меткой
ICON = re.compile("[" + chr(92) + "ue000-" + chr(92) + "uf8ff]")


def find_java() -> str | None:
    """java из PATH, иначе самый свежий JDK из Program Files."""
    found = shutil.which("java")
    if found:
        return found
    roots = [Path(os.environ.get("JAVA_HOME", "")) / "bin" / "java.exe"]
    for base in (Path("C:/Program Files/Java"), Path("C:/Program Files/Eclipse Adoptium")):
        if base.exists():
            roots += sorted(base.glob("jdk*/bin/java.exe"), reverse=True)
    for path in roots:
        if path.exists():
            return str(path)
    return None


def rules() -> list[tuple[str, str, str]]:
    out = []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for rule in pack.get("regex") or []:
            out.append((path.name, rule.get("p", ""), rule.get("r", "")))
    return out


def dump_samples(limit: int) -> list[str]:
    """
    Строки из дампа. Числа в нём уже обобщены до {n}, а правила ждут настоящих —
    поэтому подставляем число обратно, иначе примерка проверяет не то.
    """
    collected = DUMP / "collected.json"
    if not collected.exists():
        return []
    data = json.loads(collected.read_text(encoding="utf-8"))
    lines = []
    for items in (data.get("sources") or {}).values():
        for line in items:
            lines.append(re.sub(r"§.", "", line).replace("{n}", "123"))
    return lines[:limit]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--line", action="append", default=[],
                        help="примерить строку с экрана (можно несколько раз)")
    parser.add_argument("--dump", action="store_true",
                        help="примерить строки из живого дампа")
    parser.add_argument("--limit", type=int, default=400)
    args = parser.parse_args()

    java = find_java()
    if not java:
        print("не нашёл java — а без неё шаблоны проверять нечем")
        return 1

    found = rules()
    if not found:
        print("правил не нашлось — словари на месте?")
        return 1

    samples = list(args.line)
    if args.dump:
        samples += dump_samples(args.limit)

    with tempfile.TemporaryDirectory() as temp:
        table = Path(temp) / "rules.tsv"
        table.write_text("\n".join(f"{p}\t{s}\t{r}" for p, s, r in found), encoding="utf-8")
        # ⚠️ stdout.encoding задаём явно: иначе Java пишет в кодировке консоли
        # (на этой машине cp1251), и русский перевод приезжает сюда крокозябрами.
        result = subprocess.run(
            [java, "-Dstdout.encoding=UTF-8", "-Dfile.encoding=UTF-8",
             str(CHECKER), str(table), *samples],
            capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result.returncode != 0:
        print("java не смогла запустить проверку:")
        print(result.stderr.strip()[:2000])
        return 1

    broken = []
    hits = []
    misses = []
    total = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if parts[0] == "BROKEN":
            broken.append(parts[1:])
        elif parts[0] == "COMPILED":
            total = int(parts[1])
        elif parts[0] == "HIT":
            hits.append(parts[1:])
        elif parts[0] == "MISS":
            misses.append(parts[1])

    print(f"шаблонов: {total + len(broken)}, Java приняла: {total}")
    if broken:
        print(f"\n=== НЕ КОМПИЛИРУЮТСЯ: {len(broken)} ===")
        for pack, pattern, why in broken:
            print(f"  {pack}: {pattern}")
            print(f"    {why}")

    if args.line:
        print("\n=== примерка ===")
        for source, pack, result_text in hits:
            print(f"  + {ICON.sub('[иконка]', source)}")
            print(f"      -> {ICON.sub('[иконка]', result_text)}   ({pack})")
        for source in misses:
            print(f"  - {ICON.sub('[иконка]', source)}   (ни одно правило не подошло)")
    elif args.dump:
        print(f"\nиз дампа: правило нашлось для {len(hits)} строк из {len(hits) + len(misses)}")

    print(f"\nитого замечаний: {len(broken)}")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
