# -*- coding: utf-8 -*-
"""
Дешёвый отсев правил не смеет терять подходящую строку — проверяет САМ МОД.

    python tools/check_prefilter.py

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ СТОРОЖ. Перед запуском регулярки мод отказывает по двум
дешёвым признакам: литеральное начало шаблона (якорь) и обязательная
подстрока. Оба разбирают шаблон СВОИМИ правилами, и оба уже ошибались:
у «^Starts? in:» якорь выходил «Starts», и строка «Start in: 2d 3h»
отсеивалась ДО проверки — правило молча не срабатывало.

⚠️ ПОЧЕМУ СПРАШИВАЕМ МОД, А НЕ ПОВТОРЯЕМ РАЗБОР. Копия признака в Python
разошлась бы при первой же правке, причём молча: сторож остался бы зелёным,
а правило перестало бы работать в игре. Так в проекте уже расходились знаки
списка и алгоритм ключа абзаца. Поэтому свойство проверяет
`Translator.prefilterProblems` — тем же кодом, что работает у игрока.

Свойство: правило СОВПАЛО со строкой -> дешёвый отсев обязан её пропустить.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# ⚠️ Консоль Windows — cp1251, и «⚠️» роняет скрипт на печати.
# У СТОРОЖА это хуже вдвое: он молчит, пока всё хорошо, и падает
# ровно тогда, когда нашёл беду.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ROOT / "versions" / "26.2" / "build" / "classes" / "java" / "main"
RESOURCES = ROOT / "src" / "main" / "resources"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")

PER_SOURCE = 3000

JAVA_SRC = r'''
import ru.skyblockru.core.Translator;
import ru.skyblockru.config.RuConfig;
import java.nio.file.*;
import java.util.*;

public class PrefilterRun {
    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Path.of(args[0]));
        RuConfig.get().language = "ru_ru";
        RuConfig.get().onlyOnHypixel = false;
        RuConfig.get().onlySkyBlock = false;
        Translator.reload(Path.of(args[1]));
        List<String> bad = Translator.prefilterProblems(lines);
        StringBuilder out = new StringBuilder();
        out.append("RULES\t").append(Translator.regexCount()).append('\n');
        out.append("LINES\t").append(lines.size()).append('\n');
        for (String row : bad) {
            out.append("BAD\t").append(row).append('\n');
        }
        Files.writeString(Path.of(args[2]), out.toString());
    }
}
'''


def classpath() -> list[str] | None:
    import check_click_events as helper
    return helper.classpath()


def sample() -> list[str]:
    if not DUMP.exists():
        return []
    data = json.loads(DUMP.read_text(encoding="utf-8"))
    lines: list[str] = []
    for items in data.get("sources", {}).values():
        for line in list(items)[:PER_SOURCE]:
            if isinstance(line, str) and "\n" not in line:
                lines.append(line)
    return lines


def main() -> int:
    cp = classpath()
    if cp is None:
        print("нет классов игры — сперва сборка")
        return 0
    lines = sample()
    if not lines:
        print("дампа нет — проверять нечего")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "PrefilterRun.java").write_text(JAVA_SRC, encoding="utf-8")
        data = tmp / "lines.txt"
        data.write_text("\n".join(lines), encoding="utf-8")
        result = tmp / "out.txt"
        full = [str(CLASSES), str(RESOURCES), *cp]
        sep = ";" if sys.platform == "win32" else ":"
        rc = subprocess.run(
            ["javac", "-encoding", "UTF-8", "-cp", sep.join(full),
             "-d", str(tmp), str(tmp / "PrefilterRun.java")],
            capture_output=True, text=True)
        if rc.returncode != 0:
            print(rc.stderr[-2000:])
            return 1
        rc = subprocess.run(
            ["java", "-Dstdout.encoding=UTF-8", "-cp", sep.join([str(tmp), *full]),
             "PrefilterRun", str(data), str(RESOURCES), str(result)],
            capture_output=True, text=True, encoding="utf-8")
        if rc.returncode != 0:
            print(rc.stdout[-1500:], rc.stderr[-1500:])
            return 1
        report = result.read_text(encoding="utf-8").splitlines()

    rules = next((r.split("\t")[1] for r in report if r.startswith("RULES")), "?")
    count = next((r.split("\t")[1] for r in report if r.startswith("LINES")), "?")
    bad = [r.split("\t", 1)[1] for r in report if r.startswith("BAD")]
    print(f"правил {rules}, строк {count}")
    if bad:
        print(f"\n⚠️ ОТСЕВ ТЕРЯЕТ ПОДХОДЯЩИЕ СТРОКИ: {len(bad)}")
        for row in bad[:10]:
            print(f"    {row}")
        return 1
    print("ни одно правило не теряет подходящую строку")
    return 0


if __name__ == "__main__":
    sys.exit(main())
