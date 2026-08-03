"""
Сверяет КОНТРАКТ между корпусом абзацев и модом.

Зачем отдельная проверка. Ключ абзаца строят двое: мод в игре
(Paragraphs.key/runs) и скрипт при сборке корпуса (make_paragraphs.py).
Разойдутся хоть на пробел — перевод не найдётся НИ РАЗУ, и это тихая беда:
ошибок нет, подсказки просто остаются английскими, как будто словарь пуст.

Так уже было: скрипт резал абзац ещё и по строкам-характеристикам, а мод
режет только по пустым строкам. 364 абзаца оказались недостижимы — перевод
за деньги в стол.

Что делает: строит ключи ТОЧНО так же, как Paragraphs.java (копия алгоритма
ниже), и сверяет с корпусом. Каждый ключ корпуса обязан быть среди тех, что
построит мод. Обратное не требуется: мод спрашивает и про куски с
характеристиками внутри, а такие мы переводить не беремся.

⚠️ Правишь Paragraphs.java или make_paragraphs.py — прогони это.

Запуск:  python tools/check_contract.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_paragraphs import MIN_LINES, is_structural, without_name  # noqa: E402

CORPUS = ROOT / "data" / "work" / "paragraphs.json"

# ⚠️ ДВА ИСТОЧНИКА СВЕРХ ПОДСКАЗОК, и без них проверка ВРЁТ.
#
# Она сверяет корпус с ключами, которые строятся из tooltips.json — это
# подсказки ПРЕДМЕТОВ. Но абзац в корпус попадает ещё двумя путями:
#
#   * лор с аукциона (fetch_auction.py) — предметы с чужих аккаунтов, которых
#     игрок на своём экране не видел. Мод спросит их, когда встретит вещь;
#   * меню и экраны — их мод склеивает и показывает, но в tooltips.json
#     они не попадают вовсе (там только предметы). Их видно
#     в paragraph-colors.json, куда мод пишет каждый показанный абзац.
#
# Без этих двух проверка объявила «НЕДОСТИЖИМО: 8302» после первого же
# прогона с аукционом — и, стоя в круге сборки, заблокировала refresh.py.
# Ложная тревога у сторожа хуже отсутствия сторожа: она приучает не смотреть
# на красное (это в проекте уже записано про check_terms).
AUCTION = ROOT / "data" / "work" / "auction_lore.json"
SHOWN = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump"
             "/paragraph-colors.json")


def from_auction(used: list[str]) -> set[str]:
    """Ключи абзацев из лора аукциона — они уже нарезаны тем же алгоритмом."""
    if not AUCTION.exists():
        return set()
    try:
        lore = json.loads(AUCTION.read_text(encoding="utf-8")).get("lore") or {}
    except (json.JSONDecodeError, OSError):
        return set()
    if lore:
        used.append(f"auction_lore.json ({len(lore)})")
    return set(lore)


def shown_in_game(used: list[str]) -> set[str]:
    """Абзацы, которые мод РЕАЛЬНО показывал, — включая меню и экраны."""
    if not SHOWN.exists():
        return set()
    try:
        cases = json.loads(SHOWN.read_text(encoding="utf-8")).get("cases") or []
    except (json.JSONDecodeError, OSError):
        return set()
    keys = {c["key"] for c in cases if c.get("key")}
    if keys:
        used.append(f"paragraph-colors.json ({len(keys)})")
    return keys

# Источники, из которых корпус мог быть собран. Проверять надо против ВСЕХ:
# абзац из дампа в выгрузке NEU не найдётся, и проверка объявила бы его
# недостижимым — соврав ровно там, где всё хорошо.
SOURCES = [
    ROOT / "data" / "work" / "lore_tooltips.json",
    Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/tooltips.json"),
    ROOT / "data" / "work" / "tooltips.json",
]

# Кусок исходника Paragraphs.java, по которому писались копии ниже.
# Разошлись — значит копия устарела, и проверка врёт.
JAVA = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "Paragraphs.java"
JAVA_MARKERS = [
    "boolean blank = lines.get(i).getString().trim().isEmpty();",   # режем по пустым
    "i - start >= MIN_LINES",                                       # кусок короче двух — мимо
    "text.append(' ');",                                            # склейка одним пробелом
    "private static final int MIN_LINES = 2;",
    "private static Run nameAside(",                                # имя предмета — граница
]


def java_runs(lines: list[str]) -> list[tuple[int, int]]:
    """Копия Paragraphs.runs: режем ТОЛЬКО по пустым строкам."""
    found, start = [], -1
    for i, line in enumerate(lines):
        if not line.strip():
            if start >= 0 and i - start >= MIN_LINES:
                found.append((start, i))
            start = -1
        elif start < 0:
            start = i
    if start >= 0 and len(lines) - start >= MIN_LINES:
        found.append((start, len(lines)))
    return found


def java_key(lines: list[str], run: tuple[int, int]) -> str:
    """Копия Paragraphs.key: строки без §-кодов, каждая обрезана, склейка пробелом."""
    return " ".join(lines[i].strip() for i in range(*run)).strip()


def check_list_marks() -> int:
    """
    Сверяет ЗНАКИ СПИСКА: `ColorLayout.CHOICE_MARKS` против `make_queue.LIST_MARK`.

    ⚠️ Зачем отдельный сторож. Признак «строка начинается со списочного знака»
    живёт в двух местах и значит там противоположные вещи: мод по нему
    ОТКАЗЫВАЕТСЯ склеивать абзац, а очередь по нему решает, что строки надо
    брать построчно. Разойдутся — строки провалятся МЕЖДУ ними: абзац
    на экран не выкладывается, а в очередь не попадает, потому что «закрыт
    абзацем».

    Так уже было (записано в граблях про «Highest Price» и «Ending soon»),
    и починка тогда свелась к тому, что набор знаков выписали в скрипт ЗАНОВО.
    Он разошёлся опять: у мода появились «✖», «◆» и «»», а в скрипте нет.
    Замер на корпусе — 130 абзацев, 527 строк, из них 108 с УЖЕ КУПЛЕННЫМ
    переводом, который не доходил до экрана.

    Обе беды тихие одинаково: ошибок нет, счётчики выглядят осмысленно.
    """
    import re as _re
    layout = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "ColorLayout.java"
    if not layout.exists():
        print("\n=== знаки списка ===")
        print(f"  ! нет файла {layout.name} — сверить не с чем")
        return 1

    body = layout.read_text(encoding="utf-8")
    found = _re.search(r"CHOICE_MARKS\s*=\s*Set\.of\((.*?)\);", body, _re.S)
    if not found:
        print("\n=== знаки списка ===")
        print("  ! в ColorLayout.java не нашёлся CHOICE_MARKS — проверка ослепла")
        return 1
    mod_marks = set(_re.findall(r'"([^"]+)"', found.group(1)))

    from make_queue import LIST_MARK
    inside = _re.search(r"\[([^\]]+)\]", LIST_MARK.pattern)
    queue_marks = set(inside.group(1)) if inside else set()

    print("\n=== знаки списка: мод против очереди ===")
    missing = mod_marks - queue_marks
    extra = queue_marks - mod_marks
    if not missing and not extra:
        print(f"  совпадают, {len(mod_marks)} знаков")
        return 0

    if missing:
        print(f"  ! мод считает списком, а очередь НЕТ: {' '.join(sorted(missing))}")
        print("    строки таких абзацев провалятся между системами:")
        print("    на экран абзац не выложат, а в очередь не возьмут")
    if extra:
        print(f"  ! очередь считает списком, а мод НЕТ: {' '.join(sorted(extra))}")
        print("    не так опасно: строки просто уедут в очередь лишний раз")
    print("    чинить: make_queue.LIST_MARK привести к ColorLayout.CHOICE_MARKS")
    return 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    problems = 0

    # --- 0. не устарела ли копия алгоритма ---
    print("=== копия алгоритма ещё соответствует Paragraphs.java? ===")
    if not JAVA.exists():
        print(f"  ! не нашёл {JAVA.name} — сверить не с чем")
        problems += 1
    else:
        source = JAVA.read_text(encoding="utf-8")
        missing = [m for m in JAVA_MARKERS if m not in source]
        if missing:
            problems += 1
            print("  ! Paragraphs.java изменился, копия ниже могла устареть.")
            print("    не нашёл строк:")
            for m in missing:
                print(f"      {m}")
        else:
            print("  соответствует")

    if not CORPUS.exists():
        print(f"\nнет корпуса: {CORPUS}")
        return 1

    corpus = json.loads(CORPUS.read_text(encoding="utf-8")).get("paragraphs") or []
    corpus_keys = {p["text"]: p for p in corpus}

    mod_keys = set()
    used = []
    for source in SOURCES:
        if not source.exists():
            continue
        try:
            blocks = json.loads(source.read_text(encoding="utf-8")).get("tooltips") or []
        except (json.JSONDecodeError, OSError):
            continue
        used.append(f"{source.name} ({len(blocks)})")
        for block in blocks:
            lines = without_name(block["lines"], block.get("item", ""))
            for run in java_runs(lines):
                mod_keys.add(java_key(lines, run))
    mod_keys |= from_auction(used)
    mod_keys |= shown_in_game(used)
    if not used:
        print("\nне нашёл ни одного источника подсказок — сверять не с чем")
        return 1
    print(f"\nисточники: {', '.join(used)}")

    # ⚠️ Абзац с полем `source` создан НАМЕРЕННО, а не собран из подсказки:
    # лор аукциона (вещь с чужого аккаунта), варианты сезонного бонуса
    # (Hypixel покажет их только в свой сезон). В источниках их нет и быть
    # не может — но это не расхождение алгоритма, а работа впрок.
    #
    # Разделять обязательно: сторож стоит в круге сборки, и ложная тревога
    # тут останавливает refresh.py целиком. А смешав их с настоящими,
    # мы бы утопили беду («make_paragraphs режет не там») в шуме.
    unreachable = [k for k in corpus_keys
                   if k not in mod_keys and not corpus_keys[k].get("source")]
    awaited = [k for k in corpus_keys
               if k not in mod_keys and corpus_keys[k].get("source")]
    covered = len(corpus_keys) - len(unreachable) - len(awaited)

    print(f"\n=== достижимость корпуса ===")
    print(f"  мод построит разных ключей: {len(mod_keys)}")
    print(f"  в корпусе:                  {len(corpus_keys)}")
    print(f"  из них мод спросит:         {covered}")

    if unreachable:
        problems += 1
        paid = sum(1 for k in unreachable if corpus_keys[k].get("ru"))
        print(f"\n  ! НЕДОСТИЖИМО: {len(unreachable)} абзацев мод не спросит никогда")
        if paid:
            print(f"  ! из них УЖЕ ПЕРЕВЕДЕНО: {paid} — это деньги в стол")
        print("    причина почти всегда одна: make_paragraphs режет кусок не там,")
        print("    где его режет мод. Пересобери корпус после правки.")
        for k in sorted(unreachable, key=len)[:5]:
            print(f"      {k[:96]!r}")
    else:
        print("  недостижимых нет — каждый переведённый абзац дойдёт до экрана")

    if awaited:
        paid = sum(1 for k in awaited if corpus_keys[k].get("ru"))
        print(f"\n  ждут своего случая: {len(awaited)} (переведено {paid})")
        print("    Это НЕ ошибка: абзацы созданы намеренно — лор аукциона")
        print("    (вещи с чужих аккаунтов) и варианты сезонного бонуса.")
        print("    Мод спросит их, когда игрок встретит предмет или наступит сезон.")

    # --- сколько мод спросит впустую (не ошибка, но полезно знать) ---
    uncovered = len(mod_keys) - covered
    print(f"\n=== чего мод спросит, а перевода нет: {uncovered} ===")
    print("  это НЕ ошибка: куски с характеристиками внутри мы намеренно не берём,")
    print("  их закрывают шаблоны и построчные правила.")
    if mod_keys:
        print(f"  абзацами закрыто {covered * 100 // len(mod_keys)}% того, что мод спрашивает")

    problems += check_list_marks()

    print(f"\nитого замечаний: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
