# -*- coding: utf-8 -*-
"""
Абзацный путь ЦЕЛИКОМ — настоящей Java, без игры.

    python tools/check_paragraph_path.py

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ СТОРОЖ, когда есть check_paragraph_colors. Тот проверяет
РАСКЛАДКУ (`ParagraphColors`) — одну деталь пути. А беда 27.08 сидела
в СВЯЗКЕ: каждая часть по отдельности давала верный цвет, а на экране
«Green Candy x16» выходило фиолетовым (14 подсказок, нашёл игрок глазами).

Причина оказалась в механике ПРИПИСКИ: она собиралась как
`LegacyText.parse(хвост, lines.get(to-1).getStyle())`, а `getStyle()` отдаёт
стиль КОРНЯ компонента — цвета же лежат на КУСКАХ. У строки
«[green Green Candy][dark_gray x16]» корень пуст, и два цветных куска
схлопывались в один, цвета корня. А корень у Hypixel несёт цвет РЕДКОСТИ
предмета — отсюда фиолетовый.

⚠️ Раньше такое мог найти только игрок: путь брал шрифт у Minecraft и без
игры не запускался. Теперь `Paragraphs.applyWith` принимает мерку ширины
функцией, и весь путь гоняется здесь.

СВОЙСТВО, которое проверяется: цвет куска, уцелевшего в переводе ДОСЛОВНО,
обязан остаться прежним. Число, английское имя, счётчик — они переживают
перевод как есть, и терять их цвет мод не имеет права.
"""
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ROOT / "versions" / "26.2" / "build" / "classes" / "java" / "main"
RESOURCES = ROOT / "src" / "main" / "resources"

