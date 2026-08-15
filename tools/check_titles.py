"""
Предмет или кнопка — проверка признака НАСТОЯЩЕЙ Java, без игры.

Что проверяем. `core/Titles.java` решает, чем является заголовок подсказки:
именем вещи (не переводим — по нему ищут на аукционе) или подписью кнопки
меню (переводить надо). Решение принимается по БЛОКУ: у вещи в подсказке
есть строка редкости, у кнопки её нет.

Цена ошибки несимметрична, поэтому проверяются ОБА края:

  назвали кнопку вещью  -> строка молча пропадает из работы. Худший исход:
                           на этом проект уже терял 1639 строк, и найти
                           потерянное нечем — она невидима для всех отчётов;
  назвали вещь кнопкой  -> лишняя строка в списке. Видно глазами, дёшево.

⚠️ Мерцающая обёртка Hypixel обязана распознаваться: «§d§l§ka» рисуется
бегущими глифами и выглядит звёздочкой, а дамп §-коды снимает — в блоке
остаётся «a MYTHIC HELMET a». Голая буква «a» тут не артикль, и без её
разбора половина ходовых вещей считалась бы кнопками.

Сверх рукотворных случаев признак прогоняется по ЖИВЫМ блокам из дампа:
доля вещей должна быть правдоподобной (в SkyBlock меню примерно столько же,
сколько вещей). Ноль или сто процентов значат, что признак ослеп.

Запуск:
  python tools/check_titles.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "Titles.java"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/tooltips.json")

# (описание, блок подсказки, вещь ли это)
CASES = [
    ("обычная вещь", ["Ant Shard", "Mythic commodity", "", "COMMON"], True),
    ("редкость с типом", ["Wise Snorkeling Pants", "Health: +5", "", "UNCOMMON LEGGINGS"], True),
    ("мерцающая обёртка", ["Necrotic Ember Leggings", "Health: +5", "", "a LEGENDARY LEGGINGS a"], True),
    ("кролик", ["Olympe", "Grants +5 Chocolate", "", "RARE RABBIT"], True),
    ("кнопка меню", ["Accept Offer", "Click to accept this offer!"], False),
    ("кнопка с ценой", ["Sell Sacks Now", "Instantly sell all Redstone", "in your sack!"], False),
    ("экран навигации", ["Bestiary", "Track the mobs you have killed", ""], False),
    ("одна строка — не судим", ["Anvil"], False),
    ("пустой блок", [], False),
    # ⚠️ ОБРАТНЫЙ КРАЙ: слово из списка редкостей ВНУТРИ фразы вещью не делает.
    ("проза со словом RARE", ["Fishing Bait", "Grants a chance to catch", "rare sea creatures."], False),
]


def find_java(name: str) -> str | None:
    """JDK ищем как в остальных сторожах: javac и java по отдельности."""
    return shutil.which(name)


def main() -> int:
    javac, java = find_java("javac"), find_java("java")
    if not javac or not java:
        print("не нашёл JDK — без него проверять нечем")
        return 1

    live = []
    if DUMP.is_file():
        blocks = json.loads(DUMP.read_text(encoding="utf-8"))["tooltips"]
        live = [block["lines"] for block in blocks]

    work = Path(tempfile.mkdtemp(prefix="titles-"))
    try:
        package = work / "ru" / "skyblockru" / "core"
        package.mkdir(parents=True)
        shutil.copy2(SRC, package / "Titles.java")

        # ⚠️ Формат нарочно построчный, а не JSON: gson пришлось бы искать
        # в кэше Gradle и тащить в classpath, а проверке он не нужен.
        rows = []
        for name, lines, expect in CASES:
            rows.append(f"CASE	{name}	{'item' if expect else 'button'}")
            rows.extend(f"LINE	{line}" for line in lines)
            rows.append("END")
        for lines in live:
            rows.append("LIVE		")
            rows.extend(f"LINE	{line}" for line in lines)
            rows.append("END")
        (work / "cases.txt").write_text("\n".join(rows), encoding="utf-8")

        runner = work / "Check.java"
        runner.write_text(RUNNER, encoding="utf-8")
        compiled = subprocess.run(
            [javac, "-encoding", "UTF-8", "-d", str(work),
             str(package / "Titles.java"), str(runner)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if compiled.returncode != 0:
            print("не компилируется:")
            print(compiled.stdout or compiled.stderr)
            return 1

        # ⚠️ Вывод Java идёт в системной кодировке, и русский текст приезжает
        # битым — записанная грабля проекта.
        result = subprocess.run(
            [java, "-Dstdout.encoding=UTF-8", "-cp", str(work), "Check", str(work / "cases.txt")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(result.stdout.strip())
        return result.returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


RUNNER = r"""
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import ru.skyblockru.core.Titles;

public class Check {
    public static void main(String[] args) throws Exception {
        List<String> rows = Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8);
        int broken = 0, cases = 0, live = 0, items = 0;
        String name = null, kind = null;
        boolean isLive = false;
        List<String> lines = new ArrayList<>();
        for (String row : rows) {
            if (row.startsWith("CASE	")) {
                String[] parts = row.split("	", -1);
                name = parts[1];
                kind = parts[2];
                isLive = false;
                lines = new ArrayList<>();
            } else if (row.startsWith("LIVE	")) {
                isLive = true;
                lines = new ArrayList<>();
            } else if (row.startsWith("LINE	")) {
                lines.add(row.substring(5));
            } else if (row.equals("END")) {
                boolean got = Titles.hasRarity(lines);
                if (isLive) {
                    live++;
                    if (got) items++;
                } else {
                    cases++;
                    boolean expect = "item".equals(kind);
                    if (got != expect) {
                        broken++;
                        System.out.println("  СЛОМАНО: " + name + " — ждали "
                                + (expect ? "вещь" : "кнопку") + ", вышло "
                                + (got ? "вещь" : "кнопка"));
                    }
                }
            }
        }
        System.out.println("случаев: " + cases + ", сломано: " + broken);
        if (live > 0) {
            int share = items * 100 / live;
            System.out.println("живых блоков: " + live + ", вещей: " + items
                    + " (" + share + "%)");
            if (share < 10 || share > 90) {
                System.out.println("  СЛОМАНО: доля вещей " + share
                        + "% — признак ослеп или ловит всё подряд");
                broken++;
            }
        }
        System.out.println(broken == 0
                ? "СЛОМАНО: 0 — признак различает вещь и кнопку"
                : "СЛОМАНО: " + broken);
        System.exit(broken == 0 ? 0 : 1);
    }
}
"""

if __name__ == "__main__":
    raise SystemExit(main())
