# -*- coding: utf-8 -*-
"""
Обобщение СВОЕГО ника в {s} — настоящей Java, без игры.

⚠️ Зачем этот сторож. Hypixel обращается к игроку по нику прямо в тексте
(«[NPC] Terry: Ahoy, Player_1!»), и такая строка бесполезна всем остальным,
а с телеметрией уезжает вместе с личным именем. Замер 07.08: в дампе 23 такие
строки, и все 23 уже ушли на сервер.

⚠️ Проверяем ОБА края. Сторож, знающий только «должно замениться», пройдёт
и у функции, которая заменяет вообще всё, — поэтому рядом стоят строки,
которые обязаны остаться нетронутыми: чужой ник, ник-префикс другого игрока,
имя внутри слова.

⚠️ ГРАНИЦА ПРИЗНАКА, названная честно. Ник бывает обычным словом («Melon»),
и тогда замена задевает посторонние строки. Это принято осознанно: ключ дампа
управляет СБОРОМ, а не переводом (Translator ищет по сырой строке), поэтому
у такого игрока появится мусорная запись в дампе — но экран не изменится.
Случай стоит в наборе ниже, чтобы цена была видна, а не забыта.

Запуск:
  python tools/check_self_name.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Форма ника Minecraft — та же, что в SelfName.VALID.
NICK_FORM = re.compile(r"^[A-Za-z0-9_]{3,16}$")

# Места, где дамп называет имя САМОГО игрока: витрина музея и табличка «From».
SELF_HINT = re.compile(r"([A-Za-z0-9_]{3,16})'s Museum|^From: ([A-Za-z0-9_]{3,16})$")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "SelfName.java"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")

# ⚠️ Заведомые случаи: ник, что подать, что обязано получиться, почему.
CASES = [
    # --- обобщать НАДО ---
    ("Player_1", "[NPC] Terry: Ahoy, Player_1! Welcome to Terry's Shack!",
     "[NPC] Terry: Ahoy, {s}! Welcome to Terry's Shack!", "реплика NPC — ник в середине"),
    ("Player_1", "[NPC] Rosetta: Hey Player_1!!!",
     "[NPC] Rosetta: Hey {s}!!!", "ник перед знаками препинания"),
    ("Player_1", "Player_1's Museum",
     "{s}'s Museum", "притяжательная форма"),
    ("Ivankovvs", "Ivankovvs' Profile",
     "{s}' Profile", "притяжательная у ника на «s» — апостроф без второй s"),
    ("Player_1", "Player_1 invited Player_1 to visit Your Island!",
     "{s} invited {s} to visit Your Island!", "несколько вхождений сразу"),
    ("Player_1", "From: Player_1",
     "From: {s}", "ник в конце строки"),
    # ⚠️ Известная цена признака, а не недосмотр: ник-слово задевает прозу.
    # Строка стоит здесь, чтобы поведение было названо, а не обнаружено потом.
    ("Melon", "Melon Minion I",
     "{s} Minion I", "ЦЕНА: ник-слово задевает имя предмета (дамп, не экран)"),

    # --- не трогать ---
    ("Player_1", "RARE REWARD! sentiences found a Recombobulator 3000!",
     "RARE REWARD! sentiences found a Recombobulator 3000!",
     "ЧУЖОЙ ник — это дело структурного признака, не наше"),
    ("Player_1", "Player_12 joined the lobby",
     "Player_12 joined the lobby", "другой игрок: наш ник — лишь начало его ника"),
    ("Player_1", "xPlayer_1 sold you an item",
     "xPlayer_1 sold you an item", "имя внутри слова"),
    ("Player_1", "[NPC] Elizabeth: Hey there!",
     "[NPC] Elizabeth: Hey there!", "ника нет вовсе"),
    ("", "[NPC] Terry: Ahoy, Player_1!",
     "[NPC] Terry: Ahoy, Player_1!", "имя не известно — работаем как раньше"),
    ("a", "a quick brown fox",
     "a quick brown fox", "неправдоподобное имя не подставляем вовсе"),
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

    work = Path(tempfile.mkdtemp(prefix="sbru-selfname-"))
    try:
        done = subprocess.run([javac, "-d", str(work), str(SRC)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if done.returncode != 0:
            print("СЛОМАНО: не компилируется SelfName.java")
            print(done.stderr[:2000])
            return 1

        def ask(self_name: str, line: str) -> str:
            answer = subprocess.run(
                [java, "-Dstdout.encoding=UTF-8", "-cp", str(work),
                 "ru.skyblockru.core.SelfName", self_name, line],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            return answer.stdout.rstrip("\r\n")

        print("=== заведомые случаи ===")
        bad = 0
        for self_name, line, expected, why in CASES:
            got = ask(self_name, line)
            ok = got == expected
            if not ok:
                bad += 1
            print("   %-8s %s" % ("ок " if ok else "СЛОМАНО", why))
            if not ok:
                print("            подали:  %r (ник %r)" % (line, self_name))
                print("            ждали:   %r" % expected)
                print("            вышло:   %r" % got)

        # --- живой дамп: что изменится на самом деле ---
        if DUMP.exists():
            print()
            print("=== живой дамп ===")
            data = json.loads(DUMP.read_text(encoding="utf-8"))
            sources = data.get("sources") or {}
            # Ник берём из самого дампа: строки «X's Museum»/«From: X» его
            # называют. Спрашивать клиент тут нечем — игра не запущена.
            # ⚠️ Кандидата обязательно сверяем с формой ника. Без этого сторож
            # принимал за имя уже обобщённое «{s}» из той же строки и считал
            # «101 строку с ником» — то есть отвечал на свой вопрос, а не на наш.
            # ⚠️ Кандидата обязательно сверяем с формой ника. Без этого сторож
            # принимал за имя уже обобщённое «{s}» из той же строки и считал
            # «101 строку с ником» — то есть отвечал на свой вопрос, а не на наш.
            #
            # ⚠️ И берём его РЕГУЛЯРКОЙ, а не отрезанием хвоста: боковая панель
            # присылает строку вместе со значком приватной зоны
            # (« Player_1's Museum»), и «всё до "'s Museum"» ником не будет.
            guess = None
            for rows in sources.values():
                for line in rows:
                    found = SELF_HINT.search(line)
                    candidate = (found.group(1) or found.group(2)) if found else None
                    if candidate and NICK_FORM.match(candidate):
                        guess = candidate
                        break
                if guess:
                    break
            if not guess:
                print("   ник игрока в дампе не назван — пропускаю")
            else:
                print("   ник по дампу: %s" % guess)
                total = 0
                shown = 0
                for source, rows in sorted(sources.items()):
                    hits = [line for line in rows if guess in line]
                    if not hits:
                        continue
                    total += len(hits)
                    print("   %-12s строк с ником: %d" % (source, len(hits)))
                    for line in hits[:2]:
                        if shown < 6:
                            print("        %s" % ask(guess, line)[:88])
                            shown += 1
                print("   ИТОГО строк, которые перестанут нести ник: %d" % total)
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
