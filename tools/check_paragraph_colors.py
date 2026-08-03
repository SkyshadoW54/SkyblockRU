"""
Проверка РАСКРАСКИ переведённого абзаца — настоящей Java, без игры.

Зачем. Перенос абзаца красил все получившиеся строки цветом ПЕРВОЙ строки, и на
экране это выглядело так: у питомца «§6Pursuit Повышает шанс поймать Trophy Fish
ступеней GOLD и DIAMOND на 10%.» — всё золотое, подсветка чисел и названий
пропала, заголовок слился с прозой. Проверить раскраску было нечем: дамп §-коды
снимает, цвет живёт стилями компонента и до инструментов не доезжает.

Теперь логика раздачи цветов вынесена в ru.skyblockru.core.ParagraphColors —
класс не знает про Minecraft, значит его можно скомпилировать и прогнать здесь.
На входе куски оригинала (цвет + текст) и готовый перевод, на выходе — куски
перевода с цветами.

Случаи лежат в data/work/paragraph-color-cases.json, каждый пришёл с реального
скриншота. Поле «expect» говорит, что ОБЯЗАНО остаться подсвеченным: правка,
после которой «10%» перестанет быть жёлтым, провалит проверку здесь, а не
на экране игрока.

Запуск:
  python tools/check_paragraph_colors.py
  python tools/check_paragraph_colors.py --all     показать раскладку целиком
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core"
SRC = CORE / "ParagraphColors.java"
# ⚠️ Компилируем ВМЕСТЕ с ColorLayout: `markedHeadEnd` спрашивает у него признак
# маркера списка (`cutMark`), а заводить копию нельзя — знаки списка в этом
# проекте уже расходились молча. Оба файла чистые, Minecraft им не нужен.
DEPS = [CORE / "ColorLayout.java"]
CASES = ROOT / "data" / "work" / "paragraph-color-cases.json"
# Мод пишет сюда живые раскладки абзацев, если игрок уже играл на свежем jar
LIVE = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/paragraph-colors.json")

PIECE_SEP = "\u0002"
FIELD_SEP = "\u0001"

RUNNER = '''
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import ru.skyblockru.core.ParagraphColors;
import ru.skyblockru.core.ParagraphColors.Piece;

public class ParagraphRun {
	public static void main(String[] args) throws Exception {
		for (String line : Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8)) {
			if (line.isBlank()) continue;
			String[] parts = line.split("\\t", -1);
			List<Piece> pieces = new ArrayList<>();
			for (String raw : parts[0].split("\\u0002", -1)) {
				if (raw.isEmpty()) continue;
				String[] pair = raw.split("\\u0001", 2);
				pieces.add(new Piece(pair.length > 1 ? pair[1] : "", pair[0]));
			}
			String translated = parts[1];
			String body = parts[2].isEmpty() ? ParagraphColors.body(pieces) : parts[2];
			// заголовок: отделяем ДО раздачи цветов, как это делает Paragraphs
			String headColor = parts.length > 3 ? parts[3] : "";
			List<String> variants = new ArrayList<>();
			if (parts.length > 4 && !parts[4].isEmpty()) {
				variants = Arrays.asList(parts[4].split("\\u0002", -1));
			}
			int cut = headColor.isEmpty() ? 0
					: ParagraphColors.headerCut(headColor, body, translated, variants);
			String head = cut > 0 ? translated.strip().substring(0, cut) : "";
			if (cut > 0) {
				translated = translated.strip().substring(cut).strip();
			}
			// как переведён каждый цветной кусок: «англ=рус», через \\u0002
			Map<String, String> aliases = new LinkedHashMap<>();
			if (parts.length > 5 && !parts[5].isEmpty()) {
				for (String pair : parts[5].split("\\u0002", -1)) {
					String[] kv = pair.split("\\u0001", 2);
					if (kv.length == 2) {
						aliases.put(kv[0], kv[1]);
					}
				}
			}
			List<Piece> laid = ParagraphColors.layout(pieces, translated, body, aliases);
			StringBuilder out = new StringBuilder();
			for (Piece piece : laid) {
				if (out.length() > 0) out.append("\\u0002");
				out.append(piece.color()).append("\\u0001").append(piece.text());
			}
			// ⚠️ Перенос обязан вернуть РОВНО тот же текст. Ширину берём заведомо
			// огромную, чтобы всё легло в одну строку: тогда расхождение может
			// дать только сама склейка кусков. Так поймался выдуманный пробел
			// перед точкой — «§5Crystal Hollows§7.» выходило «Crystal Hollows .».
			StringBuilder flat = new StringBuilder();
			for (List<Piece> row : ParagraphColors.wrap(laid, 1 << 20, t -> t.length())) {
				for (Piece piece : row) flat.append(piece.text());
			}
			System.out.println(body + "\\t" + ParagraphColors.painted(laid, body)
					+ "\\t" + out + "\\t" + head + "\\t" + flat);
		}
	}
}
'''


def find_java(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for base in (Path("C:/Program Files/Java"), Path("C:/Program Files/Eclipse Adoptium")):
        if base.exists():
            for path in sorted(base.glob(f"jdk*/bin/{name}.exe"), reverse=True):
                return str(path)
    return None


def load_cases() -> list[dict]:
    cases: list[dict] = []
    if CASES.exists():
        cases += json.loads(CASES.read_text(encoding="utf-8")).get("cases") or []
    if LIVE.exists():
        # Живые раскладки из игры: у них нет «expect» — их смотрят глазами,
        # а проверка тут одна: сколько подсветки удалось вернуть.
        for item in json.loads(LIVE.read_text(encoding="utf-8")).get("cases") or []:
            item.setdefault("name", "из игры: " + (item.get("item") or "?"))
            item["_live"] = True
            cases.append(item)
    return cases


def run_java(cases: list[dict]) -> list[tuple[str, int, list[tuple[str, str]]]] | None:
    javac, java = find_java("javac"), find_java("java")
    if not javac or not java:
        print("не нашёл javac/java — а без них логику проверять нечем")
        return None
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        runner = work / "ParagraphRun.java"
        runner.write_text(RUNNER, encoding="utf-8")
        build = subprocess.run(
            [javac, "-encoding", "UTF-8", "-d", str(work), str(SRC),
             *[str(dep) for dep in DEPS], str(runner)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            print("Java не собрала ParagraphColors:")
            print(build.stderr.strip()[:2000])
            return None

        table = work / "cases.tsv"
        rows = []
        for case in cases:
            pieces = PIECE_SEP.join(
                f"{color}{FIELD_SEP}{text}" for color, text in case.get("pieces") or [])
            variants = PIECE_SEP.join(case.get("headVariants") or [])
            # как переведён цветной кусок: цвет вернётся и переведённому слову
            aliases = PIECE_SEP.join(
                f"{k}{FIELD_SEP}{v}" for k, v in (case.get("aliases") or {}).items())
            rows.append(f"{pieces}\t{case.get('ru', '')}\t{case.get('body', '')}"
                        f"\t{case.get('headColor', '')}\t{variants}\t{aliases}")
        table.write_text("\n".join(rows), encoding="utf-8")

        result = subprocess.run(
            [java, "-Dstdout.encoding=UTF-8", "-Dfile.encoding=UTF-8",
             "-cp", str(work), "ParagraphRun", str(table)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            print("Java не смогла прогнать случаи:")
            print(result.stderr.strip()[:2000])
            return None

    out = []
    torn = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        body, painted, laid = parts[0], parts[1], parts[2]
        head = parts[3] if len(parts) > 3 else ""
        flat = parts[4] if len(parts) > 4 else None
        pieces = []
        for raw in laid.split(PIECE_SEP):
            if not raw:
                continue
            color, _, text = raw.partition(FIELD_SEP)
            pieces.append((color, text))
        # ⚠️ Перенос не смеет менять ТЕКСТ — только раскладывать его по строкам.
        # Склейка кусков выдумывала пробел там, где кусок примыкал вплотную.
        whole = "".join(text for _, text in pieces)
        if flat is not None and flat != whole:
            torn.append((whole, flat))
        out.append((body, int(painted), pieces, head))
    if torn:
        print(f"⚠️ ПЕРЕНОС ПОРТИТ ТЕКСТ: {len(torn)}")
        for whole, flat in torn[:5]:
            print("   было:", whole[:90])
            print("   ушло:", flat[:90])
        print()
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Проверка раскраски абзацев")
    parser.add_argument("--all", action="store_true", help="показать раскладку целиком")
    args = parser.parse_args()

    cases = load_cases()
    if not cases:
        print(f"нет случаев: {CASES}")
        return 1
    results = run_java(cases)
    if results is None:
        return 1

    live = [case for case in cases if case.get("_live")]
    print(f"случаев: {len(cases)}" + (f", из них живых из игры: {len(live)}" if live else ""))
    if not live:
        print("  (живых раскладок ещё нет — они появятся в dump/paragraph-colors.json"
              " после игры на свежем jar)")
    else:
        # ⚠️ Сторож на СБОР кусков, а не на логику раздачи. Эталоны его не ловят:
        # в них куски записаны руками и заведомо верны. А в моде куски собирались
        # из line.getString() + стиль КОРНЯ — и каждая строка давала ровно один
        # кусок, то есть цвета терялись ещё до всякой логики. Признак простой:
        # у разноцветной подсказки кусков обязано быть больше, чем строк.
        flat = sum(1 for case in live
                   if len({color for color, _ in case.get("pieces") or []}) <= 1)
        if flat == len(live):
            print(f"  ⚠️ ВО ВСЕХ {len(live)} живых раскладках ровно по одному цвету —"
                  " похоже, куски собираются неверно (стиль корня вместо кусков)")
        else:
            print(f"  одноцветных среди них: {flat} из {len(live)}")
    print()

    broken = 0
    for case, (body, painted, pieces, head) in zip(cases, results):
        colors = {}
        for color, text in pieces:
            colors[text.strip()] = color
        misses = []
        # ⚠️ Заголовок проверяем и на «должен отделиться», и на «НЕ должен»:
        # прозу, у которой первая строка просто короткая, резать нельзя.
        want_head = case.get("expectHead")
        if want_head is not None and head.strip() != want_head.strip():
            misses.append(f"заголовок должен быть «{want_head}», а вышел "
                          + (f"«{head}»" if head else "не отделён"))
        # ⚠️ Цвет ТЕЛА проверяем первым: ошибка тут красит ВЕСЬ абзац чужим
        # цветом, и это худшее, что может случиться («весь профиль стал
        # фиолетовым» — живая поломка из истории проекта).
        want_body = case.get("expectBody")
        if want_body and body != want_body:
            misses.append(f"цвет тела должен быть {want_body}, а вышел {body or '(нет)'}")
        for text, want in (case.get("expect") or {}).items():
            got = colors.get(text)
            if got != want:
                misses.append(f"«{text}» должно быть {want}, а вышло "
                              + (f"{got}" if got else "не отдельным куском"))
        total = len(case.get("ru", "").strip())
        share = painted * 100 // total if total else 0
        mark = "ОШИБКА" if misses else "ok"
        print(f"  [{mark}] {case.get('name', '?')}")
        print(f"     тело: {body}, подсвечено {painted} знаков из {total} ({share}%)")
        if args.all or misses:
            for color, text in pieces:
                shown = text if len(text) <= 46 else text[:46] + "…"
                print(f"       {color or '(тело)':<14} {shown}")
        for miss in misses:
            print(f"     ! {miss}")
            broken += 1
        print()

    print(f"итого замечаний: {broken}")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
