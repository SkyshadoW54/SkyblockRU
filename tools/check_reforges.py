# -*- coding: utf-8 -*-
"""
Название перекованной вещи: «Fortunate Lapis Pickaxe» -> «Удачливая
лазуритовая кирка».

Гоняет `core/Reforge.compose` НАСТОЯЩЕЙ Java, без запуска игры.

⚠️ ЗАЧЕМ. Механика склеивает название из двух половин, и ошибиться она может
тихо: не тем родом («Удачливый кирка»), не там разрезав («Ancient Necron's
Chestplate» — тут первое слово ЧАСТЬ имени) или выдав смесь языков
(«Удачливая Lapis Pickaxe»). Всё это видно только на экране и только тому,
у кого такая вещь есть.

⚠️ ОБА КРАЯ ОБЯЗАТЕЛЬНЫ. «Перековки переводятся» проверить мало: механика,
которая режет ВСЁ подряд, эту проверку тоже прошла бы, а на экране появились
бы покалеченные названия обычных вещей.

    python tools/check_reforges.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

SOURCE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "Reforge.java"

# Словарь, который подсовываем проверке. Не берём настоящий: сторож обязан
# мерить МЕХАНИКУ, а не сегодняшнее содержимое словаря — иначе он покраснеет
# в день, когда перевод поправят.
NAMES = {
    "Lapis Pickaxe": "Лазуритовая кирка",
    "Sword": "Меч",
    "Ring": "Кольцо",
    "Shadow Assassin Boots": "Ботинки убийцы теней",
    "Necron's Chestplate": "Кираса Некрона",
    "Aspect of the End": "Аспект конца",
    "Divan's Drill": "Дрель Дивана",
    "Truffle": "Трюфель",
    "Hyperion": "Гиперион",
    "Necron's Leggings": "Поножи Некрона",
}

# Слова, у которых окончание рода не выдаёт. Список короткий и явный —
# ровно так же в проекте перечислены двойственные имена.
GENDERS = {"дрель": "f"}
REFORGES = {
    "Fortunate": ["Удачливый", "Удачливая", "Удачливое", "Удачливые"],
    "Fierce": ["Свирепый", "Свирепая", "Свирепое", "Свирепые"],
}

# (название, сказал ли NBT «перекована», чего ждём, зачем случай)
CASES = [
    ("Fortunate Lapis Pickaxe", True, "Удачливая лазуритовая кирка",
     "женский род берётся из перевода основы"),
    ("Fierce Sword", True, "Свирепый меч",
     "мужской род"),
    ("Fierce Ring", True, "Свирепое кольцо",
     "средний род"),
    ("Fierce Shadow Assassin Boots", True, "Свирепые ботинки убийцы теней",
     "множественное число"),
    ("Fierce Necron's Chestplate", True, "Свирепая кираса Некрона",
     "имя собственное внутри названия остаётся с заглавной"),
    ("Fortunate Lapis Pickaxe", False, None,
     "NBT МОЛЧИТ — не режем вовсе, даже если название выглядит перекованным"),
    ("Ancient Necron's Chestplate", True, None,
     "перековки «Ancient» в словаре нет — оставляем как есть, а не гадаем"),
    ("Fierce Unknown Sword", True, None,
     "основа словарю неизвестна: «Свирепый Unknown Sword» был бы смесью языков"),
    ("Sword", True, "Меч",
     "одно слово: резать нечего, но имя целиком в словаре есть"),
    ("Fierce", True, None,
     "только перековка, без основы"),
    ("Fierce Divan's Drill", True, "Свирепая дрель Дивана",
     "МЯГКИЙ ЗНАК: род не выводится окончанием, берётся из списка"),
    ("Fierce Truffle", True, "Свирепый трюфель",
     "тот же мягкий знак, но слово мужское — списка ему не нужно"),
    ("Hyperion ✪✪✪✪✪", False, "Гиперион ✪✪✪✪✪",
     "ХВОСТ ПРОКАЧКИ: без перековки, но звёзды мешают найти имя"),
    ("Fierce Necron's Leggings ✪✪✪✪✪➎", True, "Свирепые поножи Некрона ✪✪✪✪✪➎",
     "перековка И хвост разом — самая частая форма на аукционе"),
    ("Hyperion", False, "Гиперион",
     "имя без хвоста и без перековки — обычный словарь"),
    ("Unknown Sword ✪✪", False, None,
     "хвост снят, но имени в словаре нет — оставляем английским"),
    # ⚠️ ВЕДУЩИЙ ЗНАЧОК. Hypixel помечает часть вещей значком ПЕРЕД именем,
    # и до 23.08 всё помеченное оставалось английским: хвост звёзд мы снимали,
    # а начало — нет. Замер по строкам от игроков: 1501 такое имя, из них
    # 1229 переводятся сразу, как только значок снят.
    ("✿ Hyperion", False, "✿ Гиперион",
     "ВЕДУЩИЙ ЗНАЧОК: снимается так же, как хвост, и возвращается на место"),
    ("✿ Fierce Necron's Leggings ✪✪✪✪✪➎", True,
     "✿ Свирепые поножи Некрона ✪✪✪✪✪➎",
     "значок, перековка и хвост разом — самая частая форма на аукционе"),
    ("✿Hyperion", False, None,
     "ЗНАЧОК БЕЗ ПРОБЕЛА не снимаем: иначе признак съел бы начало имени"),
    ("✿ Unknown Sword", False, None,
     "значок снят, а имени в словаре нет — оставляем английским, не гадаем"),
    # ⚠️ ПРИЗНАК, А НЕ СПИСОК. Перечень увиденных значков отстал от первой же
    # новой вещи: у самоцветов значок свой на каждый тип, у метки рецепта
    # третий, у реликвии четвёртый. Замер: список закрывал 1229 имён,
    # признак — на 179 больше, и все 179 просмотрены глазами.
    ("✖ Hyperion", False, "✖ Гиперион",
     "метка рецепта «не собрано» — значка нет ни в каком списке, а имя за ней"),
    ("⚚ Hyperion", False, "⚚ Гиперион",
     "значок реликвии — тот же случай, признак берёт его без правки списка"),
    ("- Hyperion", False, "- Гиперион",
     "любой ведущий знак с пробелом: снятие безопасно, потому что остаток "
     "обязан найтись"),
    ("(1/2) Hyperion", False, None,
     "СКОБКА СО СЧЁТЧИКОМ не значок: за ней идёт цифра, а не пробел"),
]

PROBE = """package ru.skyblockru.core;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class ReforgeProbe {
    // ⚠️ ДАННЫЕ ЧИТАЕМ ФАЙЛОМ, а не берём из аргументов: Windows кодирует
    // командную строку системной кодировкой, и звёзды прокачки приезжают
    // вопросительными знаками. Записанная грабля проекта — на ней уже
    // однажды объявили рабочее правило несработавшим.
    public static void main(String[] args) throws IOException {
        List<String> lines = Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8);
        Map<String, String> names = new HashMap<>();
        Map<String, String[]> reforges = new HashMap<>();
        Map<String, String> genders = new HashMap<>();
        List<String[]> cases = new ArrayList<>();
        String section = "";
        for (String line : lines) {
            if (line.startsWith("#")) {
                section = line.substring(1);
                continue;
            }
            String[] parts = line.split("	", -1);
            switch (section) {
                case "names" -> names.put(parts[0], parts[1]);
                case "reforges" -> reforges.put(parts[0],
                        new String[] { parts[1], parts[2], parts[3], parts[4] });
                case "genders" -> genders.put(parts[0], parts[1]);
                case "cases" -> cases.add(parts);
                default -> { }
            }
        }
        StringBuilder out = new StringBuilder();
        for (String[] row : cases) {
            String got = Reforge.compose(row[0], row[1].equals("yes"),
                    names::get, reforges::get, genders::get);
            out.append(got == null ? "~" : got).append(System.lineSeparator());
        }
        Files.writeString(Path.of(args[1]), out.toString(), StandardCharsets.UTF_8);
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
        print("не собрать classpath — пропускаю")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        task = work / "task.txt"
        rows = ["#names"]
        rows += [f"{k}	{v}" for k, v in NAMES.items()]
        rows.append("#reforges")
        rows += ["	".join([k, *v]) for k, v in REFORGES.items()]
        rows.append("#genders")
        rows += [f"{k}	{v}" for k, v in GENDERS.items()]
        rows.append("#cases")
        rows += [f"{title}	{'yes' if reforged else 'no'}"
                 for title, reforged, _w, _why in CASES]
        task.write_text(chr(10).join(rows), encoding="utf-8")
        answer = work / "answer.txt"

        probe = work / "ReforgeProbe.java"
        probe.write_text(PROBE, encoding="utf-8")
        out = work / "classes"
        out.mkdir()
        build = subprocess.run(
            [javac, "-encoding", "UTF-8", "-nowarn", "-cp", ";".join(cp),
             "-d", str(out), str(SOURCE), str(probe)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            print("СЛОМАНО: Reforge.java не компилируется")
            print(build.stderr[:1500])
            return 1
        run = subprocess.run(
            [java, "-Dstdout.encoding=UTF-8", "-cp", ";".join([str(out)] + cp),
             "ru.skyblockru.core.ReforgeProbe", str(task), str(answer)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode != 0:
            print("СЛОМАНО: проверка не запустилась")
            print(run.stderr[:1500])
            return 1
        produced = answer.read_text(encoding="utf-8")

    got = [row for row in produced.splitlines() if row.strip()]
    if len(got) != len(CASES):
        print(f"СЛОМАНО: ждали {len(CASES)} ответов, получили {len(got)}")
        print(produced[:600])
        return 1

    bad = 0
    for (title, reforged, want, why), have in zip(CASES, got):
        real = None if have == "~" else have
        if real == want:
            continue
        bad += 1
        print(f"  СЛОМАНО: {title!r} (NBT: {'перекована' if reforged else 'молчит'})")
        print(f"     ждали: {want!r}")
        print(f"     вышло: {real!r}")
        print(f"     {why}")

    if bad:
        print(f"названия перековок: СЛОМАНО {bad} из {len(CASES)}")
        return 1
    print(f"названия перековок: {len(CASES)} случаев обоих краёв — все верны")
    return 0


if __name__ == "__main__":
    sys.exit(main())
