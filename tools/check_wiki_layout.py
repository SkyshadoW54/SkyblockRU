"""
Раскладка столбцов справки — настоящей Java, без игры.

⚠️ Зачем. Столбец справки уехал ПОД подсказку предмета, и увидеть это можно
было только на экране: игрок прислал скриншот. Ровно тем же путём проект уже
обжигался на цветах — правило меняли четырежды и дважды ломали экран, пока
логику не вынесли в чистый класс (`ColorLayout`) и не начали гонять без игры.

Здесь то же самое: `PanelLayout.place` — арифметика без Minecraft, и проверить
её можно до сборки. Случаи взяты не из головы: это положения курсора и ширины,
какие бывают в игре, включая тот самый — меч с двумя десятками зачарований,
когда справка не влезает ни справа, ни слева целиком.

Проверяем ДВА свойства, и второе важнее первого:
  1. столбец не выходит за экран;
  2. столбец НЕ НАКРЫВАЕТ подсказку предмета — то, что было на скриншоте.

Запуск:
  python tools/check_wiki_layout.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "PanelLayout.java"

GAP = 12
EDGE = 4

# screen, mainX, mainWidth, [ширины столбцов], что должно получиться
CASES = [
    # Один столбец, места справа вдоволь — встаёт рядом с подсказкой.
    ("один столбец справа", 640, 100, 200, [150], 1),
    # Курсор у правого края: справа места нет, уходим влево.
    ("один столбец слева", 640, 380, 240, [150], 1),
    # ⚠️ ТОТ САМЫЙ СЛУЧАЙ: два столбца, подсказка широкая и посередине.
    # Раньше второй столбец зажимался по краю экрана и ложился на подсказку.
    ("два столбца по бокам", 640, 200, 240, [150, 150], 2),
    # Широкий экран: оба помещаются справа подряд.
    ("два столбца справа", 960, 60, 200, [150, 150], 2),
    # Второму места нет — показываем один, честно, а не втискиваем поверх.
    # ⚠️ Числа посчитаны, а не взяты на глаз: подсказка 120..320, справа
    # свободно 332..516 — первый столбец (150) влезает, второму нужно ещё
    # 12+150, и он уже за краем.
    ("второму места нет", 520, 120, 200, [150, 150], 1),
    # Подсказка почти во весь экран — не помещается ни один.
    ("не помещается никто", 300, 20, 260, [150], 0),
]

JAVA = """
import java.util.List;
import java.util.ArrayList;
import ru.skyblockru.core.PanelLayout;

public class CheckWikiLayout {
    public static void main(String[] args) throws Exception {
        String raw = new String(java.nio.file.Files.readAllBytes(
                java.nio.file.Path.of(args[0])), java.nio.charset.StandardCharsets.UTF_8);
        StringBuilder out = new StringBuilder("[");
        for (String line : raw.split("\\n")) {
            if (line.isBlank()) continue;
            String[] p = line.trim().split(";");
            int screen = Integer.parseInt(p[0]);
            int mainX = Integer.parseInt(p[1]);
            int mainWidth = Integer.parseInt(p[2]);
            List<Integer> widths = new ArrayList<>();
            for (String w : p[3].split(",")) widths.add(Integer.parseInt(w));
            List<Integer> places = PanelLayout.place(screen, mainX, mainWidth,
                    %d, %d, widths);
            boolean over = PanelLayout.overlaps(mainX, mainWidth, places, widths);
            if (out.length() > 1) out.append(",");
            out.append("{\\"places\\":").append(places)
               .append(",\\"overlaps\\":").append(over).append("}");
        }
        out.append("]");
        System.out.println(out);
    }
}
""" % (GAP, EDGE)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not SOURCE.exists():
        print(f"нет исходника: {SOURCE}")
        return 1

    work = Path(tempfile.mkdtemp(prefix="wikilayout"))
    (work / "CheckWikiLayout.java").write_text(JAVA, encoding="utf-8")
    feed = "\n".join(
        f"{screen};{main_x};{main_w};{','.join(str(w) for w in widths)}"
        for _, screen, main_x, main_w, widths, _ in CASES)
    (work / "cases.txt").write_text(feed, encoding="utf-8")

    compiled = subprocess.run(
        ["javac", "-d", str(work), str(SOURCE), str(work / "CheckWikiLayout.java")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if compiled.returncode:
        print("Java НЕ СОБРАЛАСЬ:")
        print(compiled.stderr.strip()[:2000])
        return 1

    run = subprocess.run(["java", "-cp", str(work), "CheckWikiLayout", str(work / "cases.txt")],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if run.returncode:
        print("Java упала:")
        print(run.stderr.strip()[:2000])
        return 1

    results = json.loads(run.stdout.strip())
    bad = 0
    for (name, screen, main_x, main_w, widths, expect), got in zip(CASES, results):
        places = got["places"]
        problems = []
        if len(places) != expect:
            problems.append(f"столбцов {len(places)}, ждали {expect}")
        if got["overlaps"]:
            problems.append("НАКРЫВАЕТ ПОДСКАЗКУ")
        for x, w in zip(places, widths):
            if x < EDGE or x + w > screen - EDGE:
                problems.append(f"вылез за экран: {x}..{x + w} при ширине {screen}")
        mark = "[ok]  " if not problems else "[ПРОВАЛ] "
        bad += bool(problems)
        print(f"  {mark}{name}: {places}")
        for problem in problems:
            print(f"          {problem}")

    print()
    print(f"случаев: {len(CASES)}, замечаний: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
