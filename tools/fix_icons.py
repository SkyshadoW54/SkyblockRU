"""
Приводит правила в соответствие с настоящими строками из игры.

Две вещи, которые руками сделать нельзя:

1. Иконки Hypixel (сердце, защита, мана, удача фермера) — это символы
   приватной зоны Unicode. Набрать их с клавиатуры невозможно, поэтому берём
   прямо из дампа, который мод собрал во время игры.

2. Цвета. Перевод целой строки берёт цвет первого куска на всю строку, и
   разноцветная полоска над хотбаром становится сплошь красной. Лечится тем,
   что цвета прописываются прямо в перевод кодами §.

Запуск:  python tools/fix_icons.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# Словари разложены по языкам: packs/<язык>/. Скрипты этого проекта делают
# русский, поэтому пишут сюда. Для другого языка — поменять одну строку.
LANG = "ru_ru"
DUMP = Path(r"C:\MultiMC\instances\26.2\.minecraft\config\skyblockru\dump\untranslated.json")

# Коды иконок, снятые с живой игры 2026-07-24. Держим здесь, потому что дамп —
# движущаяся цель: как только строка переведена, она из «непереведённого» пропадает,
# и достать из него исходные символы уже нельзя.
HEART = ""      # здоровье
SHIELD = ""     # защита
MANA = ""       # мана
AQUATIC = ""    # водные мобы
FARM_FORTUNE = ""  # удача фермера

# Строки, где иконка стоит внутри фразы (тоже сняты с живой игры)
KNOWN_LORE = {
    f"Increases damage dealt to {AQUATIC}": f"Повышает урон по {AQUATIC}",
    f"The more {FARM_FORTUNE} Farming Fortune you": f"Чем больше {FARM_FORTUNE} Удачи фермера,",
}


def is_pua(ch: str) -> bool:
    """Символ из приватной зоны Unicode — там Hypixel держит свои иконки."""
    return 0xE000 <= ord(ch) <= 0xF8FF


def load_dump_keys() -> list[str]:
    """Строки из дампа, если он есть. Отсутствие дампа — не беда: ниже есть запасные коды."""
    if not DUMP.exists():
        print(f"дампа нет ({DUMP.name}) — беру известные коды иконок")
        return []
    return list(json.loads(DUMP.read_text(encoding="utf-8"))["exact"])


def save(path: Path, data: dict) -> None:
    """
    Пишет JSON так, чтобы невидимые символы были видны глазами: \\uE010 вместо
    самого символа. Ровно ОДИН обратный слэш — с двумя JSON прочитает это как
    текст, а не как символ, и правило молча перестанет совпадать.
    """
    text = json.dumps(data, ensure_ascii=False, indent=1)
    for code in sorted({ord(c) for c in text if is_pua(c)}):
        text = text.replace(chr(code), f"\\u{code:04X}")
    path.write_text(text, encoding="utf-8")


def find(keys: list[str], *needles: str) -> str | None:
    for key in keys:
        if all(n in key for n in needles):
            return key
    return None


def main() -> int:
    keys = load_dump_keys()

    bar = find(keys, "Defense", "Mana")
    if bar:
        icons = [c for c in bar if is_pua(c)]
        if len(icons) != 3:
            print(f"Ожидал 3 иконки в строке над хотбаром, нашёл {len(icons)}", file=sys.stderr)
            return 1
        heart, shield, mana = icons
        print("иконки взяты из свежего дампа")
    else:
        # Строка уже переводится, поэтому в «непереведённом» её нет — берём известные коды.
        heart, shield, mana = HEART, SHIELD, MANA
        print("строки над хотбаром в дампе нет (уже переводится) — беру известные коды")
    print(f"иконки: сердце=U+{ord(heart):04X} защита=U+{ord(shield):04X} мана=U+{ord(mana):04X}")

    # ---- строка над хотбаром: цвета пишем прямо в перевод ----
    # §c красный (здоровье), §a зелёный (защита), §b голубой (мана) — как у Hypixel
    ui_path = PACKS / LANG / "20-ui.json"
    ui = json.loads(ui_path.read_text(encoding="utf-8"))
    ui["regex"][0]["p"] = (rf"^([\d,]+)/([\d,]+){re.escape(heart)}\s+"
                           rf"([\d,]+){re.escape(shield)} Defense\s+"
                           rf"([\d,]+)/([\d,]+){re.escape(mana)} Mana$")
    ui["regex"][0]["r"] = (f"§c$1/$2{heart}     §a$3{shield} Защита"
                           f"     §b$4/$5{mana} Мана")
    ui["regex"][1]["p"] = (rf"^([\d,]+)/([\d,]+){re.escape(heart)}\s+"
                           rf"([\d,]+)/([\d,]+){re.escape(mana)} Mana$")
    ui["regex"][1]["r"] = f"§c$1/$2{heart}     §b$3/$4{mana} Мана"
    save(ui_path, ui)

    # ---- строки описаний, внутри которых иконка ----
    lore_path = PACKS / LANG / "40-lore.json"
    lore = json.loads(lore_path.read_text(encoding="utf-8"))
    exact = lore["exact"]

    # выкидываем всё, что попало в файл испорченным (текст \uXXXX вместо символа)
    broken = [k for k in exact if re.search(r"\\u[0-9a-fA-F]{4}", k)]
    for key in broken:
        exact.pop(key)
    if broken:
        print(f"убрано испорченных записей: {len(broken)}")

    for key, value in KNOWN_LORE.items():
        exact[key] = value
        print(f"добавлено: {key!r}")

    save(lore_path, lore)

    # ---- проверка: правила совпадают с настоящими строками? ----
    print("\n=== проверка на строках из игры ===")
    ok = True

    ui = json.loads(ui_path.read_text(encoding="utf-8"))
    for key in keys:
        if "Defense" in key and "Mana" in key:
            for rule in ui["regex"]:
                if re.match(rule["p"], key):
                    result = re.sub(rule["p"], rule["r"].replace("$", "\\"), key)
                    print("OK    " + repr(key))
                    print("  ->  " + repr(result))
                    break
            else:
                print("МИМО  " + repr(key))
                ok = False

    lore = json.loads(lore_path.read_text(encoding="utf-8"))["exact"]
    for key in keys:
        if "Increases damage dealt to" in key or "Farming Fortune you" in key:
            if key in lore:
                print("OK    " + repr(key))
            else:
                print("МИМО  " + repr(key))
                ok = False

    # ---- самопроверка регулярки на собранном образце ----
    # Дамп — движущаяся цель, поэтому не полагаемся на него: строим строку сами
    # ровно из тех символов, что видели в игре, и проверяем совпадение.
    sample = f"1,234/1,234{heart}     83{shield} Defense     100/100{mana} Mana"
    matched = False
    for rule in ui["regex"]:
        if re.match(rule["p"], sample):
            print("OK    образец строки над хотбаром совпал")
            print("  ->  " + repr(re.sub(rule["p"], rule["r"].replace("$", "\\"), sample)))
            matched = True
            break
    if not matched:
        print("МИМО  собранный образец не совпал с регуляркой")
        ok = False

    # ---- двойное экранирование: смотрим ТОЛЬКО рабочие поля ----
    # Поля-комментарии (_ и _comment) законно содержат текст \uXXXX как пояснение,
    # поэтому проверять сырой файл нельзя — будет ложная тревога.
    bad_escape = re.compile(r"\\u[0-9a-fA-F]{4}")
    for path in sorted(PACKS.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        used: list[str] = []
        used += list((data.get("exact") or {}).keys())
        used += list((data.get("glossary") or {}).keys())
        for rule in data.get("regex") or []:
            used += [rule.get("p", ""), rule.get("r", "")]
        for value in used:
            if bad_escape.search(value):
                print(f"! {path.name}: в рабочем поле лежит ТЕКСТ {value!r} вместо символа")
                ok = False

    print("\nитог:", "всё сходится" if ok else "есть расхождения, смотри выше")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
