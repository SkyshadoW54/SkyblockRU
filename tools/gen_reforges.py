# -*- coding: utf-8 -*-
"""
Перековки для РЕЖИМА ПОЛНОГО ПЕРЕВОДА: «Fortunate» -> «Удачливый/ая/ое/ые».

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ СЛОВАРЬ, а не пары «перековка + предмет». Их 148 на 5162
имени — перечислить нельзя, это сотни тысяч записей и лишние мегабайты в jar.
Замер по строкам от игроков: заголовков вида «префикс + имя» 10 147, то есть
БОЛЬШЕ, чем обычных имён (6545), и у 9512 перевод основы уже куплен.
Собирает название мод: core/Reforge.java по данным NBT (modifier).

⚠️ ЧЕТЫРЕ ФОРМЫ, потому что префикс согласуется с названием: «Удачливая
кирка», но «Удачливый меч». Род машинно из английского не выводится — тем же
способом устроены редкости (gen_rarity).

    python tools/gen_reforges.py --skeleton   заготовка из списка сервера
    python tools/gen_reforges.py --write      собрать 84-reforges.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ⚠️ Консоль Windows — cp1251, и `print` со значком «⚠️» роняет скрипт
# на первой же находке. Записанная грабля проекта: инструмент, падающий
# на печати, ВРЁТ О СВОЕЙ РАБОТЕ — вывод оборван, а выглядит как поломка
# того, что он проверял. У сторожа это хуже вдвое: он молчит, пока всё
# хорошо, и ломается ровно тогда, когда нашёл беду.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

SKELETON = WORK / "reforges_ru.json"
PACK = PACKS / "ru_ru" / "84-reforges.json"
AUCTION = WORK / "auction_lore.json"
PLAYERS = WORK / "from_players.json"
CATALOG = WORK / "item_names.json"

# Хвост прокачки: звёзды, свитки, значки. Задаём КОДАМИ — записанная грабля:
# диапазон, набранный литералами, схлопывается в буквальный дефис.
STAR = re.compile("[\\s✪➀-➄❁✦⚚☘]+$")
CODES = re.compile("§.")


# ⚠️ РОД СЛОВ НА МЯГКИЙ ЗНАК НЕ ВЫВОДИТСЯ, и гадать тут нельзя: «дрель»
# женского рода, «трюфель» мужского, а окончание у них одно. Поэтому список
# ЯВНЫЙ — ровно как protected.AMBIGUOUS для двойственных имён.
#
# Перечислены ТОЛЬКО те, где мужской род по умолчанию неверен: остальные
# 61 слово на мягкий знак и так мужские, и запись о них была бы шумом.
# Замер: на живых заголовках задето 9 имён, у 4 род определялся неверно
# («Древний дрель Дивана»).
GENDERS = {
    "f": ["благодарность", "брошь", "гиперпечь", "драгоценность", "дрель",
          "какао-сеть", "кость", "кровать", "кровь", "кукла-житель", "медаль",
          "медь", "метель", "морковь", "нить", "обувь", "панель", "печать",
          "плоть", "полироль", "пыль", "рукоять", "скорбь", "слизь", "смесь",
          "суперпечь", "цепь", "челюсть", "ярость"],
    "n": ["печенье-ускоритель"],
}


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def bare(text: str) -> str:
    return STAR.sub("", CODES.sub("", text)).strip()


def norm(word: str) -> str:
    """
    Написание к виду ключа NBT: «Pitchin'» -> «pitchin».

    ⚠️ ПРИТЯЖАТЕЛЬНОЕ «'s» СНИМАЕТСЯ ЦЕЛИКОМ, а не одним апострофом. Сервер
    пишет на экране «Prospector's Iron Pickaxe», а в NBT ключ «prospector» —
    и голое удаление апострофа давало «prospectors», которое с ключом
    не совпадало НИКОГДА. Из-за этого написание бралось из КЛЮЧА, и в словарь
    попадало «Prospector» вместо экранного «Prospector's»: правило не ловило
    строку, хотя формы были готовы. Замер 23.08: так молчали три перековки
    (Prospector's, Lumberjack's, Peasant's) на 34 живых заголовка.
    """
    word = re.sub(r"'s$", "", word.lower())
    return word.replace("'", "").replace("-", "").replace("_", "").replace(" ", "")


def server_keys() -> set[str]:
    """Перековки, которые назвал САМ Hypixel (NBT живых лотов)."""
    data = load(AUCTION, {})
    return {m for row in data.get("items", {}).values()
            for m in row.get("modifiers", []) if m and m != "none"}


def spellings() -> dict[str, int]:
    """Как перековка НАПИСАНА в заголовке — берём из живых строк от игроков.

    ⚠️ Написание берём из НАЗВАНИЯ, а не выводим из ключа NBT: там «pitchin»,
    а на экране «Pitchin'». Ключ служит лишь подтверждением, что первое слово —
    перековка, а не часть имени.
    """
    catalog = set(load(CATALOG, {}).get("names", {}).values())
    keys = {norm(k) for k in server_keys()}
    seen: dict[str, int] = {}
    for raw, count in (load(PLAYERS, {}).get("item_name") or {}).items():
        name = bare(raw)
        parts = name.split(" ", 1)
        if len(parts) != 2 or parts[1] not in catalog:
            continue
        if norm(parts[0]) in keys:
            number = count if isinstance(count, int) else 1
            seen[parts[0]] = seen.get(parts[0], 0) + number
    return seen


def forms_from(male: str) -> list[str]:
    """Достроить женский, средний и множественный род по мужскому.

    Правила русского прилагательного механические, а результат ПОЛНОСТЬЮ
    просматривается глазами (148 слов), поэтому гадания тут нет: спорное
    правится в заготовке вручную полем «forms».
    """
    if male.endswith("ний"):
        stem = male[:-2]
        return [male, stem + "яя", stem + "ее", stem + "ие"]
    # ⚠️ После к/г/х средний род на «-ое» («Лёгкое», «Мифическое»), а после
    # шипящих — на «-ее» («Хорошее», «Могучее»). Одно правило на обе группы
    # давало «Лёгкее», и увидеть это можно было только глазами: формы
    # для того и просматриваются целиком.
    if male.endswith(("кий", "гий", "хий")):
        stem = male[:-2]
        return [male, stem + "ая", stem + "ое", stem + "ие"]
    if male.endswith(("ший", "щий", "чий", "жий")):
        stem = male[:-2]
        return [male, stem + "ая", stem + "ее", stem + "ие"]
    if male.endswith("ый"):
        stem = male[:-2]
        return [male, stem + "ая", stem + "ое", stem + "ые"]
    if male.endswith("ой"):
        stem = male[:-2]
        return [male, stem + "ая", stem + "ое", stem + "ые"]
    if male.endswith("ий"):
        stem = male[:-2]
        return [male, stem + "яя", stem + "ее", stem + "ие"]
    return [male, male, male, male]


def do_skeleton() -> int:
    old = load(SKELETON, {}) or {}
    ready = old.get("reforges", {})
    seen = spellings()

    # Перековки, ни разу не встреченные префиксом: написание выводим из ключа.
    # Это догадка не о переводе, а о том, как Hypixel напишет слово, — а он
    # пишет его с заглавной. Встретится живьём — заготовка поправится сама.
    known_norm = {norm(w) for w in seen}
    guessed = []
    for key in sorted(server_keys()):
        if norm(key) in known_norm:
            continue
        guessed.append(" ".join(part.capitalize() for part in key.split("_")))

    fresh: dict[str, dict] = {}
    for word in sorted(seen, key=lambda w: (-seen[w], w)):
        row = {"ru": ready.get(word, {}).get("ru", ""), "seen": seen[word]}
        if "forms" in ready.get(word, {}):
            row["forms"] = ready[word]["forms"]
        fresh[word] = row
    for word in sorted(set(guessed)):
        row = {"ru": ready.get(word, {}).get("ru", ""), "seen": 0}
        if "forms" in ready.get(word, {}):
            row["forms"] = ready[word]["forms"]
        fresh[word] = row

    save(SKELETON, {
        "_comment": "Перековки для режима полного перевода. ИСТОЧНИК ПРАВДЫ — "
                    "этот файл, словарь 84-reforges.json собирается из него. "
                    "Заполняй поле ru МУЖСКИМ родом («Удачливый») — остальные "
                    "три формы генератор достроит. Если слово нестандартное, "
                    "задай все четыре явно полем forms: [м, ж, с, мн]. "
                    "Порядок — по числу заголовков, где перековка встречалась.",
        "reforges": fresh,
    })
    done = sum(1 for row in fresh.values() if row["ru"])
    print(f"перековок: {len(fresh)} (встречались префиксом: {len(seen)}, "
          f"написание выведено из ключа: {len(set(guessed))})")
    print(f"  переведено {done}, ждут {len(fresh) - done}")
    top = [w for w, r in fresh.items() if not r["ru"]][:10]
    print("  верхушка:", ", ".join(top))
    return 0


def do_write() -> int:
    data = load(SKELETON, {}) or {}
    rows = data.get("reforges", {})
    out: dict[str, list[str]] = {}
    for word, row in rows.items():
        if row.get("forms"):
            forms = row["forms"]
        elif row.get("ru"):
            forms = forms_from(row["ru"])
        else:
            continue
        if len(forms) != 4 or any(not f for f in forms):
            print(f"⚠️ {word}: форм {len(forms)} — нужно четыре")
            return 1
        out[word] = forms
    if not out:
        print("переведённых перековок нет — писать нечего")
        return 1

    # ⚠️ Две перековки с одинаковым переводом — беда: от перековки зависят
    # числа вещи, и по подсказке игрок не поймёт, чем она перекована.
    back: dict[str, list[str]] = {}
    for word, forms in out.items():
        back.setdefault(forms[0], []).append(word)
    clashes = {ru: ws for ru, ws in back.items() if len(ws) > 1}
    if clashes:
        print(f"⚠️ ОДИН ПЕРЕВОД У РАЗНЫХ ПЕРЕКОВОК: {len(clashes)}")
        for russian, words in sorted(clashes.items())[:10]:
            print(f"   {russian!r} <- {words}")
        return 1

    pack = {
        "id": "reforges",
        "priority": 63,
        "default": False,
        "group": "full",
        "about": "перековки в названиях вещей (Fortunate Lapis Pickaxe -> "
                 "Удачливая лазуритовая кирка). По умолчанию выключено: "
                 "по английскому названию вещь ищут на аукционе",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_reforges.py из "
                    "data/work/reforges_ru.json — правь заготовку. "
                    "ЧЕТЫРЕ ФОРМЫ на перековку: [мужской, женский, средний, "
                    "множественный]. Род названия мод выводит сам "
                    "(core/Reforge.genderOf), а склеивает половины по данным "
                    "NBT: сервер сам говорит, перекована ли вещь.",
        "only": ["item_name"],
        "reforges": dict(sorted(out.items())),
        # Род названия мод выводит по окончанию, а тут — исключения,
        # которые окончанием не выводятся вовсе.
        "genders": {word: gender
                    for gender, words in GENDERS.items() for word in sorted(words)},
    }
    save(PACK, pack)
    print(f"записано {PACK.name}: {len(out)} перековок")
    print("⚠️ впиши файл в packs/index.json, иначе он молча не загрузится")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeleton", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.skeleton:
        return do_skeleton()
    if args.write:
        return do_write()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
