# -*- coding: utf-8 -*-
"""
Что мод считает текстом ЧУЖОГО МОДА — настоящей Java, без игры.

⚠️ Зачем. Признак `core/ForeignMods.java` теперь ГАСИТ перевод: строка,
признанная чужой, остаётся английской и в дамп не попадает. Значит ошибка
здесь стоит не лишней записи, а НЕПЕРЕВЕДЁННОЙ строки Hypixel — причём
молча, потому что выглядит это как «перевода просто нет».

⚠️ Поэтому проверяем ОБА края, и второй важнее первого:
  * чужое обязано отсеяться;
  * СВОЁ обязано пройти. Слово «Odin» сидит внутри «exploding», а
    «Exception» — в обычном тексте про исключения; признак по подстроке
    выкосил бы законные строки.

Запуск:
  python tools/check_foreign.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "ForeignMods.java"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")

# слева — строка, справа — чужая ли она
CASES = [
    # --- чужое: не переводим ---
    ("[SkyHanni] +5 SkyBlock XP (Collections) (3/10)", True, "чат SkyHanni"),
    ("(From SkyHanni)", True, "приписка соседа к ПОДСКАЗКЕ ПРЕДМЕТА"),
    ("block.skyhanni.opaque_water", True, "ключ локализации соседа"),
    ("Odin Update Available", True, "заголовок Odin"),
    ("There's a new Skyblocker update available!", True, "чат Skyblocker"),
    ("Caught a IllegalStateException in at.hannibal2.skyhanni.api.ReforgeApi",
     True, "стектрейс соседа"),
    ("- [Repo - NotEnoughUpdates] Error while posting repo reload event.",
     True, "ошибка соседа"),

    # --- НАШЕ: обязано переводиться ---
    ("✖ Exploding Frog (3/10)", False, "«exploding», а не мод Odin"),
    ("and exploding for 5 damage.", False, "«exploding» внутри фразы"),
    ("Purse: 1,000,000", False, "обычная строка панели Hypixel"),
    ("Grants +5 ❤ Health.", False, "обычное описание предмета"),
    ("[NPC] Terry: Ahoy! Welcome to Terry's Shack!", False, "реплика NPC"),
    ("Mining Speed: +250", False, "характеристика"),
    ("You are playing on profile: Papaya", False, "системное сообщение Hypixel"),
]


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
    javac, java = find_java("javac"), find_java("java")
    if not javac or not java:
        print("СЛОМАНО: не нашёл javac/java — проверять нечем")
        return 1

    work = Path(tempfile.mkdtemp(prefix="sbru-foreign-"))
    try:
        done = subprocess.run([javac, "-d", str(work), str(SRC)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if done.returncode != 0:
            print("СЛОМАНО: не компилируется ForeignMods.java")
            print(done.stderr[:2000])
            return 1

        def ask_many(lines: list[str]) -> list[bool]:
            """Пачкой: одна JVM на все строки.

            ⚠️ Раньше здесь был запуск java НА КАЖДУЮ строку, и прогон по
            живому дампу (28 тысяч строк) не заканчивался вовсе. Перенос
            строки в тексте сломал бы разбивку — такие строки не проверяем,
            их в дампе не бывает по построению.
            """
            safe = [line.replace("\n", " ").replace("\r", " ") for line in lines]
            answer = subprocess.run(
                [java, "-Dstdout.encoding=UTF-8", "-Dfile.encoding=UTF-8",
                 "-cp", str(work), "ru.skyblockru.core.ForeignMods"],
                input="\n".join(safe), capture_output=True, text=True,
                encoding="utf-8", errors="replace")
            got = answer.stdout.split()
            if len(got) != len(safe):
                raise RuntimeError("ответов %d на %d строк: %s"
                                   % (len(got), len(safe), answer.stderr[:200]))
            return [word == "FOREIGN" for word in got]

        def ask(line: str) -> bool:
            return ask_many([line])[0]

        print("=== заведомые случаи ===")
        bad = 0
        for line, expected, why in CASES:
            got = ask(line)
            ok = got == expected
            if not ok:
                bad += 1
            print("   %-8s %-14s %s" % ("ок " if ok else "СЛОМАНО",
                                        "чужое" if got else "наше", why))
            if not ok:
                print("            строка: %r" % line[:80])
                print("            ждали: %s" % ("чужое" if expected else "наше"))

        # --- живой дамп: сколько НАШИХ строк потеряет перевод ---
        if DUMP.exists():
            print()
            print("=== живой дамп: что перестанет переводиться ===")
            data = json.loads(DUMP.read_text(encoding="utf-8"))
            sources = data.get("sources") or {}
            pairs = [(source, line)
                     for source, rows in sorted(sources.items()) for line in rows]
            verdicts = ask_many([line for _, line in pairs])
            hit = [pair for pair, foreign in zip(pairs, verdicts) if foreign]
            print("   проверено строк: %d" % len(pairs))
            print("   строк, признанных чужими: %d" % len(hit))
            for source, line in hit[:10]:
                print("      %-10s %s" % (source, line[:80]))
            if not hit:
                print("   (в чистом дампе Hypixel чужого нет — так и должно быть)")
        else:
            print("\nживого дампа нет — проверил только заведомые случаи")

        print()
        if bad:
            print(f"СЛОМАНО: {bad} случаев из {len(CASES)} ведут себя не так")
            return 1
        print(f"СЛОМАНО: 0 — все {len(CASES)} случаев верны")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
