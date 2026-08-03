"""
Перки мэров из ОФИЦИАЛЬНОГО API Hypixel — вместе с разметкой цвета.

Зачем отдельный инструмент. Выборы идут круглый год, мэры и их перки меняются,
и каждый раз это десяток новых текстов, которые мы переводили руками ПЛОСКИМИ —
цвета взять было неоткуда. А Hypixel отдаёт их уже размеченными:

    "Get §3+60☯ Mining Wisdom §7on public islands."

То есть перевод можно сразу класть с §-кодами, и мод не будет угадывать цвет
(«не улучшать догадки, а убирать необходимость догадываться»).

⚠️ Ключ не нужен: /resources/* открыты. Но и данные там ЖИВЫЕ — состав перков
меняется вместе с выборами, поэтому запускать надо по ходу событий, а не раз
и навсегда.

⚠️ Инструмент НИЧЕГО не переводит и не лезет в словари. Он собирает заготовку
data/work/election_perks.json, где переводы вписываются руками (их единицы),
и сохраняет уже написанное при повторном запуске — как это делает
gen_enchants.py с заготовкой зачарований. Перезапись без чтения однажды уже
обнулила 41 перевод, повторять не будем.

Запуск:
    python tools/fetch_election.py            собрать/обновить заготовку
    python tools/fetch_election.py --show     показать, что не переведено
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "work" / "election_perks.json"
URL = "https://api.hypixel.net/v2/resources/skyblock/election"
UA = {"User-Agent": "SkyblockRU/0.1 (translation project)"}

SECTION = re.compile(r"§.")


def fetch() -> dict:
    request = urllib.request.Request(URL, headers=UA)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def candidates(data: dict) -> list[tuple[str, dict]]:
    """Кандидаты из ОБОИХ блоков: прошлые выборы и текущие."""
    found = []
    for block in ("election", "current"):
        part = data.get(block) or {}
        year = part.get("year")
        for candidate in (part.get("candidates") or []):
            found.append((str(year), candidate))
    return found


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Перки мэров из API Hypixel")
    parser.add_argument("--show", action="store_true", help="показать непереведённое")
    args = parser.parse_args()

    # ⚠️ Сперва читаем СВОЁ: в файле лежит ручная работа.
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")).get("perks", {})
        except (json.JSONDecodeError, OSError) as problem:
            print(f"не смог прочитать прежнюю заготовку: {problem}")
            return 1

    if args.show:
        waiting = {key: item for key, item in old.items() if not item.get("ru")}
        print(f"перков в заготовке: {len(old)}, ждут перевода: {len(waiting)}")
        for key, item in waiting.items():
            print(f"\n  [{item.get('mayor')}] {key}")
            print(f"    {item.get('en')}")
        return 0

    try:
        data = fetch()
    except (urllib.error.URLError, TimeoutError) as problem:
        print(f"API недоступен: {problem}")
        return 1

    perks = dict(old)
    added, refreshed, coloured = 0, 0, 0
    for year, candidate in candidates(data):
        mayor = candidate.get("name", "?")
        for perk in (candidate.get("perks") or []):
            name = perk.get("name")
            english = perk.get("description", "")
            if not name or not english:
                continue
            if SECTION.search(english):
                coloured += 1
            entry = perks.get(name)
            if entry is None:
                perks[name] = {
                    "mayor": mayor,
                    "year": year,
                    "minister": bool(perk.get("minister")),
                    "en": english,
                    "ru": "",
                }
                added += 1
                continue
            # ⚠️ Текст у Hypixel меняется (правят числа и формулировки).
            # Обновляем оригинал, но НЕ трогаем перевод: решать, устарел ли он,
            # должен человек — молча стереть работу хуже, чем показать расхождение.
            if entry.get("en") != english:
                entry["stale_en"] = entry.get("en")
                entry["en"] = english
                refreshed += 1
            entry["mayor"] = mayor
            entry["year"] = year

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_comment": "Перки мэров из api.hypixel.net/v2/resources/skyblock/election. "
                    "Оригинал приходит С §-КОДАМИ — переводить надо вместе с ними, "
                    "тогда мод выложит цвет точно, а не догадкой. Поле stale_en "
                    "означает, что Hypixel переписал текст: перевод стоит перечитать.",
        "perks": perks,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    waiting = sum(1 for item in perks.values() if not item.get("ru"))
    stale = sum(1 for item in perks.values() if item.get("stale_en"))
    print(f"перков всего: {len(perks)} (новых {added}, обновлён текст у {refreshed})")
    print(f"  из них с §-кодами в оригинале: {coloured}")
    print(f"  ждут перевода: {waiting}" + (f", устарел оригинал у {stale}" if stale else ""))
    print(f"\nзаготовка: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
