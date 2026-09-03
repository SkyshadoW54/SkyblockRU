# -*- coding: utf-8 -*-
"""
ЦВЕТ В РЕПЛИКАХ NPC: сервер против вики.

Реплики собраны с fandom (`fetch_dialogues.py`), и цвет в них — тот, что
записала ВИКИ. А вики отстаёт от сервера: это записанная грабля проекта,
и здесь она вылезла цветом. Замер 24.08 по логам Minecraft (там §-коды целы):

    «Lumber Jack»   вики §a (5 реплик) / §2 (17)   сервер §2 — 13 из 13
    «Ryan»          вики §a (3)                     сервер §c
    «Taming»        вики §a (1)                     сервер §3

То есть у одного и того же имени вики даёт два цвета, а сервер — один.
Прав сервер: игрок видит именно его.

⚠️ ПОРОГ ОБЯЗАТЕЛЕН — тот же, что у `check_head_colors`: цвет считается
устойчивым, только если в логах он ОДИН и встретился не меньше пяти раз.
Hypixel красит один и тот же кусок по-разному в разных местах, и без порога
мы бы «чинили» законное разнообразие.

⚠️ ИСТИНА ТОЛЬКО ИЗ ЛОГОВ. Для реплик не годятся ни `paragraph-colors`
(там лор, и цвет того же слова другой), ни вики. Проверено: сверка реплик
с цветами лора дала 45 «расхождений», и все до одного ложные — область
у признака своя, и она уже, чем кажется.

⚠️ Правится ИСТОЧНИК `data/work/npc_dialogues.json`, а не словарь:
`62-npc-dialogues.json` автосборный, и правка в нём живёт до первого
`merge_dialogues.py`.

⚠️ Текст меняться не смеет — проверяется на каждой замене: снимаем коды
и сверяем со старым значением. Не сошлось — запись пропускается.

    python tools/fix_chat_colors.py          показать расхождения
    python tools/fix_chat_colors.py --yes    поправить
    (после — python tools/merge_dialogues.py)
"""
from __future__ import annotations

import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

SRC = ROOT / "data" / "work" / "npc_dialogues.json"
PIECE = re.compile(r"§([0-9a-f])((?:[^§]|§[k-or])*)")
CODES = re.compile("§.")
MIN_SEEN = 5


def live_colours() -> dict[str, str]:
    """Как сервер красит каждый кусок — по логам Minecraft."""
    import color_chat
    seen: dict[str, Counter] = defaultdict(Counter)
    for _, raw in color_chat.chat_with_colours().items():
        for m in PIECE.finditer(raw):
            text = CODES.sub("", m.group(2)).strip()
            if len(text) >= 3:
                seen[text][m.group(1)] += 1
    return {t: next(iter(c)) for t, c in seen.items()
            if len(c) == 1 and sum(c.values()) >= MIN_SEEN}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    apply = "--yes" in sys.argv
    if not SRC.exists():
        print(f"нет источника реплик: {SRC}")
        return 0
    stable = live_colours()
    print(f"кусков с устойчивым цветом по логам: {len(stable)}")

    doc = json.loads(SRC.read_text(encoding="utf-8"))
    lines = doc.get("lines") or {}
    fix: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for key, row in lines.items():
        russian = row.get("ru")
        if not isinstance(russian, str) or "§" not in russian:
            continue
        for m in PIECE.finditer(russian):
            text = CODES.sub("", m.group(2)).strip()
            want = stable.get(text)
            if want and want != m.group(1):
                fix[text].append((key, m.group(1), want))

    total = sum(len(v) for v in fix.values())
    if not total:
        print("СЛОМАНО: 0 — цвета реплик совпадают с сервером")
        return 0
    print(f"\n=== РАСХОЖДЕНИЙ С СЕРВЕРОМ: {total} ===")
    for text, rows in sorted(fix.items(), key=lambda x: -len(x[1])):
        had = Counter(code for _, code, _ in rows)
        print(f"  «{text}»: {len(rows)} реплик, у нас {dict(had)}, "
              f"сервер §{rows[0][2]}")
    if not apply:
        print("\nсухой прогон. Применить: --yes")
        return 0

    done = 0
    for text, rows in fix.items():
        want = rows[0][2]
        for key, had, _ in rows:
            russian = lines[key]["ru"]
            new = russian.replace(f"§{had}{text}", f"§{want}{text}")
            # ⚠️ Текст меняться не смеет — иначе это уже не правка цвета.
            if new != russian and CODES.sub("", new) == CODES.sub("", russian):
                lines[key]["ru"] = new
                done += 1
    SRC.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nпоправлено реплик: {done} (правился только цвет)")
    print("дальше: python tools/merge_dialogues.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
