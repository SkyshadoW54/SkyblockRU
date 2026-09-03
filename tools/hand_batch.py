# -*- coding: utf-8 -*-
"""
Приёмник РУЧНОЙ пачки: проверяет, делит по режимам и вливает.

    python tools/full_batch.py --size 250      отобрать
    python tools/hand_batch.py --export        выгрузить задание с масками
       (заполнить поле "ru"; «-» значит «переводить нечего», пустое — обрывок)
    python tools/hand_batch.py --load          проверить и влить

⚠️ ПРИ БРАКЕ НЕ ВЛИВАЕТ ВОВСЕ. 26.08 я влил пачку с обрезанным переводом,
хотя проверка брак нашла: она только ПЕЧАТАЛА. Проверка, которая не может
остановить, — это отчёт, а не защита.

⚠️ Обрывки (пустое «ru») уходят в `_batch_skip.json`, а НЕ в `_asis`:
у обрывка нет своего смысла, его лечит перевод АБЗАЦА, а `_asis` означал бы
принятое решение «переводить нечего». Без этого списка 98 разобранных
обрывков всплывали в верхушке каждой пачки.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
sys.path.insert(0, str(ROOT / "tools"))

TASK = WORK / "_hand_now.json"
SKIP = WORK / "_batch_skip.json"
QUEUE = WORK / "from_game.json"
NAMES = WORK / "item_names_ru.json"
STRINGS = WORK / "full_strings.json"

# Письменности, которых у Hypixel не бывает: строка с ЧУЖОГО клиента.
ALIEN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af"
                   r"\u0600-\u06ff\u0590-\u05ff\u0e00-\u0e7f\u0900-\u097f]")
MASK = re.compile(r"\{i\d+\}")


def load(path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default if default is not None else {}


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def export(size_source=WORK / "_batch_next.json") -> int:
    import translate_tooltips as tt
    rows = load(size_source, [])
    if not rows:
        print("пачки нет — сперва tools/full_batch.py")
        return 1
    # ⚠️ БЕЗ re.I: регистр И ЕСТЬ признак. С IGNORECASE первая ветвь
    # становится ^[A-Za-z] и обрывком считается любая строка с буквы —
    # так замер показал «цельных 6» вместо 181.
    lower = re.compile(r"^[a-z+{]")
    tail = re.compile(r"(?:,|\b(?:by|for|and|the|to|with|of|your|you|while|when"
                      r"|from|in|on|a|an|that|this|per|at|it|is|are)\.?)$", re.I)
    out = []
    for row in rows:
        line = row["en"]
        if lower.search(line) or tail.search(line):
            continue
        raw = row.get("key") or line
        masked, codes = tt.mask_icons(raw)
        out.append({"en": masked, "ru": "", "src": row["src"],
                    "_key": raw, "_codes": codes})
    save(TASK, out)
    print(f"выгружено: {len(out)} из {len(rows)}")
    for i, item in enumerate(out, 1):
        print(f'{i:3}|{item["src"][:9]:9}|{item["en"]}')
    return 0


def defects(rows) -> list[str]:
    """Что не так с переводами. Пусто — можно вливать."""
    found = []
    for row in rows:
        en, ru = row["en"], row["ru"]
        for hole in ("{n}", "{s}"):
            if en.count(hole) != ru.count(hole):
                found.append(f"дырок {hole} разное: {en!r} -> {ru!r}")
        if set(MASK.findall(en)) != set(MASK.findall(ru)):
            found.append(f"маски значков разошлись: {en!r} -> {ru!r}")
        if ALIEN.search(ru):
            found.append(f"чужая письменность: {ru!r}")
        if en == ru:
            found.append(f"тождественная запись: {en!r}")
    return found


def unmask(row) -> tuple[str, str]:
    ru = row["ru"]
    for mask, char in (row.get("_codes") or {}).items():
        ru = ru.replace(mask, char)
    return row["_key"], ru


def do_load() -> int:
    import protected
    import status
    import mode_split
    rows = load(TASK, [])
    # «-» — переводить нечего, «~» — обрывок: ни то ни другое переводом
    # не является и на брак не проверяется.
    done = [r for r in rows if r["ru"].strip() not in ("", "-", "~")]
    # ⚠️ ПОМЕТКИ СОХРАНЯЕМ ДАЖЕ БЕЗ ЕДИНОГО ПЕРЕВОДА. Пачка целиком из
    # обрывков и решений — обычное дело на исходе работы, и терять их нельзя:
    # иначе те же строки придут в следующую пачку и разбирать их придётся
    # заново.
    decided = [r for r in rows if r["ru"].strip() == "-"]
    if decided:
        skel = load(NAMES)
        names_asis = skel.setdefault("_asis", [])
        queue = load(QUEUE)
        queue_asis = queue.setdefault("_asis", [])
        added = 0
        for row in decided:
            key = row["_key"]
            box = names_asis if row["src"] == "item_name" else queue_asis
            if key not in box:
                box.append(key)
                added += 1
        save(NAMES, skel)
        save(QUEUE, queue)
        print(f"решений «переводить нечего»: +{added}")
    if not done:
        postponed = set(load(SKIP, []))
        was = len(postponed)
        for row in rows:
            if row["ru"].strip() == "~":
                postponed.add(row["_key"])
        save(SKIP, sorted(postponed))
        print(f"переводов нет; отложено обрывков: +{len(postponed) - was}")
        return 0

    bad = defects(done)
    if bad:
        print(f"БРАК: {len(bad)} — НЕ ВЛИВАЮ")
        for line in bad[:20]:
            print("   ", line)
        return 1

    plain = status.Dictionaries()
    full = status.Dictionaries(groups={"full"})
    known = protected.collect()
    mode, ordinary = [], []
    for row in done:
        why = mode_split.decide(row, plain, full, status.lookup, protected, known)
        (mode if why else ordinary).append(row)

    queue = load(QUEUE); exact = queue.setdefault("exact", {})
    added_q = 0
    for row in ordinary:
        key, ru = unmask(row)
        if not exact.get(key):
            exact[key] = ru
            added_q += 1
    save(QUEUE, queue)

    skel = load(NAMES)
    names = skel.get("names") if isinstance(skel.get("names"), dict) else skel
    strings_file = load(STRINGS)
    strings = (strings_file.get("strings")
               if isinstance(strings_file.get("strings"), dict) else strings_file)
    added_n = added_s = 0
    for row in mode:
        key, ru = unmask(row)
        if row["src"] == "item_name":
            if not names.get(key):
                names[key] = ru
                added_n += 1
        elif not strings.get(key):
            strings[key] = ru
            added_s += 1
    save(NAMES, skel)
    save(STRINGS, strings_file)

    # ⚠️⚠️ ПУСТОЕ «ru» ЗНАЧИТ «НЕ РАЗОБРАНО», А НЕ «ОБРЫВОК». Откладывая
    # пустые подряд, я 27.08 спрятал 197 ЦЕЛЬНЫХ строк — то есть работу,
    # которую просто не успел сделать в этой пачке. Записанная грабля проекта:
    # фильтр, делающий строку невидимой, дороже отсутствия перевода.
    #
    # Отложить — это РЕШЕНИЕ, и помечается оно явно: «~» в поле «ru».
    # Пустая строка вернётся в следующую пачку, как и должна.
    postponed = set(load(SKIP, []))
    was = len(postponed)
    for row in rows:
        if row["ru"].strip() == "~":
            postponed.add(row["_key"])
    save(SKIP, sorted(postponed))

    print(f"влито: очередь {added_q}, имена {added_n}, режимные строки {added_s}")
    print(f"отложено обрывков: +{len(postponed) - was} (всего {len(postponed)})")
    print("дальше: gen_item_names.py --write, gen_full_strings.py --write,"
          " export_pack.py from_game 90-from-game.json")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", action="store_true", help="выгрузить задание")
    ap.add_argument("--load", action="store_true", help="проверить и влить")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.export:
        return export()
    if args.load:
        return do_load()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
