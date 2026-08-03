"""
Разрезание абзаца ЗАЧАРОВАНИЙ на секции — настоящей Java, без игры.

Зачем отдельная проверка. Hypixel ставит каждое зачарование своей строкой,
а пустой строкой их не разделяет — значит для мода это ОДИН абзац. После
склейки заголовки втекают в прозу:

    Bank V Сохраняет 50% твоих монет при смерти. Кроме того, враги роняют
    +2.5 монет при убийстве. Родство с водой I Увеличивает скорость добычи
    под водой. Рост V Даёт +75 к здоровью. Защита V Даёт +20 Защиты.

Читать невозможно, и структура пропадает. Лечится тем же приёмом, что заголовок
и приписка: режется уже НАЙДЕННЫЙ перевод (ParagraphColors.sections), поэтому
ключ абзаца не меняется и платить заново не нужно.

⚠️ Гоняем на НАСТОЯЩИХ абзацах корпуса, а не на рукотворных случаях. В проекте
это уже стоило дорого: эталоны раскраски пропустили беду в СБОРЕ данных, потому
что в них куски записаны руками и заведомо верны. Здесь входные данные — те же,
что увидит мод.

Что проверяется:
  1. сколько абзацев разрежется, а сколько нет (и почему);
  2. ⚠️ ГЛАВНОЕ: склейка кусков обратно обязана дать ИСХОДНЫЙ перевод знак
     в знак. Резка не смеет ни терять текст, ни добавлять — а именно это
     и ломается незаметно, когда позиции считают по длине, а не по месту.

Запуск:  python tools/check_sections.py
"""
from __future__ import annotations

import json
import re
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
# ⚠️ ColorLayout нужен на компиляцию: `markedHeadEnd` спрашивает у него признак
# маркера списка. Копию признака заводить нельзя — знаки списка в этом проекте
# уже расходились молча, и на это есть отдельный сторож.
LAYOUT = CORE / "ColorLayout.java"

# Тот же признак, что в Paragraphs.ENCHANT_HEAD. Копия намеренно маленькая
# и проверяется тут же: если она разойдётся, счётчик «разрезано» просядет.
ENCHANT_HEAD = re.compile(r"^[A-Z][A-Za-z' -]*\s[IVXLC]+$")

GROUP_SEP = "\u0002"
VARIANT_SEP = "\u0001"

