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


def anchors_are_safe() -> list[str]:
    """
    Якорь-прифильтр не смеет отбрасывать строку, которая правилу ПОДХОДИТ.

    ⚠️⚠️ ЭТО НЕ ТЕОРИЯ. `Translator.anchorOf` брал литеральное начало шаблона
    и останавливался на первом особом символе — но букву ПЕРЕД `?` успевал
    добавить. У «^Starts? in:» якорь выходил «Starts», и строка «Start in: 2d
    3h» отсеивалась ДО проверки: правило молча не срабатывало. Замер 23.08 —
    задето 5 правил, 4 из них живые (таймеры событий) плюс надпись миньона.

    ⚠️ Беда тихая по построению: правило компилируется, словарь грузится,
    счётчики растут — просто перевода нет. Компиляция такого не ловит, потому
    проверка и стоит отдельным разделом.

    Свойство проверяется на ЖИВЫХ строках дампа: `pattern.match(line)`
    истинно -> `line.startswith(anchor)` обязано быть истинным тоже.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import status
    try:
        import make_queue
        rows = make_queue.load("collected.json").get("sources") or {}
    except Exception:
        rows = {}
    lines: set[str] = set()
    for items in rows.values():
        lines.update(list(items)[:3000])
    dictionaries = status.Dictionaries(groups={"full"})
    bad = []
    for rule in dictionaries.rules:
        if not rule.anchor:
            continue
        for line in lines:
            if rule.pattern.match(line) and not line.startswith(rule.anchor):
                bad.append("%s: якорь %r отбрасывает %r"
                           % (rule.pattern.pattern[:44], rule.anchor, line[:44]))
                break
    return bad


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
        # ⚠️ Примеряемые строки уходят ФАЙЛОМ, а не аргументами командной
        # строки. Аргументы Windows кодирует системной кодировкой (cp1251),
        # и каждый значок Hypixel — «❣», «➡», приватная зона — превращался
        # в «?». Правило со значком объявлялось несработавшим, хотя работает:
        # проверка отвечала на СВОЙ вопрос («подходит ли правило к строке
        # из вопросительных знаков»), а выглядело это как приговор правилу.
        lines_file = Path(temp) / "lines.txt"
        lines_file.write_text("\n".join(samples), encoding="utf-8")
        # ⚠️ stdout.encoding задаём явно: иначе Java пишет в кодировке консоли
        # (на этой машине cp1251), и русский перевод приезжает сюда крокозябрами.
        result = subprocess.run(
            [java, "-Dstdout.encoding=UTF-8", "-Dfile.encoding=UTF-8",
             str(CHECKER), str(table), str(lines_file)],
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

    # ⚠️ ДВОЙНАЯ ОБРАТНАЯ КОСАЯ В ШАБЛОНЕ — правило мертво по построению.
    # В json косая записывается ОДНА (json.dumps удвоит её сам); написав
    # две, получаешь буквальное «\\d» вместо класса цифр, и правило
    # не совпадёт НИКОГДА. Записанная грабля проекта про \uXXXX,
    # всплывшая 25.08 в правиле статуса миньона «[SLOW]»: словарь
    # грузится, Java шаблон принимает, ошибок нет — просто перевода нет.
    doubled = []
    for pack, pattern, _replacement in rules():
        if "\\\\" in pattern:
            doubled.append(f"{pack}: {pattern[:70]}")
    print("\n=== ДВОЙНАЯ КОСАЯ В ШАБЛОНЕ ===")
    if doubled:
        print(f"  правил, где косая удвоена и класс мёртв: {len(doubled)}")
        for note in doubled[:8]:
            print(f"    {note}")
    else:
        print("  ни одного правила с удвоенной косой")

    unsafe = anchors_are_safe()
    print("\n=== ЯКОРЬ-ПРИФИЛЬТР ===")
    if unsafe:
        print(f"  правил, у которых якорь режет своё же: {len(unsafe)}")
        for note in unsafe[:8]:
            print(f"    {note}")
    else:
        print("  ни одно правило не теряет подходящую строку")

    print(f"\nитого замечаний: {len(broken) + len(unsafe) + len(doubled)}")
    return 1 if broken or unsafe or doubled else 0


if __name__ == "__main__":
    raise SystemExit(main())
