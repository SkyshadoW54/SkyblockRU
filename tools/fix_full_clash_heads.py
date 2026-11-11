# -*- coding: utf-8 -*-
"""Заголовок режимного абзаца — взять ГОТОВЫЙ построчный перевод режима.

⚠️⚠️ ЗАЧЕМ. `Paragraphs.header` режет заголовок своей строкой, только если
вырезанное СОВПАДАЕТ с построчным переводом первой строки. В режиме
построчный даёт «Способность: Как дела?  ПКМ», а абзац несёт «Способность:
Whassup? ПКМ» — совпадения нет, резка отменяется, заголовок втекает в
описание и теряет свой цвет. Скриншот игрока 07.09 (Бэтфон Мэддокса).

⚠️ `fix_full_headings` такие места НЕ берёт по построению: он ищет ИМЯ
регуляркой слов с Заглавной, а «Whassup?» кончается вопросительным знаком.
Тут имя вообще не нужно — построчный перевод заголовка УЖЕ ЕСТЬ целиком,
его и ставим.

⚠️ Признак строгий: начало абзаца обязано совпасть с ОБЫЧНЫМ построчным
переводом того же заголовка знак в знак (после снятия §-кодов). Тогда мы
меняем ровно заголовок и ничего не угадываем.

⚠️ §-коды заголовка СОХРАНЯЕМ: цвет ставит Hypixel, и подмена ведущих кодов
идёт при резке. Меняем только текст между ними.

    python tools/fix_full_clash_heads.py         покажет
    python tools/fix_full_clash_heads.py --yes   применит
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gen_full_paragraphs as skeleton  # noqa: E402
import status                            # noqa: E402

MODE = ROOT / "data" / "work" / "full_paragraphs_ru.json"
CODE = re.compile("\u00a7.")
HOLE = re.compile(r"\{[nsi]\d*\}")
# ⚠️ полуперевод: латиница рядом с кириллицей в одном заголовке
HALF = re.compile(r"[A-Za-z]{2,}")


def soft(text: str) -> str:
    """Сравниваем мягко по пробелам: Hypixel ставит двойной перед клавишей."""
    return re.sub(r"\s+", " ", CODE.sub("", text)).strip()


def replace_head(russian: str, old_head: str, new_head: str) -> str | None:
    """Заменить в абзаце только ИЗМЕНИВШИЙСЯ кусок заголовка.

    ⚠️⚠️ ЦЕЛИКОМ ЗАГОЛОВОК ПОДСТАВЛЯТЬ НЕЛЬЗЯ: у абзаца своя разметка
    («§6Способность: Whassup?§7 §e§lПКМ§7»), а у построчной записи своя —
    и клавиша теряла жёлтый жирный. Меняем ровно кусок между общим началом
    и общим концом двух переводов, то есть само имя; коды вокруг целы.

    ⚠️ Выравнивание по кускам (`SequenceMatcher`) сюда не годится —
    записанная грабля проекта: оно дробит термин и ставит §-код перед
    каждым словом. Общий префикс и суффикс дают ОДИН кусок.
    """
    if old_head == new_head:
        return None
    head, tail = 0, 0
    while head < min(len(old_head), len(new_head)) and old_head[head] == new_head[head]:
        head += 1
    while (tail < min(len(old_head), len(new_head)) - head
           and old_head[-1 - tail] == new_head[-1 - tail]):
        tail += 1
    was = old_head[head:len(old_head) - tail]
    now = new_head[head:len(new_head) - tail]
    if not was:
        return None
    # ⚠️ ищем кусок в абзаце СКВОЗЬ §-коды: Hypixel красит слова порознь,
    # и дословный поиск имя не находит — записанная грабля проекта.
    flat, pos = [], []
    i = 0
    while i < len(russian):
        if russian[i] == "§" and i + 1 < len(russian):
            i += 2
            continue
        flat.append(russian[i])
        pos.append(i)
        i += 1
    text = "".join(flat)
    at = text.find(was)
    if at < 0:
        return None
    # ⚠️ только в ЗАГОЛОВКЕ: дальше по абзацу то же слово может стоять
    # в косвенном падеже, и подставлять туда именительный нельзя.
    if at > len(old_head) + 8:
        return None
    return russian[:pos[at]] + now + russian[pos[at + len(was) - 1] + 1:]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Заголовок режимного абзаца")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--show", type=int, default=10)
    args = parser.parse_args()

    data = json.loads(MODE.read_text(encoding="utf-8"))
    rows = data["rows"]
    plain_dict, mode_dict = skeleton._PLAIN(), skeleton._MODE()

    fixed, refused, shown = 0, {}, 0
    for key, row in rows.items():
        russian = row.get("ru") or ""
        if not russian:
            continue
        for head in skeleton.heading_candidates(key):
            got_plain = status.lookup(head, plain_dict, origin="item_lore")
            got_mode = status.lookup(head, mode_dict, origin="item_lore")
            if not got_plain or not got_mode:
                continue
            # ⚠️⚠️ ОСТАНАВЛИВАЕМСЯ НА ПЕРВОМ КАНДИДАТЕ, КОТОРОГО ЗНАЮТ ОБА
            # СЛОВАРЯ. `heading_candidates` идёт от длинного к короткому,
            # и у «Ability: Burning Vengeance» среди коротких есть «Ability:
            # Burning» — а общее правило «^Ability: (.+)$» с `tg` честно
            # переводит «Burning» -> «Горящий». Пойди мы дальше, вышло бы
            # «Способность: Горящий Vengeance», смесь ВНУТРИ имени.
            # ⚠️ Признаком «за кандидатом слово с Заглавной» это не берётся:
            # у «Ability: Whassup?  RIGHT CLICK» дальше идёт проза «Lets you
            # call…», и правильный кандидат отбрасывался.
            if got_plain[0] == got_mode[0]:
                break
            made = replace_head(russian, got_plain[0], got_mode[0])
            if made is None:
                refused["начало абзаца не совпало с построчным"] = \
                    refused.get("начало абзаца не совпало с построчным", 0) + 1
                continue
            # ⚠️⚠️ ПОЛУПЕРЕВОД ХУЖЕ АНГЛИЙСКОГО ЦЕЛИКОМ. У части заголовков
            # режимный перевод сам смешанный («Способность: Горящий
            # Vengeance») — ставить его значит менять одну беду на худшую.
            # Клавиша и римский уровень английскими быть обязаны.
            if HALF.search(re.sub(r"(?<![A-Za-z])(?:Shift|SNEAK|RIGHT|LEFT|"
                                  r"CLICK|SHOOT|DIG|[IVXLCDM]+)(?![A-Za-z])",
                                  "", CODE.sub("", got_mode[0]))):
                refused["перевод заголовка сам полурусский"] =                     refused.get("перевод заголовка сам полурусский", 0) + 1
                break
            if HOLE.findall(made) != HOLE.findall(russian):
                refused["дырки разошлись"] = refused.get("дырки разошлись", 0) + 1
                break
            if shown < args.show:
                print("   было : " + CODE.sub("", russian)[:112])
                print("   стало: " + CODE.sub("", made)[:112])
                shown += 1
            fixed += 1
            if args.yes:
                row["ru"] = made
            break

    print(f"\nабзацев поправится: {fixed}")
    for why, count in sorted(refused.items(), key=lambda kv: -kv[1]):
        print(f"   отказ — {why}: {count}")
    if not args.yes:
        print("\nСУХОЙ ПРОГОН. Применить: --yes")
        return 0
    MODE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("записано. Дальше: python tools/gen_full_paragraphs.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
