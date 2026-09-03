"""
Не отдаём ли мы соседним модам СВОЙ перевод вместо текста Hypixel.

Беда, которую это сторожит. Наши точки перехвата ванильные, поэтому подмена
результата достаётся ВСЕМ, кто спрашивает игру, — не только экрану. 17.08 так
сломался SkyHanni: перевод таба стоял на `PlayerInfo.getTabListDisplayName`,
а он читает таб именно оттуда и ищет там английские заголовки виджетов
(«Info», «Island», «Area:», «Commissions:»). Получая русский текст, он не
находил ничего и ругался игроку: «Extra Information from Tab list not found».
Из 23 его маркеров наш перевод ломал 13.

⚠️ НАЙТИ ЭТО МОЖНО БЫЛО ТОЛЬКО ЧТЕНИЕМ ЧУЖОГО JAR. Ни один наш сторож такого
не ловил: у нас всё работало, потому что SkyHanni у нас не стоял. Этот и
написан, чтобы вопрос задавался сам.

Проверяет ДВЕ вещи, и обе без запуска игры:

  1. ЗАПРЕЩЁННЫЕ ЦЕЛИ — наши миксины не смеют перехватывать методы, которые
     соседи зовут САМИ. Перехват чтения достаётся всем; подменять можно
     только вызов ВНУТРИ отрисовки.
  2. ПОДМЕНА ПОЛЯ БЕЗ ВОЗВРАТА — если мы пишем в чужое поле, к выходу из
     метода оно обязано вернуться к оригиналу. Иначе сосед, прочитавший
     поле позже, получит наш перевод. Так и было с шапкой и подвалом таба:
     у SkyHanni в `TabListData` стоят `field_2153`/`field_2154` — ровно они.

Запуск:
  python tools/check_neighbours.py            проверить
  python tools/check_neighbours.py --jars     заодно поискать в jar соседей,
                                              что они читают из таба
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIXINS = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "mixin"
INSTANCES = Path("C:/MultiMC/instances")

# ⚠️ Методы, которые соседи зовут САМИ. Перехватывать их нельзя: подмена
# достанется им вместо текста Hypixel. Список именной, а не по форме, —
# каждый пункт подтверждён чтением чужого байткода.
FORBIDDEN = {
    "getTabListDisplayName":
        "SkyHanni читает таб через неё (TabListData -> getNameForDisplay -> сюда) "
        "и ищет английские заголовки виджетов",
    "getNameForDisplay":
        "её зовёт TabListData у SkyHanni (method_1918 в его байткоде)",
    "getHoverName":
        "имя предмета читают 115 классов SkyHanni и 72 Skyblocker (замер 03.09 "
        "по их jar). У SkyHanni из-за подмены гасла подсветка нажатых карточек "
        "в Superpairs: SuperPairsItemVisibility ищет в имени английские «?» и "
        "«Click any button!». Переводить имя надо в ПОДСКАЗКЕ (core/ItemName)",
}

# Поля чужих классов, которые соседи читают напрямую. Записав туда перевод,
# обязаны вернуть оригинал к выходу из метода.
WATCHED_FIELDS = {
    "header": "PlayerTabOverlay.header — SkyHanni читает его (field_2153)",
    "footer": "PlayerTabOverlay.footer — SkyHanni читает его (field_2154)",
}

TARGET = re.compile(r'target\s*=\s*"[^"]*?;([A-Za-z0-9_$]+)\(')
METHOD = re.compile(r'method\s*=\s*"([A-Za-z0-9_$<>]+)"')
WRITE = re.compile(r"this\.(\w+)\s*=")


def check_targets() -> list[str]:
    """Перехватываем ли мы то, что соседи зовут сами."""
    bad = []
    for path in sorted(MIXINS.glob("*.java")):
        text = path.read_text(encoding="utf-8")
        # ⚠️ Смотрим ТОЛЬКО аннотации: те же имена стоят в комментариях,
        # где мы как раз объясняем, почему их трогать нельзя.
        for line in text.splitlines():
            if "//" in line:
                line = line[: line.index("//")]
            for name in METHOD.findall(line) + TARGET.findall(line):
                if name not in FORBIDDEN:
                    continue
                # цель ВНУТРИ отрисовки законна: значение уходит на экран,
                # а спросивший игру сам получит оригинал
                if "target =" in line and "ModifyExpressionValue" in text:
                    continue
                bad.append("%s: перехвачена %s — %s"
                           % (path.name, name, FORBIDDEN[name]))
    return bad


def check_fields() -> list[str]:
    """Возвращаем ли чужие поля к оригиналу после отрисовки."""
    bad = []
    for path in sorted(MIXINS.glob("*.java")):
        text = path.read_text(encoding="utf-8")
        for field, why in WATCHED_FIELDS.items():
            if not re.search(r"this\.%s\s*=" % field, text):
                continue
            # ищем восстановление: запись в @At("RETURN")
            tail = text.split('@At("RETURN")')
            restored = any(re.search(r"this\.%s\s*=" % field, part)
                           for part in tail[1:])
            if not restored:
                bad.append("%s: пишем в %s и НЕ возвращаем к оригиналу — %s"
                           % (path.name, field, why))
    return bad


def scan_jars() -> None:
    """Что соседи читают из таба — справочно, по их jar в инстансах."""
    seen = set()
    for jar in INSTANCES.glob("*/.minecraft/mods/*.jar"):
        if "skyblockru" in jar.name.lower() or jar.name in seen:
            continue
        seen.add(jar.name)
        try:
            zf = zipfile.ZipFile(jar)
        except (zipfile.BadZipFile, OSError):
            continue
        hits = []
        for entry in zf.namelist():
            if not entry.endswith(".class"):
                continue
            try:
                data = zf.read(entry)
            except (KeyError, OSError):
                continue
            if b"PlayerTabOverlay" not in data and b"class_640" not in data:
                continue
            marks = [probe.decode() for probe in
                     (b"header", b"footer", b"method_1918",
                      b"getNameForDisplay", b"getTabListDisplayName")
                     if probe in data]
            if marks:
                hits.append((entry.split("/")[-1], marks))
        if hits:
            print("   %s" % jar.name)
            for name, marks in hits[:4]:
                print("      %-46s %s" % (name, ", ".join(marks)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jars", action="store_true",
                        help="показать, что соседи читают из таба")
    args = parser.parse_args()

    bad = check_targets() + check_fields()
    if args.jars:
        print("=== ЧТО СОСЕДИ ЧИТАЮТ ИЗ ТАБА ===")
        scan_jars()
        print()

    if bad:
        print("=== СЛОМАНО: %d ===" % len(bad))
        for row in bad:
            print("   " + row)
        print("\n   Перехватывать надо ВЫЗОВ ВНУТРИ ОТРИСОВКИ, а не сам метод:")
        print("   тогда перевод уходит на экран, а сосед получает текст Hypixel.")
        return 1

    print("чисто: соседям отдаём оригинал")
    print("   проверено целей: %d, полей: %d" % (len(FORBIDDEN), len(WATCHED_FIELDS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
