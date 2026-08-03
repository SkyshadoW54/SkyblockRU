"""
Ищет, ОТКУДА взялась строка, которую видно в игре.

Для случая «на экране написана ерунда — где это лежит и как поправить».
Кидаете кусок текста со скриншота, инструмент отвечает: в каком файле, в каком
слое, что было в оригинале и что с этим делать.

Почему нельзя просто grep-нуть:
  * на экране числа ПОДСТАВЛЕНЫ: видно «Удача лесоруба: +6», а в словаре лежит
    «Удача лесоруба: +{n}» — обычный поиск не найдёт;
  * цвета живут §-кодами ВНУТРИ текста, и в скопированной строке они мешают;
  * с абзацами строка на экране — это КУСОК переложенного текста, и целиком
    её в словаре нет вовсе, только весь абзац;
  * половина словарей собирается автоматически, и править их бесполезно —
    надо знать, из чего именно.

Ищет везде: словари, корпуса, дамп из игры. Ищет и по-русски, и по-английски.

Запуск:
  python tools/find_text.py "Удача лесоруба: +6"
  python tools/find_text.py "Foraging Fortune"
  python tools/find_text.py "лесоруба" --limit 30
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
WORK = ROOT / "data" / "work"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")

COLOR = re.compile("§.")
# ⚠️ Обобщение чисел — из общего pkey: копий было шесть, и одна
# уже разошлась (в measure_color процент попадал внутрь числа).
from pkey import NUMBER  # noqa: E402
AUTO_MARKS = ("собирается автоматически", "генерир", "правь скрипт", "автоматически из")


def norm(text: str) -> str:
    """Строка без §-кодов и лишних пробелов — в таком виде её и держит словарь."""
    return " ".join(COLOR.sub("", text).split())


def template(text: str) -> str:
    """Числа обобщаем в {n} — ровно так, как это делает Translator.toTemplate."""
    return NUMBER.sub("{n}", norm(text))


def needles(query: str) -> list[str]:
    """По чему ищем: как дали, без кодов и с обобщёнными числами."""
    out = []
    for form in (norm(query), template(query)):
        low = form.lower()
        if low and low not in out:
            out.append(low)
    return out


def hits(text: str, keys: list[str]) -> bool:
    low = norm(text).lower()
    return any(k in low for k in keys)


class Report:
    """
    Лимит считается ПО РАЗДЕЛАМ, а не на весь отчёт.

    Иначе находки в словарях съедали лимит целиком, и раздел «дамп из игры»
    выглядел пустым, хотя там было 128 совпадений — отчёт врал молча.
    """

    def __init__(self, limit: int):
        self.limit = limit
        self.total = 0
        self.count = 0
        self.shown = 0

    def section(self, title: str) -> None:
        self.count = 0
        self.shown = 0
        print(f"\n=== {title} ===")

    def add(self, where: str, source: str, russian: str | None, how: str) -> None:
        self.count += 1
        self.total += 1
        if self.shown >= self.limit:
            return
        self.shown += 1
        print(f"\n  {where}")
        print(f"      было:  {source[:100]!r}")
        if russian is not None:
            print(f"      стало: {russian[:100]!r}" if russian.strip()
                  else "      стало: перевода нет (заготовка)")
        print(f"      → {how}")

    def end(self) -> None:
        if not self.count:
            print("  не найдено")
        elif self.count > self.shown:
            print(f"\n  ... ещё {self.count - self.shown} в этом разделе (--limit покажет больше)")


def pack_advice(path: Path, pack: dict) -> str:
    comment = (pack.get("_comment") or "").strip()
    if any(mark in comment.lower() for mark in AUTO_MARKS):
        first = comment.split(".")[0]
        return f"АВТОсловарь, править бесполезно. {first}"
    return f"правится руками прямо тут ({path.name}), дальше /skyblockru reload"


def search_packs(keys: list[str], report: Report) -> None:
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        advice = pack_advice(path, pack)
        # ⚠️ Выключенный словарь говорим ПРЯМО. Иначе находка вводит в
        # заблуждение: перевод в файле есть, а на экране его нет и не будет,
        # потому что игрок пакет отключил. Я сам на это попался с «Огранкой»:
        # искал, почему строка переведена, — а она была выключена.
        if pack.get("default") is False:
            advice = (f"⚠️ ВЫКЛЮЧЕН игроком (пакет {pack.get('id') or path.stem}) — "
                      f"на экране этого перевода НЕТ. " + advice)
        for section in ("exact", "glossary"):
            for src, dst in (pack.get(section) or {}).items():
                if hits(src, keys) or hits(dst, keys):
                    report.add(f"словарь {path.name} [{section}]", src, dst, advice)
        for item, lines in (pack.get("byItem") or {}).items():
            for src, dst in lines.items():
                if hits(src, keys) or hits(dst, keys):
                    report.add(f"словарь {path.name} [byItem: {item}]", src, dst, advice)
        for src, dst in (pack.get("paragraphs") or {}).items():
            if hits(src, keys) or hits(dst, keys):
                report.add(f"словарь {path.name} [АБЗАЦ]", src, dst,
                           "это ЦЕЛЫЙ абзац: на экране мод переносит его сам, "
                           "поэтому строка со скриншота — лишь его кусок. " + advice)
        for rule in (pack.get("regex") or []):
            p, r = rule.get("p", ""), rule.get("r", "")
            if hits(p, keys) or hits(r, keys) or hits(rule.get("_sample", ""), keys):
                report.add(f"словарь {path.name} [regex]", p, r, advice)


def section(data: dict, name: str, kind):
    """Секция файла НУЖНОГО типа, иначе пустая.

    ⚠️ Одноимённое поле бывает не данными, а СЧЁТЧИКОМ: у планки сторожа
    `markup_gaps_baseline.json` поле `paragraphs` — это число 501, и `for`
    по нему валил весь инструмент (TypeError: 'int' object is not iterable).
    Падал он ПОСЛЕ вывода первых разделов, поэтому выглядел работающим.

    ⚠️ Это ВТОРОЙ раз, когда find_text падает на чужой структуре файла:
    первый (корень — список у `_dialogue_pages.json`) записан в CLAUDE.md,
    и починили тогда МЕСТО, а не признак. Поэтому тип проверяется теперь
    у КАЖДОЙ секции, а не у той, что подвела: в data/work лежат рабочие
    файлы разного устройства, и совпадение имён полей ничего не обещает.
    """
    value = data.get(name)
    return value if isinstance(value, kind) else kind()


def search_corpora(keys: list[str], report: Report) -> None:
    for path in sorted(WORK.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # ⚠️ В data/work лежат не только словари: у _dialogue_pages.json корень —
        # СПИСОК имён страниц. На нём инструмент падал с AttributeError, причём
        # ВСЕГДА и на любом запросе: разделы «корпуса» и «дамп из игры» просто
        # не выводились, а поиск выглядел так, будто ничего не нашлось.
        if not isinstance(data, dict):
            continue
        where = f"корпус {path.name}"
        how = (f"правится тут; из этого файла пересобирается словарь — "
               f"без правки корпуса термин вернётся")
        for src, dst in section(data, "exact", dict).items():
            if hits(src, keys) or hits(dst, keys):
                report.add(f"{where} [exact]", src, dst, how)
        for block in section(data, "tooltips", list):
            if not isinstance(block, dict):
                continue
            ru = block.get("ru") or []
            for i, line in enumerate(block.get("lines") or []):
                mine = ru[i] if i < len(ru) else None
                if hits(line, keys) or (mine and hits(mine, keys)):
                    report.add(f"{where} [{block.get('item')}]", line, mine, how)
        for para in section(data, "paragraphs", list):
            if not isinstance(para, dict):
                continue
            if hits(para.get("text", ""), keys) or hits(para.get("ru") or "", keys):
                report.add(f"{where} [АБЗАЦ, предмет {para.get('item')}]",
                           para.get("text", ""), para.get("ru"),
                           "перевод абзаца целиком; на экране мод переносит его сам")


def search_dump(keys: list[str], report: Report) -> None:
    if not DUMP.is_dir():
        return
    collected = DUMP / "collected.json"
    if collected.exists():
        try:
            data = json.loads(collected.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        for origin, strings in (data.get("sources") or {}).items():
            for line, count in strings.items():
                if hits(line, keys):
                    report.add(f"дамп из игры [{origin}], встречалась {count}x", line, None,
                               "ПЕРЕВОДА НЕТ — строка собрана в игре, но в словарях её нет")
    tips = DUMP / "tooltips.json"
    if tips.exists():
        try:
            data = json.loads(tips.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        for block in (data.get("tooltips") or [])[:4000]:
            for line in block.get("lines") or []:
                if hits(line, keys):
                    report.add(f"подсказка из игры [{block.get('item')}]", line, None,
                               "так строка приходит от сервера — это оригинал")
                    break


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Откуда взялась строка из игры")
    parser.add_argument("query", help="кусок текста со скриншота, по-русски или по-английски")
    parser.add_argument("--limit", type=int, default=15, help="сколько находок показать")
    args = parser.parse_args()

    keys = needles(args.query)
    print(f"ищу: {args.query!r}")
    if keys[0] != args.query.lower():
        print(f"  без §-кодов и лишних пробелов: {keys[0]!r}")
    if len(keys) > 1:
        print(f"  с обобщёнными числами:         {keys[1]!r}")

    report = Report(args.limit)

    report.section("СЛОВАРИ (то, что видит игрок)")
    search_packs(keys, report)
    report.end()

    report.section("КОРПУСА (источники автословарей)")
    search_corpora(keys, report)
    report.end()

    report.section("ДАМП ИЗ ИГРЫ (что присылает сервер)")
    search_dump(keys, report)
    report.end()

    print(f"\nвсего находок: {report.total}")
    if not report.total:
        print("\nНичего. Возможные причины:")
        print("  * строка приходит от сервера и в дамп ещё не попала — сыграйте и /skyblockru dump")
        print("  * это КУСОК абзаца: попробуйте два-три слова из середины, без начала и конца")
        print("  * текст с картинки распознан неточно — возьмите короткий кусок без цифр")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
