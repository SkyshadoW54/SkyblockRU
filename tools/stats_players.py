# -*- coding: utf-8 -*-
"""
Сколькими людьми мод пользуется — сводка по меткам установок.

⚠️ Что здесь считается и чего НЕТ. Метка установки — случайный UUID,
который мод придумывает на машине игрока при первом запуске. По ней видно
только, что два пакета пришли с одной установки: ни ника, ни аккаунта
Minecraft, ни адреса тут нет и не будет.

⚠️ Границы цифры, чтобы не обмануться:
  * считаются те, кто ЗАХОДИЛ В SKYBLOCK с включённой отправкой. Выключил
    `/skyblockru telemetry off` — в счёт не попадает;
  * переставил мод начисто (снёс config) — станет «новой установкой»;
  * один человек с двумя инстансами — это две установки. У нас самих их
    шесть, и первые дни счёта состоят почти целиком из них.

  python tools/stats_players.py            сводка
  python tools/stats_players.py --days 30  окно активности
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REMOTE_DIR = "/var/lib/skyblockru"


def server() -> str | None:
    """Адрес сервера — из окружения: репозиторий публичный."""
    value = os.environ.get("SKYBLOCKRU_SERVER")
    if value:
        return value
    try:
        got = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Environment]::GetEnvironmentVariable('SKYBLOCKRU_SERVER','User')"],
            capture_output=True, text=True, timeout=60)
        return (got.stdout or "").strip() or None
    except Exception:
        return None


def fetch(host: str) -> list[tuple[str, dict]]:
    """Пакеты с сервера: (дата, запись)."""
    # ⚠️ Дату берём из ИМЕНИ ФАЙЛА штатным grep-ом, а не собираем строку
    # в шелле: первая версия склеивала её через `basename` внутри двойных
    # кавычек, экранирование поехало, и команда возвращала ПУСТО при коде 0 —
    # то есть инструмент выходил молча, как будто данных нет вовсе.
    got = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host,
         f"grep -H '' {REMOTE_DIR}/*.jsonl"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if got.returncode != 0 or not got.stdout.strip():
        print("с сервера ничего не пришло.",
              (got.stderr or "").strip()[:200] or "файлов нет?")
        return []
    out = []
    for row in got.stdout.splitlines():
        # «/var/lib/skyblockru/2026-08-08.jsonl:{...}»
        path, _, raw = row.partition(":")
        if not raw.strip():
            continue
        day = Path(path).stem
        try:
            out.append((day, json.loads(raw)))
        except json.JSONDecodeError:
            continue
    if not out:
        print("строки пришли, но ни одна не разобралась как JSON")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="окно активности")
    args = parser.parse_args()

    host = server()
    if not host:
        print("не задан SKYBLOCKRU_SERVER — адрес сервера держим в окружении")
        return 1

    packets = fetch(host)
    if not packets:
        return 1

    installs: dict[str, list[str]] = defaultdict(list)
    no_mark = 0
    games = Counter()
    mods = Counter()
    for day, rec in packets:
        mark = rec.get("install") or ""
        if not mark:
            no_mark += 1
            continue
        installs[mark].append(day)
        games[rec.get("game") or "?"] += 1
        mods[rec.get("mod") or "?"] += 1

    print(f"пакетов всего: {len(packets)}")
    if no_mark:
        # ⚠️ Пакеты от старых сборок метки не несут — их и не посчитать.
        # Это не потеря: счёт начинается с той версии, где метка появилась.
        print(f"   без метки (мод старее 0.2.14): {no_mark}")

    print()
    print(f"=== УСТАНОВОК ВСЕГО: {len(installs)} ===")
    if not installs:
        print("   пока ни одной — метка появилась в 0.2.14, нужен хотя бы один заход")
        return 0

    today = date.today()
    window = {(today - timedelta(days=n)).isoformat() for n in range(args.days)}
    active = [m for m, days in installs.items() if window & set(days)]
    print(f"=== АКТИВНЫХ за {args.days} дн.: {len(active)} ===")

    print()
    print("=== ПО ДНЯМ (уникальных установок) ===")
    by_day: dict[str, set[str]] = defaultdict(set)
    for mark, days in installs.items():
        for day in days:
            by_day[day].add(mark)
    for day in sorted(by_day)[-14:]:
        print(f"   {day}   {len(by_day[day]):3d}")

    print()
    print("=== ВЕРСИИ ИГРЫ (по пакетам) ===")
    for name, count in games.most_common():
        print(f"   {name:12} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
