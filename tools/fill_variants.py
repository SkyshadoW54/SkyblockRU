# -*- coding: utf-8 -*-
"""
Перенос перевода на ВАРИАНТЫ того же абзаца — бесплатно, без API.

Один и тот же текст попадает в корпус несколькими ключами: Hypixel режет его
по ширине окна ИГРОКА, добавляет «✯» перку министра, меняет регистр слова
(«rabbits» / «Rabbits»). Ключ абзаца строится по тексту, поэтому каждый такой
вариант — отдельная запись, и переведён обычно ОДИН из них. На экране это
выглядит как «перевод пропал»: игрок прислал подсказки кандидатов в мэры,
где половина перков английская, хотя все девять давно переведены.

Признак совпадения нарочно СТРОГИЙ: снимаем «✯», схлопываем пробелы и
сравниваем без учёта регистра. Всё остальное обязано совпасть знак в знак —
иначе перенесём перевод на другой текст. Так «Schedules an extra Spooky
Festival» не станет переводом для «...an extra Fishing Festival»: сервер
переписал перк, и это РАЗНЫЕ вещи, хоть и похожие.

    python tools/fill_variants.py          показать, что перенесётся
    python tools/fill_variants.py --yes    применить
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

CORPUS = ROOT / "data" / "work" / "paragraphs.json"
CODES = re.compile("§.")
# знак перка министра: он есть у одного варианта и нет у другого
STAR = "✯"


def shape(text: str) -> str:
    """Ключ без того, что Hypixel меняет от случая к случаю."""
    plain = CODES.sub("", text).replace(STAR, " ")
    return re.sub(r"\s+", " ", plain).strip().lower()


# ⚠️ ВТОРОЙ, более широкий признак (18.10, четыре снимка игрока: «Gain без
# перевода вообще» в режиме full): тот же текст, но ЗНАЧОК другой или его нет.
# Сервер шлёт значок приватной зоны (U+E010), NEU — обычный юникод (❤), а в
# 26.x часть значков вовсе не текст (объект-компонент): в ключе остаётся
# двойной пробел. Замер по живому дампу 18.10: 211 абзацев (424 показа)
# лежали английскими при готовом переводе соседнего варианта. Перенос
# строгий: число значков в ключах равно — подставляем значки ЦЕЛЕВОГО ключа
# по порядку; у цели значков нет — снимаем их из перевода. Иначе не берём.
ICON = re.compile("[-☀-⟿⬀-⯿←-⇿■-◿"
                  "ༀ-࿿ᜀ-៿฀-๿᠀-᢯ꠀ-ꣿ"
                  "℀-⅏①-⓿ƀ-ɏͰ-Ͽᚠ-᛿԰-֏]")
# кириллицу из ICON исключаем явно: U+0400–04FF туда не входит, но проверим подсадкой
assert not ICON.search("Удача шахтёра ёЁ"), "ICON задевает кириллицу"


def shape_icons(text: str) -> str:
    """Форма без значков: то же, что shape, но значки сняты."""
    return shape(ICON.sub(" ", text))


def icons_of(text: str) -> list[str]:
    return [c for c in CODES.sub("", text) if ICON.match(c) and c != STAR]


def with_icons(ru: str, donor_key: str, target_key: str) -> str | None:
    """Перевод донора со значками ЦЕЛЕВОГО ключа — или None, если подогнать нельзя."""
    have, want = icons_of(donor_key), icons_of(target_key)
    if have == want:
        return ru
    if not want:
        # у цели значка нет вовсе (объект-компонент) — снимаем значки, пробелы
        # внутри оставляем (в ключе цели там двойной пробел), по краям — нет
        out = "".join(c for c in ru if not (ICON.match(c) and c != STAR))
        return out.strip()
    if len(have) != len(want):
        return None
    # значки в переводе обязаны идти в том же порядке, что в ключе донора
    in_ru = [c for c in ru if ICON.match(c) and c != STAR]
    if in_ru != have:
        return None
    out, i = [], 0
    for c in ru:
        if ICON.match(c) and c != STAR:
            out.append(want[i])
            i += 1
        else:
            out.append(c)
    return "".join(out)


def with_star(ru: str, need: bool) -> str | None:
    """Подогнать звезду перевода под оригинал. None — если подогнать нельзя."""
    has = STAR in ru
    if has == need:
        return ru
    if need:
        # звезду ставим В НАЧАЛО, перед первым видимым знаком, сохраняя коды
        match = re.match(r"^((?:§.)*)(.*)$", ru, re.S)
        return f"{match.group(1)}{STAR} {match.group(2)}"
    # звезда есть, а в оригинале её нет — убираем вместе с пробелом за ней
    return re.sub(re.escape(STAR) + r"\s*", "", ru, count=1)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Перенос перевода на варианты абзаца")
    parser.add_argument("--yes", action="store_true", help="применить")
    parser.add_argument("--show", type=int, default=15)
    args = parser.parse_args()

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = doc.get("paragraphs") or []

    # доноры: у кого перевод есть. Если у одной формы доноров несколько
    # и переводы разные — не берём ни один: угадывать, какой верен, нельзя.
    donors: dict[str, str | None] = {}
    donor_raw: dict[str, str] = {}
    # доноры по форме БЕЗ значков: (перевод, сырой ключ донора) или None при разнобое
    donors_icons: dict[str, tuple[str, str] | None] = {}
    for para in paragraphs:
        ru = para.get("ru")
        if not ru:
            continue
        raw = pkey.key_of(para.get("lines") or [])
        key = shape(raw)
        if key in donors and donors[key] is not None and shape(donors[key]) != shape(ru):
            donors[key] = None
        else:
            donors.setdefault(key, ru)
            donor_raw.setdefault(key, para.get("text") or raw)
        key2 = shape_icons(raw)
        was = donors_icons.get(key2)
        if key2 in donors_icons and was is not None and shape_icons(was[0]) != shape_icons(ru):
            donors_icons[key2] = None
        else:
            donors_icons.setdefault(key2, (ru, raw))

    filled, skipped_star, ambiguous, skipped_icons, by_icons = [], 0, 0, 0, 0
    for para in paragraphs:
        if para.get("ru") or para.get("nothing"):
            continue
        raw = pkey.key_of(para.get("lines") or [])
        key = shape(raw)
        donor = donors.get(key)
        source_key = donor_raw.get(key, "")
        if donor is None:
            if key in donors:
                ambiguous += 1
                continue
            # второй признак: тот же текст, значки другие или их нет
            pair = donors_icons.get(shape_icons(raw))
            if pair is None:
                if shape_icons(raw) in donors_icons:
                    ambiguous += 1
                continue
            donor = with_icons(pair[0], pair[1], raw)
            if donor is None:
                skipped_icons += 1
                continue
            source_key = pair[1]
            by_icons += 1
        ru = with_star(donor, STAR in raw)
        if ru is None:
            skipped_star += 1
            continue
        filled.append((para, raw, ru, source_key))

    print(f"абзацев без перевода: {sum(1 for p in paragraphs if not p.get('ru') and not p.get('nothing'))}")
    print(f"можно закрыть переводом ДРУГОГО варианта: {len(filled)} (из них по значкам: {by_icons})")
    if skipped_icons:
        print(f"  пропущено (значки не подогнать: число или порядок разошлись): {skipped_icons}")
    if ambiguous:
        print(f"  пропущено (у формы разные переводы, гадать нельзя): {ambiguous}")
    print()
    for para, raw, ru, _src in filled[:args.show]:
        print(f"   {raw[:64]}")
        print(f"      -> {ru[:64]}")
    if len(filled) > args.show:
        print(f"   ... ещё {len(filled) - args.show}")

    # ⚠️ РЕЖИМ FULL — ТЕМ ЖЕ ПЕРЕНОСОМ. Заготовка режима (`full_paragraphs_ru.json`)
    # хранит режимную версию по тому же ключу; у донора она готова (`done`),
    # у варианта её нет — и в режиме вариант показывал бы обычный перевод с
    # английскими терминами. Переносим режимную версию донора с теми же
    # поправками (звезда, значки) и помечаем готовой: правка термина у донора
    # уже сделана человеком, текст тот же.
    mode_rows = 0
    skeleton = ROOT / "data" / "work" / "full_paragraphs_ru.json"
    mode = json.loads(skeleton.read_text(encoding="utf-8")) if skeleton.exists() else {}
    rows = mode.get("rows", {}) if isinstance(mode, dict) else {}
    for para, raw, ru, src in filled:
        key = para.get("text") or raw
        was = rows.get(src)
        if not was or not was.get("done") or not was.get("ru") or key in rows:
            continue
        mode_ru = with_icons(was["ru"], src, raw)
        if mode_ru is None:
            continue
        mode_ru = with_star(mode_ru, STAR in raw)
        if mode_ru is None:
            continue
        rows[key] = {"ru": mode_ru, "base": ru, "terms": list(was.get("terms") or []),
                     "live": para.get("live") or 0, "done": True}
        mode_rows += 1
    print(f"режимных версий из донора: {mode_rows}")

    if not args.yes:
        print("\nсухой прогон. Применить: --yes")
        return 0

    for para, _raw, ru, _src in filled:
        para["ru"] = ru
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано переводов: {len(filled)}")
    if mode_rows and isinstance(mode, dict):
        mode["rows"] = rows
        skeleton.write_text(json.dumps(mode, ensure_ascii=False, indent=1), encoding="utf-8")
        done = sum(1 for r in rows.values() if r.get("done"))
        print(f"заготовка режима: +{mode_rows} готовых записей, всего готово {done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
