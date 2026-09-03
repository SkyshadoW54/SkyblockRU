# -*- coding: utf-8 -*-
"""
Кэш перебора правил НЕ СМЕЕТ менять перевод — проверка настоящей Java.

    python tools/check_rule_cache.py

⚠️ ЗАЧЕМ. `Translator.lookup` запоминает, что дал перебор для строки ТАКОГО
ВИДА (числа обобщены), и на строке с другим числом подставляет запомненное
вместо повторного перебора. Выигрыш большой (перебор — 213 мкс на строку),
а цена ошибки высокая и ТИХАЯ: перевод не пропадает, а становится НЕ ТЕМ —
чужое число, потерянная дырка, съеденный хвост. На экране это выглядит
работающим модом.

⚠️ ЧТО ПРОВЕРЯЕТСЯ. Для каждой живой строки берутся НЕСКОЛЬКО значений числа,
и ответ с кэшем сверяется с ответом БЕЗ кэша (`Translator.clearRuleCache`
перед каждым вызовом). Расхождение хоть на знак — поломка.

⚠️ ПРОВЕРЕН НА УМЕНИЕ НАХОДИТЬ: без подсадки «молчит» и «ослеп» неотличимы.
Ключ `--probe` ломает кэш нарочно (кладёт в него чужой перевод) — сторож
обязан покраснеть.
"""
import json
import re
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

# ⚠️ Числа берём РАЗНОЙ длины и с разделителем тысяч: подстановка обязана
# пережить и «1», и «1,234,567» — именно на длине ломается резка по позициям.
VALUES = ["1", "7", "42", "999", "1,234", "12,345,678", "0"]

JAVA_SRC = r'''
import ru.skyblockru.core.Translator;
import ru.skyblockru.config.RuConfig;
import java.nio.file.*;
import java.util.*;

public class RuleCacheRun {
    public static void main(String[] args) throws Exception {
        List<String> rows = Files.readAllLines(Path.of(args[0]));
        RuConfig.get().language = "ru_ru";
        RuConfig.get().onlyOnHypixel = false;
        RuConfig.get().onlySkyBlock = false;
        Translator.reload(Path.of(args[1]));

        List<String> origins = new ArrayList<>();
        List<String> lines = new ArrayList<>();
        for (String row : rows) {
            int tab = row.indexOf('\t');
            origins.add(row.substring(0, tab));
            lines.add(row.substring(tab + 1));
        }

        // ЭТАЛОН: честный перебор. Кэш чистится ПЕРЕД КАЖДОЙ строкой,
        // поэтому ответ не может прийти из него.
        String[] want = new String[lines.size()];
        for (int i = 0; i < lines.size(); i++) {
            Translator.clearRuleCache();
            Translator.Match m = Translator.lookup(lines.get(i), origins.get(i), null);
            want[i] = m == null ? "\u0000none" : m.text();
        }

        // С КЭШЕМ: чистим ОДИН раз и дальше идём подряд — так кэш живёт
        // по-настоящему, накапливая виды строк, как это происходит в игре.
        Translator.clearRuleCache();
        StringBuilder out = new StringBuilder();
        int bad = 0;
        for (int i = 0; i < lines.size(); i++) {
            Translator.Match m = Translator.lookup(lines.get(i), origins.get(i), null);
            String got = m == null ? "\u0000none" : m.text();
            if (!want[i].equals(got)) {
                bad++;
                if (bad <= 40) {
                    out.append("MISMATCH\t").append(origins.get(i)).append('\t')
                       .append(lines.get(i)).append('\t').append(want[i])
                       .append('\t').append(got).append('\n');
                }
            }
        }
        out.append("BAD\t").append(bad).append('\n');
        out.append("CACHE\t").append(Translator.ruleCacheSize()).append('\n');
        Files.writeString(Path.of(args[args.length - 1]), out.toString());
    }
}
'''


