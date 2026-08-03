"""
Лор предметов С ЦВЕТАМИ из ОФИЦИАЛЬНОГО API аукциона Hypixel.

Зачем. Главная дыра проекта — разметка: перевод хранится чистым текстом, и цвет
мод восстанавливает догадкой (возвращается 19-47% подсветки). Источников цвета
было два: репозиторий NEU (исчерпан) и живая игра — а в ней цвет приходит только
там, куда игрок сходил.

Оказалось, есть третий, и он лучше обоих: `api.hypixel.net/v2/skyblock/auctions`
отдаёт ВСЕ лоты (51 страница по 1000), и у каждого поле `item_lore` — лор
с §-кодами. Проверено: у 1000 из 1000 лотов коды на месте.

⚠️ Промах был системным, и записан в CLAUDE.md: проект ходил в ДВА эндпоинта
Hypixel из тринадцати, а список ни разу не открывал. Причём про перки мэров
у нас прямо написано «из API — С §-КОДАМИ»: факт был известен и применён
к двадцати строкам вместо пятидесяти тысяч.

⚠️ Что этот источник НЕ покрывает, чтобы не завышать снова:
  * предметы, которых сейчас нет в продаже (квестовые, привязанные к аккаунту);
  * меню, экраны и справочники — их на аукционе не бывает;
  * чат, реплики NPC, боковую панель, полосу над хотбаром.
Для всего этого по-прежнему нужна игра либо другие эндпоинты.

Второе, что тут есть, — NBT каждого предмета (`item_bytes`: base64 + gzip).
Оттуда берутся ИДЕНТИФИКАТОР, зачарования с уровнями, самоцветы и перековка —
то есть ровно те сведения, которые мы годами добывали разбором готового текста.
Читает их `tools/nbt.py`; проверено на живой странице: 1000 из 1000 без сбоев,
у всех есть `ExtraAttributes.id`.

⚠️ Формат в API — СТАРЫЙ (`tag.ExtraAttributes`), а в клиенте 1.21 данные живут
в компонентах (`custom_data`). Это не мелочь: код, написанный под один формат,
на другом молча вернёт пустоту. Оба пути нужны, и оба проверены на живых данных.

⚠️ Главное, что даёт NBT, — ПОЛНЫЙ список зачарований от самого сервера.
Наши списки собирались из того, что мод встретил на экране, и были неполны
везде (98 против 131 на вики). Список сервера — канонический, и по нему можно
проверять машинно, а не признаком по форме строки.

Запуск:
  python tools/fetch_auction.py              все страницы, лор и NBT
  python tools/fetch_auction.py --pages 8    только первые восемь
  python tools/fetch_auction.py --no-nbt     без разбора NBT (быстрее)
  python tools/fetch_auction.py --dry        ничего не писать, только замер
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import nbt  # noqa: E402
from pkey import NUMBER  # noqa: E402

API = "https://api.hypixel.net/v2/skyblock/auctions"
OUT = ROOT / "data" / "work" / "auction_lore.json"
CORPUS = ROOT / "data" / "work" / "paragraphs.json"

CODE = re.compile("§.")


def strip_codes(text: str) -> str:
    return CODE.sub("", text)


def fetch(page: int, tries: int = 3) -> dict | None:
    """Одна страница. None — не получилось, и это не повод падать."""
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(f"{API}?page={page}", timeout=120) as answer:
                return json.loads(answer.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == tries - 1:
                print(f"     страница {page}: не вышло ({type(error).__name__})")
                return None
            time.sleep(2)
    return None


def paragraphs_of(lore: str) -> dict[str, list[str]]:
    """
    Абзацы из лора одного лота: ключ -> строки С §-кодами.

    ⚠️ Режем ТОЧНО как мод и как корпус: только по пустым строкам, короче двух
    строк не берём, склейка одним пробелом, числа обобщаем. Разойдись хоть
    на пробел — ключи не совпадут НИ РАЗУ, и источник молча даст ноль
    попаданий. Этой граблей проект уже платил (см. check_contract.py).
    """
    out: dict[str, list[str]] = {}
    run: list[str] = []
    for line in lore.split("\n") + [""]:
        if strip_codes(line).strip():
            run.append(line.strip())
            continue
        if len(run) >= 2:
            key = NUMBER.sub("{n}", " ".join(
                strip_codes(part).strip() for part in run)).strip()
            out.setdefault(key, run.copy())
        run = []
    return out


def bare(text: str) -> str:
    """Имя без регистра и разделителей — как Paragraphs.bareName в моде."""
    return "".join(c.lower() for c in text if c.isalnum())


def known_names() -> set[str]:
    """
    Все имена, которые знают наши словари.

    ⚠️ Читаем ВСЕ словари и ВСЕ секции, а не группу `enchant` из terms.py.
    Ванильные зачарования живут отдельно (`76-enchant-names.json`), потому что
    их переводит сам клиент, и считать их «отсутствующими» — та же ошибка
    «условие не выполнено = работа есть», на которой я сегодня погорел трижды.
    Из правил достаём термин из шаблона: «^Angler ([IVXLC]+)$» -> «Angler».
    """
    packs = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
    out: set[str] = set()
    for path in packs.rglob("*.json"):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in (pack.get("exact") or {}):
            out.add(bare(re.sub(r"\s+[IVXLC]+$", "", key)))
        for key in (pack.get("glossary") or {}):
            out.add(bare(key))
        for rule in (pack.get("regex") or []):
            pattern = rule.get("p") if isinstance(rule, dict) else ""
            term = re.sub(r"[\^\$]|\(.*?\)|\\[sb]\+?|\s+$", "", pattern or "")
            if term:
                out.add(bare(term))
    return out


def report_missing(server: list[str]) -> None:
    """
    Каких зачарований СЕРВЕРА мы не знаем.

    Это главная польза NBT для проверок: список зачарований у нас собирался
    из того, что мод встретил на экране, и был неполон всегда — 98 против 131
    на вики. Сервер отдаёт канонический перечень, и сверка становится
    механической вместо «поискать глазами на вики».
    """
    ours = known_names()
    missing = []
    for name in server:
        probe = bare(name)
        # Ультимативные сервер пишет с префиксом: ultimate_chimera -> Chimera.
        short = bare(name[len("ultimate_"):]) if name.startswith("ultimate_") else probe
        if probe not in ours and short not in ours:
            missing.append(name)
    print()
    print(f"=== ЗАЧАРОВАНИЙ СЕРВЕРА НЕТ В НАШИХ СЛОВАРЯХ: {len(missing)} ===")
    if not missing:
        print("  все известны")
        return
    for name in missing:
        print(f"   {name}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Лор с цветами из API аукциона")
    parser.add_argument("--pages", type=int, default=0,
                        help="сколько страниц взять (0 — все)")
    parser.add_argument("--no-nbt", action="store_true",
                        help="не разбирать item_bytes (только лор)")
    parser.add_argument("--dry", action="store_true", help="не записывать файл")
    args = parser.parse_args()

    first = fetch(0)
    if first is None or not first.get("success"):
        print("API аукциона не ответил")
        return 1
    total = int(first.get("totalPages") or 1)
    pages = total if args.pages <= 0 else min(args.pages, total)
    print(f"страниц у API: {total}, лотов {first.get('totalAuctions')}")
    print(f"беру: {pages}")

    # Прежние находки НЕ выбрасываем: аукцион живой, и предмет, который сегодня
    # не продают, вчера мог попасться. Файл накопительный — по той же причине,
    # по которой накопителен дамп цветов.
    known: dict[str, list[str]] = {}
    items: dict[str, dict] = {}
    if OUT.exists():
        try:
            saved = json.loads(OUT.read_text(encoding="utf-8"))
            known = saved.get("lore") or {}
            items = saved.get("items") or {}
        except (json.JSONDecodeError, OSError):
            known, items = {}, {}
    was, was_items = len(known), len(items)

    lots = 0
    broken = 0
    for page in range(pages):
        data = first if page == 0 else fetch(page)
        if data is None:
            continue
        for lot in data.get("auctions") or []:
            lore = lot.get("item_lore") or ""
            if CODE.search(lore):
                lots += 1
                for key, lines in paragraphs_of(lore).items():
                    known.setdefault(key, lines)
            if args.no_nbt or not lot.get("item_bytes"):
                continue
            try:
                extra = nbt.find(nbt.read_item_bytes(lot["item_bytes"]),
                                 "ExtraAttributes")
            except (ValueError, OSError, EOFError):
                broken += 1
                continue
            if not isinstance(extra, dict) or not extra.get("id"):
                continue
            # По одному на идентификатор: нужна СТРУКТУРА предмета, а не архив
            # чужих лотов. Тысяча одинаковых мечей ничего не добавит, а вот
            # набор зачарований у них разный — его и копим.
            record = items.setdefault(str(extra["id"]), {
                "name": lot.get("item_name") or "",
                "tier": lot.get("tier") or "",
                "enchants": [],
                "modifiers": [],
            })
            for name in (extra.get("enchantments") or {}):
                if name not in record["enchants"]:
                    record["enchants"].append(name)
            modifier = extra.get("modifier")
            if modifier and modifier not in record["modifiers"]:
                record["modifiers"].append(modifier)
        if (page + 1) % 10 == 0 or page + 1 == pages:
            print(f"     {page + 1:2}/{pages}: абзацев {len(known)}, "
                  f"предметов {len(items)}")

    print()
    print(f"лотов с цветным лором: {lots}")
    print(f"абзацев: {len(known)}  (новых за прогон: {len(known) - was})")
    if not args.no_nbt:
        every = sorted({name for row in items.values() for name in row["enchants"]})
        mods = sorted({m for row in items.values() for m in row["modifiers"]})
        print(f"предметов по id: {len(items)}  (новых: {len(items) - was_items})")
        print(f"  разных ЗАЧАРОВАНИЙ у сервера: {len(every)}")
        print(f"  разных перековок (modifier):  {len(mods)}")
        if broken:
            print(f"  NBT не разобрался у {broken} лотов")
        report_missing(every)

    # Замер по делу: сколько НАШИХ плоских переводов это закрывает.
    if CORPUS.exists():
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))["paragraphs"]
        flat = {p["text"] for p in corpus if p.get("ru") and "§" not in p["ru"]}
        marked = {p["text"] for p in corpus if p.get("ru") and "§" in p["ru"]}
        closes = len(flat & set(known))
        print()
        print(f"плоских переводов в корпусе: {len(flat)}")
        print(f"  из них закрывает аукцион:  {closes}"
              f"  ({closes * 100 // max(len(flat), 1)}%)")
        fresh = len(set(known) - flat - marked)
        print(f"абзацев, которых в корпусе НЕТ вовсе: {fresh}")
        print("  (это материал для ПЕРЕВОДА, а не подарок: за него платят)")

    if args.dry:
        print("\nсухой прогон: файл не записан")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_comment": "Item lore WITH color codes and item NBT from the official Hypixel "
                    "auction API. Accumulative: an item not on sale today may have been "
                    "yesterday. Lore is read by tools/color_lore.py as a source of "
                    "colors; items[] holds the server's own enchantment names.",
        "lore": known,
        "items": items,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано: {OUT.relative_to(ROOT)}")
    print("дальше: python tools/color_lore.py   (посмотреть, сколько ждёт разметки)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
