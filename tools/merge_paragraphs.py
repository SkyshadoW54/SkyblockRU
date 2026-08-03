"""
Переносит переведённые АБЗАЦЫ из корпуса в словарь мода.

В отличие от построчного merge_tooltips тут ничего разбирать не надо: ключ
абзаца и есть то, что мод построит в игре (Paragraphs.key), а значение —
готовый перевод целиком. Мод сам разложит его по строкам нужной ширины.

⚠️ Ключи обязаны совпадать с тем, что строит мод, буква в букву. Сторожит это
tools/check_contract.py — он и запускается в конце.

Секция `only` — только описания предметов: абзацы собраны из подсказок,
и применять их к чату или боковой панели незачем.

Запуск:
  python tools/merge_paragraphs.py
  python tools/merge_paragraphs.py --out 96-paragraphs.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
INDEX = PACKS / "index.json"

# Словари разложены по языкам: packs/<язык>/. Этот скрипт делает русский.
LANG = "ru_ru"



# Уровень зачарования римскими: «Growth V», «Bane of Arthropods VII»
ROMAN = r"(?:[IVXLC]{1,6})"

# Чужая подстановка из выгрузки NEU — движок знает только {n} и {s}


HOLE = re.compile(r"\{[^{}]*\}|\{\{[^{}]*\}\}")


def has_foreign_hole(text: str) -> bool:
    """
    В тексте есть подстановка, которой движок НЕ ЗНАЕТ?

    Движок понимает ровно две: {n} — число, {s} — ник. Всё остальное в фигурных
    скобках приехало из выгрузки NEU, и в игре такой строки не бывает вовсе:
    ключ не совпадёт НИКОГДА, перевод уходит в стол.

    Пород две, и вторую я сперва не заметил:
      {INTELLIGENCE}  — именованная подстановка NEU;
      {{n}}           — её же {0}, внутрь которого попало наше обобщение чисел.
    Проверка «есть ли [A-Z_]» вторую не ловила: там внутри обычное {n}.
    Поэтому судим не по виду дырки, а по списку разрешённых.
    """
    return any(hole not in ("{n}", "{s}") for hole in HOLE.findall(text))


def enchant_names() -> dict[str, str]:
    """
    Название зачарования -> перевод. Из правил вида ^Name ([IVXLC]+)$.

    ⚠️ ВЫКЛЮЧЕННЫЕ словари не читаем, и это не мелочь. `sb_enchants` выключен
    по умолчанию — по английским названиям ищут вещи на аукционе. А сборка
    брала оттуда пары и «подтягивала» переводы: в корпусе лежит правильное
    «Growth V Даёт +{n} к здоровью», а в словарь мода уезжало «Рост V Даёт…».
    На экране игрок видел русское название зачарования при выключенном
    переключателе — то есть его решение обходили при СБОРКЕ, молча.

    Замер на живом корпусе: 39 абзацев. В самом корпусе слова «Рост» нет
    ни разу — оно рождалось здесь.

    **Это ТРЕТИЙ раз, когда утечка выключенного словаря лезет через генератор**
    (были очередь строк и gen_stat_forms, оба записаны в граблях). Мораль там
    же и написана: генератор, читающий словари, обязан спрашивать, включены ли
    они. Проверять надо КАЖДЫЙ такой генератор, а не тот, где беду заметили.
    """
    found: dict[str, str] = {}
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if pack.get("default") is False:
            continue
        for rule in pack.get("regex") or []:
            match = re.match(r"\^(.+?) \(\[IVXLC\]", rule.get("p", ""))
            if match:
                target = re.sub(r"(?:\s*\$\d)+\s*$", "", rule.get("r", "")).strip()
                if target:
                    found.setdefault(match.group(1).replace("\\", ""), target)
    return found


def keep_enchants_consistent(text: str, translated: str,
                             names: dict[str, str]) -> tuple[str, int]:
    """
    Дотягивает зачарования, которые модель оставила английскими.

    Зачем. Модель переводит «Growth V» то как «Рост V», то оставляет как есть —
    и одно и то же зачарование выходит русским в одной подсказке и английским
    в соседней. Построчный путь его переводит всегда, так что расходится
    абзац именно с самим модом.

    Значение вида «@enchantment.minecraft.protection» подставляется КАК ЕСТЬ:
    движок разворачивает @ключи внутри перевода сам, беря официальное название
    из самой игры. Если игра ключа не знает, перевод абзаца просто не применится —
    это безопасный отказ, а не дыра на экране.

    Длинные названия вперёд: «Fire Protection» должен победить «Protection».
    """
    fixed = 0
    for name in sorted(names, key=len, reverse=True):
        pattern = rf"(?<![A-Za-z]){re.escape(name)} ({ROMAN})(?![A-Za-z])"
        if not re.search(pattern, text):
            continue

        def swap(match: re.Match, target: str = names[name]) -> str:
            # ВНИМАНИЕ. Перед именем не должно стоять ЕЩЁ ОДНО слово с заглавной.
            # Иначе подтяжка лезет внутрь составного имени: «Trophy Hunter V»
            # превращалось в «Trophy Охотник V», потому что «Hunter» — известное
            # зачарование. Та же беда, что «Depth Чемпион» в глоссарии, только
            # сделанная уже мной. Два заглавных слова подряд — это имя целиком.
            before = match.string[:match.start()].rstrip()
            previous = re.search(r"([A-Za-z]+)$", before)
            if previous and previous.group(1)[0].isupper():
                return match.group(0)
            return f"{target} {match.group(1)}"

        translated, count = re.subn(pattern, swap, translated)
        fixed += count
    return translated, fixed


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Перенос переведённых абзацев в словарь")
    parser.add_argument("--file", default="paragraphs.json", help="корпус в data/work")
    parser.add_argument("--out", default="96-paragraphs.json", help="имя словаря в packs/<язык>/")
    args = parser.parse_args()

    source = WORK / args.file
    if not source.exists():
        print(f"нет корпуса: {source}")
        return 1

    paragraphs = json.loads(source.read_text(encoding="utf-8")).get("paragraphs") or []
    done = [p for p in paragraphs if p.get("ru")]
    print(f"абзацев в корпусе: {len(paragraphs)}, переведено: {len(done)}")
    if not done:
        print("переносить нечего")
        return 1

    # Ключ -> перевод. Дубликатов быть не может: корпус их схлопывает,
    # но проверим на всякий случай — молчаливая потеря тут недопустима.
    names = enchant_names()
    elsewhere: set[str] = set()
    for path in PACKS.rglob("*.json"):
        if path.name in ("index.json", args.out):
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        elsewhere.update(k for k, v in (pack.get("exact") or {}).items() if v)
    table: dict[str, str] = {}
    clashes = 0
    tightened = 0
    foreign = 0
    for para in done:
        key, value = para["text"], para["ru"]
        if has_foreign_hole(key) or has_foreign_hole(value):
            # Подстановка, которой движок не знает: ключ не совпадёт никогда,
            # а в мод такая запись попадать не должна вовсе.
            foreign += 1
            continue
        value, fixed = keep_enchants_consistent(key, value, names)
        tightened += fixed
        if key in table and table[key] != value:
            clashes += 1
        table[key] = value
    if clashes:
        print(f"! одинаковый абзац с разным переводом: {clashes} — взят последний")
    if foreign:
        print(f"не выпущено в мод (чужая подстановка NEU): {foreign}")
    if tightened:
        print(f"зачарований подтянуто к словарю: {tightened}")

    out = PACKS / LANG / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    # ⚠️ ТЕ ЖЕ записи кладём и в exact.
    #
    # Абзац — это склейка нескольких строк, и мод спрашивает его только когда
    # строк ДВЕ и больше. Но ширина окна у игрока своя: то, что в выгрузке NEU
    # занимало две строки, у него помещается в одну. Тогда абзацем это уже
    # не считается, а построчный поиск секцию paragraphs не читает — перевод
    # лежит в словаре и недостижим. Так пропала «Your arrows have a magical
    # shine!»: в корпусе она из двух строк, на экране из одной.
    #
    # Длинные записи в exact просто не совпадут (целой строкой они не бывают),
    # так что это чистое дополнение, а не риск.
    pack = {
        "id": "paragraphs",
        # ⚠️ Кроме тех, что уже лежат точной записью в ДРУГОМ словаре: там
        # они переведены осознанно и, как правило, короче. Две записи на одну
        # строку — это спор, который решается номером файла, а не качеством.
        "exact": {k: v for k, v in table.items() if k not in elsewhere},
        "priority": 21,
        "_comment": "Переводы АБЗАЦЕВ целиком. Собирается автоматически из "
                    "data/work/paragraphs.json — правь корпус, а не этот файл. "
                    "Ключ равен тому, что мод склеивает из строк подсказки "
                    "(Paragraphs.key); совпадение сторожит tools/check_contract.py.",
        "only": ["item_lore"],
        "paragraphs": table,
    }
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"записано: {out.relative_to(ROOT)}  ({len(table)} абзацев)")

    # Не вписал в index.json — молча не загрузится. Эта грабля в проекте уже была.
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    listing = index.setdefault("languages", {}).setdefault(LANG, [])
    if out.name not in listing:
        listing.append(out.name)
        listing.sort()
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"добавил {out.name} в index.json ({LANG})")
    else:
        print(f"{out.name} уже в index.json")

    covered = sum(p.get("count") or 1 for p in done)
    total = sum(p.get("count") or 1 for p in paragraphs)
    print(f"покрытие: {covered * 100 // total}% вхождений в подсказках")

    print("\n=== сверка ключей с модом ===")
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "check_contract.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in (result.stdout or "").splitlines():
        if "недостижим" in line or "итого" in line or "НЕДОСТИЖИМО" in line:
            print(" ", line.strip())
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