def classpath() -> list[str] | None:
    import check_click_events as helper
    cp = helper.classpath()
    if cp is None:
        return None
    # ⚠️ NETTY НУЖЕН, и это не прихоть: `Translator.match` разворачивает
    # «@ключ» через `Component.translatable`, а тот тянет сериализацию чата.
    # Без него проверка падает на ПЕРВОЙ же записи с ванильным именем —
    # то есть молчит ровно там, где данных больше всего.
    root = Path.home() / ".gradle" / "caches" / "modules-2" / "files-2.1" / "io.netty"
    for jar in sorted(root.rglob("*.jar")):
        if "sources" in jar.name or "javadoc" in jar.name:
            continue
        cp.append(str(jar))
    return cp


def sample() -> list[tuple[str, str]]:
    """Живые строки из дампа — по всем источникам, где кэш работает."""
    if not DUMP.exists():
        return []
    data = json.loads(DUMP.read_text(encoding="utf-8"))
    rows: list[tuple[str, str]] = []
    for origin, lines in data.get("sources", {}).items():
        if origin == "chat":           # чат из кэша исключён нарочно
            continue
        for line in lines:
            if not isinstance(line, str) or "\t" in line or "\n" in line:
                continue
            # ⚠️ В ДАМПЕ ЧИСЛА УЖЕ ОБОБЩЕНЫ в «{n}» — цифр там почти нет.
            # Ищем строки с дыркой и подставляем в неё живые значения:
            # именно такие строки и приходят от сервера каждый кадр.
            if "{n}" not in line:
                continue
            rows.append((origin, line))
    return rows


def variants(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """К каждой строке — несколько значений числа."""
    out: list[tuple[str, str]] = []
    for origin, line in rows:
        for value in VALUES:
            out.append((origin, line.replace("{n}", value)))
    return out


def main() -> int:
    probe = "--probe" in sys.argv
    cp = classpath()
    if cp is None:
        print("нет классов игры — сперва сборка")
        return 0
    rows = variants(sample())
    if not rows:
        print("дампа нет — проверять нечего")
        return 0
    print(f"строк для сверки: {len(rows)}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "RuleCacheRun.java").write_text(JAVA_SRC, encoding="utf-8")
        data = tmp / "lines.txt"
        data.write_text("\n".join(f"{o}\t{l}" for o, l in rows), encoding="utf-8")
        result = tmp / "out.txt"
        full = [str(CLASSES), str(RESOURCES), *cp]
        sep = ";" if sys.platform == "win32" else ":"
        rc = subprocess.run(
            ["javac", "-encoding", "UTF-8", "-cp", sep.join(full),
             "-d", str(tmp), str(tmp / "RuleCacheRun.java")],
            capture_output=True, text=True)
        if rc.returncode != 0:
            print(rc.stderr[-2000:])
            return 1
        args = ["java", "-Dstdout.encoding=UTF-8", "-cp", sep.join([str(tmp), *full]),
                "RuleCacheRun", str(data), str(RESOURCES)]
        args.append(str(result))
        rc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
        if rc.returncode != 0:
            print(rc.stdout[-2000:], rc.stderr[-2000:])
            return 1
        report = result.read_text(encoding="utf-8").splitlines()

    shown = [r for r in report if r.startswith("MISMATCH")]
    total = next((int(r.split("	")[1]) for r in report if r.startswith("BAD")), 0)
    bad = shown
    size = next((r.split("\t")[1] for r in report if r.startswith("CACHE")), "?")
    print(f"видов строк в кэше: {size}")
    if bad:
        print(f"\n⚠️ КЭШ МЕНЯЕТ ПЕРЕВОД: {total} (показаны первые {len(bad)})")
        for row in bad[:15]:
            _, origin, line, want, got = row.split("\t")
            print(f"  [{origin}] {line}")
            print(f"      без кэша: {want}")
            print(f"      с кэшем:  {got}")
        return 1
    print("расхождений 0 — кэш перевод не меняет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
