"""
Переименовывает ТЕРМИН во всём проекте разом.

Зачем отдельный инструмент. Термин повторяется ВНУТРИ переведённых фраз и потому
размазан по трём слоям:
  ручные словари      — правятся напрямую;
  генераторы tools/   — русский зашит в скрипте, правка json бесполезна;
  корпуса data/work/  — русский внутри переведённых предложений.
Автословари (95-tooltips, 50-rarity, 26-time…) собираются из двух последних:
поправишь только их — следующая пересборка вернёт старое слово.

Замер на живом проекте: «Защита» лежит в 23 местах четырёх слоёв. Руками это
не делается, а разовым скриптом «на коленке» — делается ровно один раз и никем
не проверяется.

⚠️ ПАДЕЖИ. Термин живёт в разных формах: «Удача лесоруба», но «Удачи лесоруба».
Замена по одной форме молча пропустит остальные. Морфологию мы тут НЕ гадаем
(и не тянем pymorphy): формы ИЩУТСЯ в самих файлах и показываются глазами —
источник правды это наш текст, а не словарь русского языка.

Как считается форма. Правится только то слово, которое изменилось; слова,
оставшиеся прежними, подхватываются в любой форме и переносятся как есть:
    «Удача лесозаготовки» -> «Удача лесоруба»
    находит «Удач|и| лесозаготовк|и|» и делает «Удач|и| лесоруба»
Первое слово в таких парах — главное, оно и склоняется. Поэтому если меняется
ИМЕННО ОНО, вывести формы machinery не может, и инструмент честно требует
задать пары руками (--pair), а не угадывает.

Запуск:
  python tools/rename_term.py "Удача лесозаготовки" "Удача лесоруба"
  python tools/rename_term.py "Удача лесозаготовки" "Удача лесоруба" --yes
  python tools/rename_term.py "Защита" "Броня" --pair "Защиты=Брони" --pair "Защите=Броне"
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
WORK = ROOT / "data" / "work"
TOOLS = ROOT / "tools"

# Признак автословаря — тот же, что и в его собственном _comment.
AUTO_MARKS = ("собирается автоматически", "генерир", "правь скрипт", "автоматически из")


def is_generated(path: Path) -> bool:
    if path.suffix != ".json" or not path.is_relative_to(PACKS):
        return False
    try:
        comment = (json.loads(path.read_text(encoding="utf-8")).get("_comment") or "").lower()
    except (json.JSONDecodeError, OSError):
        return False
    return any(mark in comment for mark in AUTO_MARKS)


SELF = Path(__file__).resolve()

# Пользовательские словари в самой игре. Мы их НЕ правим — это чужая территория,
# копии кладут туда руками для быстрой проверки через /skyblockru reload.
# Но предупредить обязаны: они перекрывают встроенные, и забытая копия будет
# молча возвращать старый термин, сколько его ни меняй в проекте.
USER_PACKS = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/packs")


def warn_user_packs(old: str) -> None:
    if not USER_PACKS.is_dir():
        return
    stale = []
    for path in sorted(USER_PACKS.glob("*.json")):
        try:
            if old.split()[0][:-1] in path.read_text(encoding="utf-8"):
                stale.append(path.name)
        except (OSError, UnicodeDecodeError):
            continue
    if stale:
        print(f"\n⚠️ В {USER_PACKS} лежат словари: {', '.join(stale)}")
        print("   Они перекрывают встроенные и здесь НЕ правятся. Обновите их копии")
        print("   или удалите, иначе в игре останется старый термин.")


def layers() -> list[tuple[str, list[Path]]]:
    """Все места, где может жить русский текст. Порядок — как в отчёте."""
    packs = sorted(p for p in PACKS.rglob("*.json") if p.name != "index.json")
    # Себя из поиска исключаем: в докстринге лежат примеры вида
    # «Удача лесозаготовки» -> «Удача лесоруба», и без этого инструмент
    # переписал бы собственную документацию — проверено, переписывал.
    scripts = sorted(p for p in TOOLS.glob("*.py") if p.resolve() != SELF)
    return [
        ("ручные словари", [p for p in packs if not is_generated(p)]),
        ("АВТОсловари (пересобираются)", [p for p in packs if is_generated(p)]),
        ("генераторы", scripts),
        ("корпуса", sorted(WORK.glob("*.json"))),
    ]


def stem(word: str) -> str:
    """
    Огрызок слова без окончания. Не морфология — просто зацепка для поиска:
    дальше идёт \\w*, а лишнее отсеет второе слово в паре и ваши глаза.
    """
    return word[:-1] if len(word) > 4 else word


def make_rule(old: str, new: str) -> tuple[re.Pattern, callable] | None:
    """
    Правило замены с учётом падежей. None — формы вывести нельзя, нужны --pair.
    """
    old_words, new_words = old.split(), new.split()
    if len(old_words) != len(new_words) or len(old_words) < 2:
        return None
    if old_words[0] != new_words[0]:
        # Меняется главное слово — склонять его пришлось бы нам, а мы не гадаем
        return None

    parts = [f"({stem(old_words[0])}\\w*)"]
    for word in old_words[1:]:
        parts.append(r"(\s+)")
        parts.append(f"({stem(word)}\\w*)")
    pattern = re.compile("".join(parts))

    def repl(match: re.Match) -> str:
        out = [match.group(1)]                       # главное слово — как нашли
        for i, word in enumerate(new_words[1:], start=1):
            out.append(match.group(i * 2))           # пробелы как были
            out.append(word)                         # зависимое — новое
        return "".join(out)

    return pattern, repl


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Переименование термина во всём проекте")
    parser.add_argument("old", help="как было, в именительном падеже")
    parser.add_argument("new", help="как стало")
    parser.add_argument("--pair", action="append", default=[],
                        help="явная пара форм: --pair \"Защиты=Брони\" (можно несколько)")
    parser.add_argument("--yes", action="store_true", help="применить (по умолчанию сухой прогон)")
    args = parser.parse_args()

    explicit: list[tuple[str, str]] = []
    for pair in args.pair:
        if "=" not in pair:
            print(f"! пара без знака равенства: {pair!r}")
            return 1
        was, became = pair.split("=", 1)
        explicit.append((was.strip(), became.strip()))

    rule = make_rule(args.old, args.new)
    if rule is None and not explicit:
        print("Формы вывести не могу — задайте их через --pair.\n")
        print("Так бывает, когда меняется главное слово («Защита» -> «Броня»): его")
        print("пришлось бы склонять, а машинную догадку о падежах мы сюда не пускаем.")
        print("Ниже — что реально лежит в файлах, отсюда и берите формы:\n")
        found = scan_loose(args.old)
        if not found:
            print("  ничего похожего не нашлось")
        for text, count in sorted(found.items(), key=lambda kv: -kv[1]):
            print(f"  {count:4}x  {text!r}")
        return 1

    # --- что будет заменено ---
    plan: dict[Path, dict[str, tuple[str, int]]] = {}
    for label, files in layers():
        for path in files:
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            hits: dict[str, tuple[str, int]] = {}
            if rule is not None:
                pattern, repl = rule
                for match in pattern.finditer(content):
                    was = match.group(0)
                    hits.setdefault(was, (repl(match), 0))
                    hits[was] = (hits[was][0], hits[was][1] + 1)
            for was, became in explicit:
                n = content.count(was)
                if n:
                    hits[was] = (became, hits.get(was, ("", 0))[1] + n)
            if hits:
                plan[path] = hits

    if not plan:
        print(f"«{args.old}» в проекте не найдено — менять нечего")
        return 0

    print(f"«{args.old}» -> «{args.new}»\n")
    total = 0
    risky: list[Path] = []
    for label, files in layers():
        touched = [p for p in files if p in plan]
        if not touched:
            continue
        print(f"=== {label} ===")
        for path in touched:
            count = sum(n for _, n in plan[path].values())
            total += count
            print(f"  {path.relative_to(ROOT)}  ({count})")
            for was, (became, n) in sorted(plan[path].items()):
                print(f"      {n:3}x  {was!r} -> {became!r}")
            if label.startswith("генераторы") or label.startswith("корпуса"):
                risky.append(path)
        print()

    print(f"всего замен: {total}")
    if risky:
        print("\nтермин лежит в источниках автословарей — это правильно:")
        print("без них правка отвалилась бы при следующей пересборке.")
    warn_user_packs(args.old)

    if not args.yes:
        print("\nЭто СУХОЙ ПРОГОН, ничего не изменено. Применить: добавьте --yes")
        return 0

    # --- применяем ---
    for path, hits in plan.items():
        content = path.read_text(encoding="utf-8")
        if rule is not None:
            pattern, repl = rule
            content = pattern.sub(repl, content)
        for was, became in explicit:
            content = content.replace(was, became)
        path.write_text(content, encoding="utf-8")
    print(f"\nзаписано файлов: {len(plan)}")

    # --- проверки после правки ---
    broken = 0
    for path in plan:
        if path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exception:
                broken += 1
                print(f"! {path.name} перестал разбираться: {exception}")
    print("JSON цел" if not broken else f"! испорчено файлов: {broken}")

    print("\n=== проверка на путаницу терминов ===")
    result = subprocess.run([sys.executable, str(TOOLS / "check_terms.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((result.stdout or "").strip().splitlines()[-1] if result.stdout else "не запустилась")
    print("\nДальше: install.cmd (или скопировать словари в config/skyblockru/packs "
          "и /skyblockru reload)")
    return 1 if broken else 0


def scan_loose(term: str) -> dict[str, int]:
    """Все живые формы термина в файлах — по огрызкам слов."""
    words = term.split()
    pattern = re.compile(r"\s+".join(f"{stem(w)}\\w*" for w in words))
    found: dict[str, int] = {}
    for _, files in layers():
        for path in files:
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in pattern.finditer(content):
                found[match.group(0)] = found.get(match.group(0), 0) + 1
    return found


if __name__ == "__main__":
    raise SystemExit(main())
