# -*- coding: utf-8 -*-
"""
Имя предмета: переводится ли оно ПОСЛЕ переезда из миксина в подсказку.

03.09 перехват `ItemStack.getHoverName` снят: подменённое имя доставалось
ВСЕМ, кто спрашивает игру, и у SkyHanni гасла подсветка нажатых карточек
в Superpairs (`SuperPairsItemVisibility` ищет в имени английские «?» и
«Click any button!»). Логика переехала в `core/ItemName`, а зовётся
из первой строки подсказки.

Правка снимает беду у соседей — но могла бы снять и сам перевод. Здесь
проверяется, что имя по-прежнему переводится: гоняем НАСТОЯЩУЮ Java
по классам мода и jar игры, без запуска Minecraft.

⚠️ ОБОИМИ КРАЯМИ. Мало показать, что знакомое имя переводится, — надо
показать, что незнакомое остаётся нетронутым. Иначе «переводит всё подряд»
и «работает» неотличимы.

Запуск:
  python tools/check_item_name.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ⚠️ classpath и поиск java берём у соседа, копии не заводим: список
# собирался по одной ошибке за прогон, и вторая копия разошлась бы с ним
# при первом же обновлении игры.
import check_click_events as sibling  # noqa: E402

# Строки вымышленные: проверка не должна зависеть от содержимого словарей.
DICT = {
    "id": "zz-item-name-test",
    "priority": 1,
    "exact": {"ZZ Test Blade": "Тестовый клинок ZZ"},
}

CASES = [
    ("known", "ZZ Test Blade", "Тестовый клинок ZZ"),
    # ⚠️ ОБРАТНЫЙ КРАЙ: незнакомое имя не трогаем вовсе. Именно на этом
    # держится починка соседей — что мы не сочиняем перевод там, где его нет.
    ("unknown", "ZZ Unknown Thing", "ZZ Unknown Thing"),
    # ⚠️⚠️ А ВОТ ЭТО НЕ ОШИБКА, И ОЖИДАНИЕ ЗДЕСЬ БЫЛО НЕВЕРНЫМ У МЕНЯ.
    # «Click any button!» — имя НЕОТКРЫТОЙ карточки Superpairs, и по нему
    # SkyHanni отличает нажатую от ненажатой. Перевод у нас ЕСТЬ, и он
    # правильный: на ЭКРАНЕ игрок обязан видеть русский текст.
    #
    # Соседа спасает не отказ от перевода, а МЕСТО перевода: он читает
    # `ItemStack.getHoverName()`, которую мы больше не перехватываем, и
    # получает оригинал, пока подсказка показывает русское. Проверяет это
    # `check_neighbours` (запрещённая цель) — здесь достаточно убедиться,
    # что путь перевода жив.
    ("superpairs-card", "Click any button!", "Нажми на любую кнопку"),
    # знак неоткрытой карточки: словарь его не знает, трогать нечего
    ("skyhanni-hidden", "?", "?"),
]

RUNNER = """
import net.minecraft.network.chat.Component;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.ItemName;
import ru.skyblockru.core.Translator;

import java.nio.file.Path;

public final class NameRun {
    public static void main(String[] args) {
        RuConfig.get().dumpUntranslated = false;
        RuConfig.get().language = "ru_ru";
        RuConfig.get().onlyOnHypixel = false;
        RuConfig.get().onlySkyBlock = false;
        Translator.reload(Path.of(args[0]));
        for (int i = 1; i < args.length; i++) {
            Component original = Component.literal(args[i]);
            // stack = null: сборка перекованного имени требует NBT, а её
            // проверяет check_reforges. Здесь важен сам путь перевода.
            Component got = ItemName.translate(null, original);
            String text = (got == null ? original : got).getString();
            System.out.println(args[i] + "\t" + text);
        }
    }
}
"""


def main() -> int:
    paths = sibling.classpath()
    if paths is None:
        print("нет classpath — сперва: gradlew :26.2:build")
        return 0
    javac = sibling.find_java("javac")
    java = sibling.find_java("java")
    if not javac or not java:
        print("не нашёл JDK")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        packs = work / "packs" / "ru_ru"
        packs.mkdir(parents=True)
        (packs / "zz-item-name.json").write_text(
            json.dumps(DICT, ensure_ascii=False), encoding="utf-8")
        (work / "packs" / "index.json").write_text(
            json.dumps({"languages": {"ru_ru": ["zz-item-name.json"]}},
                       ensure_ascii=False), encoding="utf-8")
        source = work / "NameRun.java"
        source.write_text(RUNNER, encoding="utf-8")
        sep = ";" if sys.platform == "win32" else ":"
        cp = sep.join(paths)
        build = subprocess.run([javac, "-encoding", "UTF-8", "-cp", cp,
                                "-d", str(work), str(source)],
                               capture_output=True, text=True)
        if build.returncode:
            print("не собралось:")
            print(build.stdout[-1500:])
            print(build.stderr[-1500:])
            return 1
        run = subprocess.run(
            [java, "-Dstdout.encoding=UTF-8", "-cp", cp + sep + str(work),
             "NameRun", str(work / "packs"), *[c[1] for c in CASES]],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode:
            print("не запустилось:")
            print((run.stderr or "")[-1500:])
            return 1
        got = {}
        for line in (run.stdout or "").splitlines():
            if "	" in line:
                key, value = line.split("	", 1)
                got[key] = value

    broken = 0
    for name, source_text, want in CASES:
        value = got.get(source_text)
        ok = value == want
        broken += not ok
        print(f"  {'ok ' if ok else 'СЛОМАНО'} [{name:16}] {source_text!r} -> {value!r}")
        if not ok:
            print(f"        ждали: {want!r}")
    print()
    if broken:
        print(f"=== СЛОМАНО: {broken} ===")
        print("  Перевод имени переехал в подсказку (core/ItemName) — проверь,")
        print("  зовётся ли он из TextHooks.translateTooltip для первой строки.")
        return 1
    # ⚠️ Вторая половина доказательства: перевод должен идти ЧЕРЕЗ ПОДСКАЗКУ,
    # а не через перехват метода. Смотрим СОБРАННЫЙ jar, а не исходники:
    # игроку уезжает он.
    import zipfile
    # ⚠️ САМЫЙ СВЕЖИЙ ПО ВРЕМЕНИ, а не по имени: рядом лежат 22 сборки, и
    # по алфавиту «0.2.9» идёт ПОСЛЕ «0.2.28». Записанная грабля проекта —
    # этот же сторож на ней и попался, взяв jar месячной давности.
    jars = sorted((ROOT / "versions" / "26.2" / "build" / "libs").glob("*.jar"),
                  key=lambda f: f.stat().st_mtime)
    if jars:
        with zipfile.ZipFile(jars[-1]) as jar:
            names = jar.namelist()
            mixin = [n for n in names if "ItemStackMixin" in n]
            declared = json.loads(jar.read("skyblockru.mixins.json").decode("utf-8"))
            listed = [m for m in declared.get("client", []) + declared.get("mixins", [])
                      if "ItemStack" in m]
        if mixin or listed:
            print(f"=== СЛОМАНО: в jar вернулся перехват имени: {mixin or listed} ===")
            return 1
        print(f"  jar {jars[-1].name}: миксина на ItemStack нет")
    print("ок: имя переводится, а соседям достаётся оригинал")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
