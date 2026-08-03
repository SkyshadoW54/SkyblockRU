"""
Не упёрся ли сбор в свои потолки — молча.

Зачем. У каждого накопителя в моде есть предел, и упор в него выглядит как
«новых данных больше не встречается»: счётчик просто перестаёт расти, ошибок
нет, в логе тишина. В проекте это случалось дважды и оба раза дорого:

  * MAX_TOOLTIPS был 5000, и в файле оказалось РОВНО 5000 — подсказки
    не собирались неизвестно сколько, и зимнее событие прошло мимо дампа;
  * MAX_PARAGRAPH_COLORS упёрся в 10000, и сбор ЦВЕТОВ стоял. Заметил это
    игрок по счётчику в чате, а не мод: у того потолка не было голоса.

Цена у второго высшая: живые цвета — единственный источник разметки для меню
и экранов, которых нет ни в NEU, ни на аукционе.

⚠️ Пределы читаются ИЗ Java, а не дублируются здесь. Копия разошлась бы с модом
молча — ровно так уже разъезжались знаки списка и алгоритм ключа.

Запуск:  python tools/check_limits.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")
JAVA = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "UnknownStrings.java"

# Какой предел стережёт какой файл. Слева — имя константы в Java.
WATCH = [
    ("MAX_PER_SOURCE", "collected.json", "строки по источникам"),
    ("MAX_TOOLTIPS", "tooltips.json", "подсказки блоками"),
    ("MAX_PARAGRAPH_COLORS", "paragraph-colors.json", "ЦВЕТА абзацев"),
    ("MAX_ITEM_IDS", "item-ids.json", "идентификаторы предметов"),
    ("MAX_NBT_SAMPLES", "item-ids.json", "образцы NBT"),
]

# Порог тревоги: 90% — это уже «упрётся на днях»
NEAR = 90


def limits() -> dict[str, int]:
    """Пределы из исходника мода: копии тут нет и быть не должно."""
    if not JAVA.exists():
        return {}
    source = JAVA.read_text(encoding="utf-8", errors="replace")
    out = {}
    for name, value in re.findall(r"int (MAX_[A-Z_]+)\s*=\s*([\d_]+)", source):
        out[name] = int(value.replace("_", ""))
    return out


def load(name: str):
    path = DUMP / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def counts() -> list[tuple[str, str, int]]:
    """(константа, что считаем, сколько) — по живому дампу."""
    out: list[tuple[str, str, int]] = []
    collected = load("collected.json") or {}
    for source, rows in (collected.get("sources") or {}).items():
        out.append(("MAX_PER_SOURCE", f"строки [{source}]", len(rows)))
    tips = load("tooltips.json") or {}
    out.append(("MAX_TOOLTIPS", "подсказки блоками", len(tips.get("tooltips") or [])))
    colors = load("paragraph-colors.json") or {}
    out.append(("MAX_PARAGRAPH_COLORS", "цвета абзацев", len(colors.get("cases") or [])))
    ids = load("item-ids.json") or {}
    out.append(("MAX_ITEM_IDS", "идентификаторы", len(ids.get("ids") or {})))
    out.append(("MAX_NBT_SAMPLES", "образцы NBT", len(ids.get("samples") or {})))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    caps = limits()
    if not caps:
        print("не прочитал пределы из UnknownStrings.java — проверять не с чем")
        return 1
    if not DUMP.exists():
        print(f"нет папки дампа: {DUMP}")
        return 0

    full, near = [], []
    for const, what, count in counts():
        cap = caps.get(const)
        if not cap:
            continue
        share = count * 100 // cap
        if count >= cap:
            full.append((what, count, cap))
        elif share >= NEAR:
            near.append((what, count, cap, share))

    print(f"пределов прочитано из Java: {len(caps)}")
    if full:
        print(f"\n=== СЛОМАНО: сбор УПЁРСЯ в потолок ({len(full)}) ===")
        print("  Счётчик перестал расти — новые данные НЕ СОБИРАЮТСЯ.")
        for what, count, cap in full:
            print(f"   {what}: {count} из {cap}")
        print("  Поднять предел в UnknownStrings.java либо заархивировать файл дампа.")
        return 1
    if near:
        print(f"\n=== близко к потолку: {len(near)} ===")
        for what, count, cap, share in near:
            print(f"   {what}: {count} из {cap} ({share}%)")
        print("  Не беда, но упрётся скоро — поднять предел заранее.")
    else:
        print("до потолков далеко — сбор идёт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
