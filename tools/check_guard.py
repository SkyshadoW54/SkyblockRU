# -*- coding: utf-8 -*-
"""
ОГРАДА вокруг наших перехватов — проверка настоящей Java, без игры.

Зачем. `core/Guard.java` не даёт нашей поломке уронить чужую подсказку:
Fabric отдаёт нам список строк БЕЗ копирования (проверено javap по
fabric-item-api-v1: он берёт cir.getReturnValue()), и исключение отсюда
роняет построение подсказки целиком — у нас и у соседних модов сразу.
Мод пойдёт к людям с REI, JEI, Skyblocker, и «ваш мод ломает мою сборку»
хуже любого непереведённого текста.

⚠️ Но защита, которую нечем проверить, — это ещё одно место, где поломка
живёт молча. У ограды ДВА способа соврать, и проверяем оба:
  * не поймать то, что должна (исключение уходит наружу);
  * поймать то, что нельзя (OutOfMemoryError сказать нечего, это состояние
    всей игры, и глушить его — прятать настоящую беду).

Плюс третье: сбой обязан быть СОСЧИТАН. Молча проглоченное исключение
означает английскую подсказку без единого следа — ровно та беда, на которой
проект уже обжигался (потолок сбора, обнулённый словарь).

    python tools/check_guard.py
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "Guard.java"

CASE = r"""
import ru.skyblockru.core.Guard;

public class CheckGuard {
    static int failures = 0;

    static void expect(boolean ok, String what) {
        System.out.println((ok ? "  [ok]   " : "  [ПЛОХО] ") + what);
        if (!ok) failures++;
    }

    public static void main(String[] args) {
        // 1. Ловит RuntimeException и НЕ выпускает наружу.
        boolean ok = Guard.run("test.runtime", () -> {
            throw new IllegalStateException("подсаженная поломка");
        });
        expect(!ok, "RuntimeException пойман, наружу не ушёл");

        // 2. Ловит LinkageError — типичный отказ в ЧУЖОЙ сборке
        //    (другой Fabric API, другая версия библиотеки).
        ok = Guard.run("test.linkage", () -> {
            throw new NoSuchMethodError("метода нет в этой сборке");
        });
        expect(!ok, "NoSuchMethodError пойман (чужая сборка не роняет мод)");

        // 3. Исправный код проходит и говорит true.
        final int[] ran = {0};
        ok = Guard.run("test.fine", () -> ran[0]++);
        expect(ok && ran[0] == 1, "исправный код выполняется и отчитывается true");

        // 4. Сбой СОСЧИТАН и назван по месту — иначе это глушилка.
        expect(Guard.total() == 2, "сбоев сосчитано ровно 2, а не " + Guard.total());
        expect(Guard.failures().containsKey("test.runtime")
                && Guard.failures().containsKey("test.linkage"),
                "в диагностике видно ГДЕ упало");

        // 5. get() отдаёт запасное значение, а не бросает.
        String value = Guard.get("test.value", () -> {
            throw new IllegalArgumentException("и тут поломка");
        }, "исходное");
        expect("исходное".equals(value), "get() вернул исходное значение вместо броска");

        // 6. ⚠️ OutOfMemoryError глушить НЕЛЬЗЯ: это состояние всей игры,
        //    а не наш промах. Он обязан пройти ограду насквозь.
        boolean passedThrough = false;
        try {
            Guard.run("test.fatal", () -> {
                throw new OutOfMemoryError("память кончилась");
            });
        } catch (OutOfMemoryError expected) {
            passedThrough = true;
        }
        expect(passedThrough, "OutOfMemoryError проброшен наружу, а не проглочен");

        System.out.println();
        if (failures > 0) {
            System.out.println("СЛОМАНО: " + failures);
            System.exit(1);
        }
        System.out.println("ограда работает: ловит наше, пропускает чужое, считает сбои");
    }
}
"""


def find(pattern):
    hits = glob.glob(os.path.expanduser(pattern), recursive=True)
    return hits[0] if hits else None


def main():
    javac = find("C:/Program Files/Java/jdk-*/bin/javac.exe") or "javac"
    java = find("C:/Program Files/Java/jdk-*/bin/java.exe") or "java"

    # slf4j нужен: ограда пишет в лог первый сбой каждого места.
    slf4j = find("~/.gradle/caches/**/slf4j-api-*.jar")
    if not slf4j:
        print("не нашёл slf4j-api в кэше gradle — соберите проект хотя бы раз")
        return 1

    work = Path(tempfile.mkdtemp())
    try:
        pkg = work / "ru" / "skyblockru" / "core"
        pkg.mkdir(parents=True)
        shutil.copy(GUARD, pkg / "Guard.java")
        (work / "CheckGuard.java").write_text(CASE, encoding="utf-8")

        compile_run = subprocess.run(
            [javac, "-encoding", "UTF-8", "-cp", slf4j, "-d", str(work),
             str(pkg / "Guard.java"), str(work / "CheckGuard.java")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if compile_run.returncode != 0:
            print("НЕ КОМПИЛИРУЕТСЯ:")
            print(compile_run.stderr)
            return 1

        run = subprocess.run(
            [java, "-cp", os.pathsep.join([str(work), slf4j]), "CheckGuard"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(run.stdout, end="")
        if run.stderr.strip():
            # ожидаемый шум: ограда печатает первый сбой каждого места
            noise = [ln for ln in run.stderr.splitlines()
                     if not re.search(r"SLF4J|skyblockru\] failed|^\s+at |Exception|Error", ln)]
            if noise:
                print("\n".join(noise))
        return run.returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
