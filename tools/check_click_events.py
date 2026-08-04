"""
Не путает ли перевод КНОПКИ: у каждой ли остаётся СВОЯ команда.

Самая дорогая беда проекта была не про текст, а про игру: нажимаешь «Не-а»,
а NPC продолжает рассказывать. У набора вариантов ответа у КАЖДОЙ кнопки свой
clickEvent, а перевод собирал строку заново из ПЛОСКОГО текста — структура
кусков терялась, и событие вешалось ОДНО на всю строку. Любая кнопка выполняла
команду первого варианта.

⚠️ Заметить это по экрану НЕЛЬЗЯ: текст переведён, кнопки на месте, цвет верный.
Нашёл игрок поведением — дважды отказался от разговора и дважды получил
продолжение. Ни один сторож проекта такого не ловил: все смотрят текст и цвет.

Здесь проверяется само свойство: после перевода каждый кусок текста обязан
сохранить СВОЮ команду. Гоняем настоящей Java по классам мода и jar игры,
без запуска Minecraft.

⚠️ Проверка идёт ОБОИМИ краями. Мало убедиться, что живой путь хорош, — надо
показать, что критерий отличает хорошее от плохого. Поэтому второй прогон
имитирует старую поломку (плоский текст + первое событие на всю строку),
и сторож ОБЯЗАН на нём покраснеть. Иначе «сторож молчит» и «сторож работает»
неотличимы — на этом проект уже обжигался.

Запуск:
  python tools/check_click_events.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ROOT / "versions" / "26.2" / "build" / "classes" / "java" / "main"
RESOURCES = ROOT / "src" / "main" / "resources"
GRADLE = Path.home() / ".gradle" / "caches"
LOOM_JAR = (GRADLE / "fabric-loom" / "minecraftMaven" / "net" / "minecraft"
            / "minecraft-merged-deobf" / "26.2" / "minecraft-merged-deobf-26.2.jar")

# Строки нарочно вымышленные: так проверка не зависит от того, что лежит
# в настоящих словарях, и не сломается от их пополнения.
DICT = {
    "id": "zz-click-test",
    "priority": 1,
    "exact": {
        "[ZZ-YES]": "[ДА]",
        "[ZZ-NO]": "[НЕТ]",
        "[ZZ-MORE]": "[ПОДРОБНЕЕ]",
        "ZZ single line": "Одна строка",
    },
}

# Что обязано выйти: команда -> текст при ней.
EXPECT = {
    "all": {"/zz 1": "[ДА]", "/zz 2": "[НЕТ]", "/zz 3": "[ПОДРОБНЕЕ]"},
    # Не перевелось ничего — отдаём оригинал: английская кнопка, которая
    # работает, лучше русской, которая врёт.
    "none": {"/zz a": "[ZZ-UNKNOWN-A]", "/zz b": "[ZZ-UNKNOWN-B]"},
    "part": {"/zz 1": "[ДА]", "/zz b": "[ZZ-UNKNOWN-B]"},
    "single": {"/zz one": "Одна строка"},
}

RUNNER = """
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;
import ru.skyblockru.core.Translator;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/** Гоняет настоящий путь перевода и печатает пары «текст куска -> его команда». */
public final class ClickRun {

    static MutableComponent button(String text, String command) {
        return Component.literal(text)
                .setStyle(Style.EMPTY.withClickEvent(new ClickEvent.RunCommand(command)));
    }

    static Component choices(String[][] items) {
        MutableComponent root = Component.empty();
        for (int i = 0; i < items.length; i++) {
            if (i > 0) {
                root.append(Component.literal(" "));
            }
            root.append(button(items[i][0], items[i][1]));
        }
        return root;
    }

    static List<String[]> pairs(Component source) {
        List<String[]> out = new ArrayList<>();
        source.visit((style, text) -> {
            if (!text.isEmpty()) {
                ClickEvent event = style.getClickEvent();
                String command = (event instanceof ClickEvent.RunCommand run) ? run.command() : "";
                out.add(new String[]{text, command});
            }
            return Optional.empty();
        }, Style.EMPTY);
        return out;
    }

    /** Старая поломка: плоский текст и ПЕРВОЕ событие на всю строку. */
    static Component brokenWay(Component source) {
        Style[] first = {Style.EMPTY};
        source.visit((style, text) -> {
            if (style.getClickEvent() != null && first[0].getClickEvent() == null) {
                first[0] = style;
            }
            return Optional.empty();
        }, Style.EMPTY);
        Component real = TextTranslator.translate(source, TextTranslator.SRC_CHAT, null);
        return Component.literal(real.getString()).setStyle(first[0]);
    }

    static void emit(String name, String mode, Component source) {
        Component result = "broken".equals(mode)
                ? brokenWay(source)
                : TextTranslator.translate(source, TextTranslator.SRC_CHAT, null);
        for (String[] pair : pairs(result)) {
            System.out.println(name + "\\t" + pair[0] + "\\t" + pair[1]);
        }
    }