JAVA_SRC = r'''
import ru.skyblockru.core.*;
import ru.skyblockru.config.RuConfig;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.*;
import java.nio.file.*;
import java.util.*;

public class ParagraphPathRun {
    static int bad = 0;
    static StringBuilder out = new StringBuilder();

    static MutableComponent piece(String text, ChatFormatting color) {
        return Component.literal(text).withStyle(color);
    }

    /** Строка подсказки: куски со своими цветами и КОРЕНЬ со своим. */
    static Component row(ChatFormatting root, MutableComponent... parts) {
        MutableComponent line = root == null
                ? Component.literal("") : Component.literal("").withStyle(root);
        for (MutableComponent p : parts) {
            line.append(p);
        }
        return line;
    }

    static String render(List<Component> lines) {
        StringBuilder sb = new StringBuilder();
        for (Component c : lines) {
            c.visit((style, text) -> {
                if (!text.isEmpty()) {
                    sb.append(style.getColor() == null ? "-" : style.getColor().serialize())
                      .append(":").append(text).append("|");
                }
                return Optional.empty();
            }, Style.EMPTY);
            sb.append("\n");
        }
        return sb.toString();
    }

    static void check(String title, List<Component> lines, String item, String[] mustKeep) {
        List<Component> copy = new ArrayList<>(lines);
        Paragraphs.applyWith(copy, "item_lore", item,
                new Paragraphs.Widths(c -> c.getString().length() * 6, t -> t.length() * 6));
        String shown = render(copy);
        List<String> lost = new ArrayList<>();
        for (String want : mustKeep) {
            if (!shown.contains(want)) {
                lost.add(want);
            }
        }
        if (lost.isEmpty()) {
            out.append("  [ok]   ").append(title).append("\n");
        } else {
            bad++;
            out.append("  [СЛОМАНО] ").append(title).append("\n");
            out.append("      потеряно: ").append(lost).append("\n");
            out.append("      вышло:\n");
            for (String s : shown.split("\n")) {
                out.append("        ").append(s).append("\n");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        RuConfig.get().language = "ru_ru";
        RuConfig.get().onlyOnHypixel = false;
        RuConfig.get().onlySkyBlock = false;
        Translator.reload(Path.of(args[0]));

        // ⚠️ ЖИВОЙ СЛУЧАЙ, ради которого сторож и написан. Подсказка торговца:
        // «Cost» серым, товар зелёным, счётчик тусклым. Мод принимал вторую
        // строку за ПРИПИСКУ и красил её цветом КОРНЯ — то есть цветом редкости.
        for (ChatFormatting root : new ChatFormatting[] {
                null, ChatFormatting.DARK_PURPLE, ChatFormatting.RED }) {
            check("витрина торговца, корень строки = "
                            + (root == null ? "без цвета" : root.toString()),
                    List.of(
                            piece("Cost", ChatFormatting.GRAY),
                            row(root, piece("Green Candy ", ChatFormatting.GREEN),
                                    piece("x16", ChatFormatting.DARK_GRAY))),
                    null,
                    new String[] { "green:Green Candy", "dark_gray:" });
        }

        // ⚠️ ПОДПИСЬ И ЗНАЧЕНИЕ НЕ РАЗЛУЧАТЬ. Признак приписки — «хвост иного
        // цвета до конца строки», и у пары «подпись: значение» под него
        // подходит САМО ЗНАЧЕНИЕ: Hypixel красит его отдельно всегда.
        // На экране выходило «Коллекция:» / «Potato VI» двумя строками,
        // хотя у Hypixel это одна.
        check("подпись и значение остаются вместе",
                List.of(
                        piece("Scroll crafted from recipe!", ChatFormatting.RED),
                        row(null, piece("Collection: ", ChatFormatting.GRAY),
                                piece("Potato VI", ChatFormatting.GREEN))),
                null,
                new String[] { "gray:Коллекция:|green: Potato VI" });

        // ⚠️ ОБРАТНЫЙ КРАЙ: НАСТОЯЩАЯ приписка обязана остаться отдельной
        // строкой и сохранить свой тусклый цвет. Без этого случая починка
        // «не терять цвет» могла бы просто отменить отделение приписки.
        check("настоящая приписка тусклым цветом",
                List.of(
                        piece("Consume this item to unlock", ChatFormatting.GRAY),
                        piece("a new pet slot!", ChatFormatting.GRAY),
                        piece("This is permanent!", ChatFormatting.DARK_GRAY)),
                null,
                new String[] { "dark_gray:" });

        System.out.print(out);
        System.out.println(bad == 0
                ? "\nСЛОМАНО: 0 — цвета уцелевших кусков не теряются"
                : "\nСЛОМАНО: " + bad);
        Files.writeString(Path.of(args[1]), String.valueOf(bad));
    }
}
'''


def classpath() -> list[str] | None:
    import check_click_events as helper
    cp = helper.classpath()
    if cp is None:
        return None
    # ⚠️ NETTY нужен: путь трогает сериализацию чата через «@ключи».
    root = Path.home() / ".gradle" / "caches" / "modules-2" / "files-2.1" / "io.netty"
    for jar in sorted(root.rglob("*.jar")):
        if "sources" not in jar.name and "javadoc" not in jar.name:
            cp.append(str(jar))
    return cp


def main() -> int:
    cp = classpath()
    if cp is None:
        print("нет классов игры — сперва сборка")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "ParagraphPathRun.java").write_text(JAVA_SRC, encoding="utf-8")
        full = [str(CLASSES), str(RESOURCES), *cp]
        sep = ";" if sys.platform == "win32" else ":"
        rc = subprocess.run(
            ["javac", "-encoding", "UTF-8", "-cp", sep.join(full),
             "-d", str(tmp), str(tmp / "ParagraphPathRun.java")],
            capture_output=True, text=True)
        if rc.returncode != 0:
            print(rc.stderr[-2000:])
            return 1
        result = tmp / "bad.txt"
        rc = subprocess.run(
            ["java", "-Dstdout.encoding=UTF-8", "-cp", sep.join([str(tmp), *full]),
             "ParagraphPathRun", str(RESOURCES), str(result)],
            capture_output=True, text=True, encoding="utf-8")
        print(rc.stdout)
        if rc.returncode != 0:
            print(rc.stderr[-1000:])
            return 1
        bad = int(result.read_text(encoding="utf-8").strip() or 0)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
