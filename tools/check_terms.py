"""
Проверяет словарь на путаницу терминов.

Главная беда перевода игры — не корявая фраза, а два РАЗНЫХ понятия, переведённых
одинаково. Игрок тогда не может их различить в принципе. Живой пример: в SkyBlock
есть Gems (платная валюта) и Gemstones (самоцветы с добычи) — если оба стали
«Самоцветами», человек не поймёт, что у него просят.

Что ищется:
  1. РАЗНЫЕ английские строки с ОДИНАКОВЫМ переводом (самое опасное);
  2. ОДНА английская строка с разными переводами в разных файлах;
  3. известные пары-ловушки — проверяются отдельно и всегда;
  4. перевод, совпавший с оригиналом (запись бесполезна).

Запуск:  python tools/check_terms.py
"""

from __future__ import annotations

import json
import sys
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# Пары понятий, которые легко перепутать. Их переводы обязаны отличаться.
# Список пополняется по мере находок — каждая строка тут появилась не просто так.
CONFUSABLE = [
    ("Mythic", "Mythological", "ступень редкости vs контент Дианы (гриффины, норы)"),
    ("Gems", "Gemstone", "валюта за деньги vs самоцветы с добычи"),
    ("Gems", "Gemstones", "валюта за деньги vs самоцветы с добычи"),
    ("Bits", "Bit", "валюта vs единица"),
    ("Speed", "Attack Speed", "скорость передвижения vs скорость атаки"),
    ("Speed", "Mining Speed", "скорость передвижения vs скорость добычи"),
    ("Damage", "Ability Damage", "обычный урон vs урон способностей"),
    ("Defense", "True Defense", "защита vs истинная защита"),
    ("Health", "Hearts", "здоровье vs сердца"),
    ("Fortune", "Fortitude", "удача vs стойкость"),
    ("Wisdom", "Intelligence", "мудрость vs интеллект"),
    ("Slayer", "Slayer Quest", "истребитель vs его задание"),
    ("Pet", "Pet Item", "питомец vs предмет питомца"),
    ("Accessory", "Accessory Power", "аксессуар vs его сила"),
    ("Enchantment", "Enchanting", "чара vs навык зачарования"),
    ("Rune", "Rune Slot", "руна vs гнездо под неё"),
    ("Collection", "Collection Item", "коллекция vs предмет коллекции"),
]


def load_all() -> dict[str, list[tuple[str, str]]]:
    """строка -> [(перевод, файл)]"""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exception:
            print(f"! {path.name}: {exception}")
            continue
        for section in ("exact", "glossary"):
            for source, target in (pack.get(section) or {}).items():
                if target:
                    out[source].append((target, path.name))
        # Привязки к предмету помечаем: это НАМЕРЕННЫЕ переопределения общего
        # перевода (у разных предметов обрывок продолжает разные фразы).
        # Считать их «расхождением» нельзя — иначе проверка утонет в шуме
        # ровно там, где механизм работает как задумано.
        for item_lines in (pack.get("byItem") or {}).values():
            for source, target in item_lines.items():
                if target:
                    out[source].append((target, path.name + " [для предмета]"))
    return out


def same_words(a: str, b: str) -> bool:
    """
    Строки различаются только знаками или регистром.

    «Right Click to open!» и «Right-click to open!» — это одно и то же,
    Hypixel просто пишет по-разному. Одинаковый перевод тут не ошибка,
    и поднимать тревогу незачем.
    """
    strip = lambda s: re.sub(r"[^a-zа-я0-9]+", "", s.lower())
    return strip(a) == strip(b)


def related(a: str, b: str) -> bool:
    """Похожие строки: одна входит в другую или отличаются окончанием."""
    la, lb = a.lower(), b.lower()
    if la in lb or lb in la:
        return True
    # Gems / Gemstone — общий корень от 4 букв
    common = 0
    for x, y in zip(la, lb):
        if x != y:
            break
        common += 1
    return common >= 4


def main() -> int:
    # Консоль Windows по умолчанию не кодирует значки вроде ☀ и падает на печати.
    # Данные тут не виноваты — чиним именно вывод.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = load_all()
    print(f"строк в словарях: {len(data)}\n")

    problems = 0

    # --- 1. разные строки, одинаковый перевод ---
    by_translation: dict[str, list[str]] = defaultdict(list)
    for source, entries in data.items():
        for target, _ in entries:
            by_translation[target].append(source)

    print("=== разные понятия с одинаковым переводом ===")
    dangerous, harmless = [], []
    for target, sources in by_translation.items():
        uniq = sorted(set(sources))
        if len(uniq) < 2:
            continue
        # Опасно, когда исходники ПОХОЖИ: значит это близкие понятия,
        # и одинаковый перевод их склеивает.
        # различие только в знаках — это одна и та же строка, а не два понятия
        if all(same_words(uniq[0], other) for other in uniq[1:]):
            continue
        if any(related(a, b) for i, a in enumerate(uniq) for b in uniq[i + 1:]):
            dangerous.append((target, uniq))
        else:
            harmless.append((target, uniq))

    if dangerous:
        problems += len(dangerous)
        for target, sources in dangerous:
            print(f"  ОПАСНО  «{target}»  <-  {', '.join(repr(s) for s in sources)}")
    else:
        print("  похожих понятий с одним переводом нет")

    if harmless:
        print(f"\n  (ещё {len(harmless)} совпадений у непохожих строк — обычно это нормально)")

    # --- 2. одна строка, разные переводы ---
    print("\n=== одна строка переведена по-разному ===")
    conflicts = 0
    overrides = 0
    for source, entries in data.items():
        general = [(t, f) for t, f in entries if "[для предмета]" not in f]
        if len(entries) != len(general):
            overrides += 1
            entries = general  # сравниваем только общие переводы между собой
        variants = {t for t, _ in entries}
        if len(variants) > 1:
            conflicts += 1
            problems += 1
            where = ", ".join(f"{t!r} ({f})" for t, f in entries)
            print(f"  «{source}»  ->  {where}")
    if not conflicts:
        print("  расхождений нет")
    if overrides:
        print(f"  ({overrides} строк переопределены для конкретных предметов — так и задумано)")

    # --- 3. пары-ловушки ---
    print("\n=== известные пары-ловушки ===")
    checked = 0
    for first, second, why in CONFUSABLE:
        got_first = {t for t, _ in data.get(first, [])}
        got_second = {t for t, _ in data.get(second, [])}
        if not got_first or not got_second:
            continue
        checked += 1
        overlap = got_first & got_second
        if overlap:
            problems += 1
            print(f"  ОПАСНО  {first} и {second} переведены одинаково: {overlap}")
            print(f"          ({why})")
        else:
            print(f"  ok      {first} != {second}")
    if not checked:
        print("  ни одна пара пока не встречается в словаре целиком")

    # --- 4. перевод равен оригиналу ---
    print("\n=== перевод совпадает с оригиналом ===")
    same = [s for s, entries in data.items() for t, _ in entries if s == t]
    if same:
        problems += len(same)
        for s in same[:10]:
            print(f"  «{s}»")
    else:
        print("  таких нет")

    print(f"\nитого замечаний: {problems}")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
