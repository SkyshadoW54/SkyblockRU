"""
Сколько лора реально привязывается к ID предмета — замер, а не рассуждение.

Зачем. Весь перевод в проекте привязан к ТЕКСТУ: обобщённому по числам,
очищенному от цветов и склеенному из кусков, которые сервер разрезал по ширине
окна ИГРОКА. Каждое звено — место расхождения, и большинство граблей в CLAUDE.md
пришли оттуда. У предмета при этом есть настоящий идентификатор в NBT.

Прежде чем строить на нём перевод, надо знать ЦИФРУ: какая доля лора вообще
привязана к id однозначно. Инструмент отвечает ровно на этот вопрос.

⚠️ Связки «id -> лор» нет ни в одном сохранённом файле. `fetch_auction.py`
раскладывает лот на две части: лор уходит в `lore` по ТЕКСТОВОМУ ключу (он
источник цветов), а NBT — в `items` по id. Поэтому замер берёт данные заново.

⚠️ Берём ОДНУ страницу аукциона (1000 лотов), а не все 51: для доли этого
достаточно, а качать 110 МБ ради оценки незачем. Число лотов печатается —
если понадобится точность, страниц можно взять больше через --pages.

Запуск:
  python tools/check_item_ids.py            одна страница
  python tools/check_item_ids.py --pages 5  точнее, дольше
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import urllib.request
from pathlib import Path

CODES = re.compile(r"§.")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import nbt  # noqa: E402
from pkey import NUMBER  # noqa: E402

API = "https://api.hypixel.net/v2/skyblock/auctions?page={}"
CORPUS = ROOT / "data" / "work" / "paragraphs.json"


def fetch(page: int) -> list[dict]:
    with urllib.request.urlopen(API.format(page), timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("success"):
        raise SystemExit(f"API ответил success=false на странице {page}")
    return data.get("auctions") or []


def paragraphs_of(lore: str) -> list[str]:
    """
    Куски лора ТЕМ ЖЕ правилом, что у мода: режем по пустым строкам,
    короче двух строк не берём, склейка одним пробелом.

    Копия правила здесь недопустима — оно живёт в `Paragraphs.runs` и
    `make_paragraphs.py`, и расхождение уже стоило проекту 364 абзацев.
    Поэтому повторяем ровно то, что записано в контракте: пустая строка —
    единственная граница.
    """
    out: list[str] = []
    run: list[str] = []
    for line in lore.split("\n") + [""]:
        text = CODES.sub("", line).strip()
        if text:
            run.append(text)
            continue
        if len(run) >= 2:
            out.append(NUMBER.sub("{n}", " ".join(run)))
        run = []
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Доля лора, привязанного к ID предмета")
    parser.add_argument("--pages", type=int, default=1, help="сколько страниц аукциона взять")
    args = parser.parse_args()

    lots = []
    for page in range(args.pages):
        lots.extend(fetch(page))
        print(f"страница {page}: всего лотов {len(lots)}")

    with_id = 0
    without_id = 0
    # абзац -> множество id, у которых он встречается
    owners: dict[str, set[str]] = collections.defaultdict(set)
    ids_seen: set[str] = set()

    for lot in lots:
        raw = lot.get("item_bytes")
        lore = lot.get("item_lore") or ""
        item_id = ""
        if raw:
            try:
                item_id = nbt.find(nbt.read_item_bytes(raw), "id") or ""
            except (ValueError, OSError, KeyError, IndexError):
                item_id = ""
        if item_id:
            with_id += 1
            ids_seen.add(item_id)
        else:
            without_id += 1
            continue
        for para in paragraphs_of(lore):
            owners[para].add(item_id)

    print()
    print(f"лотов разобрано: {len(lots)}")
    print(f"  с ID в NBT:  {with_id}"
          f"  ({with_id * 100 // max(1, len(lots))}%)")
    print(f"  без ID:      {without_id}")
    print(f"  разных ID:   {len(ids_seen)}")
    print()

    single = [p for p, who in owners.items() if len(who) == 1]
    shared = [p for p, who in owners.items() if len(who) > 1]
    print(f"абзацев лора всего: {len(owners)}")
    print(f"  принадлежат ОДНОМУ id (можно привязать железно): {len(single)}"
          f"  ({len(single) * 100 // max(1, len(owners))}%)")
    print(f"  встречаются у НЕСКОЛЬКИХ id (общие фразы):       {len(shared)}")
    if shared:
        top = sorted(shared, key=lambda p: -len(owners[p]))[:5]
        print("  самые общие:")
        for para in top:
            print(f"     {len(owners[para]):4} предметов: {para[:56]}")
    print()

    # Главный вопрос: сколько НАШИХ переводов можно было бы привязать к id.
    if CORPUS.exists():
        corpus = json.loads(CORPUS.read_text(encoding="utf-8")).get("paragraphs") or []
        translated = {p["text"] for p in corpus if p.get("ru")}
        hit = translated & set(owners)
        hit_single = {p for p in hit if len(owners[p]) == 1}
        print(f"наш корпус: переведённых абзацев {len(translated)}")
        print(f"  встретились в этой выборке аукциона: {len(hit)}")
        print(f"  из них привязаны к ОДНОМУ id:        {len(hit_single)}")
        if hit:
            print(f"  доля однозначных среди встреченных:  "
                  f"{len(hit_single) * 100 // len(hit)}%")
    else:
        print(f"корпус не найден: {CORPUS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
