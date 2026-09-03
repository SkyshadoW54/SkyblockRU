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
CORE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core"
SRC = CORE / "TelemetryFilter.java"
# ⚠️ Признак «строка чужого мода» переехал в ForeignMods — компилируем ОБА.
# Записанная грабля проекта: сторож, собирающий класс в одиночку, краснеет
# на ровном месте, когда у того появляется зависимость.
SOURCES = [SRC, CORE / "ForeignMods.java"]
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
    # ⚠️ ИДЕНТИФИКАТОР ПРОФИЛЯ. Hypixel пишет его в чат при каждом входе,
    # и он уезжал: 22 записи на сервере, пока признака не было. Ловим по
    # ПОДПИСИ — к моменту отправки числа обобщены в {n}, и от UUID остаётся
    # огрызок, под шаблон идентификатора не подходящий.
    ("chat", "Profile ID: 31c58c52-6c0c-466d-8abf-9522fa8c9dc8", False,
     "идентификатор профиля"),
    ("chat", "Profile ID: {n}cc{n}-c{n}-{n}bc{n}-{n}b{n}-{n}e{n}a{n}", False,
     "он же, уже обобщённый числами"),
    # обратный край: обычная строка со словом «profile» уезжать обязана
    ("chat", "You are playing on profile: Papaya", True, "имя профиля — не идентификатор"),
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


# ⚠️ ПАКЕТНЫЙ ПРОГОН, а не запуск JVM на каждую строку.
#
# До 27.08 сторож звал `java` отдельно на КАЖДУЮ строку: чат целиком плюс
# по 40 на источник — около 1900 запусков, 233 с из 316 с всего круга сборки
# (74%). Дороговизну знали и лечили ВЫБОРКОЙ, то есть сузили проверку вместо
# того, чтобы удешевить прогон. Приём взят у соседей (`check_rule_cache`,
# `check_prefilter`): данные уходят ФАЙЛОМ, ответ приходит файлом.
#
# ⚠️⚠️ ФАЙЛ ЗДЕСЬ НЕ ТОЛЬКО РАДИ СКОРОСТИ. Строки уходили АРГУМЕНТАМИ
# командной строки, а Windows кодирует их системной cp1251: каждый значок
# Hypixel и каждая стрелка превращались в «?». Записанная грабля проекта
# (так `check_rules --line` объявлял рабочее правило несработавшим), и здесь
# она означала, что часть живых строк проверялась в искажённом виде.
BATCH_SRC = r"""
import ru.skyblockru.core.TelemetryFilter;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public class TelemetryBatch {
    public static void main(String[] args) throws Exception {
        List<String> rows = Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8);
        StringBuilder out = new StringBuilder();
        for (String row : rows) {
            int tab = row.indexOf('\t');
            if (tab < 0) { continue; }
            String source = row.substring(0, tab);
            String line = unescape(row.substring(tab + 1));
            out.append(TelemetryFilter.worthSending(source, line) ? "SEND" : "SKIP");
            out.append('\n');
        }
        Files.writeString(Path.of(args[1]), out.toString(), StandardCharsets.UTF_8);
    }

    /** Обратно к настоящему тексту: перенос и табуляция пришли экранированными. */
    private static String unescape(String text) {
        StringBuilder made = new StringBuilder(text.length());
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch == '\\' && i + 1 < text.length()) {
                char next = text.charAt(++i);
                if (next == 'n') { made.append('\n'); }
                else if (next == 't') { made.append('\t'); }
                else if (next == '\\') { made.append('\\'); }
                else { made.append('\\').append(next); }
            } else {
                made.append(ch);
            }
        }
        return made.toString();
    }
}
"""


def escape(line: str) -> str:
    """Перенос и табуляция — служебные знаки формата, их надо спрятать."""
    return (line.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\t", "\\t"))


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
        batch = work / "TelemetryBatch.java"
        batch.write_text(BATCH_SRC, encoding="utf-8")
        done = subprocess.run([javac, "-encoding", "UTF-8", "-d", str(work)]
                              + [str(f) for f in SOURCES] + [str(batch)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if done.returncode != 0:
            print("СЛОМАНО: не компилируется TelemetryFilter.java")
            print(done.stderr[:2000])
            return 1

        def ask_many(pairs: list[tuple[str, str]]) -> list[bool]:
            """Один запуск JVM на всю пачку. Ответ построчно, в том же порядке."""
            if not pairs:
                return []
            src = work / "in.tsv"
            dst = work / "out.txt"
            src.write_text("".join(f"{source}\t{escape(line)}\n"
                                   for source, line in pairs), encoding="utf-8")
            answer = subprocess.run(
                [java, "-Dfile.encoding=UTF-8", "-cp", str(work), "TelemetryBatch",
                 str(src), str(dst)],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if answer.returncode != 0 or not dst.exists():
                print("СЛОМАНО: пакетный прогон не отработал")
                print((answer.stderr or "")[:1000])
                return []
            got = dst.read_text(encoding="utf-8").splitlines()
            # ⚠️ Ответов обязано быть столько же, сколько вопросов. Разошлись —
            # значит формат съел строку, и молча сдвинутые ответы будут врать
            # про КАЖДУЮ строку после сдвига.
            if len(got) != len(pairs):
                print(f"СЛОМАНО: спросили {len(pairs)}, ответов {len(got)}")
                return []
            return [row == "SEND" for row in got]

        def ask(source: str, line: str) -> bool:
            got = ask_many([(source, line)])
            return bool(got) and got[0]

        print("=== заведомые случаи ===")
        bad = 0
        verdicts = ask_many([(source, line) for source, line, _, _ in CASES])
        if len(verdicts) != len(CASES):
            return 1
        for (source, line, expected, why), got in zip(CASES, verdicts):
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
            # ⚠️ ВЕСЬ ДАМП, а не выборка. Прежняя оговорка «по 40 на источник,
            # иначе часы» отвалилась вместе с запуском JVM на строку: пачкой
            # весь дамп проходит за один прогон. Выборка тут была не осторожностью,
            # а платой за дороговизну — и молчала ровно там, куда не дотянулась.
            pairs = [(source, line) for source, rows in sorted(sources.items())
                     for line in rows]
            verdicts = ask_many(pairs)
            if len(verdicts) != len(pairs):
                return 1
            by_source: dict[str, list[str]] = {}
            for (source, line), sent in zip(pairs, verdicts):
                if not sent:
                    by_source.setdefault(source, []).append(line)
            for source, rows in sorted(sources.items()):
                lines = list(rows)
                skipped = by_source.get(source, [])
                print("   %-12s строк %5d, не отправим %3d"
                      % (source, len(lines), len(skipped)))
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
