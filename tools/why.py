# -*- coding: utf-8 -*-
"""
ПОЧЕМУ на экране английский — разбор одной подсказки по шагам.

Отвечает не «переведено / нет», а НА КАКОМ ШАГЕ сломалось. Шагов у мода
немного, и каждый умеет молча ничего не сделать:

    1. строка вообще дошла до нас?      (есть ли в дампе)
    2. перевод куплен?                   (есть ли в словарях по ЭТОМУ ключу)
    3. ключ совпал?                      (разрезка по ширине окна, «✯», регистр)
    4. абзац склеится?                   (список и таблицу мод не склеивает)
    5. заголовок отделится?              (нужен построчный перевод первой строки)

Раньше на каждый такой вопрос уходил отдельный заход: `status.py` про строку,
`db.py` про словари, `check_colors.py` про склейку, а связать их приходилось
в голове. Здесь всё сразу и про КОНКРЕТНУЮ подсказку.

    python tools/why.py --item "Mossy Helianthus"   разобрать подсказку целиком
    python tools/why.py "Swap this helmet's skin"   разобрать одну строку

Источник — `dump/preview.json`: мод пишет туда подсказку ДО и ПОСЛЕ перевода,
то есть ровно то, что видит игрок. Значит разбор идёт по фактам, а не по
догадкам о том, как оно, наверное, выглядит.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pkey  # noqa: E402
import status  # noqa: E402

PREVIEW = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/preview.json")
CODES = re.compile("§.")
LATIN = re.compile(r"[A-Za-z]")
CYRIL = re.compile(r"[А-Яа-яЁё]")
# знаки, по которым мод НЕ склеивает абзац (список) — копия признака ColorLayout
LIST_MARK = re.compile(r"^[▶▸➤✔✖◼◆‣•▪»○✓⋗⁍∙✧✦+]")
# заголовок зачарования: имя и римский уровень, больше ничего (Paragraphs.ENCHANT_HEAD)
ENCHANT_HEAD = re.compile(r"^[A-Z][A-Za-z' -]*\s[IVXLC]+$")
# значок Hypixel: приватная зона шрифта
ICON = re.compile(r"[-]")


def load_cases() -> list[dict]:
    if not PREVIEW.exists():
        print("нет dump/preview.json — поиграй на свежем jar, мод его напишет")
        return []
    return json.loads(PREVIEW.read_text(encoding="utf-8")).get("cases") or []


def lines_of(block: list) -> list[str]:
    return ["".join(text for _, text in row) for row in block]


def runs(rows: list[str]) -> list[list[str]]:
    """Куски между пустыми строками — как режет Paragraphs.runs."""
    out, current = [], []
    for row in rows:
        if row.strip():
            current.append(row.strip())
        elif current:
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def near_keys(key: str, known: dict, limit: int = 3) -> list[str]:
    """Ключи словаря, похожие на наш, — чтобы увидеть РАЗОШЁДШИЙСЯ вариант."""
    head = key[:28]
    return [k for k in known if k[:28] == head and k != key][:limit]


def explain_run(rows: list[str], dictionaries, queue, corpus, known: dict) -> None:
    key = pkey.key_of(rows)
    print("  абзац из %d строк: %s" % (len(rows), key[:66]))

    translated = known.get(key)
    if translated:
        print("     [есть] перевод абзаца найден по этому ключу")
    else:
        print("     [НЕТ]  перевода по ЭТОМУ ключу нет")
        similar = near_keys(key, known)
        if similar:
            print("     ⚠️ но в словаре есть ПОХОЖИЙ ключ — значит разошлась разрезка")
            print("        по ширине окна, «✯» или регистр слова:")
            for k in similar:
                print("          %s" % k[:78])
            print("        чинит: python tools/fill_variants.py")

    # ⚠️ Блок зачарований мод режет на СЕКЦИИ и ищет перевод каждой отдельно
    # (Paragraphs.bySections). Не сказав этого, разбор соврёт: по ключу всего
    # блока перевода нет никогда, а на экране он при этом переводится.
    heads = [i for i, row in enumerate(rows) if ENCHANT_HEAD.match(row)]
    if not translated and len(heads) >= 2:
        print("     это блок ЗАЧАРОВАНИЙ (%d заголовков) — мод режет его на секции:"
              % len(heads))
        for n, start in enumerate(heads):
            end = heads[n + 1] if n + 1 < len(heads) else len(rows)
            section = pkey.key_of(rows[start:end])
            mark = "[есть]" if section in known else "[НЕТ] "
            print("        %s %s" % (mark, section[:62]))
            if section not in known:
                for k in near_keys(section, known, 2):
                    print("                похожий: %s" % k[:62])

    # склеит ли мод этот кусок
    marks = [row for row in rows if LIST_MARK.match(row)]
    if len(marks) >= 2:
        print("     ⚠️ это СПИСОК (знак в начале у %d строк) — мод его не склеит," % len(marks))
        print("        а перевод применит, разрезав по маркерам (Paragraphs.listed)")

    # что будет со строками по отдельности
    missing = []
    for row in rows:
        answer = status.verdict(row, dictionaries, queue, corpus)
        if answer["status"] in ("ЖДЁТ В ОЧЕРЕДИ", "НЕТ НИГДЕ — даже не собрано"):
            missing.append((row, answer["status"]))
    if missing:
        print("     построчно НЕ закрыты %d строк(и):" % len(missing))
        for row, state in missing[:4]:
            print("        %-56s %s" % (row[:56], state))
        # ⚠️ «нет в дампе» — это НЕ поломка, а дырка покрытия: строку просто
        # никто ещё не видел. Отделяем явно, иначе она читается как беда
        # и уводит в поиск несуществующей причины.
        fresh = [row for row, state in missing if state.startswith("НЕТ НИГДЕ")]
        if fresh:
            print("     ⚠️ из них %d мод видит ВПЕРВЫЕ — это дырка покрытия," % len(fresh))
            print("        а не поломка: перевода для них не покупали.")
            print("        дальше: python tools/refresh.py (соберёт их в очередь)")


def explain_item(name: str) -> int:
    cases = load_cases()
    hits = [c for c in cases if name.lower() in (c.get("item") or "").lower()]
    if not hits:
        print("подсказки с таким именем в dump/preview.json нет.")
        print("Открой предмет в игре — мод запишет её сам.")
        return 1

    dictionaries = status.Dictionaries()
    queue, corpus = status.load_queue(), status.load_corpus()
    known = {k: v for k, (v, _where) in dictionaries.paragraphs.items()}

    case = hits[0]
    before, after = lines_of(case["before"]), lines_of(case["after"])
    print("=" * 74)
    print("  %s" % case.get("item"))
    print("=" * 74)
    english = [r for r in after if r.strip() and LATIN.search(r) and not CYRIL.search(r)]
    print("строк всего: %d, осталось английскими: %d" % (len(after), len(english)))
    if english:
        print("английские строки:")
        for row in english[:8]:
            print("   %s" % row.strip()[:68])

    # ⚠️ ЦВЕТ И ЖИРНОСТЬ. Строка бывает переведена, но «поехать» видом — игрок
    # присылает это так же часто, как английский текст, а по самому тексту
    # беду не видно. Сравниваем набор стилей ДО и ПОСЛЕ.
    def styles(block):
        out = set()
        for row in block:
            for colour, text in row:
                if str(text).strip():
                    out.add(colour)
        return out

    was, now = styles(case["before"]), styles(case["after"])
    gained, lost = now - was, was - now
    if gained or lost:
        print()
        print("ЦВЕТ:")
        if gained:
            print("   ⚠️ появился, которого у Hypixel НЕТ: %s" % ", ".join(sorted(gained)))
            print("      обычно это разметка перевода, взятая с ДРУГОГО предмета —")
            print("      проверить: python tools/check_head_colors.py")
        if lost:
            print("   ⚠️ пропал: %s" % ", ".join(sorted(lost)))
            print("      цвет теряет ПЕРЕВЕДЁННОЕ слово: искать его в переводе нечего.")
            print("      лечится §-кодами в самом переводе")
    print()
    for rows in runs(before):
        explain_run(rows, dictionaries, queue, corpus, known)
        print()
    return 0


def explain_line(text: str) -> int:
    dictionaries = status.Dictionaries()
    queue, corpus = status.load_queue(), status.load_corpus()
    answer = status.verdict(text, dictionaries, queue, corpus)
    print("  %s" % text[:70])
    print("     состояние: %s" % answer["status"])
    if answer.get("result"):
        print("     перевод:   %s" % str(answer["result"])[:70])
    if answer.get("where"):
        print("     лежит в:   %s" % answer["where"])
    if answer["status"] == "закрыто абзацем":
        print("     ⚠️ строка сама по себе не переводится — её закрывает АБЗАЦ.")
        print("        Если на экране английский, значит абзац не применился:")
        print("        разберите подсказку целиком — python tools/why.py --item \"имя\"")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Почему на экране английский")
    parser.add_argument("text", nargs="?", help="строка с экрана")
    parser.add_argument("--item", help="имя предмета: разобрать подсказку целиком")
    args = parser.parse_args()

    if args.item:
        return explain_item(args.item)
    if args.text:
        return explain_line(args.text)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
