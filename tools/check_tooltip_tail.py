# -*- coding: utf-8 -*-
"""
Где мод отрезает ХВОСТ ЧУЖИХ МОДОВ у подсказки предмета — настоящей Java,
без игры.

⚠️ Зачем. REI/EMI дописывают в конец подсказки «Minecraft», клиент при F3+H —
идентификатор и число компонентов, NEU — цены. Пустой строкой они от лора
не отделены, и `Paragraphs.runs` приклеивал их к последнему абзацу: ключ
не находился, и действия питомца («Left-click to summon!…») оставались
английскими у всех, у кого стоит REI. Прислано игроком скриншотом 03.09.

`core/TooltipTail` находит границу ПО ЛОРУ предмета: всё после последней
строки лора прислал не Hypixel. Проверяем оба края:
  * хвост ОБЯЗАН отрезаться — иначе беда вернётся молча;
  * без лора, при переписанной соседом последней строке лора и при
    подсказке без хвоста резать НЕЛЬЗЯ — отрезанная строка Hypixel
    осталась бы без перевода.

Запуск:
  python tools/check_tooltip_tail.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "TooltipTail.java"

LORE_PET = ["Farming Pet", "", "Speed: +12.9", "", "Spiky Quills",
            "Deal 86% more damage to \ue018 Pests.", "",
            "Left-click to summon!", "Shift Left-click to toggle as favorite!",
            "Right-click to convert to an item!"]

# (лор, подсказка, ожидаемый индекс начала хвоста, почему)
CASES = [
    (LORE_PET, ["[Lvl 86] Hedgehog"] + LORE_PET + ["Minecraft"],
     1 + len(LORE_PET), "REI дописал «Minecraft» — хвост из одной строки"),
    (LORE_PET, ["[Lvl 86] Hedgehog"] + LORE_PET
     + ["minecraft:player_head", "skyblock:HEDGEHOG", "3 компонента", "Minecraft"],
     1 + len(LORE_PET), "F3+H, Skyblocker и REI разом — хвост из четырёх строк"),
    (LORE_PET, ["[Lvl 86] Hedgehog"] + LORE_PET,
     1 + len(LORE_PET), "хвоста нет — граница в самом конце, резать нечего"),
    ([], ["[Lvl 86] Hedgehog", "Minecraft"], 2,
     "лора у предмета нет — границы нет, НЕ режем"),
    (LORE_PET, ["[Lvl 86] Hedgehog"] + LORE_PET[:-1]
     + ["Right-click to convert to an item! (edited by SkyHanni)", "Minecraft"],
     1 + len(LORE_PET) + 1, "сосед переписал последнюю строку лора — НЕ режем"),
    (["Line", ""], ["Name", "Line", "Minecraft"], 2,
     "у лора пустая последняя строка — граница по последней НЕПУСТОЙ"),
    (["Only line"], ["Only line"], 1,
     "подсказка из одной строки — ничего не делаем"),
    (["§7Grants §a+5 §7Health."], ["Name", "§7Grants §a+5 §7Health.", "Minecraft"], 2,
     "§-коды в лоре и подсказке совпадают — сравнение дословное"),
    (["RARE"], ["Name", "Cost", "RARE", "Minecraft"], 3,
     "последняя строка лора — редкость, хвост после неё"),
    (["A", "B"], ["Name", "A", "B", "Lowest BIN: 1,000 coins", "Minecraft"], 3,
     "цены NEU и «Minecraft» — режем всё после лора"),
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
    work = Path(tempfile.mkdtemp(prefix="sbru-tail-"))
    try:
        done = subprocess.run([javac, "-encoding", "UTF-8", "-d", str(work), str(SRC)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        if done.returncode != 0:
            print("СЛОМАНО: не компилируется TooltipTail.java (он обязан жить без Minecraft)")
            print(done.stderr[:2000])
            return 1

        def ask(lore: list[str], tooltip: list[str]) -> int:
            payload = "\n".join([str(len(lore))] + lore + tooltip) + "\n"
            answer = subprocess.run(
                [java, "-Dstdout.encoding=UTF-8", "-Dfile.encoding=UTF-8",
                 "-cp", str(work), "ru.skyblockru.core.TooltipTail"],
                input=payload, capture_output=True, text=True,
                encoding="utf-8", errors="replace")
            if answer.returncode != 0:
                raise RuntimeError(answer.stderr[:300])
            return int(answer.stdout.strip())

        bad = 0
        print("=== заведомые случаи ===")
        for lore, tooltip, expected, why in CASES:
            got = ask(lore, tooltip)
            ok = got == expected
            bad += 0 if ok else 1
            print("   %-8s хвост с %2d (ждали %2d)  %s" % ("ок " if ok else "СЛОМАНО", got, expected, why))
        print()
        if bad:
            print(f"СЛОМАНО: {bad} из {len(CASES)}")
            return 1
        print(f"хвост чужих модов: {len(CASES)} случаев обоих краёв, расхождений нет")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
