# -*- coding: utf-8 -*-
"""
Сколько времени мод тратит на подсказку — НАСТОЯЩЕЙ Java, без игры.

    python tools/check_speed.py

⚠️ ЗАЧЕМ ПОСТОЯННЫЙ ИНСТРУМЕНТ. Замер 03.08 делался разово, и записанная
к нему оговорка («мерился путь ПОИСКА; отрисовка, склейка абзацев и раскраска
в замер не входили») быстро потерялась — в разговоре осталось короткое
«мод не влияет на FPS», которое замер не подтверждал.
А словари с тех пор выросли вдвое: правил было 2368, стало 4578 даже
в обычном режиме. Разовый замер устаревает молча, поэтому он теперь в круге.

⚠️ ЧТО МЕРИМ. Худший путь — строка, перевода для которой НЕТ: она проходит
весь список правил до конца. Именно он определяет цену подсказки, потому что
у переведённой строки поиск обрывается на первом совпадении.

⚠️ ГРАНИЦА (её надо называть каждый раз): мерится ПОИСК и СКЛЕЙКА. Отрисовка
Minecraft сюда не входит — она у нас общая с ванилью и не меняется.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ROOT / "versions" / "26.2" / "build" / "classes" / "java" / "main"
RESOURCES = ROOT / "src" / "main" / "resources"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")

FRAME_MS = 16.7          # кадр при 60 FPS
TOOLTIP_LINES = 30       # строк в обычной подсказке предмета
SWEEP_ITEMS = 8          # столько предметов мод читает за один обход меню

JAVA_SRC = r'''
import ru.skyblockru.core.Translator;
import ru.skyblockru.core.TextTranslator;
import ru.skyblockru.config.RuConfig;
import net.minecraft.network.chat.Component;
import java.nio.file.*;
import java.util.*;

public class SpeedRun {
    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Path.of(args[0]));
        RuConfig.get().language = "ru_ru";
        RuConfig.get().onlyOnHypixel = false;
        RuConfig.get().onlySkyBlock = false;
        // третий аргумент «nodump» — замер без сбора в дамп: так видно,
        // сколько стоит САМ перевод, а сколько учёт непереведённого
        if (args.length > 3 && "nodump".equals(args[3])) {
            RuConfig.get().dumpUntranslated = false;
        }
        Translator.reload(Path.of(args[1]));
        String origin = args[2];
        int frames = 60;

        // ⚠️ МЕРИМ ТО, ЧТО В ИГРЕ: каждый кадр строка ТА ЖЕ, но число в ней
        // другое — у надписи над мобом меняется здоровье, в табе счётчики.
        // Именно поэтому кэш промахов по сырой строке не срабатывал ни разу.
        for (int warm = 0; warm < 2; warm++) {
            for (int f = 0; f < frames; f++) {
                for (String line : lines) {
                    TextTranslator.translate(Component.literal(line.replace("@", String.valueOf(f))), origin);
                }
                // ⚠️ РАЗБОР СОБРАННОГО ИДЁТ В ТИКЕ, а тик втрое длиннее
                // кадра при 60 FPS. Не звать его в замере — значит мерить
                // мод, который копит и не разбирает: цифра польстит.
                if (f % 3 == 0) ru.skyblockru.core.UnknownStrings.drainPending();
            }
        }
        // ⚠️⚠️ МЕРИМ ДВА СЛУЧАЯ, И ОБА НУЖНЫ.
        //
        // ХОЛОДНЫЙ — каждая строка встречается ВПЕРВЫЕ: игрок повернулся,
        // сменился этаж, зашёл в новую зону. Кэш пуст, работа полная.
        // ТЁПЛЫЙ — текст на экране тот же, что кадр назад. Так проходит
        // почти всё время игры: таб не меняется, пока не сменится счётчик.
        //
        // ⚠️ Брать минимум из нескольких раундов, как я сделал сперва, —
        // значит мерить только тёплый: к третьему прогону кэш уже полон,
        // и замер льстит. Холодный меряем ОДНИМ проходом с чистого листа.
        TextTranslator.clearCache();
        long t0 = System.nanoTime();
        for (int f = 0; f < frames; f++) {
            for (String line : lines) {
                TextTranslator.translate(Component.literal(line.replace("@", String.valueOf(f))), origin);
            }
        }
        long cold = System.nanoTime() - t0;

        long best = Long.MAX_VALUE;
        for (int round = 0; round < 3; round++) {
            long t1 = System.nanoTime();
            for (int f = 0; f < frames; f++) {
                for (String line : lines) {
                    TextTranslator.translate(Component.literal(line.replace("@", String.valueOf(f))), origin);
                }
                // ⚠️ РАЗБОР СОБРАННОГО ИДЁТ В ТИКЕ, а тик втрое длиннее
                // кадра при 60 FPS. Не звать его в замере — значит мерить
                // мод, который копит и не разбирает: цифра польстит.
                if (f % 3 == 0) ru.skyblockru.core.UnknownStrings.drainPending();
            }
            best = Math.min(best, System.nanoTime() - t1);
        }
        System.out.println("cold	" + cold);
        // ⚠️ ПРОВЕРКА, ЧТО ЗАМЕР МЕРИТ РАБОТУ, А НЕ ПУСТОТУ: без неё
        // «стало в сто раз быстрее» может значить «мод перестал переводить».
        int translated = 0;
        for (String line : lines) {
            String one = line.replace("@", "7");
            String out = TextTranslator.translate(Component.literal(one), origin).getString();
            if (!out.equals(one)) translated++;
        }
        System.out.println("translated\t" + translated);
        System.out.println("lines\t" + lines.size());
        System.out.println("frames\t" + frames);
        System.out.println("nanos\t" + best);
        System.out.println("rules\t" + Translator.regexCount());
    }
}
'''



def newest(pattern: str) -> Path | None:
    found = sorted((Path.home() / ".gradle" / "caches").glob(pattern))
    return found[-1] if found else None


def classpath() -> list[str] | None:
    import check_click_events as helper
    return helper.classpath()


# ⚠️ «@» в строке ЗАМЕНЯЕТСЯ НОМЕРОМ КАДРА — так замер повторяет игру:
# у надписи над мобом каждый тик другое здоровье, в табе другие счётчики.
# Со СТАТИЧНОЙ строкой замер врал бы в добрую сторону: кэш промахов
# срабатывал бы со второго кадра, чего в игре не происходит.
# ⚠️ СТРОКИ БЕРЁМ ИЗ ДАМПА, а не выдумываем: в настоящем табе 168 разных
# строк, и цена растёт именно от РАЗНООБРАЗИЯ — на одной строке кэш ловит
# почти всегда, а в живом табе почти никогда. Выдуманный сценарий из пяти
# строк показывал 3% кадра там, где настоящий даёт тридцать.
DUMP_SOURCES = ("tab", "name_tag", "scoreboard")


def sample_lines(origin: str, want: int) -> list[str]:
    """Кадр из ЖИВЫХ строк источника; «{n}» станет номером кадра."""
    data = json.loads(DUMP.read_text(encoding="utf-8"))
    rows = list((data.get("sources") or {}).get(origin) or {})
    if not rows:
        return []
    # «{n}» из дампа — это обобщение; вернём на его место меняющееся число
    rows = [r.replace("{n}", "@") for r in rows]
    return [rows[i % len(rows)] for i in range(want)]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(ROOT / "tools"))
    cp = classpath()
    if cp is None:
        return 1
    scenes = [("name_tag", 40, "надписи над мобами в поле зрения"),
              ("tab", 80, "строки таба"),
              ("scoreboard", 20, "боковая панель"),
              ("tab", 80, "строки таба — БЕЗ сбора в дамп", ["nodump"])]

    worst = 0.0
    warm_total = 0.0
    cold_total = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        src = out / "SpeedRun.java"
        src.write_text(JAVA_SRC, encoding="utf-8")
        javac = subprocess.run(["javac", "-encoding", "UTF-8", "-cp", ";".join(cp),
                                "-d", str(out), str(src)],
                               capture_output=True, text=True, encoding="utf-8")
        if javac.returncode != 0:
            print("не собралось:", (javac.stderr or javac.stdout)[:900])
            return 1
        for origin, count, label, *rest in scenes:
            extra = list(rest[0]) if rest else []
            lines = sample_lines(origin, count)
            data = out / f"lines-{origin}.txt"
            # ⚠️ строки передаём ФАЙЛОМ: аргументом Windows бьёт каждый значок
            # в «?» — записанная грабля проекта.
            data.write_text("\n".join(lines), encoding="utf-8")
            proc = subprocess.run(
                ["java", "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8",
                 "-cp", ";".join([str(out)] + cp), "SpeedRun",
                 str(data), str(out / "nopacks"), origin] + extra,
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if proc.returncode != 0:
                print(f"прогон «{origin}» не запустился:")
                print((proc.stderr or proc.stdout).strip()[:1200])
                return 1
            got = dict(row.split("	") for row in proc.stdout.splitlines() if "	" in row)
            frames = int(got["frames"])
            per_frame_ms = int(got["nanos"]) / frames / 1e6
            share = per_frame_ms / FRAME_MS * 100
            done = int(got.get("translated", 0))
            cold_ms = int(got["cold"]) / frames / 1e6
            worst = max(worst, cold_ms / FRAME_MS * 100)
            if "БЕЗ сбора" not in label:
                warm_total += per_frame_ms
                cold_total += cold_ms
            print(f"{label} ({count} строк; переводится {done} из {count}):")
            print(f"   ХОЛОДНЫЙ (всё впервые): {cold_ms:7.2f} мс на кадр")
            print(f"   ТЁПЛЫЙ (текст тот же): {per_frame_ms:7.2f} мс на кадр"
                  f"   [правил в памяти {got.get('rules')}]")
    print()
    # ⚠️ ДОЛЮ КАДРА СЧИТАЕМ ОТ РАЗНОГО FPS. Сравнение с 60 успокаивает зря:
    # у игрока было 140, то есть кадр 7.1 мс, и мод съедал 80% бюджета.
    # Чем выше FPS, тем меньше кадр — и тем заметнее любая наша миллисекунда.
    print("что это значит при разном FPS (сумма таба, панели и надписей):")
    print(f"   {'':16} {'кадр':>7}  {'обычно':>9}  {'при смене обстановки':>22}")
    for fps in (60, 140, 240, 280):
        frame = 1000 / fps
        print(f"   {str(fps) + ' FPS':16} {frame:6.1f} мс  {warm_total / frame * 100:7.1f}%"
              f"  {cold_total / frame * 100:20.0f}%")
    print()
    print("«обычно» — текст на экране тот же, что кадр назад: так проходит")
    print("почти всё время. «при смене обстановки» — все строки разом новые:")
    print("повернулся, сменил зону, открыл таб впервые. Это ОДИН кадр, не поток.")
    print()
    if worst > 25:
        print(f"⚠️ СЛОМАНО: перевод съедает {worst:.0f}% кадра — это видимая просадка FPS")
        return 1
    print(f"ок: худший случай {worst:.1f}% кадра")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
