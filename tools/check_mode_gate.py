# -*- coding: utf-8 -*-
"""
Ворота перевода: когда мод молчит, а когда работает.

Проверяет `Hypixel.mayTranslate` — решение «переводить ли, раз включено
только SkyBlock». Гоняет НАСТОЯЩЕЙ Java, без запуска игры.

⚠️ ЗАЧЕМ СТОРОЖ. 22.08 нашлось, что первые сообщения после входа выходят
английскими: проценты банка, «You are playing on profile», «Welcome to
Hypixel SkyBlock!». Перевод для них куплен и лежит в словаре, но мод его
даже не спрашивал — при переходе на другой сервер Hypixel боковая панель
пропадает на несколько секунд, а в поле висит ПРЕЖНИЙ режим, лоббийный.
Замер по логам: 64 строки с готовым переводом на 86 входов.

⚠️ Беда была НЕВИДИМА для всех отчётов: сбор непереведённого стоит НИЖЕ
тех же ворот, поэтому строки не попадали и в дамп. Нашлось только сверкой
логов Minecraft с логом мода.

⚠️ Проверяются ОБА края. «Мод больше не молчит» проверить мало: если бы
он начал переводить всегда, эта проверка тоже позеленела бы, а мод полез
бы в чужие режимы Hypixel.

    python tools/check_mode_gate.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

SOURCE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "Hypixel.java"

# Случаи: (что сказал API, заголовок панели, возраст панели в мс, ждём, зачем)
CASES = [
    ("true", "HYPIXEL", 0, True,
     "API сказал «SkyBlock» — верим ему, а не тексту панели"),
    ("false", "SKYBLOCK", 0, False,
     "API сказал «не SkyBlock» — молчим даже при панели SKYBLOCK"),
    ("none", "", 0, True,
     "режим неизвестен — работаем, незнание мод не выключает"),
    ("none", "SKYBLOCK", 0, True,
     "панель свежая и говорит SKYBLOCK"),
    ("none", "SKYBLOCK GUEST", 0, True,
     "гостевой профиль — тот же режим"),
    ("none", "HYPIXEL", 0, False,
     "панель свежая и лоббийная — вот тут молчать обязаны"),
    ("none", "HYPIXEL", 999, False,
     "почти протухла, но ещё свежая — по-прежнему молчим"),
    ("none", "HYPIXEL", 5000, True,
     "ПАНЕЛИ НЕТ 5 секунд: переход между серверами, режим устарел"),
    ("none", "BEDWARS", 3000, True,
     "чужой режим, но панели давно нет — значение уже ни о чём"),
    ("none", "BEDWARS", 200, False,
     "чужой режим и панель рисуется — молчим"),
]

PROBE = """package ru.skyblockru.core;

public final class ModeGateProbe {
    public static void main(String[] args) {
        for (int i = 0; i + 2 < args.length; i += 3) {
            Boolean api = args[i].equals("none") ? null : Boolean.valueOf(args[i]);
            String title = args[i + 1].equals("~") ? "" : args[i + 1];
            long age = Long.parseLong(args[i + 2]);
            System.out.println(Hypixel.mayTranslate(api, title, age));
        }
    }
}
"""


def main() -> int:
    import check_click_events as helper

    java = helper.find_java("java")
    javac = helper.find_java("javac")
    if not java or not javac:
        print("Java не найдена — пропускаю")
        return 0
    cp = helper.classpath()
    if cp is None:
        print("не собрать classpath (нет jar игры или библиотек) — пропускаю")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        probe = work / "ModeGateProbe.java"
        probe.write_text(PROBE, encoding="utf-8")
        out = work / "classes"
        out.mkdir()
        # ⚠️ Компилируем ИСХОДНИК Hypixel.java, а не берём готовый класс из
        # сборки: иначе сторож проверял бы вчерашний jar, а не сегодняшнюю правку.
        build = subprocess.run(
            [javac, "-encoding", "UTF-8", "-nowarn", "-cp", ";".join(cp),
             "-d", str(out), str(SOURCE), str(probe)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            print("СЛОМАНО: Hypixel.java не компилируется")
            print(build.stderr[:1500])
            return 1

        args = []
        for api, title, age, _want, _why in CASES:
            args += [api, title or "~", str(age)]
        run = subprocess.run(
            [java, "-Dstdout.encoding=UTF-8", "-cp", ";".join([str(out)] + cp),
             "ru.skyblockru.core.ModeGateProbe", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode != 0:
            print("СЛОМАНО: проверка не запустилась")
            print(run.stderr[:1500])
            return 1

    got = [line.strip() == "true" for line in run.stdout.split() if line.strip()]
    if len(got) != len(CASES):
        print(f"СЛОМАНО: ждали {len(CASES)} ответов, получили {len(got)}")
        return 1

    bad = 0
    for (api, title, age, want, why), have in zip(CASES, got):
        if have == want:
            continue
        bad += 1
        shown = title or "(пусто)"
        print(f"  СЛОМАНО: api={api} панель={shown!r} возраст={age}мс — "
              f"ждали {'переводим' if want else 'молчим'}, "
              f"вышло {'переводим' if have else 'молчим'}")
        print(f"           {why}")

    if bad:
        print(f"ворота перевода: СЛОМАНО {bad} из {len(CASES)}")
        return 1
    print(f"ворота перевода: {len(CASES)} случаев обоих краёв — все верны")
    return 0


if __name__ == "__main__":
    sys.exit(main())
