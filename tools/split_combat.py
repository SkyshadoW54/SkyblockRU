# -*- coding: utf-8 -*-
"""Термины с Combat: в обычном режиме английские, в режиме full — русские.

Решение игрока 28.08: «combat stats и всё, что связано с комбат, переводи
в режиме full на русский. В обычном режиме оставляй combat на английском».

⚠️ СВЕДЕНИЕ — ЭТО ДВЕ ПОЛОВИНЫ, и вторую легко забыть: убрать русское из
обычного словаря И добавить русскую пару в режимный. Сделав только первую,
получаешь английский в ОБОИХ режимах, то есть решение не выполнено ни для
одного (замер 28.08: так вышло с «Опыт Combat»).

⚠️ ПАРЫ ВЗЯТЫ ИЗ ДАННЫХ, а не выдуманы: так эти термины уже переведены
в режимных словарях. Свой список разошёлся бы с ними при первой правке.

    python tools/split_combat.py          сухой прогон
    python tools/split_combat.py --yes    применить
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src/main/resources/assets/skyblockru/packs/ru_ru"

# русская форма -> английский термин. Порядок ВАЖЕН: длинные раньше коротких,
# иначе короткая съест хвост длинной (записанная грабля про «ПКМ С ШИФТОМ»).
PAIRS: list[tuple[str, str]] = [
    ("Ускорение опыта боя", "Combat Exp Boost"),
    ("Ускоритель опыта боя", "Combat XP Boost"),
    ("Бонус мудрости воина", "Combat Wisdom Boost"),
    # ⚠️ У форм одного термина ИМЕНИТЕЛЬНЫЙ идёт ПЕРВЫМ: обратная замена
    # берёт первую подходящую, и «Combat Wisdom: +3» иначе даёт «Мудрости
    # воина: +3» вместо «Мудрость воина: +3».
    ("Мудрость воина", "Combat Wisdom"),
    ("Мудрости воина", "Combat Wisdom"),
    ("боевые характеристики", "Combat Stats"),
    ("боевых характеристик", "Combat Stats"),
    ("боевым характеристикам", "Combat Stats"),
    ("Боевой торговец", "Combat Merchant"),
    ("Боевое обличье", "Combat Morph"),
    ("Боевое поселение", "Combat Settlement"),
    ("Боевой питомец", "Combat Pet"),
    ("Боевой талисман", "Combat Talisman"),
    ("боевой мешок", "Combat Sack"),
    ("Уровень боя", "Combat Level"),
    ("уровень боя", "Combat Level"),
    ("уровня боя", "Combat Level"),
    ("уровню боя", "Combat Level"),
    ("навык Бой", "Combat Skill"),
    ("навыка боя", "Combat Skill"),
    ("навыку боя", "Combat Skill"),
    ("Опыт боя", "Combat XP"),
    ("опыт боя", "Combat XP"),
    ("опыта боя", "Combat XP"),
    ("опыту боя", "Combat XP"),
]

# ⚠️ БЕЗ \b: §-код кончается ЦИФРОЙ, и границы слова между «§3» и «опыта»
# НЕТ — записанная грабля проекта, наступали четырежды.
LEFT = r"(?<![а-яА-ЯёЁa-zA-Z])"
RIGHT = r"(?![а-яА-ЯёЁ])"


# английское слово с Заглавной рядом — признак СОСТАВНОГО имени
NEIGHBOUR = re.compile(r"[A-Z][A-Za-z']*")
ROMAN = re.compile(r"^[IVXLCDM]+$")


def standalone(text: str, start: int, end: int) -> bool:
    """Целый ли это термин, а не кусок длинного имени.

    ⚠️ Записанная грабля проекта: подстановка по ЧАСТИ имени даёт смесь
    языков — «Combat XP Boost I Potion» -> «опыту боя Boost I Potion».
    Признак от соседа: английское слово с Заглавной вплотную справа или
    слева значит, что имя длиннее найденного куска. Римская цифра
    соседом НЕ считается («Уровень боя IX» законна).
    """
    right = re.sub("§.", "", text[end:]).strip().split()
    # ⚠️ Римский уровень СЛЕДУЕТ ПРОПУСТИТЬ, а не остановиться на нём:
    # у «Combat XP Boost I Potion» справа стоит «I», а за ней «Potion» —
    # то есть имя длиннее. Иначе выходит «Ускоритель опыта боя I Potion».
    while right and ROMAN.match(right[0].strip(".,!?:;()")):
        right = right[1:]
    if right:
        word = NEIGHBOUR.fullmatch(right[0].strip(".,!?:;()"))
        if word:
            return False
    left = re.sub("§.", "", text[:start]).strip().split()
    if left:
        word = NEIGHBOUR.fullmatch(left[-1].strip(".,!?:;()"))
        if word and not ROMAN.match(word.group(0)):
            return False
    return True


def to_english(text: str) -> str:
    """Русский термин -> английский (для ОБЫЧНОГО режима)."""
    out = text
    for ru, en in PAIRS:
        out = re.sub(LEFT + re.escape(ru) + RIGHT, en, out)
    return out


# ⚠️ ПАДЕЖ ЗАДАЁТ СЛОВО СЛЕВА, и машинно он не выводится — записанное правило
# проекта. Но управляющее слово стоит РЯДОМ и его видно, поэтому формы для
# косвенных падежей перечислены ЯВНО (как `full_prefill.HEADS`).
# Без этого выходит «Даёт +5 к боевые характеристики».
CASES: list[tuple[str, str, str]] = [
    # (что слева, английский термин, русская форма В НУЖНОМ падеже)
    (r"к", "Combat Stats", "боевым характеристикам"),
    (r"к", "Combat Wisdom", "Мудрости воина"),
    (r"к", "Combat XP", "опыту боя"),
    (r"все", "Combat Stats", "боевые характеристики"),
    (r"всех", "Combat Stats", "боевых характеристик"),
    (r"твои", "Combat Stats", "боевые характеристики"),
    (r"больше", "Combat XP", "опыта боя"),
    (r"опыта", "Combat XP", "опыта боя"),
    (r"\d+x?", "Combat XP", "опыта боя"),
    (r"уровень", "Combat Level", "уровень боя"),
    (r"нужен", "Combat Level", "уровень боя"),
]


def to_russian(text: str) -> str:
    """Английский термин -> русский (для режима FULL).

    Сперва падежные формы по управляющему слову слева, потом обычные:
    так «к Combat Stats» становится «к боевым характеристикам», а не
    «к боевые характеристики».
    """
    out = text
    for left, en, ru in CASES:
        # ⚠️ ГРАНИЦА ПО ОБОИМ АЛФАВИТАМ. С проверкой только латиницы предлог
        # «к» совпадал с концом РУССКОГО слова: «Подаро[к] Combat XP» ->
        # «Подарок опыту боя Boost I Potion». Записанная грабля проекта.
        pat = re.compile(r"(?i)(?<![а-яА-ЯёЁA-Za-z])(" + left + r"\s+)"
                         + re.escape(en) + r"(?![A-Za-z])")
        pieces, last = [], 0
        for m in pat.finditer(out):
            if not standalone(out, m.end(1), m.end()):
                continue
            pieces.append(out[last:m.start()])
            pieces.append(m.group(1) + ru)
            last = m.end()
        if pieces:
            pieces.append(out[last:])
            out = "".join(pieces)
    # длинные термины раньше коротких: «Combat XP Boost» до «Combat XP»
    for ru, en in sorted(PAIRS, key=lambda p: -len(p[1])):
        pat = re.compile(r"(?<![A-Za-z])" + re.escape(en) + r"(?![A-Za-z])")
        pieces, last = [], 0
        for m in pat.finditer(out):
            if not standalone(out, m.start(), m.end()):
                continue
            pieces.append(out[last:m.start()])
            pieces.append(ru)
            last = m.end()
        if pieces:
            pieces.append(out[last:])
            out = "".join(pieces)
    return out


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: pathlib.Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def fix_plain(apply: bool) -> int:
    """Обычные источники: русский термин -> английский."""
    total = 0
    # корпус абзацев — правим поле ru
    p = WORK / "paragraphs.json"
    d = load(p)
    key = next(iter(d)) if isinstance(d, dict) and len(d) == 1 else None
    rows = d[key] if key else d
    items = list(rows.values()) if isinstance(rows, dict) else rows
    n = 0
    for r in items:
        if not isinstance(r, dict):
            continue
        was = str(r.get("ru") or "")
        if not was:
            continue
        now = to_english(was)
        if now != was:
            r["ru"] = now
            n += 1
    if n:
        print(f"  корпус абзацев: {n}")
        if apply:
            save(p, d)
    total += n

    # плоские рабочие файлы: очередь, архив, кнопки, надписи
    for name in ("from_game.json", "queue_archive.json", "buttons.json", "nametags.json"):
        p = WORK / name
        if not p.exists():
            continue
        d = load(p)
        n = 0

        def rec(node):
            nonlocal n
            if isinstance(node, dict):
                for k, v in list(node.items()):
                    if isinstance(v, str):
                        now = to_english(v)
                        if now != v:
                            node[k] = now
                            n += 1
                    else:
                        rec(v)
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    if not isinstance(v, str):
                        rec(v)
        rec(d)
        if n:
            print(f"  {name}: {n}")
            if apply:
                save(p, d)
        total += n

    # ручные словари
    for name in ("25-sidebar.json", "40-lore.json", "20-ui.json"):
        p = PACKS / name
        if not p.exists():
            continue
        d = load(p)
        n = 0
        for sec in ("exact", "glossary"):
            for k, v in list((d.get(sec) or {}).items()):
                if not isinstance(v, str):
                    continue
                now = to_english(v)
                if now != v:
                    d[sec][k] = now
                    n += 1
        if n:
            print(f"  {name} (ручной): {n}")
            if apply:
                save(p, d)
        total += n
    return total


def fix_mode(apply: bool) -> int:
    """Режимные пары: для каждой английской записи обычного словаря — русская."""
    strings = load(WORK / "full_strings.json")
    skel = load(WORK / "full_paragraphs_ru.json")
    added_s = added_p = 0

    queue = load(WORK / "from_game.json")
    qrows = queue.get("exact") or {}
    for k, v in qrows.items():
        if not isinstance(v, str) or "Combat" not in v:
            continue
        ru = to_russian(v)
        if ru == v or strings["strings"].get(k) == ru:
            continue
        strings["strings"][k] = ru
        added_s += 1

    for name in ("buttons.json", "nametags.json"):
        p = WORK / name
        if not p.exists():
            continue
        for k, v in (load(p).get("exact") or {}).items():
            if not isinstance(v, str) or "Combat" not in v:
                continue
            ru = to_russian(v)
            if ru == v or strings["strings"].get(k) == ru:
                continue
            strings["strings"][k] = ru
            added_s += 1

    d = load(WORK / "paragraphs.json")
    key = next(iter(d)) if isinstance(d, dict) and len(d) == 1 else None
    rows = d[key] if key else d
    items = list(rows.values()) if isinstance(rows, dict) else rows
    for r in items:
        if not isinstance(r, dict):
            continue
        k, v = str(r.get("text") or ""), str(r.get("ru") or "")
        if not k or "Combat" not in v:
            continue
        ru = to_russian(v)
        if ru == v:
            continue
        was = skel["rows"].get(k, {})
        if was.get("ru") == ru:
            continue
        skel["rows"][k] = {"ru": ru, "base": v, "terms": was.get("terms") or [],
                           "live": was.get("live", 0), "done": True}
        added_p += 1

    print(f"  режимные пары: строк {added_s}, абзацев {added_p}")
    if apply:
        save(WORK / "full_strings.json", strings)
        save(WORK / "full_paragraphs_ru.json", skel)
    return added_s + added_p


def main() -> int:
    apply = "--yes" in sys.argv
    print("=== ОБЫЧНЫЕ источники: Combat английским ===")
    a = fix_plain(apply)
    print()
    print("=== РЕЖИМ full: Combat по-русски ===")
    b = fix_mode(apply)
    print()
    print(f"ВСЕГО: {a} правок в обычных, {b} режимных пар")
    print("применено" if apply else "сухой прогон. Применить: --yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
