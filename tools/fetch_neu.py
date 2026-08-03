"""
Собирает тексты предметов из репозитория NotEnoughUpdates-REPO.

Зачем это нужно вдобавок к API Hypixel: в API у предметов есть название, но
почти нет описаний (в ответе всего ~460 уникальных строк описаний на 5.5 тысяч
предметов). Настоящий лор — характеристики, способности, комментарии — лежит
в NEU-репозитории: сообщество вычитало его из игры и держит в JSON.

Репозиторий: https://github.com/NotEnoughUpdates/NotEnoughUpdates-REPO (лицензия MIT)
Формат файла предмета: items/<ID>.json -> { "displayname": "...", "lore": ["...", ...] }
Строки идут с кодами §, они здесь вырезаются.

Что получается (папка data/):
  data/neu/repo.zip              - скачанный архив (второй раз не качается)
  data/en/neu_names.txt          - названия предметов
  data/en/neu_lore.txt           - строки описаний с частотой
  data/skeleton/neu_items.json   - заготовка словаря: названия -> ""
  data/skeleton/neu_lore.json    - заготовка словаря: строки описаний -> ""

Запуск:  python tools/fetch_neu.py
         python tools/fetch_neu.py --offline   (взять уже скачанный архив)
"""

from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

ZIP_URL = "https://github.com/NotEnoughUpdates/NotEnoughUpdates-REPO/archive/refs/heads/master.zip"

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

SECTION_CODE = re.compile(r"§[0-9a-fk-orA-FK-OR]")
# Строки, которые переводить бессмысленно: только числа, чёрточки, проценты
NOISE = re.compile(r"^[\d\s\-–—+%.,:/()\[\]]*$")


def strip_codes(text: str) -> str:
    return SECTION_CODE.sub("", text).strip()


