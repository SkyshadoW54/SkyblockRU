# -*- coding: utf-8 -*-
r"""
ПРАВИЛО С ДЫРКОЙ В ШАБЛОНЕ — сработает ли оно у игрока.

Беда, ради которой написано. Движок гоняет правила по СЫРОЙ строке
(`Translator.lookup` -> `matcher(source)`, где `source` — это текст со снятыми
§-кодами, но с ЖИВЫМИ числами). А шаблон вида `^Maximum Charge Capacity
(\{n\})$` совпадает только с обобщённой строкой, которой на экране не бывает.

⚠️ ПОЙМАТЬ ЭТО ПРЕЖНИМИ СРЕДСТВАМИ БЫЛО НЕЛЬЗЯ, и это главное:
  * `check_rules` спрашивает «компилируется ли шаблон» — а он безупречен;
  * `try_rule` примеряет к ОЧЕРЕДИ, где строки уже обобщены, — и показывает
    бодрые совпадения;
  * дамп тоже хранит строки обобщёнными, поэтому и он молчит.
То есть все три инструмента отвечали на свой вопрос, а не на нужный.

Что делает проверка: берёт каждое правило с дыркой, строит из его шаблона
ЖИВУЮ строку (подставляет число вместо `\{n\}`, ник вместо `\{s\}`)
и спрашивает НАСТОЯЩИЙ движок, переводится ли она.

⚠️ Ответ «не переводится» — ещё не приговор: строку может закрывать точная
запись или другое правило. Поэтому спрашиваем движок ЦЕЛИКОМ, а не одно
правило, и красным считаем только то, где перевода нет вовсе.

Запуск:
    python tools/check_hole_rules.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
OUT = ROOT / "build" / "holerun"

import check_click_events as base  # обвязка classpath уже написана и выверена

JAVA = r"""
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.Translator;
import java.nio.file.*;
import java.util.*;

