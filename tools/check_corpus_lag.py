"""
Не отстал ли КОРПУС от собранного из него словаря.

Беда, ради которой написано, случалась ЧЕТЫРЕ раза и каждый раз стоила
переводов: 1610, 1860, 3880 и 3862 абзаца.

Устройство простое и потому опасное: `96-paragraphs.json` собирается ИЗ
`data/work/paragraphs.json`, а корпус пересобирается из источников, которых
сегодня может уже не быть — дамп чистится, лот с аукциона продан, игрок
больше не открывал то меню. Абзац выпадает из корпуса вместе с переводом,
и ПЕРВАЯ ЖЕ пересборка словаря уносит его к игрокам молча: файл на месте,
ошибок нет, на экране английский.

⚠️ `check_shrink` этого не ловит и не может — он сверяет СЛОВАРЬ с последним
jar, то есть на шаг ПОЗЖЕ: к тому времени перевод уже потерян, и спасать
приходится из jar. Здесь вопрос задаётся раньше: переживёт ли словарь
собственную пересборку.

⚠️ Сторож НЕ ЧИНИТ. Вернуть перевод — решение человека: у выпавшей записи
не восстановить `lines` (разбивку на строки), а выдумать её опаснее, чем
оставить пустой.

Запуск:
  python tools/check_corpus_lag.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ⚠️ Консоль Windows — cp1251, и печать «⚠️» роняет инструмент на первой же
# находке. У сторожа это хуже вдвое: он молчит, пока всё хорошо, и падает
# ровно тогда, когда нашёл беду.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

# Пары «рабочий файл -> собранный из него словарь». Список ИМЕНОВАННЫЙ:
# признак «этот словарь собран из того файла» из кода не выводится.
PAIRS = [
    (ROOT / "data" / "work" / "paragraphs.json",
     ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
     / "ru_ru" / "96-paragraphs.json",
     "paragraphs"),
]


def corpus_keys(path: Path) -> set[str]:
    """Ключи корпуса — поле `text` каждой записи."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["paragraphs"] if isinstance(data, dict) else data
    return {str(row.get("text")) for row in rows if row.get("text")}


def pack_keys(path: Path, section: str) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return set((data.get(section) or {}).keys())


def corpus_translations(path: Path) -> dict[str, str]:
    """Ключ корпуса -> его перевод ("" если перевода нет).

    Помеченные «переводить нечего» не берём: там пустое поле `ru` — это
    РЕШЕНИЕ, а не потеря, и звать его бедой значило бы краснеть вечно.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["paragraphs"] if isinstance(data, dict) else data
    return {str(row.get("text")): (row.get("ru") or "")
            for row in rows if row.get("text") and not row.get("nothing")}


def lagging(corpus: set[str], pack: set[str]) -> set[str]:
    """Чистая проверка ради подсадки: что словарь потеряет при пересборке."""
    return pack - corpus


def orphans(corpus: dict[str, str], pack: dict[str, str]) -> set[str]:
    """Второй край: ключ в корпусе ЕСТЬ, а перевода нет — хотя в словаре он есть.

    ⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ ПРИЗНАК, когда рядом уже стоит сверка ключей.
    28.08 сторож напечатал «корпус не отстал», а 3861 перевод при этом
    в корпус не доехал: пересборка вернула ключи (источник нашёлся), но поле
    `ru` осталось пустым. Ключи сошлись — значит первый признак молчал.
    А словарь собирают ИЗ корпуса (merge_paragraphs), то есть следующая же
    сборка словаря выбросила бы эти переводы — та же потеря, другая дверь.

    Мораль записана в CLAUDE.md и повторилась здесь: сторож отвечает на СВОЙ
    вопрос. «Ключ на месте» и «перевод на месте» — разные утверждения.
    """
    return {key for key, value in pack.items()
            if value and key in corpus and not corpus[key]}


def main() -> int:
    problems = 0
    for work, pack, section in PAIRS:
        if not work.exists() or not pack.exists():
            print(f"нет {work.name} или {pack.name} — сравнивать нечего, пропускаю")
            continue
        corpus, built = corpus_keys(work), pack_keys(pack, section)
        gone = lagging(corpus, built)
        print(f"{pack.name}: в корпусе {len(corpus)}, в словаре {len(built)}")
        if gone:
            problems += len(gone)
            print(f"   ⚠️ ОТСТАЛ на {len(gone)}: столько переводов съест первая же пересборка")
            for key in sorted(gone)[:5]:
                print(f"        {key[:88]}")
            print(f"   вернуть можно из {pack.name} — там переводы ещё лежат")

        # второй край: ключ есть, а перевода при нём нет
        data = json.loads(pack.read_text(encoding="utf-8"))
        lost = orphans(corpus_translations(work), data.get(section) or {})
        if lost:
            problems += len(lost)
            print(f"   ⚠️ ПЕРЕВОД НЕ ДОЕХАЛ до корпуса: {len(lost)}"
                  f" — ключ на месте, а поле `ru` пустое")
            for key in sorted(lost)[:5]:
                print(f"        {key[:88]}")
            print(f"   вернуть можно из {pack.name}: сборка словаря идёт ИЗ корпуса,"
                  f" и следующая же выбросит их")

        if not gone and not lost:
            print("   корпус не отстал — пересборка ничего не потеряет")

    # ⚠️ ПРОВЕРКА НА УМЕНИЕ НАХОДИТЬ. Без неё «молчит» и «работает»
    # неотличимы, а этот сторож молчит почти всегда.
    blind = []
    if lagging({"а", "б"}, {"а", "б", "в"}) != {"в"}:
        blind.append("не заметил отставшего ключа")
    if lagging({"а", "б"}, {"а"}):
        blind.append("здоровый случай объявлен бедой (в корпусе больше — это норма)")
    if lagging(set(), {"а"}) != {"а"}:
        blind.append("пустой корпус не назван бедой")
    if orphans({"а": "", "б": "перевод"}, {"а": "перевод", "б": "перевод"}) != {"а"}:
        blind.append("не заметил перевода, не доехавшего до корпуса")
    if orphans({"а": "перевод"}, {"а": "перевод"}):
        blind.append("здоровый случай объявлен бедой (перевод на месте)")
    if orphans({}, {"а": "перевод"}):
        blind.append("отсутствующий ключ спутан с пустым переводом (это первый признак)")

    print()
    if blind:
        print("⚠️ СТОРОЖ СЛЕП:")
        for line in blind:
            print(f"   {line}")
        return 1
    print("подсадка: 6 случаев обоих краёв — все верны")

    print()
    if problems:
        print(f"СЛОМАНО: {problems} переводов под угрозой пересборки")
        return 1
    print("СЛОМАНО: 0 — корпус и словарь сходятся")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
