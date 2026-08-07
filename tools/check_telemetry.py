# -*- coding: utf-8 -*-
"""
Что мод отправит на сервер перевода — настоящей Java, без игры.

⚠️ Зачем этот сторож. Промах здесь дороже всех прочих в проекте: кривой
перевод правится следующим прогоном, а чужая переписка, уехавшая на сервер,
не отзывается. Поэтому признак вынесен в `core/TelemetryFilter.java`
(чистая логика, без Minecraft) и гоняется тут — на ЖИВОМ дампе и с подсадкой
заведомых случаев.

⚠️ Проверяем ОБА края. Сторож, проверенный только на «должно отсеяться»,
может отсеивать вообще всё и выглядеть безупречным — поэтому рядом стоят
строки, которые обязаны пройти.

Запуск:
  python tools/check_telemetry.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "TelemetryFilter.java"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")

# ⚠️ Заведомые случаи. Слева — что подать, справа — обязан ли уйти на сервер.
CASES = [
    # то, что отправлять НЕЛЬЗЯ
    ("chat", "[128] ᛝ Vasya: привет, как дела", False, "реплика игрока"),
    ("chat", "[{n}] {s}: you are cringier", False, "реплика игрока, обобщённая"),
    ("chat", "From Petya: скинь координаты", False, "личное входящее"),
    ("chat", "To Petya: сейчас скину", False, "личное исходящее"),
    ("chat", "Party > Vasya: го в данж", False, "чат пати"),
    ("chat", "Guild > Petya: всем привет", False, "чат гильдии"),
    ("chat", "Co-op > Masha: я на острове", False, "чат кооператива"),
    ("chat", "x" * 501, False, "слишком длинная"),
    ("chat", "   ", False, "пустая"),
    # ⚠️ ЧУЖИЕ МОДЫ. У игрока рядом стоят SkyHanni, Skyblocker, Odin: они пишут
    # в чат, рисуют экраны и дописывают в подсказку предмета. Переводить это
    # не наше дело, и уезжать с машины игрока оно не должно.
    ("chat", "[SkyHanni] +5 SkyBlock XP (Collections) (3/10)", False, "чат SkyHanni"),
    ("chat", "There's a new Skyblocker update available!", False, "чат Skyblocker"),
    ("chat", "Caught a IllegalStateException in at.hannibal2.skyhanni.api.ReforgeApi",
     False, "стектрейс чужого мода"),
    ("chat", "- [Repo - NotEnoughUpdates] Error while posting repo reload event.",
     False, "ошибка чужого мода"),
    ("item_lore", "(From SkyHanni)", False, "приписка соседа к ПРЕДМЕТУ"),
    ("item_name", "block.skyhanni.opaque_water", False, "ключ локализации чужого мода"),
    ("title", "Odin Update Available", False, "заголовок чужого мода"),
    # то, что отправлять НАДО
    ("chat", "From stash: Dark Oak Log", True, "выдача из хранилища — это сервер"),
    ("chat", "[NPC] Hunter Ava: You can find him past the bridge.", True, "реплика NPC"),
    ("chat", "You are playing on profile: Pomegranate", True, "системное сообщение"),
    ("chat", "SLAYER QUEST STARTED!", True, "системное сообщение"),
    ("item_lore", "Grants +5 Health.", True, "описание предмета"),
    ("screen", "Top Items", True, "надпись меню"),
    ("scoreboard", "Кошелёк: 43,855", True, "боковая панель"),
    ("tab", "Combat Stats", True, "таб"),
    # ⚠️ ОБРАТНЫЙ КРАЙ признака «чужой мод»: «Odin» сидит внутри «exploding»,
    # и в живом дампе таких строк четыре. Ищем по ГРАНИЦЕ СЛОВА — эти обязаны
    # уехать как обычно.
    ("item_lore", "✖ Exploding Frog (3/10)", True, "«exploding», а не мод Odin"),
    ("item_lore", "and exploding for 5 damage.", True, "«exploding» внутри фразы"),
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

    work = Path(tempfile.mkdtemp(prefix="sbru-telemetry-"))
    try:
        done = subprocess.run([javac, "-d", str(work), str(SRC)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if done.returncode != 0:
            print("СЛОМАНО: не компилируется TelemetryFilter.java")
            print(done.stderr[:2000])
            return 1

        def ask(source: str, line: str) -> bool:
            answer = subprocess.run(
                [java, "-cp", str(work), "ru.skyblockru.core.TelemetryFilter", source, line],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            return answer.stdout.strip() == "SEND"

        print("=== заведомые случаи ===")
        bad = 0
        for source, line, expected, why in CASES:
            got = ask(source, line)
            mark = "ок " if got == expected else "СЛОМАНО"
            if got != expected:
                bad += 1
            print("   %-8s %-30s %s  (%s)"
                  % (mark, source, "отправит" if got else "не отправит", why))
            if got != expected:
                print("            ждали: %s | строка: %r"
                      % ("отправит" if expected else "не отправит", line[:70]))

        # --- живой дамп: что уйдёт на самом деле ---
        if DUMP.exists():
            print()
            print("=== живой дамп ===")
            data = json.loads(DUMP.read_text(encoding="utf-8"))
            sources = data.get("sources") or {}
            # ⚠️ Чат проверяем ЦЕЛИКОМ (там и риск), остальное — выборкой:
            # запуск java на каждую из 27 тысяч строк занял бы часы.
            for source, rows in sorted(sources.items()):
                lines = list(rows)
                sample = lines if source == "chat" else lines[:40]
                skipped = [line for line in sample if not ask(source, line)]
                note = "" if source == "chat" else " (выборка 40)"
                print("   %-12s строк %5d, не отправим %3d%s"
                      % (source, len(lines), len(skipped), note))
                for line in skipped[:3]:
                    print("        %s" % line[:80])
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
