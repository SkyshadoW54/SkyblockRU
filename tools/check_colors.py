"""
Проверка правила «склеивать ли абзац» — по РЕАЛЬНЫМ раскладкам из игры, без игры.

Зачем. Решение принимается по цветам строк, а дамп §-коды снимает — то есть
проверить правило до сборки было нечем. Я менял его четыре раза за день и дважды
сломал экран: сперва весь профиль стал фиолетовым, потом перестали переводиться
подсказки с заголовком. Оба раза узнавал об этом по скриншоту от игрока.

Теперь мод пишет каждую встреченную раскладку в dump/color-cases.json вместе
со своим решением, а этот скрипт прогоняет по ним ТУ ЖЕ логику (ColorLayout,
скомпилированный настоящей Java) и показывает расхождения.

То есть: поправил правило -> запустил -> увидел, какие подсказки поменяют
поведение, ДО того как это увидит игрок.

Запуск:
  python tools/check_colors.py            сверить с тем, что решал мод
  python tools/check_colors.py --all      показать все случаи, а не только разошедшиеся
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "ColorLayout.java"
CASES = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/color-cases.json")

# Эталон: раскладки с реальных скриншотов, где правило когда-то ошибалось.
# Проверяются ВСЕГДА, даже если игра ещё ничего не записала: каждая строка тут
# появилась после поломки на экране, и молча менять эти ответы нельзя.
KNOWN = ROOT / "data" / "work" / "color-cases-known.json"

RUNNER = '''
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import ru.skyblockru.core.ColorLayout;

public class ColorRun {
	public static void main(String[] args) throws Exception {
		for (String line : Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8)) {
			if (line.isBlank()) continue;
			String[] parts = line.split("\\t", -1);
			List<String> colors = Arrays.asList(parts[0].split(",", -1));
			List<String> markers = parts[1].isEmpty()
					? List.of() : Arrays.asList(parts[1].split(",", -1));
			boolean allowHeader = Boolean.parseBoolean(parts[2]);
			ColorLayout.Verdict v = ColorLayout.decide(colors, markers, allowHeader);
			System.out.println(v.merge() + "\\t" + v.reason());
		}
	}
}
'''


def find_java(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for base in (Path("C:/Program Files/Java"), Path("C:/Program Files/Eclipse Adoptium")):
        if base.exists():
            for path in sorted(base.glob(f"jdk*/bin/{name}.exe"), reverse=True):
                return str(path)
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="показать все случаи")
    args = parser.parse_args()

    sources = []
    if KNOWN.exists():
        sources.append(("эталон", json.loads(KNOWN.read_text(encoding="utf-8"))["cases"]))
    if CASES.exists():
        sources.append(("из игры", json.loads(CASES.read_text(encoding="utf-8"))["cases"]))
    else:
        print(f"! файла из игры пока нет: {CASES.name}")
        print("  Поиграй на свежей сборке — мод запишет его сам.")
        print()
    if not sources:
        return 1
    javac, java = find_java("javac"), find_java("java")
    if not javac or not java:
        print("не нашёл JDK — без него проверять нечем")
        return 1

    cases = [dict(c, _from=tag) for tag, group in sources for c in group]
    if not cases:
        print("раскладок пока не записано")
        return 1

    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        (out / "ColorRun.java").write_text(RUNNER, encoding="utf-8")
        build = subprocess.run(
            [javac, "-d", str(out), str(SRC), str(out / "ColorRun.java")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            print("ColorLayout не компилируется:")
            print(build.stderr.strip()[:1500])
            return 1

        table = out / "cases.tsv"
        rows = [c["colors"] + chr(9) + c.get("markers", "") + chr(9) + "true"
                for c in cases]
        table.write_text(chr(10).join(rows), encoding="utf-8")
        run = subprocess.run(
            [java, "-Dstdout.encoding=UTF-8", "-cp", str(out), "ColorRun", str(table)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode != 0:
            print("не запустилось:", run.stderr.strip()[:800])
            return 1

    now = [row.split("\t") for row in run.stdout.splitlines() if row.strip()]
    if len(now) != len(cases):
        print(f"! ответов {len(now)}, а случаев {len(cases)} — разбор сломан")
        return 1

    changed, merge_now, merge_was = [], 0, 0
    for case, (merged, reason) in zip(cases, now):
        new = merged == "true"
        old = bool(case.get("merged"))
        merge_now += new
        merge_was += old
        if new != old or args.all:
            changed.append((case, old, new, reason))

    print(f"раскладок из игры: {len(cases)}")
    print(f"  склеивал мод:  {merge_was}")
    print(f"  склеит сейчас: {merge_now}")
    print()
    if not changed:
        print("расхождений нет — правило ведёт себя точно так же, как в игре")
        return 0

    print(f"=== ИЗМЕНИЛОСЬ: {sum(1 for c in changed if c[1] != c[2])} ===")
    for case, old, new, reason in changed:
        if old == new and not args.all:
            continue
        mark = "+ теперь СКЛЕИТ" if new else "- теперь НЕ склеит"
        print(f"\n  {mark}   цвета: {case['colors']}")
        print(f"     было: {case.get('reason', '')}")
        print(f"     стало: {reason}")
        if case.get("sample"):
            print(f"     {case['sample'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
