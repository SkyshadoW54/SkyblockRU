"""
Термины справки, которые мод НЕ НАХОДИТ в подсказке.

Беда, ради которой написано. Игрок трижды сообщал, что у «Tracking» справка
не появляется ни по Shift, ни по Alt. Две попытки починки прошли мимо, потому
что баг воспроизводится не всегда: строки подсказки склеиваются ПРОБЕЛОМ, и
последнее слово имени предмета оказывается вплотную к первому термину лора —

    Future Calories Talisman     <- имя предмета
    Tracking: +0.5               <- термин
    склеено: «Future Calories Talisman Tracking: +0.5»

а правило «слева слово с Заглавной — часть длинного имени» (оно нужно для
«Sea Creature Chance») принимало «Talisman» за начало имени и гасило термин.
На предмете с коротким именем всё работало, и баг выглядел починенным.

⚠️ Признак поломки ЖЕЛЕЗНЫЙ и не зависит от списка статей: если термин стоит
ОТДЕЛЬНЫМ словом в своей строке, он обязан находиться и в склеенном тексте.
Строку проверяем саму по себе — там границ нет и мешать нечему.

⚠️ Логика берётся из НАСТОЯЩЕЙ Java (`core/TermMatch.java`), а не переписывается
на Python: копия признака в этом проекте расходилась молча уже трижды.

Запуск:
  python tools/check_wiki_terms.py
  python tools/check_wiki_terms.py --show 20
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core"
SRC = CORE / "TermMatch.java"
WIKI = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "wiki" / "ru_ru.json"
TOOLTIPS = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/tooltips.json")

RUNNER = """
import java.nio.file.*;
import java.util.*;
import ru.skyblockru.core.TermMatch;

