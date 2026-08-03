"""
Возвращает РАЗМЕТКУ ЦВЕТОМ, подменяя термин заменой вместо покупки перевода.

⚠️ Зачем этот инструмент вообще появился. Чтобы сделать термин английским
(«магический поиск» → «Magic Find»), я отправил 157 абзацев на повторный
перевод за $7.5. Это была ошибка: перевод вернулся ЧИСТЫМ ТЕКСТОМ, то есть
§-коды разметки пропали, а часть формулировок стала хуже («Renowned Бонус»
вместо вычитанного «Бонус Renowned»).

Замена делает то же самое даром и ЛУЧШЕ:

    было : §7§9Бонус Renowned§7 Повышает все §cбоевые§7 …и §bмагический поиск§7
    стало: §7§9Бонус Renowned§7 Повышает все §cбоевые§7 …и §bMagic Find§7

Причина простая: английское слово НЕ СКЛОНЯЕТСЯ. Русский термин в любом падеже
уступает ему место, а соседние слова менять не нужно — «за каждые {n} Magic
Find», «и Magic Find на +{n}%». Это ровно обратный случай к записанному в
граблях: там мы меняли РУССКОЕ на РУССКОЕ («дыни» → «арбузы») и ломали падежи,
потому что у русского слова есть род и склонение. У латиницы их нет.

⚠️ Остаётся один класс мест, где замена всё-таки коробит: согласованное
прилагательное перед термином («повышенная Удача шахтёра» → «повышенная Mining
Fortune»). Их немного, и скрипт их показывает отдельно — смотреть глазами.

Запуск:
  python tools/restore_by_replace.py              сухой прогон
  python tools/restore_by_replace.py --yes        применить
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"

# Падежные формы русского термина -> английский оригинал.
#
# ⚠️ Формы перечислены ЯВНО, а не выведены морфологией: источник правды —
# наш собственный текст, а не словарь русского языка. Это уже записанное
# решение проекта, и оно тут работает как нельзя лучше — форм у термина
# считанные единицы, и все они на виду.
# ⚠️ Между словами термина бывают §-КОДЫ, а не только пробел: Hypixel красит
# слова по отдельности, и в переводе лежит «§bМагического§7 §bпоиска§7».
# Обычный \s+ такое не ловит, и один абзац пережил три захода замены подряд.
# Та же грабля уже записана про поиск строки целиком: коды живут ВНУТРИ текста.
SEP = r"(?:§.|\s)+"

FORMS: list[tuple[str, str]] = [
    (r"[Мм]агическ(?:ий|ого|ому|им|ом)" + SEP + r"поиск(?:а|у|ом|е)?", "Magic Find"),
    (r"[Сс]вирепост(?:ь|и|ью|ей)", "Ferocity"),
    (r"[Уу]дач(?:а|и|е|у|ей)" + SEP + r"питомцев", "Pet Luck"),
    (r"[Шш]анс(?:а|у|ом|е)?" + SEP + r"сокровищ", "Treasure Chance"),
    (r"[Шш]анс(?:а|у|ом|е)?" + SEP + r"морских" + SEP + r"существ", "Sea Creature Chance"),
    (r"[Цц]ветени(?:е|я|ю|ем|и)", "Overbloom"),
    (r"[Рр]едки(?:й|ого|ому|им|ом)" + SEP + r"урожа(?:й|я|ю|ем|е)", "Overbloom"),
    # ⚠️ «Чистота» пишется и с предлогом («+{n} к чистоте»), поэтому дательный
    # падеж обязателен. Нашлось это не рассуждением, а проверкой остатка:
    # после первого прохода осталось 8 таких абзацев.
    (r"[Чч]истот(?:а|ы|е|у|ой)", "Pristine"),
]

# Прилагательное перед термином согласовано по роду русского слова, а латиница
# рода не имеет: «повышенная Mining Fortune» читается коряво. Ловим и показываем.
ADJECTIVE = re.compile(r"\b\w+(?:ая|ой|ую|ые|ым|ого|ому|ий|ая)\s+$")


def replace(text: str) -> str:
    for pattern, target in FORMS:
        text = re.sub(pattern, target, text)
    return text


def fix_rest(data: dict, apply: bool) -> int:
    """
    Дочищает остаток: термин остался русским, а разметки в старой версии не было.

    ⚠️ Сравниваем по тексту БЕЗ §-кодов. Иначе «§bMagic Find» считается
    непереведённым: перед словом стоит латинская «b» из кода, и граница слова
    не срабатывает. Та же грабля уже записана про check_translation.
    """
    strip = re.compile("§.")
    fixed = 0
    for para in data["paragraphs"]:
        russian = para.get("ru") or ""
        if not russian:
            continue
        after = replace(russian)
        if after != russian:
            para["ru"] = after
            fixed += 1
    print(f"дочищено заменой: {fixed}")
    if not apply:
        print()
        print("сухой прогон — ничего не изменено. Применить: --yes")
        return 0
    CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"записан {CORPUS.name}. Дальше: python tools/merge_paragraphs.py")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="вернуть разметку заменой термина")
    parser.add_argument("--from", dest="source", default="",
                        help="корпус ДО повторного перевода (там цела разметка)")
    parser.add_argument("--rest", action="store_true",
                        help="просто заменить термин во ВСЕХ переводах, где он остался русским")
    parser.add_argument("--yes", action="store_true", help="применить")
    args = parser.parse_args()

    data = json.loads(CORPUS.read_text(encoding="utf-8"))

    if args.rest:
        return fix_rest(data, args.yes)

    source = Path(args.source)
    if not args.source or not source.exists():
        print(f"нет файла: {source or '(--from не задан)'}")
        return 1

    old = {p["text"]: p.get("ru", "")
           for p in json.loads(source.read_text(encoding="utf-8"))["paragraphs"]}

    restored = 0
    kept = 0
    awkward: list[str] = []

    for para in data["paragraphs"]:
        was = old.get(para["text"], "")
        if not was or "§" not in was:
            continue  # в старой версии разметки не было — возвращать нечего
        now = para.get("ru", "")
        if now and "§" in now:
            kept += 1
            continue  # разметка на месте, не трогаем
        fixed = replace(was)
        if fixed == was and not now:
            # термина в нём не было вовсе, но перевод потерялся — вернём как есть
            pass
        for pattern, _ in FORMS:
            for match in re.finditer(pattern, was):
                head = was[:match.start()]
                if ADJECTIVE.search(head):
                    awkward.append(fixed[:100])
                    break
        para["ru"] = fixed
        restored += 1

    print(f"вернул разметку заменой : {restored}")
    print(f"разметка и так на месте : {kept}")
    if awkward:
        print(f"⚠️ смотреть глазами (прилагательное перед термином): {len(awkward)}")
        for line in awkward[:5]:
            print("   " + line)

    if not args.yes:
        print()
        print("сухой прогон — ничего не изменено. Применить: --yes")
        return 0

    CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(f"записан {CORPUS.name}. Дальше: python tools/merge_paragraphs.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
