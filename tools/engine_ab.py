# -*- coding: utf-8 -*-
"""
A/B движка: тот же дамп, старые классы против новых, построчный diff.

Беда, ради которой написано (11.10). Чинили три бага `Translator`; правка
«{s}-правила ставим впереди всех правил» прошла ВСЕ 11 сторожей зелёными —
и ухудшила 66 строк чата в ОБЫЧНОМ режиме (цветное «погиб от §cOld Wolf»
из 60-chat-rules проиграло сырому «был убит: Old Wolf» из 90-from-game).
Сторожа проверяют свойства (кэш не меняет перевод, прифильтр не теряет
строки), а не ВЫВОД: вопрос «что увидит игрок после правки» никто не задавал.
Этот инструмент задаёт его буквально: гоняет настоящий `Translator` по всем
строкам дампа и абзацам корпуса в обоих режимах старыми и новыми классами
и печатает различия. Различие в обычном режиме — красное по умолчанию:
людям вывод менять можно только намеренно (`--allow-normal`).

Порядок:
    python tools/engine_ab.py --snapshot     ДО правки движка: запомнить классы
    ...правка, сборка (build_all / gradlew :26.2:build)...
    python tools/engine_ab.py                ПОСЛЕ: сравнить, показать различия
    python tools/engine_ab.py --race         стенд гонки reload/lookup на новых классах
    python tools/engine_ab.py --show 30      больше примеров

⚠️ Снимок лежит в data/work/engine-baseline/ (не в git). Снимок старее
исходников — предупреждение, не ошибка: сравниваем то, что есть.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ROOT / "versions" / "26.2" / "build" / "classes" / "java" / "main"
RESOURCES = ROOT / "src" / "main" / "resources"
BASELINE = ROOT / "data" / "work" / "engine-baseline"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
JDK = Path(r"C:\Program Files\Java\jdk-25.0.3\bin")

JAVA_SRC = r'''
import ru.skyblockru.core.Translator;
import ru.skyblockru.config.RuConfig;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/** args: mode(lookup|paragraph|race) resources linesTsv out full(on|off) */
public class EngineAbRun {
    public static void main(String[] args) throws Exception {
        String mode = args[0];
        Path resources = Path.of(args[1]);
        Path linesFile = Path.of(args[2]);
        Path out = Path.of(args[3]);
        boolean full = "on".equals(args[4]);
        RuConfig.get().language = "ru_ru";
        RuConfig.get().onlyOnHypixel = false;
        RuConfig.get().onlySkyBlock = false;
        if (full) {
            RuConfig.get().groups.put(Translator.FULL_GROUP, true);
        }
        Translator.reload(resources);

        List<String> origins = new ArrayList<>();
        List<String> texts = new ArrayList<>();
        for (String row : Files.readAllLines(linesFile, StandardCharsets.UTF_8)) {
            int tab = row.indexOf('\t');
            if (tab < 0) continue;
            origins.add(row.substring(0, tab));
            texts.add(row.substring(tab + 1));
        }
        StringBuilder sb = new StringBuilder();
        sb.append("packs=").append(Translator.packCount()).append(" rules=")
          .append(Translator.regexCount()).append(" terms=").append(Translator.glossaryCount()).append('\n');
        switch (mode) {
            case "lookup" -> {
                for (int i = 0; i < texts.size(); i++) {
                    Translator.Match m = Translator.lookup(texts.get(i), origins.get(i), null);
                    sb.append(origins.get(i)).append('\t').append(texts.get(i)).append("\t->\t")
                      .append(m == null ? "null" : m.kind() + " | " + m.text()).append('\n');
                }
            }
            case "paragraph" -> {
                for (int i = 0; i < texts.size(); i++) {
                    Translator.Match m = Translator.lookupParagraph(texts.get(i), origins.get(i), null);
                    sb.append(origins.get(i)).append('\t').append(texts.get(i)).append("\t->\t")
                      .append(m == null ? "null" : m.kind() + " | " + m.text()).append('\n');
                }
            }
            case "race" -> {
                int n = Math.min(texts.size(), 3000);
                List<String> errors = Collections.synchronizedList(new ArrayList<>());
                int[] done = {0};
                Thread worker = new Thread(() -> {
                    long end = System.currentTimeMillis() + 4000;
                    while (System.currentTimeMillis() < end) {
                        for (int i = 0; i < n; i++) {
                            try {
                                Translator.lookup(texts.get(i), origins.get(i), null);
                                done[0]++;
                            } catch (Throwable t) {
                                errors.add(t.toString());
                                if (errors.size() > 20) return;
                            }
                        }
                    }
                });
                worker.start();
                Thread.sleep(300);
                int reloads = 0;
                while (worker.isAlive()) {
                    Translator.reload(resources);
                    reloads++;
                }
                worker.join();
                sb.append("RACE reloads=").append(reloads).append(" lookups=").append(done[0])
                  .append(" errors=").append(errors.size()).append('\n');
                for (String e : new LinkedHashSet<>(errors)) sb.append("  ").append(e).append('\n');
            }
            default -> throw new IllegalArgumentException(mode);
        }
        Files.writeString(out, sb.toString(), StandardCharsets.UTF_8);
    }
}
'''


def tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidate = JDK / (name + ".exe")
    return str(candidate) if candidate.exists() else name


def classpath() -> list[str] | None:
    """Классы игры и библиотеки — как у соседних сторожей, своей копии не держим."""
    import check_click_events as helper
    cp = helper.classpath()
    if cp is None:
        return None
    netty = Path.home() / ".gradle" / "caches" / "modules-2" / "files-2.1" / "io.netty"
    for jar in sorted(netty.rglob("*.jar")):
        if "sources" not in jar.name and "javadoc" not in jar.name:
            cp.append(str(jar))
    return cp


def fill(text: str) -> str:
    """Дырки заполняем ОДИНАКОВО в обоих прогонах — сравниваем движок, а не числа."""
    return text.replace("{n}", "7").replace("{s}", "Steve")


def inputs(work: Path) -> tuple[Path, Path]:
    lines = work / "lines.tsv"
    rows = []
    if DUMP.exists():
        data = json.loads(DUMP.read_text(encoding="utf-8"))
        for origin, found in (data.get("sources") or {}).items():
            for line in found:
                if isinstance(line, str) and "\t" not in line and "\n" not in line:
                    rows.append(f"{origin}\t{fill(line)}")
    lines.write_text("\n".join(rows), encoding="utf-8")
    paras = work / "paras.tsv"
    prow = []
    if CORPUS.exists():
        for para in json.loads(CORPUS.read_text(encoding="utf-8")).get("paragraphs") or []:
            text = para.get("text") or ""
            if text and "\t" not in text and "\n" not in text:
                prow.append(f"item_lore\t{fill(text)}")
    paras.write_text("\n".join(prow), encoding="utf-8")
    return lines, paras


def compile_runner(work: Path, cp: list[str]) -> bool:
    (work / "EngineAbRun.java").write_text(JAVA_SRC, encoding="utf-8")
    sep = ";" if sys.platform == "win32" else ":"
    rc = subprocess.run([tool("javac"), "-encoding", "UTF-8",
                         "-cp", sep.join([str(CLASSES), str(RESOURCES), *cp]),
                         "-d", str(work), str(work / "EngineAbRun.java")],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if rc.returncode != 0:
        print("Java не собрала стенд:\n" + rc.stderr[-3000:])
        return False
    return True


def run(work: Path, cp: list[str], classes: Path, mode: str, lines: Path,
        full: str, tag: str) -> Path | None:
    out = work / f"{tag}_{mode}_{full}.txt"
    sep = ";" if sys.platform == "win32" else ":"
    rc = subprocess.run([tool("java"), "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8",
                         "-cp", sep.join([str(work), str(classes), str(RESOURCES), *cp]),
                         "EngineAbRun", mode, str(RESOURCES), str(lines), str(out), full],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if rc.returncode != 0:
        print(f"стенд упал ({tag}, {mode}, full={full}):\n" + rc.stderr[-3000:])
        return None
    return out


def diff(old: Path, new: Path, label: str, show: int) -> int:
    a = old.read_text(encoding="utf-8").splitlines()
    b = new.read_text(encoding="utf-8").splitlines()
    changed = [(x, y) for x, y in zip(a[1:], b[1:]) if x != y]
    head = "" if a[:1] == b[:1] else f"   (словари: {a[0] if a else ''} -> {b[0] if b else ''})"
    print(f"\n=== {label}: строк {len(a) - 1}, различий {len(changed)}{head}")
    if len(a) != len(b):
        print("   ⚠️ РАЗНОЕ ЧИСЛО СТРОК — стенды читали разный вход")
    for x, y in changed[:show]:
        print("   БЫЛО:", x[:220])
        print("   СТАЛО:", y[:220])
    if len(changed) > show:
        print(f"   ... ещё {len(changed) - show}")
    return len(changed)


def snapshot() -> int:
    if not CLASSES.is_dir():
        print(f"нет классов: {CLASSES} — сперва сборка")
        return 1
    target = BASELINE / "classes"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(CLASSES, target)
    (BASELINE / "snapshot.txt").write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    print(f"снимок классов сделан: {target} ({sum(1 for _ in target.rglob('*.class'))} классов)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", action="store_true", help="запомнить текущие классы как эталон")
    parser.add_argument("--race", action="store_true", help="стенд гонки на новых классах")
    parser.add_argument("--show", type=int, default=10, help="сколько различий показать")
    parser.add_argument("--allow-normal", action="store_true",
                        help="различия в обычном режиме ожидаемы (намеренная правка)")
    args = parser.parse_args()
    if args.snapshot:
        return snapshot()

    cp = classpath()
    if cp is None:
        print("нет классов игры — сперва сборка")
        return 1
    old = BASELINE / "classes"
    if not args.race and not old.is_dir():
        print("нет снимка эталона — сперва: python tools/engine_ab.py --snapshot (ДО правки)")
        return 1
    stamp = (BASELINE / "snapshot.txt").read_text(encoding="utf-8") if (BASELINE / "snapshot.txt").exists() else "?"

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        if not compile_runner(work, cp):
            return 1
        lines, paras = inputs(work)
        print(f"строк дампа: {sum(1 for _ in lines.open(encoding='utf-8'))}, "
              f"абзацев корпуса: {sum(1 for _ in paras.open(encoding='utf-8'))}; эталон от {stamp}")
        if args.race:
            out = run(work, cp, CLASSES, "race", lines, "off", "new")
            if out is None:
                return 1
            text = out.read_text(encoding="utf-8")
            print(text)
            return 0 if "errors=0" in text else 1

        normal = 0
        total = 0
        for full in ("off", "on"):
            for mode, src in (("lookup", lines), ("paragraph", paras)):
                a = run(work, cp, old, mode, src, full, "old")
                b = run(work, cp, CLASSES, mode, src, full, "new")
                if a is None or b is None:
                    return 1
                n = diff(a, b, f"{mode}, режим full={full}", args.show)
                total += n
                if full == "off":
                    normal += n
    print(f"\nитого различий: {total}, из них в обычном режиме (у людей): {normal}")
    if normal and not args.allow_normal:
        print("СЛОМАНО: вывод для людей изменился — либо это намеренно (--allow-normal), "
              "либо правка движка задела то, чего не должна")
        return 1
    print("СЛОМАНО: 0 — обычный режим без изменений" if not normal
          else "различия в обычном режиме приняты как намеренные")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