public class TermRun {
    public static void main(String[] args) throws Exception {
        List<String> rows = Files.readAllLines(Paths.get(args[0]));
        StringBuilder out = new StringBuilder();
        for (String row : rows) {
            if (row.isEmpty()) { continue; }
            // формат: термин \\u0001 имена-помехи через \\u0003 \\u0001 строка \\u0001 строка ...
            String[] parts = row.split("\\u0001", -1);
            String term = parts[0];
            // ⚠️ Имена, внутри которых термин термином не является («Fear»
            // в «Fear Mongerer»), спрашиваются на ОБЕИХ сторонах сверки.
            // Иначе сторож объявил бы поломкой правку, которая как раз и
            // убирает чужую справку: в строке термин «стоит отдельно»,
            // а в склейке его законно нет.
            List<String> names = new ArrayList<>();
            for (String name : parts[1].split("\\u0003", -1)) {
                if (!name.isEmpty()) { names.add(name); }
            }
            StringBuilder whole = new StringBuilder();
            List<Integer> starts = new ArrayList<>();
            for (int i = 2; i < parts.length; i++) {
                starts.add(whole.length());
                whole.append(parts[i]).append(' ');
            }
            String text = whole.toString();
            boolean joined = TermMatch.mentions(text, term, starts, names);
            boolean alone = false;
            for (int i = 2; i < parts.length; i++) {
                if (TermMatch.mentions(parts[i] + " ", term, null, names)) { alone = true; break; }
            }
            out.append(joined ? '1' : '0').append(alone ? '1' : '0').append('\\n');
        }
        System.out.print(out);
    }
}
"""


def find_java(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for base in (Path("C:/Program Files/Java"), Path("C:/Program Files/Eclipse Adoptium")):
        if not base.exists():
            continue
        for path in sorted(base.glob(f"*/bin/{name}.exe"), reverse=True):
            return str(path)
    return None


def cases() -> list[tuple[str, list[str]]]:
    """Пары «термин + строки подсказки», где термин вообще встречается."""
    terms = list((json.loads(WIKI.read_text(encoding="utf-8")).get("terms") or {}))
    if not TOOLTIPS.exists():
        return []
    tips = json.loads(TOOLTIPS.read_text(encoding="utf-8")).get("tooltips") or []
    out: list[tuple[str, list[str]]] = []
    seen: set[tuple[str, str]] = set()
    for tip in tips:
        lines = [str(line) for line in (tip.get("lines") or [])]
        if not lines:
            continue
        blob = " ".join(lines)
        for term in terms:
            if term not in blob:
                continue
            key = (term, lines[0][:40])
            if key in seen:
                continue
            seen.add(key)
            out.append((term, lines))
    return out


def names_of() -> dict[str, list[str]]:
    """Имена, внутри которых термин термином НЕ является.

    Кладёт их в справку `tools/gen_wiki_names.py` из защищённых имён проекта:
    «Fear» внутри NPC «Fear Mongerer», «Bank» внутри «Dragontail Bank».
    Пустой словарь — значит помех нет, и сверка идёт как раньше.
    """
    terms = (json.loads(WIKI.read_text(encoding="utf-8")).get("terms") or {})
    return {name: entry.get("names") or [] for name, entry in terms.items()
            if entry.get("names")}


def run_java(rows: list[tuple[str, list[str]]]) -> list[tuple[bool, bool]] | None:
    javac, java = find_java("javac"), find_java("java")
    if not javac or not java:
        print("не нашёл javac/java — а без них логику проверять нечем")
        return None
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "TermRun.java").write_text(RUNNER, encoding="utf-8")
        build = subprocess.run(
            [javac, "-encoding", "UTF-8", "-d", str(work), str(SRC),
             str(work / "TermRun.java")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            print("Java не собрала TermMatch:")
            print(build.stderr[:1500])
            return None
        data = work / "cases.txt"
        # ⚠️ Вторым полем идут ИМЕНА-ПОМЕХИ этой статьи (см. RUNNER): без них
        # сторож объявил бы поломкой правку, которая как раз убирает чужую
        # справку: «Fear» внутри имени NPC «Fear Mongerer».
        blockers = names_of()
        data.write_text("\n".join(
            "\u0001".join([term, "\u0003".join(blockers.get(term, [])), *lines])
            .replace("\n", " ") for term, lines in rows), encoding="utf-8")
        got = subprocess.run([java, "-cp", str(work), "TermRun", str(data)],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if got.returncode != 0:
            print("Java упала:", got.stderr[:800])
            return None
        return [(line[0] == "1", line[1] == "1")
                for line in got.stdout.splitlines() if len(line) >= 2]


# Заведомые случаи для ИМЁН-ПОМЕХ: «должна ли справка появиться».
#
# ⚠️ Нужны обоих краёв. Проверив только «чужая справка ушла», мы бы не заметили,
# что заодно погасла законная: беда, ради которой всё делалось, — справка
# про характеристику «Fear» на конфете, где есть лишь NPC «Fear Mongerer».
BLOCKER_CASES = [
    ("Fear", False, [
        "Green Candy",
        "Конфеты можно обменять у Fear",
        "Mongerer во время Spooky Festival!",
    ]),
    ("Fear", True, [
        "Great Spook Cloak",
        "Fear: +{n}",
        "Obtained during the Alchemist experiments!",
    ]),
    ("Fear", True, [
        "Great Spook Armor",
        "Мобы вокруг разбегаются, если их",
        "уровень меньше твоего Fear.",
    ]),
]


def check_blockers() -> int:
    """Гасят ли имена-помехи ровно то, что надо, и ничего сверх."""
    rows = [(term, lines) for term, _, lines in BLOCKER_CASES]
    verdicts = run_java(rows)
    if verdicts is None:
        return 1
    bad = []
    for (term, want, lines), (joined, _) in zip(BLOCKER_CASES, verdicts):
        if joined != want:
            bad.append((term, want, lines[0], joined))
    print("=== ИМЕНА-ПОМЕХИ ===")
    if not bad:
        print(f"    все {len(BLOCKER_CASES)} случая верны: термин внутри имени "
              f"справки не даёт, законный — даёт")
        return 0
    print(f"СЛОМАНО: {len(bad)}")
    for term, want, first, got in bad:
        print(f"   {term} в «{first}»: ждали {'справку' if want else 'тишину'}, "
              f"вышло {'справка' if got else 'тишина'}")
    return 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Термины справки, потерянные при склейке")
    parser.add_argument("--show", type=int, default=12)
    args = parser.parse_args()

    if check_blockers() != 0:
        return 1
    print()

    rows = cases()
    if not rows:
        print(f"нет данных: {TOOLTIPS}")
        print("Сходи в игру — мод запишет подсказки, тогда будет что проверять.")
        return 0

    verdicts = run_java(rows)
    if verdicts is None:
        return 1

    lost = [(term, lines) for (term, lines), (joined, alone) in zip(rows, verdicts)
            if alone and not joined]
    print(f"пар «термин + подсказка» проверено: {len(rows)}")
    print()
    if not lost:
        print("=== ПОТЕРЯННЫХ ТЕРМИНОВ НЕТ ===")
        print("    Всё, что стоит отдельным словом в строке, находится и в склейке.")
        return 0

    print(f"=== СЛОМАНО: {len(lost)} ===")
    print("    Термин стоит отдельным словом в строке, но в склеенной подсказке")
    print("    не находится — значит справка по нему не появится.")
    for term, lines in lost[:args.show]:
        print(f"   {term:24} в подсказке «{lines[0][:44]}»")
    if len(lost) > args.show:
        print(f"   ... ещё {len(lost) - args.show}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
