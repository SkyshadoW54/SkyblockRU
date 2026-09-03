"""ШКАЛА не смеет перекраситься при переводе.

Hypixel рисует заполнение ЦВЕТОМ, а не длиной: полоса выборов всегда из десяти
знаков, и сколько набрано, видно по тому, сколько из них окрашено.

    [light_purple "Paul: "] [light_purple "||||||"] [white "|||| "] [white "(54%)"]
                             6 цветных = 54%         4 белых = пусто

⚠️ ПОЧЕМУ ЭТО НЕ ЛОВИЛ НИ ОДИН СТОРОЖ. Все проверки цвета в проекте смотрят,
не ПОТЕРЯЛСЯ ли цвет. А тут он не терялся — он вставал не на своё место:
куски шкалы состоят из ОДИНАКОВЫХ символов, и сопоставление «кусок → место
в переводе» неразрешимо по построению. У Аатрокса 18% выглядели как 100%
(вся полоса красная), у Пола заполненная часть уезжала в конец. Нашёл игрок
скриншотом, сравнив с оригиналом.

Проверяется само свойство: после перевода СТРУКТУРА полосы (цвета и длины
кусков) обязана совпасть с оригиналом Hypixel знак в знак. Имя кандидата при
этом переводится — и это единственное, чему меняться разрешено.

⚠️ Данные НЕ выдуманы: куски берутся из dump/panel-colors.json, куда мод
записал их сам — до перевода и до снятия §-кодов. Это единственный набор,
где известно, как строка выглядела У СЕРВЕРА.

⚠️ Проверка идёт ОБОИМИ краями: второй прогон снимает признак шкалы, и сторож
ОБЯЗАН покраснеть. Иначе «молчит» и «работает» неотличимы.

Запуск:
  python tools/check_scale_bars.py
"""

from __future__ import annotations


import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_click_events as base  # noqa: E402  (общий classpath и поиск java)

# консоль Windows — cp1251: без этого печать значка роняет сторожа
# ровно тогда, когда он НАШЁЛ беду (записанная грабля проекта)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CASES = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/panel-colors.json")
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

RUNNER = r'''
import com.google.gson.*;
import net.minecraft.network.chat.*;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;
import ru.skyblockru.core.Translator;
import java.nio.file.*;
import java.util.*;

public final class ScaleRun {
    static Component build(JsonArray pieces) {
        MutableComponent root = Component.empty();
        for (JsonElement e : pieces) {
            JsonArray pair = e.getAsJsonArray();
            String colour = pair.get(0).getAsString();
            Style st = Style.EMPTY;
            if (!colour.isEmpty()) {
                TextColor c = TextColor.parseColor(colour).result().orElse(null);
                if (c != null) st = st.withColor(c);
            }
            root.append(Component.literal(pair.get(1).getAsString()).setStyle(st));
        }
        return root;
    }

    static String render(Component c) {
        StringBuilder sb = new StringBuilder();
        c.visit((style, text) -> {
            if (!text.isEmpty()) {
                sb.append('[').append(style.getColor() == null ? "-" : style.getColor().serialize())
                  .append(' ').append(text).append(']');
            }
            return Optional.empty();
        }, Style.EMPTY);
        return sb.toString();
    }

    public static void main(String[] args) throws Exception {
        RuConfig.get().dumpUntranslated = false;
        RuConfig.get().language = "ru_ru";
        RuConfig.get().onlyOnHypixel = false;
        RuConfig.get().onlySkyBlock = false;
        // Полосу переводит РЕЖИМНОЕ правило: без full строка остаётся английской,
        // и проверять было бы нечего.
        RuConfig.get().groups.put(Translator.FULL_GROUP, true);
        Translator.reload(Path.of(args[0]));

        JsonObject root = JsonParser.parseString(Files.readString(Path.of(args[1]))).getAsJsonObject();
        for (JsonElement e : root.getAsJsonArray("cases")) {
            JsonObject o = e.getAsJsonObject();
            if (!o.get("key").getAsString().contains("|")) continue;
            Component src = build(o.getAsJsonArray("pieces"));
            Component out = TextTranslator.translate(src, o.get("source").getAsString(), null);
            System.out.println(o.get("key").getAsString() + "\t" + render(src)
                    + "\t" + (out == null ? render(src) : render(out)));
        }
    }
}
'''

PIECE = re.compile(r"\[(\S+) ([^\]]*)\]")


def shape(rendered: str) -> list[tuple[str, int]]:
    """Цвета и ДЛИНЫ кусков, кроме первого.

    Первый кусок — имя кандидата, ему меняться и положено: «Paul: » -> «Пол: ».
    Всё остальное обязано остаться ровно таким, каким прислал сервер.
    """
    return [(colour, len(text)) for colour, text in PIECE.findall(rendered)][1:]


def head_colour(rendered: str) -> str:
    found = PIECE.findall(rendered)
    return found[0][0] if found else ""


def run_java(disable_scale: bool) -> list[tuple[str, str, str]] | None:
    cp = base.classpath()
    javac, java = base.find_java("javac"), base.find_java("java")
    if cp is None or not javac or not java:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "ScaleRun.java").write_text(RUNNER, encoding="utf-8")
        done = subprocess.run([javac, "-encoding", "UTF-8", "-cp", ";".join(cp),
                               "-d", str(work), str(work / "ScaleRun.java")],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        if done.returncode:
            print(done.stdout, done.stderr)
            return None
        args = [java, "-Dstdout.encoding=UTF-8", "-cp", ";".join(cp + [str(work)]),
                "ScaleRun", str(PACKS), str(CASES)]
        if disable_scale:
            args.insert(1, "-Dskyblockru.noscale=1")
        done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        rows = []
        for line in (done.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                rows.append((parts[0], parts[1], parts[2]))
        return rows


def problems(rows: list[tuple[str, str, str]]) -> list[str]:
    bad = []
    for key, before, after in rows:
        if shape(before) != shape(after):
            bad.append(f"{key}\n     Hypixel: {before}\n     мы     : {after}")
        elif head_colour(before) != head_colour(after):
            bad.append(f"{key}: цвет имени {head_colour(before)} -> {head_colour(after)}")
    return bad


def main() -> int:
    if not CASES.exists():
        print(f"нет собранных цветов ({CASES.name}) — проверять нечего, пропускаю")
        return 0
    rows = run_java(disable_scale=False)
    if rows is None:
        print("не собралась проверка — нужен собранный проект и JDK")
        return 0
    if not rows:
        print("в собранных цветах нет ни одной шкалы — проверять нечего")
        return 0

    print(f"полос со шкалой: {len(rows)}")
    bad = problems(rows)
    for line in bad:
        print("   ⚠️ " + line)

    print()
    if bad:
        print(f"СЛОМАНО: {len(bad)} полос перекрашены переводом")
        return 1
    print("СЛОМАНО: 0 — структура полос совпала с оригиналом")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
