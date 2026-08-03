# -*- coding: utf-8 -*-
"""
Перевод абзацев РУКАМИ — выгрузить задание, влить обратно.

⚠️ Зачем, если есть `translate_tooltips.py`. Решение игрока 01.08: небольшие
объёмы переводим сами, без API — быстрее, бесплатно и обычно точнее, потому
что виден контекст всей подсказки, разметка цветом и стык с соседней строкой.
Тот же приём уже работает для строк (`pick_queue --out/--merge`) и для
разметки (`color_lore --export/--load`); абзацам его не хватало.

    python tools/hand_paragraphs.py --export FILE.json --limit 40
        (заполнить поле "ru" у каждой записи)
    python tools/hand_paragraphs.py --load FILE.json

⚠️ ПРОВЕРКИ ТЕ ЖЕ, что у платного прогона: `translate_tooltips.accept` —
дырки {n}/{s}, значки, защищённые имена, парность маркеров цвета. Своей копии
не заводим: она разошлась бы с прогоном, а в этом проекте копии признаков
расходились трижды и всякий раз молча.

⚠️ ЗНАЧКИ ВЫДАЮТСЯ МАСКАМИ {i1}, {i2} — и переносить их надо как есть.
Символы Hypixel лежат в приватной зоне юникода, при копировании из терминала
они молча превращаются в пробел (проверено: из 26 описаний совпало 9).

⚠️ ЦВЕТ. Если цвета абзаца известны, в задании стоит размеченный оригинал:
{c1}…{/c1}. Тогда и перевод пишем С МАРКЕРАМИ — вокруг ТЕХ ЖЕ слов. Это
избавляет мод от угадывания цвета совсем: размеченный перевод он раскладывает
по §-кодам, а не по догадке.

⚠️ Разметку готовим И ПРИ ВЛИВАНИИ. `accept` разворачивает маркеры по полю
`_codes`, а его кладёт `colors_for` в момент выгрузки. Забрать перевод другим
запуском и не позвать `colors_for` — ровно та грабля, на которой Batch API
потерял разметку у 1140 переводов из 1149.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import translate_tooltips as tt   # noqa: E402

CORPUS = ROOT / "data" / "work" / "paragraphs.json"


def waiting(paragraphs: list[dict]) -> list[dict]:
    return [p for p in paragraphs if not p.get("ru") and not p.get("nothing")]


def do_export(path: Path, limit: int, contains: str | None) -> int:
    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = doc.get("paragraphs") or []

    # Те же фильтры покупки, что и у платного прогона: список, набор
    # зачарований, одни имена, всё закрыто построчно. Иначе задание наполнится
    # тем, что переводить не надо вовсе.
    tt.mark_nothing(paragraphs)
    tt.mark_lists(paragraphs)
    tt.mark_enchant_combos(paragraphs)
    tt.mark_stat_tables(paragraphs)
    tt.mark_name_lists(paragraphs)
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    pending = waiting(paragraphs)
    if contains:
        pending = [p for p in pending if contains.lower() in (p.get("text") or "").lower()]
    # Сперва то, что игрок ВИДЕЛ в игре, потом по частоте: первые N — это
    # лучшее, что можно сделать за один заход, а не случайные предметы.
    pending.sort(key=lambda p: (0 if p.get("live") else 1, -(p.get("count") or 1)))
    chunk = pending[:limit] if limit else pending

    tt.colors_for(chunk)

    task = []
    for para in chunk:
        source = para.get("_marked") or para["text"]
        masked, _ = tt.mask_icons(source)
        task.append({
            "key": para["text"],
            "item": para.get("item") or "",
            "count": para.get("count") or 1,
            "lines": para.get("lines") or [],
            "coloured": bool(para.get("_codes")),
            "en": masked,
            "ru": "",
        })
    path.write_text(json.dumps(task, ensure_ascii=False, indent=1), encoding="utf-8")
    coloured = sum(1 for row in task if row["coloured"])
    print(f"ждут перевода: {len(pending)}")
    print(f"выгружено:     {len(task)}  ->  {path}")
    print(f"  из них с известными цветами: {coloured}"
          f" (в них перевод писать С МАРКЕРАМИ {{c1}})")
    print("\nзаполнить поле \"ru\" и влить:"
          f"\n  python tools/hand_paragraphs.py --load {path}")
    return 0


def do_load(path: Path) -> int:
    task = json.loads(path.read_text(encoding="utf-8"))
    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = doc.get("paragraphs") or []
    by_key = {p["text"]: p for p in paragraphs}

    filled = [row for row in task if (row.get("ru") or "").strip()]
    if not filled:
        print("в задании нет ни одного заполненного \"ru\" — нечего вливать")
        return 1

    # ⚠️ Разметку восстанавливаем ПЕРЕД проверкой: accept разворачивает
    # маркеры {c1} в §-коды по полю _codes, а его кладёт colors_for.
    targets = [by_key[row["key"]] for row in filled if row["key"] in by_key]
    tt.colors_for(targets)

    from protected import collect, resolve_collisions
    guarded = resolve_collisions(collect())

    taken, refused, missing = 0, [], 0
    for row in filled:
        para = by_key.get(row["key"])
        if para is None:
            missing += 1
            continue
        russian, why = tt.accept(para, row["ru"], guarded)
        if russian is None:
            refused.append((row["key"], why))
            continue
        para["ru"] = russian
        para.pop("nothing", None)
        taken += 1

    if taken:
        CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"заполнено в задании: {len(filled)}")
    print(f"  принято:   {taken}")
    print(f"  отбраковано: {len(refused)}")
    if missing:
        print(f"  ключа нет в корпусе: {missing} (корпус пересобрали?)")
    for key, why in refused[:20]:
        print(f"     [{why}] {key[:70]}")
    if len(refused) > 20:
        print(f"     ... ещё {len(refused) - 20}")
    print("\nдальше: python tools/merge_paragraphs.py")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Перевод абзацев руками")
    parser.add_argument("--export", metavar="FILE", help="выгрузить задание")
    parser.add_argument("--load", metavar="FILE", help="влить заполненное задание")
    parser.add_argument("--limit", type=int, default=40, help="сколько абзацев в задании")
    parser.add_argument("--filter", metavar="ТЕКСТ", help="только абзацы с этим текстом")
    args = parser.parse_args()

    if args.export:
        return do_export(Path(args.export), args.limit, args.filter)
    if args.load:
        return do_load(Path(args.load))
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
