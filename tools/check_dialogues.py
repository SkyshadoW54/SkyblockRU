"""
Разбор полётов после перевода реплик NPC — механически, а не глазами.

⚠️ Зачем отдельно от `check_translation.py`. У реплик свои беды, которых нет
у подсказок: имя говорящего в префиксе (модель норовит его повторить),
подсветка внутри фразы и живая речь, где легко просклонять английское имя.
Первый же прогон дал 56 переводов из 94 с лишним «[Elle] » — и на глаз это
не бросалось: примеры, которые я смотрел, были чистыми.

Делим находки, как принято в проекте: СЛОМАНО (в мод отдавать нельзя)
и ПОДОЗРИТЕЛЬНО (смотреть человеку).

Запуск:
  python tools/check_dialogues.py data/work/npc_test.json
  python tools/check_dialogues.py data/work/npc_dialogues.json --show 0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import protected  # noqa: E402

PREFIX = re.compile(r"^(?:§.)*\[NPC\][^:]*:\s*")
CODE = re.compile(r"[&§]([0-9a-fk-orA-FK-OR])")
HOLE = re.compile(r"\{[ns]\}")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
# английское слово со СТРОЧНОЙ буквы, окружённое кириллицей — признак
# недоперевода, отобранный на корпусе проекта (5 находок, 0 ложных)
HALF = re.compile(r"[А-Яа-яЁё]\s+([a-z]{3,})\s+[А-Яа-яЁё]")


def strip_codes(text: str) -> str:
    return re.sub(r"[&§].", "", text)


def check(key: str, meta: dict, guarded: set[str]) -> list[tuple[str, str]]:
    """Находки по одной реплике: (важность, что не так)."""
    russian = meta.get("ru") or ""
    if not russian:
        return []
    out: list[tuple[str, str]] = []
    name = (meta.get("npc") or "").strip()
    original = meta.get("raw") or key

    body = PREFIX.sub("", russian)
    if name and (body.startswith(f"[{name}]") or body.startswith(f"{name}:")):
        out.append(("СЛОМАНО", "имя говорящего повторено в тексте реплики"))

    if not PREFIX.match(russian):
        out.append(("СЛОМАНО", "потерян префикс «[NPC] Имя:»"))

    # ⚠️ Цвета сверяем ПО НАБОРУ: посимвольно нельзя — текст другой.
    # Пропажа кода значит, что подсветка не доехала.
    # ⚠️ «§r» из сравнения ИСКЛЮЧЁН: это не цвет, а сброс форматирования,
    # и мы законно заменяем его равносильным кодом цвета тела («§r§f» -> «§f»).
    # Без этой оговорки проверка объявляла потерей каждую такую реплику.
    was = {c.lower() for c in CODE.findall(original)} - {"r"}
    now = {c.lower() for c in CODE.findall(russian)} - {"r"}
    lost = was - now
    if lost:
        out.append(("СЛОМАНО", f"пропала подсветка: {', '.join(sorted(lost))}"))

    if HOLE.findall(strip_codes(key)) != HOLE.findall(strip_codes(russian)):
        out.append(("СЛОМАНО", "дырки {n}/{s} не совпали"))

    clean_ru = strip_codes(russian)
    if not CYRILLIC.search(clean_ru):
        out.append(("ПОДОЗРИТЕЛЬНО", "в переводе нет ни одной русской буквы"))

    broken = protected.check_block(strip_codes(original), clean_ru, guarded)
    if broken:
        out.append(("СЛОМАНО", f"испорчено защищённое имя: {broken}"))

    half = HALF.search(clean_ru)
    if half:
        out.append(("ПОДОЗРИТЕЛЬНО", f"английское слово среди русских: «{half.group(1)}»"))

    # Английское имя со слипшейся кириллицей: «Outpost'е», «Bahaу»
    if re.search(r"[A-Za-z][А-Яа-яЁё]|[A-Za-z]'[а-яё]", clean_ru):
        out.append(("СЛОМАНО", "к английскому имени приклеено русское окончание"))

    if re.search(r"§\s*$|§$", russian):
        out.append(("СЛОМАНО", "код цвета в конце без текста"))

    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Проверка переведённых реплик NPC")
    parser.add_argument("file")
    parser.add_argument("--show", type=int, default=8, help="сколько примеров (0 — все)")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path
    lines = json.loads(path.read_text(encoding="utf-8")).get("lines") or {}
    guarded = protected.collect()

    translated = {k: v for k, v in lines.items() if v.get("ru")}
    findings: dict[str, list[tuple[str, str]]] = {}
    for key, meta in translated.items():
        found = check(key, meta, guarded)
        if found:
            findings[key] = found

    broken = {k: v for k, v in findings.items() if any(w == "СЛОМАНО" for w, _ in v)}
    odd = {k: v for k, v in findings.items() if k not in broken}

    print(f"реплик переведено: {len(translated)} из {len(lines)}")
    print(f"  СЛОМАНО:        {len(broken)}")
    print(f"  ПОДОЗРИТЕЛЬНО:  {len(odd)}")

    for title, group in (("СЛОМАНО", broken), ("ПОДОЗРИТЕЛЬНО", odd)):
        if not group:
            continue
        print()
        print(f"=== {title} ===")
        shown = list(group.items())
        if args.show:
            shown = shown[:args.show]
        for key, found in shown:
            print(f"  {strip_codes(key)[:74]}")
            for _, why in found:
                print(f"      {why}")
            print(f"      -> {strip_codes(lines[key]['ru'])[:74]}")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
