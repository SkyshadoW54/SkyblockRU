"""
Резка абзаца-СПИСКА по маркерам — настоящей Java, без игры.

Зачем отдельная проверка. Список мод склеивать не станет: пункты размажутся
в сплошную строку («▶ Без фильтра Обычный Необычный Редкий…»), читать это
невозможно. Но при отказе найденный перевод АБЗАЦА раньше выбрасывался совсем,
и на живом корпусе так лежали мёртвым грузом 301 оплаченный перевод — на экране
английский текст, за который заплачено.

Лечится тем же приёмом, что заголовок, приписка и зачарования: режется уже
НАЙДЕННЫЙ перевод (ParagraphColors.listCuts), поэтому ключ абзаца не меняется
и платить заново не нужно. Места разрезов не угадываются — маркер это СИМВОЛ,
и модель переносит его дословно, как иконку.

⚠️ Гоняем на НАСТОЯЩИХ абзацах корпуса, а не на рукотворных случаях. В проекте
это уже стоило дорого: эталоны раскраски пропустили беду в СБОРЕ данных, потому
что в них куски записаны руками и заведомо верны.

Что проверяется:
  1. сколько абзацев разрежется, а сколько нет;
  2. ⚠️ ГЛАВНОЕ: склейка кусков обратно обязана дать ИСХОДНЫЙ перевод знак
     в знак. Резка не смеет ни терять текст, ни добавлять — именно это ломается
     молча, когда позицию считают по длине текста, а не по месту (на этом уже
     обожглись с припиской: «время! Пи» отдельной строкой);
  3. пунктов не должно выйти БОЛЬШЕ, чем строк с маркером в оригинале —
     иначе резка нашла маркер внутри текста и выдумала границу.

Запуск:  python tools/check_list_cuts.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

CORPUS = ROOT / "data" / "work" / "paragraphs.json"
CORE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core"
SRC = CORE / "ParagraphColors.java"
LAYOUT = CORE / "ColorLayout.java"

MARK_SEP = "\u0001"

# ⚠️ Отбор маркеров делает ТА ЖЕ Java, что и мод: ColorLayout.repeatedMarker.
# Переписать его на Python значило бы завести копию признака, а копии в этом
# проекте расходятся молча — на том и стоит check_contract.py. Здесь копии нет:
# и знак, и резку считает настоящий движок, Python только сверяет результат.
#
# Нужно это не для красоты. markersOf считает маркером ЛЮБОЙ не-буквенный знак,
# поэтому в маркеры попадают «{» от дырки «{n}» и «(» от скобки; резка по ним
# разложила бы пункты по случайным местам. Проверка это и поймала.
RUNNER = '''
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import ru.skyblockru.core.ColorLayout;
import ru.skyblockru.core.ParagraphColors;

public class ListRun {
	public static void main(String[] args) throws Exception {
		for (String line : Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8)) {
			if (line.isBlank()) continue;
			String[] parts = line.split("\\t", -1);
			String translated = parts[0];
			List<String> marks = new ArrayList<>();
			if (parts.length > 1 && !parts[1].isEmpty()) {
				for (String mark : parts[1].split("\\u0001", -1)) {
					marks.add(mark);
				}
			}
			String mark = ColorLayout.repeatedMarker(marks);
			if (mark != null && !ColorLayout.cutMark(mark)) {
				mark = null;
			}
			StringBuilder out = new StringBuilder();
			// ⚠️ Печатаем КОД знака, а не сам знак: значки Hypixel живут
			// в приватной зоне юникода, и в консоли Windows они превращаются
			// в «?» — проверка начинала ругаться на собственный вывод.
			out.append(mark == null ? "" : String.valueOf(mark.codePointAt(0)));
			if (mark != null) {
				List<String> only = new ArrayList<>();
				for (String one : marks) {
					only.add(mark.equals(one) ? mark : "");
				}
				for (Integer at : ParagraphColors.listCuts(translated, only)) {
					out.append("\\u0001").append(at);
				}
			}
			System.out.println(out);
		}
	}
}
'''


def find_java(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for base in (Path("C:/Program Files/Java"), Path("C:/Program Files/Eclipse Adoptium")):
        if not base.exists():
            continue
        for path in sorted(base.glob(f"*/bin/{name}.exe"), reverse=True):
            return str(path)
    return None


def marker_of(line: str) -> str:
    """
    Знак в начале строки, если это НЕ буква и не цифра.

    ⚠️ Копия Paragraphs.markersOf, и копия намеренно крошечная: разойдись она —
    просядет счётчик «разрезано», и это будет видно тут же.
    """
    text = line.strip()
    if not text or text[0].isalnum():
        return ""
    return text[0]


def collect() -> list[dict]:
    """Абзацы корпуса, которые мод считает списком: знак повторяется у двух строк."""
    data = json.loads(CORPUS.read_text(encoding="utf-8")).get("paragraphs") or []
    cases: list[dict] = []
    for para in data:
        translated = para.get("ru") or ""
        if not translated:
            continue
        rows = [str(row) for row in (para.get("lines") or []) if str(row).strip()]
        marks = [marker_of(row) for row in rows]
        seen = [m for m in marks if m]
        if not seen:
            continue
        cases.append({
            "item": para.get("item") or "?",
            "translated": translated,
            "rows": rows,
            "marks": marks,
            "marked": len(seen),
        })
    return cases


def run_java(cases: list[dict]) -> list[list[int]] | None:
    javac, java = find_java("javac"), find_java("java")
    if not javac or not java:
        print("не нашёл javac/java — а без них логику проверять нечем")
        return None
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        (work / "ListRun.java").write_text(RUNNER, encoding="utf-8")
        build = subprocess.run(
            [javac, "-encoding", "UTF-8", "-d", str(work), str(SRC), str(LAYOUT),
             str(work / "ListRun.java")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            print("Java не собрала ParagraphColors:")
            print(build.stderr.strip()[:2000])
            return None

        feed = work / "cases.txt"
        feed.write_text("\n".join(
            case["translated"].replace("\t", " ").replace("\n", " ") + "\t"
            + MARK_SEP.join(case["marks"])
            for case in cases), encoding="utf-8")
        done = subprocess.run(
            [java, "-cp", str(work), "ListRun", str(feed)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if done.returncode != 0:
            print("Java упала:")
            print(done.stderr.strip()[:2000])
            return None

    # Первое поле — сам знак списка (его выбрала Java), дальше позиции разрезов.
    out: list[tuple[str, list[int]]] = []
    for line in done.stdout.splitlines():
        parts = line.split(MARK_SEP)
        mark = chr(int(parts[0])) if parts and parts[0].strip() else ""
        out.append((mark, [int(at) for at in parts[1:] if at]))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not CORPUS.exists():
        print("нет корпуса:", CORPUS)
        return 1

    cases = collect()
    print(f"абзацев со списочным знаком: {len(cases)}")
    if not cases:
        return 0

    found = run_java(cases)
    if found is None:
        return 1
    if len(found) != len(cases):
        print(f"СЛОМАНО: Java вернула {len(found)} ответов на {len(cases)} случаев")
        return 1

    cut = 0
    lost: list[tuple[str, str, str]] = []
    extra: list[tuple[str, int, int]] = []
    misplaced: list[tuple[str, int, str, str]] = []
    for case, (mark, cuts) in zip(cases, found):
        if not cuts:
            continue
        cut += 1
        text = case["translated"]

        # ⚠️ ГЛАВНОЕ: склейка обратно = исходный перевод знак в знак.
        pieces = []
        if cuts[0] > 0:
            pieces.append(text[:cuts[0]])
        for i, at in enumerate(cuts):
            to = cuts[i + 1] if i + 1 < len(cuts) else len(text)
            pieces.append(text[at:to])
        if "".join(pieces) != text:
            lost.append((case["item"], text, "".join(pieces)))

        # ⚠️ А вот это условие — главнее, чем кажется, и добавлено после того,
        # как проверка ПРОМОЛЧАЛА на подсаженной поломке. Склейка кусков
        # остаётся непрерывной при ЛЮБОМ сдвиге границ: куски и определяются
        # этими же позициями, поэтому «текст не потерялся» — свойство слишком
        # слабое. Резать надо РОВНО по маркеру, и проверять надо именно это:
        # сдвиг на один знак («◼ Руны» -> «Руны», а «◼» уехало в чужой хвост)
        # прежнюю проверку проходил насквозь.
        for at in cuts:
            piece = text[at:]
            while piece.startswith("§") and len(piece) > 1:
                piece = piece[2:]
            if not piece.startswith(mark):
                misplaced.append((case["item"], at, mark, piece[:40]))
                break

        # Пунктов не больше, чем строк с ЭТИМ знаком: иначе граница выдумана.
        want = sum(1 for m in case["marks"] if m == mark)
        if len(cuts) > want:
            extra.append((case["item"], len(cuts), want))

    print(f"  разрежется: {cut}")
    print(f"  осталось как есть: {len(cases) - cut}")
    print()

    if lost:
        print(f"=== СЛОМАНО: резка изменила текст ({len(lost)}) ===")
        for item, was, now in lost[:5]:
            print(f"  [{item}]")
            print(f"    было: {was[:110]}")
            print(f"    ста : {now[:110]}")
        return 1
    print("склейка кусков обратно совпала с переводом знак в знак — у всех")

    if misplaced:
        print(f"=== СЛОМАНО: разрез пришёлся не на маркер ({len(misplaced)}) ===")
        for item, at, mark, piece in misplaced[:5]:
            print(f"  [{item}] на {at} ждали «{mark}», а кусок начинается: {piece}")
        return 1
    print("каждый разрез пришёлся ровно на маркер")

    if extra:
        print(f"=== СЛОМАНО: пунктов больше, чем строк с маркером ({len(extra)}) ===")
        for item, got, want in extra[:5]:
            print(f"  [{item}] нарезано {got}, а строк с маркером {want}")
        return 1
    print("лишних границ не нашлось")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
