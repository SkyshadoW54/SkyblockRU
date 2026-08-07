# -*- coding: utf-8 -*-
"""
ЛОСКУТЫ — отбор того, за что стоит платить.

⚠️ Зачем отдельный инструмент. `scan_all.py` находит абзацы, где часть строк
переведена, а часть нет («ЛОСКУТ»), — это самая заметная беда на экране:
подсказка выглядит наполовину сломанной. Но его список НЕ равен счёту
к оплате: там и обрывки фраз (покупать их вредно — у обрывка нет своего
смысла), и списки, и наборы зачарований, и таблицы характеристик, которые
закрыты правилами.

Здесь тот же поиск, но с фильтрами покупки — теми же, что стоят в платном
прогоне (`translate_tooltips.mark_*`). Своих признаков не заводим: копия
разошлась бы с прогоном, и мы платили бы за отсеянное.

⚠️ Цена считается по замеру проекта — $0.0019 за абзац обычным режимом
(Opus 5, effort high). Это ОРИЕНТИР: настоящий счёт зависит от длины
абзацев и разовой записи кэша, и смотреть его надо в `usage` после прогона.

  python tools/pick_patches.py              показать отбор и цену
  python tools/pick_patches.py --out FILE   выгрузить задание для перевода
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

LORE = ROOT / "data" / "work" / "auction_lore.json"
CORPUS = ROOT / "data" / "work" / "paragraphs.json"

# замер проекта: обычный режим, Opus 5, effort high
PRICE_PER_PARAGRAPH = 0.0019


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="куда выгрузить задание")
    parser.add_argument("--limit", type=int, default=0, help="сколько взять")
    args = parser.parse_args()

    import scan_all
    import status
    import make_queue
    import translate_tooltips as tt

    if not LORE.exists():
        print(f"нет файла: {LORE}\nСобрать: python tools/fetch_auction.py")
        return 1

    dic = status.Dictionaries()
    filters = scan_all.load_filters()
    closed = make_queue.in_paragraphs()

    def known(line: str) -> bool:
        """Строка закрыта — переводом, абзацем или мерцающим ядром."""
        flat = scan_all.generalized(line)
        if status.lookup(flat, dic) or flat in closed:
            return True
        core = line.strip()
        if core.startswith("a ") and core.endswith(" a"):
            return bool(status.lookup(scan_all.generalized(core[2:-2].strip()), dic))
        return False

    lore = json.loads(LORE.read_text(encoding="utf-8")).get("lore") or {}

    # --- 1. собираем абзацы-лоскуты
    patches: dict[str, dict] = {}
    for lines in lore.values():
        if not isinstance(lines, list) or len(lines) < 2:
            continue
        texts = [scan_all.plain(x) for x in lines]
        joined = " ".join(t for t in texts if t)
        if not joined.strip():
            continue
        key = scan_all.generalized(joined)
        if key in patches:
            patches[key]["seen"] += 1
            continue
        # перевод абзаца уже есть — не лоскут
        got = None
        for source in (dic.paragraphs, dic.exact, dic.templates):
            got = source.get(key) or source.get(joined.strip())
            if got:
                break
        if got:
            continue
        done = [t for t in texts if t and known(t)]
        left = [t for t in texts if t and not known(t)
                and scan_all.still_english(t, filters)]
        if done and left:
            patches[key] = {"en": joined.strip(), "key": key,
                            "lines": texts, "left": left, "seen": 1}

    print(f"абзацев-лоскутов: {len(patches)}")

    # --- 2. что из них уже лежит в корпусе (значит попадёт в обычный прогон)
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    items = corpus if isinstance(corpus, list) else list(corpus.values())[0]
    in_corpus = {p.get("key") for p in items if isinstance(p, dict)}
    fresh = {k: v for k, v in patches.items() if k not in in_corpus}
    print(f"   из них НЕТ в корпусе: {len(fresh)}"
          f"  (остальные {len(patches) - len(fresh)} уже в обычной очереди)")

    # --- 3. фильтры покупки — те же, что в платном прогоне
    # ⚠️ Поле «text» обязательно: mark_nothing читает именно его,
    # а без него фильтр молча падает и счёт выходит завышенным.
    paras = [{"key": v["key"], "en": v["en"], "text": v["en"],
              "lines": v["lines"], "ru": ""}
             for v in fresh.values()]
    dropped = {}
    for name, fn in (("переводить нечего", tt.mark_nothing),
                     ("список", tt.mark_lists),
                     ("набор зачарований", tt.mark_enchant_combos),
                     ("таблица характеристик", tt.mark_stat_tables),
                     ("одни имена", tt.mark_name_lists)):
        try:
            before = sum(1 for p in paras if p.get("nothing"))
            fn(paras)
            dropped[name] = sum(1 for p in paras if p.get("nothing")) - before
        except Exception as trouble:      # фильтр требует своих полей
            dropped[name] = f"пропущен ({trouble})"

    buy = [p for p in paras if not p.get("nothing")]

    print()
    print("=== ОТСЕЯНО ФИЛЬТРАМИ ПОКУПКИ ===")
    for name, count in dropped.items():
        print(f"   {name:24} {count}")

    print()
    print(f"=== К ПОКУПКЕ: {len(buy)} абзацев ===")
    print(f"    ориентировочно: ${len(buy) * PRICE_PER_PARAGRAPH:.2f}"
          f"  (по замеру ${PRICE_PER_PARAGRAPH} за абзац)")
    for p in buy[:12]:
        print("   ", p["en"][:96])

    if args.out:
        take = buy[:args.limit] if args.limit else buy
        Path(args.out).write_text(
            json.dumps(take, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nзадание: {args.out} ({len(take)} абзацев)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
