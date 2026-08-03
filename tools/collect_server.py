# -*- coding: utf-8 -*-
"""
Забрать присланные игроками строки и отделить настоящие от подделок.

    python tools/collect_server.py            показать, что накопилось
    python tools/collect_server.py --merge    влить в data/work/from_players.json
    python tools/collect_server.py --min 3    брать только то, что прислали 3+ раза

⚠️ ГЛАВНОЕ: КЛИЕНТУ ДОВЕРЯТЬ НЕЛЬЗЯ, и это не чинится проверками в моде.
Мод стоит у игрока, адрес приёмника виден в jar, отправить туда что угодно
можно любым curl. Значит вопрос не «как запретить», а «как не пустить чужое
в перевод».

Работает признак, которого у подделки нет: **строку из игры видят МНОГИЕ**.
Настоящая надпись SkyBlock приходит от разных игроков в разных сессиях,
а выдуманная — ровно из одного пакета. Поэтому здесь считается, в скольких
РАЗНЫХ пакетах встретилась строка, и порог задаётся руками.

⚠️ Порог по умолчанию 1 — пока игрок один, иначе отсеется всё. Как только
мод разойдётся, поднять до 2–3: это и есть защита от «отправил специально».
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "work" / "from_players.json"

# ⚠️ Адрес сервера НЕ ЗАШИВАЕМ: репозиторий публичный, а это боевая машина.
# Задаётся переменной окружения SKYBLOCKRU_SERVER (например `root@1.2.3.4`
# или короткое имя из ~/.ssh/config).
SERVER = os.environ.get("SKYBLOCKRU_SERVER", "").strip()
REMOTE_DIR = os.environ.get("SKYBLOCKRU_REMOTE_DIR", "/var/lib/skyblockru")


def fetch() -> list[dict]:
    """Скачать все пакеты с сервера. Одной командой, без промежуточных файлов."""
    if not SERVER:
        raise SystemExit(
            "не задан адрес сервера: заведи переменную окружения\n"
            "  SKYBLOCKRU_SERVER=root@адрес\n"
            "В код он не вписан намеренно — репозиторий публичный.")
    done = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", SERVER, f"cat {REMOTE_DIR}/*.jsonl 2>/dev/null"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        print("не достучался до сервера:", (done.stderr or "").strip()[:200])
        return []
    packets = []
    for line in (done.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            packets.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return packets


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Строки от игроков")
    parser.add_argument("--merge", action="store_true", help="записать в data/work")
    parser.add_argument("--min", type=int, default=1,
                        help="сколько РАЗНЫХ пакетов должны прислать строку")
    parser.add_argument("--show", type=int, default=15)
    args = parser.parse_args()

    packets = fetch()
    if not packets:
        print("пакетов нет — либо никто ещё не прислал, либо сервер недоступен")
        return 0

    # (источник, строка) -> в скольких пакетах встретилась
    seen: dict[tuple[str, str], int] = Counter()
    versions = Counter()
    for packet in packets:
        versions[(packet.get("mod") or "?", packet.get("game") or "?")] += 1
        here = set()
        for source, rows in (packet.get("lines") or {}).items():
            for row in rows:
                here.add((source, row))
        for key in here:
            seen[key] += 1

    by_source: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (source, row), count in seen.items():
        by_source[source].append((row, count))

    print(f"пакетов: {len(packets)}, разных строк: {len(seen)}")
    print("версии, с которых слали:")
    for (mod, game), count in versions.most_common(5):
        print(f"   мод {mod:12} игра {game:10} — {count} пакетов")
    print()

    total_keep = 0
    print(f"{'источник':14} {'всего':>6} {'прошли порог ' + str(args.min):>18}")
    for source in sorted(by_source):
        rows = by_source[source]
        keep = [row for row, count in rows if count >= args.min]
        total_keep += len(keep)
        print(f"   {source:12} {len(rows):6} {len(keep):18}")

    # ⚠️ Одиночные строки показываем ОТДЕЛЬНО и не прячем: при одном игроке
    # это норма, а при сотне — первый признак, что кто-то шлёт своё.
    lonely = [(source, row) for (source, row), count in seen.items() if count == 1]
    if lonely and len(packets) > 3:
        print()
        print(f"прислали РОВНО ОДИН раз: {len(lonely)}")
        print("   при большом числе игроков это подозрительно — смотреть глазами")
        for source, row in lonely[:args.show]:
            print(f"      [{source}] {row[:80]}")

    if not args.merge:
        print("\nсухой прогон. Записать: --merge")
        return 0

    payload = {source: sorted(row for row, count in rows if count >= args.min)
               for source, rows in by_source.items()}
    payload = {source: rows for source, rows in payload.items() if rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано: {OUT}  ({total_keep} строк)")
    print("дальше — обычным путём: make_queue.py -> pick_queue.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