def load_existing_translations() -> dict[str, str]:
    done: dict[str, str] = {}
    if not PACKS.is_dir():
        return done
    for path in sorted(PACKS.rglob("*.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for src, dst in (pack.get("exact") or {}).items():
            if dst:
                done[src] = dst
    return done


def download(target: Path) -> None:
    print(f"качаю {ZIP_URL}")
    print("  (репозиторий ~60 МБ, это займёт минуту)")
    req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "SkyblockRU/0.1 (translation tool)"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read()
    target.write_bytes(data)
    print(f"  сохранил: {target.relative_to(ROOT)} ({len(data) / 1024 / 1024:.1f} МБ)")


def main() -> int:
    (DATA / "neu").mkdir(parents=True, exist_ok=True)
    (DATA / "en").mkdir(parents=True, exist_ok=True)
    (DATA / "skeleton").mkdir(parents=True, exist_ok=True)

    archive = DATA / "neu" / "repo.zip"
    if not archive.exists() or "--force" in sys.argv:
        if "--offline" in sys.argv:
            print("офлайн-режим, но архива нет — сначала запусти без --offline", file=sys.stderr)
            return 1
        download(archive)
    else:
        print(f"беру уже скачанный архив: {archive.relative_to(ROOT)}")

    names: Counter[str] = Counter()
    lore: Counter[str] = Counter()
    files = 0
    broken = 0

    with zipfile.ZipFile(archive) as zf:
        members = [n for n in zf.namelist() if "/items/" in n and n.endswith(".json")]
        print(f"файлов предметов в архиве: {len(members)}")
        for name in members:
            try:
                with zf.open(name) as handle:
                    item = json.load(io.TextIOWrapper(handle, encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                broken += 1
                continue
            files += 1

            display = strip_codes(item.get("displayname") or "")
            if display and not NOISE.match(display):
                names[display] += 1

            for line in item.get("lore") or []:
                if not isinstance(line, str):
                    continue
                clean = strip_codes(line)
                if clean and not NOISE.match(clean) and len(clean) <= 300:
                    lore[clean] += 1

    print(f"обработано: {files}, битых пропущено: {broken}")
    print(f"уникальных названий: {len(names)}")
    print(f"уникальных строк описаний: {len(lore)}")

    (DATA / "en" / "neu_names.txt").write_text(
        "\n".join(name for name, _ in names.most_common()) + "\n", encoding="utf-8")
    (DATA / "en" / "neu_lore.txt").write_text(
        "\n".join(f"{count}\t{line}" for line, count in lore.most_common()) + "\n", encoding="utf-8")

    done = load_existing_translations()

    def skeleton(counter: Counter[str], pack_id: str, priority: int, comment: str) -> dict:
        return {
            "id": pack_id,
            "priority": priority,
            "_comment": comment,
            "exact": {key: done.get(key, "") for key, _ in counter.most_common()},
        }

    # --- отдельная заготовка, где строки идут ПО ПРЕДМЕТАМ и в исходном порядке ---
    # Это главное для качества: фраза в подсказке разрезана на несколько строк,
    # и переводить их надо вместе, а не по одной. Плюс к каждой строке прикладывается
    # имя предмета как подсказка о контексте.
    blocks: dict[str, str] = {}
    context: dict[str, str] = {}
    with zipfile.ZipFile(archive) as zf:
        for name in sorted(n for n in zf.namelist() if "/items/" in n and n.endswith(".json")):
            try:
                with zf.open(name) as handle:
                    item = json.load(io.TextIOWrapper(handle, encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            display = strip_codes(item.get("displayname") or "")
            for line in item.get("lore") or []:
                if not isinstance(line, str):
                    continue
                clean = strip_codes(line)
                if not clean or NOISE.match(clean) or len(clean) > 300:
                    continue
                if clean not in blocks:
                    blocks[clean] = done.get(clean, "")
                    if display:
                        context[clean] = display

    # --- подсказки ЦЕЛИКОМ, а не построчно ---
    # Обрывок фразы («Bag.», «each.») в отрыве от соседей перевести нельзя, а
    # одна и та же строка у разных предметов может продолжать разные фразы.
    # Поэтому храним подсказку блоком и переводим её целиком.
    # Числа заменяем на {n}: тогда десятки одинаковых по смыслу подсказок
    # (миньоны разных ступеней) схлопываются в одну.
    NUM = re.compile(r"\d+(?:[.,]\d+)*")
    tooltips: dict[tuple[str, ...], str] = {}
    with zipfile.ZipFile(archive) as zf:
        for name in sorted(n for n in zf.namelist() if "/items/" in n and n.endswith(".json")):
            try:
                with zf.open(name) as handle:
                    item = json.load(io.TextIOWrapper(handle, encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            lines = []
            for line in item.get("lore") or []:
                if not isinstance(line, str):
                    continue
                clean = NUM.sub("{n}", strip_codes(line))
                if len(clean) <= 300:
                    lines.append(clean)
            # пустые и однострочные блоки смысла не имеют: там нечего склеивать
            if len([l for l in lines if l.strip()]) < 2:
                continue
            key = tuple(lines)
            tooltips.setdefault(key, strip_codes(item.get("displayname") or ""))

    (DATA / "work").mkdir(parents=True, exist_ok=True)
    (DATA / "work" / "lore_tooltips.json").write_text(
        json.dumps({
            "id": "lore_tooltips",
            "_comment": "Подсказки предметов ЦЕЛИКОМ. Переводить блоками: число строк "
                        "менять нельзя, иначе перевод не разложится обратно. "
                        "{n} — любое число, подставит движок.",
            "tooltips": [
                {"item": item_name, "lines": list(lines), "ru": []}
                for lines, item_name in tooltips.items()
            ],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  подсказки целиком: data/work/lore_tooltips.json ({len(tooltips)} блоков)")

    (DATA / "work" / "lore_blocks.json").write_text(
        json.dumps({
            "id": "lore_blocks",
            "priority": 40,
            "_comment": "Строки описаний В ПОРЯДКЕ ПОЯВЛЕНИЯ у предметов — соседние строки "
                        "одной подсказки идут подряд, поэтому переводчик видит их вместе "
                        "и не рубит фразу пополам.",
            "_contexts": context,
            "exact": blocks,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  блоки по предметам: data/work/lore_blocks.json ({len(blocks)} строк)")

    (DATA / "skeleton" / "neu_items.json").write_text(
        json.dumps(skeleton(names, "neu_items", 30,
                            "Названия предметов из NEU-репозитория."),
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "skeleton" / "neu_lore.json").write_text(
        json.dumps(skeleton(lore, "neu_lore", 40,
                            "Строки описаний предметов из NEU-репозитория, "
                            "отсортированы по частоте: сверху то, что встречается чаще всего."),
                   ensure_ascii=False, indent=1), encoding="utf-8")

    print()
    print("готово:")
    print(f"  data/skeleton/neu_items.json — {len(names)} строк")
    print(f"  data/skeleton/neu_lore.json  — {len(lore)} строк")
    print()
    print("Переводить начинай сверху neu_lore.txt — там самые частые строки:")
    print("одна такая строка встречается в сотнях предметов сразу.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
