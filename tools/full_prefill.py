# -*- coding: utf-8 -*-
"""
Предзаполнение режимного абзаца: подставить русский термин И СКЛОНИТЬ его.

Режимная версия отличается от обычной ровно одним — термином. Значит и
подстановка, и падеж выводятся МЕХАНИЧЕСКИ, если знать две вещи:

  * русскую форму термина — её берём у самих режимных словарей
    (`gen_jargon_forms`, `77-sb-enchants`), а не выдумываем;
  * УПРАВЛЯЮЩЕЕ СЛОВО перед термином — «к» требует дательного, «Даёт +5»
    и «расходуя 3» родительного, а после двоеточия термин стоит в списке
    и остаётся именительным.

⚠️ Это НЕ «машина угадывает падеж». Падеж тут задаёт предлог или глагол,
и он в тексте есть — гадать нечего. Склоняется только ГЛАВНОЕ слово
(«Удача» -> «Удачи»), остальное остаётся: «Удачи фермера», «Удаче фермера».
Формы главных слов перечислены ЯВНО (`HEADS`): их два десятка, и это
честнее, чем правило по окончанию.

⚠️ Термин ВНУТРИ СОСТАВНОГО ИМЕНИ не трогаем: «Odger's Blessing» — имя
набора, и половинный перевод даёт «Odger's Благословение». Признак тот же,
что у `gen_full_paragraphs.standalone`.

⚠️ ГРАНИЦА СЛОВА обязательна: без неё «Heat» находится внутри «Heated
Bonus» и даёт «Жарed Bonus». Записанная грабля проекта.

    python tools/full_prefill.py data/work/full_b2.json
    python tools/full_prefill.py data/work/full_b2.json --show 20
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
PACKS = ROOT / "src/main/resources/assets/skyblockru/packs/ru_ru"

import gen_jargon_forms as jargon  # noqa: E402

CODE = re.compile("§.")
ROMAN = re.compile(r"[IVXLC]{1,6}$")
# ⚠️ Хвост перед термином чистим от ЛЮБЫХ знаков, а не от списка значков:
# Hypixel берёт под иконки и приватную зону, и обычный юникод («☯», «⸕»),
# и буквы чужих алфавитов. Список тут устарел бы молча — а от него зависит,
# найдём ли мы управляющее слово и, значит, падеж.
TAIL = re.compile(r"[^0-9A-Za-zА-Яа-яЁё}:%.]+$")
# То же для начала строки, но фигурная скобка значима — её бережём.
LEAD = re.compile(r"^[^0-9A-Za-zА-Яа-яЁё{+-]+")

# Главное слово термина и его формы: родительный, дательный.
# Перечислено ЯВНО — правило по окончанию ошибается («Жар» и «Удача»
# кончаются по-разному, а «Скорость» и «Мудрость» склоняются одинаково).
HEADS = {
    "Удача": ("Удачи", "Удаче", "Удачу"),
    "Мудрость": ("Мудрости", "Мудрости", "Мудрость"),
    "Скорость": ("Скорости", "Скорости", "Скорость"),
    "Шанс": ("Шанса", "Шансу", "Шанс"),
    "Разброс": ("Разброса", "Разбросу", "Разброс"),
    "Размах": ("Размаха", "Размаху", "Размах"),
    "Сила": ("Силы", "Силе", "Силу"),
    "Свирепость": ("Свирепости", "Свирепости", "Свирепость"),
    "Живучесть": ("Живучести", "Живучести", "Живучесть"),
    "Чистота": ("Чистоты", "Чистоте", "Чистоту"),
    "Жар": ("Жара", "Жару", "Жар"),
    "Отслеживание": ("Отслеживания", "Отслеживанию", "Отслеживание"),
    "Притяжение": ("Притяжения", "Притяжению", "Притяжение"),
    "Страх": ("Страха", "Страху", "Страх"),
    "Урон": ("Урона", "Урону", "Урон"),
    "Здоровье": ("Здоровья", "Здоровью", "Здоровье"),
    "Интеллект": ("Интеллекта", "Интеллекту", "Интеллект"),
    "Время": ("Времени", "Времени", "Время"),
    "Восстановление": ("Восстановления", "Восстановлению", "Восстановление"),
    "Магический": ("Магического", "Магическому", "Магический"),
    "поиск": ("поиска", "поиску", "поиск"),
    "Редкий": ("Редкого", "Редкому", "Редкий"),
    "урожай": ("урожая", "урожаю", "урожай"),
    "Доп.": ("Доп.", "Доп.", "Доп."),
    "шанс": ("шанса", "шансу", "шанс"),
}
# Составные, у которых склоняются ДВА первых слова.
PAIRS = ("Магический поиск", "Редкий урожай", "Доп. шанс")

# Что перед термином требует ВИНИТЕЛЬНОГО падежа: «повысить свою Удачу»,
# «дать дополнительную Скорость». Форма чаще всего совпадает с именительным
# («Мудрость», «Шанс»), и отличаются всего три слова — но эти три встречаются
# чаще прочих.
ACCUSATIVE = ("свою", "свой", "своё", "дополнительную", "дополнительный",
              "дополнительное", "бонусную", "бонусный", "повышает", "повысить",
              "увеличивает", "увеличить", "поднимает", "поднять", "повышай",
              "увеличивай", "поднимай")

# Что перед термином требует родительного падежа.
GENITIVE = ("даёт", "дают", "получаешь", "получить", "получает", "получаете",
            "ограничено", "расходуя", "бонусы", "бонус", "дополнительно",
            "прибавляет", "добавляет", "прибавь", "уровень", "уровня",
            "усиление", "звуки", "звук", "меньше", "больше", "прирост",
            "запас", "событий", "события", "уровнем", "штук")


def table() -> dict[str, str]:
    """Русская форма каждого термина режима."""
    names = dict(jargon.known())
    for name, russian in jargon.EXTRA.items():
        names.setdefault(name, russian)
    enchants = json.loads((PACKS / "77-sb-enchants.json").read_text(encoding="utf-8"))
    for name, russian in (enchants.get("glossary") or {}).items():
        if isinstance(russian, str) and russian != name:
            names.setdefault(name, russian)
    return names


def decline(russian: str, case: int) -> str:
    """Склонить ГЛАВНОЕ слово. case: 1 родительный, 2 дательный, 3 винительный."""
    if case == 0:
        return russian
    for pair in PAIRS:
        if russian.startswith(pair):
            first, second = pair.split(" ", 1)
            if first in HEADS and second in HEADS:
                head = HEADS[first][case - 1] + " " + HEADS[second][case - 1]
                return head + russian[len(pair):]
    words = russian.split(" ", 1)
    head = HEADS.get(words[0])
    if not head:
        return russian
    return head[case - 1] + (" " + words[1] if len(words) > 1 else "")


def label_ahead(after: str) -> bool:
    """Сразу за термином идёт ЗНАЧЕНИЕ — значит это подпись, не дополнение.

    ⚠️ Без этого «☯ Мудрость воина {n} ☯ Мудрость фермера {n}» выходило
    вперемешку: первую подпись машина оставляла в именительном, а вторую
    склоняла — перед ней стоит `{n}` от ПРЕДЫДУЩЕЙ пары. Читается такое
    столбиком, и разнобой там виден сразу.
    """
    # ⚠️ Чистим ТОЛЬКО коды и незначащие знаки, а фигурную скобку оставляем:
    # с ней «{n}» и распознаётся как значение. Первая версия срезала «{»
    # заодно с пробелом — и подпись со значением опять склонялась.
    head = LEAD.sub("", CODE.sub("", after))
    return bool(re.match(r"(\{[ns]\}|[+\-]?\d)", head))


def case_of(before: str) -> int:
    """Какой падеж требует то, что стоит ПЕРЕД термином."""
    tail = TAIL.sub("", CODE.sub("", before))
    if not tail:
        return 0
    if tail.endswith(":") or tail.endswith("—") or tail.endswith("-"):
        return 0
    word = re.search(r"([A-Za-zА-Яа-яЁё\.]+|\}|\d)$", tail)
    if not word:
        return 0
    last = word.group(1).lower()
    if last == "к":
        return 2
    if last in ("}", "%") or last.isdigit():
        return 1
    if last in ACCUSATIVE:
        return 3
    if last in GENITIVE:
        return 1
    return 0


def swap(text: str, name: str, russian: str) -> str:
    """Заменить термин, склонив его по управляющему слову."""
    plain, index = [], []
    i = 0
    while i < len(text):
        match = CODE.match(text, i)
        if match:
            i = match.end()
            continue
        plain.append(text[i])
        index.append(i)
        i += 1
    flat = "".join(plain)
    for found in re.finditer(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])",
                             flat):
        before = flat[:found.start()].rstrip()
        previous = re.search(r"([A-Za-z']+)$", before)
        if previous and previous.group(1).lstrip("'")[:1].isupper():
            continue
        after = flat[found.end():].lstrip()
        nxt = re.match(r"([A-Za-z]+)", after)
        if nxt and nxt.group(1)[0].isupper() and not ROMAN.match(nxt.group(1)):
            continue
        at, stop = found.start(), found.end()
        # ⚠️ Управляющее слово ищем В ИСХОДНОЙ строке: между числом и термином
        # стоит ЗНАЧОК приватной зоны, и без его снятия падеж определится
        # неверно. Записанная грабля — значок в терминале невидим.
        rest = text[index[stop - 1] + 1:]
        case = 0 if label_ahead(rest) else case_of(text[:index[at]])
        word = decline(russian, case)
        head, tail = text[:index[at]], rest
        # ⚠️ Термин в абзаце встречается НЕСКОЛЬКО раз («Ступени I–III: … .
        # Ступени IV и V: …»), и остановка на первом оставляла второй
        # английским — половина строки по-русски, половина нет.
        return head + word + swap(tail, name, russian)
    return text


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Предзаполнить режимные абзацы")
    parser.add_argument("task", help="файл задания от --export")
    parser.add_argument("--show", type=int, default=0, help="показать N строк")
    args = parser.parse_args()

    path = Path(args.task)
    task = json.loads(path.read_text(encoding="utf-8"))
    names = table()
    changed, left = 0, []
    for item in task:
        text = item["base"]
        for name in sorted(names, key=len, reverse=True):
            text = swap(text, name, names[name])
        item["ru"] = text
        if text == item["base"]:
            left.append(item)
        else:
            changed += 1
    path.write_text(json.dumps(task, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"подставлено и склонено: {changed} из {len(task)}")
    if left:
        print(f"термин не подставился (смотреть глазами): {len(left)}")
        for item in left[:6]:
            print(f"   {','.join(item.get('terms') or [])[:26]:<26} "
                  f"{item['base'][:70]}")
    for item in task[:args.show]:
        print("   " + item["ru"][:150].replace("§", "&"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