public class HoleRun {
    public static void main(String[] args) throws Exception {
        RuConfig.get().dumpUntranslated = false;
        RuConfig.get().language = "ru_ru";
        RuConfig.get().onlyOnHypixel = false;
        RuConfig.get().onlySkyBlock = false;
        Translator.reload(Path.of(args[0]));
        for (String line : Files.readAllLines(Path.of(args[1]))) {
            if (line.isEmpty()) continue;
            int tab = line.indexOf('\t');
            if (tab < 0) continue;
            String origin = line.substring(0, tab);
            String text = line.substring(tab + 1);
            Translator.Match m = Translator.lookup(text, origin, null);
            System.out.println(text + "\t" + (m == null ? "" : m.text()));
        }
    }
}
"""

# Из шаблона надо получить строку, которую пришлёт сервер. Разбор нарочно
# трусливый: встретили конструкцию, которую не умеем разворачивать, —
# правило пропускаем. Ложная тревога тут дороже пропуска.
UNSAFE = re.compile(r"[\[\]|+*?]|\(\?")


def sample(pattern: str) -> str | None:
    """Живая строка по шаблону: дырки становятся числом, экранирование снимается."""
    body = pattern
    if not body.startswith("^") or not body.endswith("$"):
        return None
    body = body[1:-1]
    # необязательные группы вида (?:...)? просто выбрасываем — берём короткий вид
    body = re.sub(r"\(\?:[^()]*\)\?", "", body)
    # захват дырки: (\{n\}) -> 1,234
    body = re.sub(r"\(\\{n\\}\)", "1,234", body)
    body = re.sub(r"\(\\{s\\}\)", "Player", body)
    body = body.replace(r"\{n\}", "1,234").replace(r"\{s\}", "Player")
    # оставшиеся захваты слов заменяем правдоподобным словом
    body = re.sub(r"\(\.\+\)", "Sample Thing", body)
    body = re.sub(r"\(\.\+\?\)", "Sample Thing", body)
    if UNSAFE.search(body):
        return None
    return re.sub(r"\\(.)", r"\1", body)


def rules_with_holes() -> list[tuple[str, str, str, str | None]]:
    """(файл, шаблон, замена, область) для правил с дыркой в ШАБЛОНЕ."""
    out = []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # ⚠️ Выключенный словарь спрашивать бессмысленно: движок его не грузит,
        # и «перевода нет» тут значит решение игрока, а не поломку.
        if data.get("default") is False:
            continue
        only = data.get("only")
        area = only[0] if isinstance(only, list) and only else "chat"
        for rule in (data.get("regex") or []):
            pattern = rule.get("p") or ""
            if r"\{n\}" in pattern or r"\{s\}" in pattern:
                out.append((path.name, pattern, rule.get("r") or "", area))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    holed = rules_with_holes()
    print(f"правил с дыркой в шаблоне: {len(holed)} (во ВКЛЮЧЁННЫХ словарях)")

    cases = []
    for name, pattern, repl, area in holed:
        line = sample(pattern)
        if line:
            cases.append((name, pattern, repl, area, line))
    print(f"из них удалось построить живую строку: {len(cases)}")
    if not cases:
        print("проверять нечего")
        return 0

    javac, java = base.find_java("javac"), base.find_java("java")
    cp = base.classpath()
    if not (javac and java and cp):
        print("нет Java или классов мода — пропускаю")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "HoleRun.java").write_text(JAVA, encoding="utf-8")
    build = subprocess.run([javac, "-cp", ";".join(cp), "-d", str(OUT),
                            str(OUT / "HoleRun.java")],
                           capture_output=True, text=True, encoding="utf-8")
    if build.returncode != 0:
        print("не собралось:\n" + (build.stderr or build.stdout)[:1200])
        return 0

    lines = OUT / "lines.txt"
    lines.write_text("\n".join(f"{a}\t{l}" for _, _, _, a, l in cases),
                     encoding="utf-8")
    proc = subprocess.run(
        [java, "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8",
         "-cp", ";".join([str(OUT)] + cp), "HoleRun",
         str(PACKS), str(lines)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print("прогон не запустился:\n" + (proc.stderr or proc.stdout)[:1200])
        return 0

    got = {}
    for row in proc.stdout.splitlines():
        if "\t" in row:
            src, res = row.split("\t", 1)
            got[src] = res

    dead = [(n, p, l) for n, p, r, a, l in cases if not got.get(l)]
    alive = len(cases) - len(dead)
    print(f"\nпереводится: {alive} | НЕ ПЕРЕВОДИТСЯ: {len(dead)}")
    if not dead:
        print("\nвсе правила с дыркой на живой строке срабатывают")
        return 0

    by_pack = {}
    for name, _, _ in dead:
        by_pack[name] = by_pack.get(name, 0) + 1
    print("\n=== ⚠️ ПРАВИЛО НЕ СРАБАТЫВАЕТ НА ЖИВОЙ СТРОКЕ ===")
    for name, count in sorted(by_pack.items(), key=lambda x: -x[1]):
        print(f"  {count:5}  {name}")
    print()
    for name, pattern, line in dead[:12]:
        print(f"    {line[:76]}")
        print(f"      шаблон: {pattern[:76]}")
    if len(dead) > 12:
        print(f"    ... ещё {len(dead) - 12}")
    print(r"\n  Чинить: в шаблоне вместо {n} писать ([\d,]+) — движок ловит")
    print("  строку ДО обобщения, с живым числом.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


def live_line(pattern: str) -> str | None:
    r"""Живая строка по ЛЮБОМУ простому шаблону — шире, чем `sample`.

    ⚠️ Зачем отдельная функция. `sample` писан под правила с дыркой «{n}»
    и намеренно ТРУСЛИВ: встретив класс символов, он отказывается. Для его
    задачи это верно, но `check_shrink` спрашивает движок про ЛЮБОЕ выпавшее
    правило, и на «^Difficulty:(\s*)$» трусость означала слепоту: сторож
    печатал «потерь нет» при ПЯТИ пропавших переводах (26.08).

    Правило то же: не уверены — возвращаем None. Промолчать про одно правило
    дешевле, чем построить строку, которой на экране не бывает.
    """
    if not pattern.startswith("^") or not pattern.endswith("$"):
        return None
    body = pattern[1:-1]
    body = re.sub(r"\(\?:[^()]*\)\?", "", body)          # необязательная группа
    body = re.sub(r"\(\\{n\\}\)", "1,234", body)
    body = re.sub(r"\(\\{s\\}\)", "Player", body)
    body = body.replace(r"\{n\}", "1,234").replace(r"\{s\}", "Player")
    body = re.sub(r"\((?:\\s|\s)\*\)", "", body)       # (\s*) -> пусто
    body = re.sub(r"\((?:\\s|\s)\+\)", " ", body)      # (\s+) -> пробел
    body = re.sub(r"\(,\?(?:\\s|\s)\*\)", "", body)   # (,?\s*)
    body = re.sub(r"\(\[IVXLC\]\+\)", "V", body)        # (\[IVXLC\]+)
    body = re.sub(r"\(\[IVXLC\]\{1,\d+\}\)", "V", body)
    body = re.sub(r"\(\[[\d,.+\-]+\]\+%?\)", "1,234", body)
    body = re.sub(r"\(\.\+\??\)", "Sample Thing", body)
    body = re.sub(r"(?<!\\)\\s\*", "", body)            # голый \s* вне группы
    if re.search(r"(?<!\\)[\[\]()|?*+{}]", body):
        return None                                          # остались метасимволы
    return re.sub(r"\\(.)", r"\1", body)