    public static void main(String[] args) {
        // Сбор непереведённого тянет клиент Minecraft, которого вне игры нет.
        // Выключаем — record() выходит по первому же условию.
        RuConfig.get().dumpUntranslated = false;
        // ⚠️ Язык задаём ЯВНО. Иначе Translator пойдёт спрашивать язык клиента
        // через FabricLoader.getInstance(), а тот вне игры инициализируется
        // всерьёз и тянет ASM. С заданным языком выбор кончается на конфиге
        // (Translator:536-541) — и тест заодно перестаёт зависеть от того,
        // на каком языке запущена игра.
        RuConfig.get().language = "ru_ru";
        // ⚠️ Оба флага снимаем НЕ ради удобства: Hypixel.isActive() при
        // onlyOnHypixel зовёт Minecraft.getInstance(), а загрузка этого класса
        // тянет netty и половину игры. Короткое замыкание && оставляет клиент
        // нетронутым, а onlySkyBlock=false возвращает true сразу.
        RuConfig.get().onlyOnHypixel = false;
        RuConfig.get().onlySkyBlock = false;
        Translator.reload(Path.of(args[0]));
        String mode = args[1];

        emit("all", mode, choices(new String[][]{
                {"[ZZ-YES]", "/zz 1"}, {"[ZZ-NO]", "/zz 2"}, {"[ZZ-MORE]", "/zz 3"}}));
        emit("none", mode, choices(new String[][]{
                {"[ZZ-UNKNOWN-A]", "/zz a"}, {"[ZZ-UNKNOWN-B]", "/zz b"}}));
        emit("part", mode, choices(new String[][]{
                {"[ZZ-YES]", "/zz 1"}, {"[ZZ-UNKNOWN-B]", "/zz b"}}));
        emit("single", mode, button("ZZ single line", "/zz one"));
    }
}
"""


def find_java(name: str) -> str | None:
    for base in (Path("C:/Program Files/Java"), Path("C:/Program Files/Eclipse Adoptium")):
        if base.exists():
            for path in sorted(base.glob(f"jdk*/bin/{name}.exe"), reverse=True):
                return str(path)
    return None


def newest(pattern: str) -> Path | None:
    """Самый свежий jar по маске.

    ⚠️ Рядом лежат «-sources» и «-javadoc», и под маску они подходят: имя
    начинается так же. Классов внутри нет, поэтому компиляция проходит,
    а запуск падает с NoClassDefFoundError — то есть промах молчит до рантайма.
    """
    found = [p for p in GRADLE.glob(pattern)
             if not p.stem.endswith(("-sources", "-javadoc"))]
    return sorted(found, reverse=True)[0] if found else None


def classpath() -> list[str] | None:
    """Классы мода, ресурсы и то, на чём стоит Component.

    ⚠️ brigadier тут не для команд: Component наследует его Message, и без
    этого jar не компилируется даже Component.literal.
    """
    # ⚠️ Список НЕ произвольный: это то, без чего не строится Component.
    # Собирался по одной ошибке за прогон, поэтому записан явно — чтобы
    # следующая такая проверка не собирала его заново.
    #   brigadier   Component наследует его Message (иначе не компилируется)
    #   fastutil    статика PlainTextContents строит Codec -> Object2ObjectArrayMap
    #   guava       MutableComponent.create зовёт Lists
    #   dfu         кодеки текста
    #   loader      Translator тянет SkyblockRuClient, а тот ClientModInitializer
    needed = {
        "gson": "modules-2/files-2.1/com.google.code.gson/gson/*/*/gson-[0-9]*.jar",
        "slf4j": "modules-2/files-2.1/org.slf4j/slf4j-api/*/*/slf4j-api-[0-9]*.jar",
        "fabric-loader": "modules-2/files-2.1/net.fabricmc/fabric-loader/*/*/fabric-loader-[0-9]*.jar",
        "brigadier": "modules-2/files-2.1/com.mojang/brigadier/*/*/brigadier-[0-9]*.jar",
        "datafixerupper": "modules-2/files-2.1/com.mojang/datafixerupper/*/*/datafixerupper-[0-9]*.jar",
        "fastutil": "modules-2/files-2.1/it.unimi.dsi/fastutil/*/*/fastutil-[0-9]*.jar",
        "guava": "modules-2/files-2.1/com.google.guava/guava/*/*/guava-[0-9]*.jar",
        # joml — из-за кодека ClickEvent: у него в статике общий Codec игры.
        "joml": "modules-2/files-2.1/org.joml/joml/*/*/joml-[0-9]*.jar",
    }
    # Необязательные: их тянет статика кодеков игры. Список может расти
    # с версией Minecraft, поэтому отсутствие любого НЕ останавливает —
    # иначе проверка ломалась бы от обновления игры, а не от нашей ошибки.
    extra = {
        "commons-lang3": "modules-2/files-2.1/org.apache.commons/commons-lang3/*/*/commons-lang3-[0-9]*.jar",
        "commons-io": "modules-2/files-2.1/commons-io/commons-io/*/*/commons-io-[0-9]*.jar",
        "authlib": "modules-2/files-2.1/com.mojang/authlib/*/*/authlib-[0-9]*.jar",
        "mojang-logging": "modules-2/files-2.1/com.mojang/logging/*/*/logging-[0-9]*.jar",
        "log4j-api": "modules-2/files-2.1/org.apache.logging.log4j/log4j-api/*/*/log4j-api-[0-9]*.jar",
    }
    jars = {name: newest(pattern) for name, pattern in needed.items()}
    for name, pattern in extra.items():
        found = newest(pattern)
        if found is not None:
            jars[name] = found
    missing = [name for name, path in jars.items() if path is None]
    if not LOOM_JAR.exists():
        missing.append("jar игры")
    if not CLASSES.exists():
        missing.append("классы мода")
    if missing:
        print("не нашёл: " + ", ".join(missing))
        if not CLASSES.exists():
            print("сперва собери мод: python tools/build_all.py")
        return None
    return [str(CLASSES), str(RESOURCES), str(LOOM_JAR)] + [str(p) for p in jars.values()]


def run(java: str, cp: list[str], out: Path, packs: Path, mode: str) -> dict[str, dict[str, str]]:
    """Прогон одного режима: разбирает вывод в {случай: {команда: текст}}."""
    # ⚠️ stdout.encoding задаём ЯВНО: с Java 18 file.encoding уже UTF-8,
    # а консольный вывод остаётся в системной кодировке — русский текст
    # приходил битым («[??]» вместо «[ДА]»), и сверка падала на ровном месте.
    proc = subprocess.run(
        [java, "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8",
         "-cp", ";".join([str(out)] + cp), "ClickRun", str(packs), mode],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print(f"прогон «{mode}» не запустился:")
        print((proc.stderr or proc.stdout).strip()[:1500])
        return {}
    got: dict[str, dict[str, str]] = {}
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        case, text, command = parts
        if not command:
            continue  # пробел между кнопками — своей команды у него нет
        # Кусок мог разбиться на части: собираем текст одной команды целиком.
        got.setdefault(case, {})
        got[case][command] = got[case].get(command, "") + text
    return got


def compare(got: dict[str, dict[str, str]]) -> list[str]:
    """Чем результат разошёлся с ожиданием. Пусто — всё сошлось."""
    problems = []
    for case, expect in EXPECT.items():
        actual = got.get(case, {})
        if len(actual) != len(expect):
            problems.append(f"{case}: команд {len(actual)}, а должно {len(expect)}"
                            f" — кнопки слиплись или потерялись")
            continue
        for command, text in expect.items():
            if command not in actual:
                problems.append(f"{case}: пропала команда {command}")
            elif actual[command].strip() != text:
                problems.append(f"{case}: у команды {command} текст "
                                f"«{actual[command].strip()}», а должен «{text}»")
    return problems


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    javac, java = find_java("javac"), find_java("java")
    if not javac or not java:
        print("не нашёл JDK — без него проверять нечем")
        return 1
    cp = classpath()
    if cp is None:
        return 1

    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        packs = out / "packs"
        packs.mkdir()
        (packs / "99-zz-click-test.json").write_text(
            json.dumps(DICT, ensure_ascii=False), encoding="utf-8")
        (out / "ClickRun.java").write_text(RUNNER, encoding="utf-8")

        build = subprocess.run(
            [javac, "-cp", ";".join(cp), "-d", str(out), str(out / "ClickRun.java")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            print("проверка не компилируется:")
            print(build.stderr.strip()[:2000])
            return 1

        live = run(java, cp, out, packs, "real")
        if not live:
            return 1
        problems = compare(live)

        # ⚠️ Второй край: критерий обязан ЛОВИТЬ старую поломку.
        broken = run(java, cp, out, packs, "broken")
        caught = compare(broken) if broken else ["прогон не состоялся"]

    print("=== ЖИВОЙ ПУТЬ ===")
    for case, expect in EXPECT.items():
        actual = live.get(case, {})
        print(f"  {case}: кнопок {len(actual)} из {len(expect)}")
    if problems:
        print(f"\n=== СЛОМАНО: {len(problems)} ===")
        for problem in problems:
            print(f"  {problem}")
    else:
        print("\n  у каждой кнопки своя команда — перевод их не путает")

    print("\n=== ПОДСАДКА ПОЛОМКИ (сторож обязан поймать) ===")
    if caught:
        print(f"  поймано: {len(caught)} — проверка не слепая")
    else:
        print("  ⚠️ НЕ ПОЙМАНО: критерий не отличает сломанное от целого,")
        print("     значит зелёный ответ этой проверки ничего не значит")

    return 1 if problems or not caught else 0


if __name__ == "__main__":
    raise SystemExit(main())