RUNNER = '''
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import ru.skyblockru.core.ParagraphColors;
import ru.skyblockru.core.ParagraphColors.Section;

public class SectionRun {
	public static void main(String[] args) throws Exception {
		for (String line : Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8)) {
			if (line.isBlank()) continue;
			String[] parts = line.split("\\t", -1);
			String translated = parts[0];
			List<List<String>> variants = new ArrayList<>();
			if (parts.length > 1 && !parts[1].isEmpty()) {
				for (String group : parts[1].split("\\u0002", -1)) {
					variants.add(Arrays.asList(group.split("\\u0001", -1)));
				}
			}
			List<Section> found = ParagraphColors.sections(translated, variants);
			StringBuilder out = new StringBuilder();
			for (Section part : found) {
				if (out.length() > 0) out.append("\\u0002");
				out.append(part.at()).append("\\u0001").append(part.length());
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


def dictionaries():
    """Переводы заголовков берём из словарей — тем же путём, что и мод."""
    import status
    return status.Dictionaries()


# @ключ.через.точки — ровно как VanillaNames.KEY в моде.
VANILLA_KEY = re.compile(r"@([a-z0-9_]+(?:\.[a-z0-9_]+)+)")

_VANILLA: dict[str, str] | None = None


def vanilla_lang() -> dict[str, str]:
    """
    Русская локализация САМОЙ игры: ей мод разворачивает @ключи.

    ⚠️ Без этого проверка врёт в безопасную с виду сторону. Ванильные
    зачарования лежат в словаре КЛЮЧОМ («Protection V» ->
    «@enchantment.minecraft.protection V»), потому что перевод берётся
    у клиента игрока, какой бы язык он ни выбрал. Мод разворачивает ключ
    сам (Translator.match -> VanillaNames.expand), а проверка сравнивала
    с сырым ключом — и 17 абзацев из 41 объявляла неразрезаемыми, хотя
    в игре они режутся.

    Файл лежит не в jar клиента, а в хранилище ресурсов: путь к нему
    указывает индекс assets по имени «minecraft/lang/ru_ru.json».
    """
    global _VANILLA
    if _VANILLA is not None:
        return _VANILLA
    _VANILLA = {}
    for base in (Path("C:/MultiMC/assets"),
                 Path("C:/MultiMC/instances/26.2/.minecraft/assets")):
        indexes = base / "indexes"
        if not indexes.exists():
            continue
        for index in sorted(indexes.glob("*.json"), reverse=True):
            try:
                objects = json.loads(index.read_text(encoding="utf-8")).get("objects") or {}
            except (json.JSONDecodeError, OSError):
                continue
            entry = objects.get("minecraft/lang/ru_ru.json")
            if not entry:
                continue
            digest = entry.get("hash") or ""
            path = base / "objects" / digest[:2] / digest
            if not path.exists():
                continue
            try:
                _VANILLA = json.loads(path.read_text(encoding="utf-8"))
                return _VANILLA
            except (json.JSONDecodeError, OSError):
                continue
    return _VANILLA


def expand_keys(value: str) -> str | None:
    """@ключи -> перевод из игры. None, если игра ключа не знает (как в моде)."""
    lang = vanilla_lang()
    missing = False

    def swap(match: re.Match) -> str:
        nonlocal missing
        found = lang.get(match.group(1))
        if not found:
            missing = True
            return match.group(0)
        return found

    out = VANILLA_KEY.sub(swap, value)
    return None if missing else out


def variants_of(head: str, dic) -> list[str]:
    """Как заголовок может выглядеть в переводе: сам по себе и переводом."""
    out = [head]

    def add(value: str) -> None:
        if not value:
            return
        if "@" in value:
            value = expand_keys(value) or ""
        if value:
            out.append(value)

    hit = dic.exact.get(head)
    if hit:
        add(hit[0])
        return out
    for rule in dic.rules:
        pattern, replacement = rule.pattern, rule.replacement
        match = pattern.fullmatch(head)
        if match:
            try:
                add(match.expand(replacement.replace("$", "\\")))
            except (re.error, IndexError):
                pass
            break
    return out


def collect() -> list[dict]:
    """Абзацы корпуса, где два и больше заголовков зачарований."""
    data = json.loads(CORPUS.read_text(encoding="utf-8")).get("paragraphs") or []
    dic = dictionaries()
    cases: list[dict] = []
    for para in data:
        translated = para.get("ru") or ""
        if not translated:
            continue
        rows = [str(row).strip() for row in (para.get("lines") or []) if str(row).strip()]
        heads = [row for row in rows if ENCHANT_HEAD.match(row)]
        if len(heads) < 2:
            continue
        cases.append({
            "item": para.get("item") or "?",
            "translated": translated,
            "heads": heads,
            "variants": [variants_of(head, dic) for head in heads],
        })
    return cases


def run_java(cases: list[dict]) -> list[list[tuple[int, int]]] | None:
    javac, java = find_java("javac"), find_java("java")
    if not javac or not java:
        print("не нашёл javac/java — а без них логику проверять нечем")
        return None
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        (work / "SectionRun.java").write_text(RUNNER, encoding="utf-8")
        build = subprocess.run(
            [javac, "-encoding", "UTF-8", "-d", str(work), str(SRC), str(LAYOUT),
             str(work / "SectionRun.java")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            print("Java не собрала ParagraphColors:")
            print(build.stderr.strip()[:2000])
            return None

        feed = work / "cases.txt"
        feed.write_text("\n".join(
            case["translated"].replace("\t", " ") + "\t"
            + GROUP_SEP.join(VARIANT_SEP.join(group) for group in case["variants"])
            for case in cases), encoding="utf-8")
        done = subprocess.run(
            [java, "-cp", str(work), "SectionRun", str(feed)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if done.returncode != 0:
            print("Java упала:")
            print(done.stderr.strip()[:2000])
            return None

    out: list[list[tuple[int, int]]] = []
    for line in done.stdout.splitlines():
        if not line.strip():
            out.append([])
            continue
        found = []
        for pair in line.split(GROUP_SEP):
            at, _, length = pair.partition(VARIANT_SEP)
            found.append((int(at), int(length)))
        out.append(found)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not CORPUS.exists():
        print("нет корпуса:", CORPUS)
        return 1

    cases = collect()
    print(f"абзацев с двумя и более зачарованиями: {len(cases)}")
    if not cases:
        return 0

    results = run_java(cases)
    if results is None:
        return 1

    cut = whole = 0
    broken: list[str] = []
    partial: list[str] = []
    for case, found in zip(cases, results):
        if len(found) < 2:
            whole += 1
            partial.append(f"{case['item']}: нашлось {len(found)} из {len(case['heads'])}"
                           f" — {', '.join(case['heads'][:3])}")
            continue
        cut += 1
        # ⚠️ Склейка кусков обратно обязана дать исходный перевод ЗНАК В ЗНАК.
        # Резка по позициям не смеет ни терять текст, ни добавлять его; именно
        # это ломается молча, когда границу считают по длине текста, а не по месту.
        text = case["translated"]
        pieces = []
        edge = 0
        for at, length in found:
            pieces.append(text[edge:at])
            pieces.append(text[at:at + length])
            edge = at + length
        pieces.append(text[edge:])
        if "".join(pieces) != text:
            broken.append(f"{case['item']}: склейка не совпала с оригиналом")
        # и границы обязаны идти по возрастанию, не наезжая друг на друга
        for i in range(1, len(found)):
            if found[i][0] < found[i - 1][0] + found[i - 1][1]:
                broken.append(f"{case['item']}: секции наезжают друг на друга")
                break

    print(f"  разрежется по секциям: {cut}")
    print(f"  останется сплошняком : {whole}")
    if partial:
        print()
        print("=== не разрезалось (заголовок не нашёлся в переводе) ===")
        for line in partial[:8]:
            print("   ", line)
        if len(partial) > 8:
            print(f"    … ещё {len(partial) - 8}")

    print()
    print(f"=== СЛОМАНО: {len(broken)} ===")
    if broken:
        for line in broken[:10]:
            print("   ", line)
    else:
        print("  резка ничего не теряет и не добавляет")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
