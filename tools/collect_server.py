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
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "work" / "from_players.json"
BLOCKS_OUT = ROOT / "data" / "work" / "blocks_from_players.json"

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


# ⚠️⚠️ СТРОКИ ЧУЖИХ МОДОВ. Игрок с чужой сборкой присылает не только текст
# Hypixel: соседние моды пишут в чат, рисуют свои экраны и дописывают в лор.
# Замер 07.08 по живым пакетам: у одного игрока 10 таких строк —
#
#     [chat]      [SkyHanni] +{n} SkyBlock XP (Collections) ({n}/{n})
#     [chat]      Caught a IllegalStateException in at.hannibal2.skyhanni…
#     [item_lore] (From SkyHanni)
#     [title]     Odin Update Available
#
# Переводить их НЕЛЬЗЯ: это чужая работа, у большинства игроков этих строк нет
# вовсе, а «(From SkyHanni)» в подсказке — вообще приписка соседа к предмету.
#
# ⚠️ Имена ищем ПО ГРАНИЦЕ СЛОВА, а не подстрокой: «Odin» сидит внутри
# «exploding», и в нашем чистом дампе таких строк три. Прочие имена
# в чистой игре не встречаются НИ РАЗУ (проверено по dump/collected.json).
FOREIGN = re.compile(
    r"\b(?:SkyHanni|Skyblocker|NotEnoughUpdates|Firmament|Odin|Devonian"
    r"|ModMenu|Sodium|Lithium|FerriteCore|Bazaar\s?Utils"
    # ⚠️ найдены 13.08 ГЛАЗАМИ при ручном переводе очереди, а не сторожем:
    # их строки спокойно доехали до списка к покупке
    r"|RRV|MarketGuard|btrbz|BetterBazaar|ScamScreener)\b"
    # сайт-помощник: строку про него пишет мод, а не Hypixel
    r"|\beliteskyblock\.com\b"
    # технический мусор чужого мода: стектрейс, исключение, отчёт об ошибке
    r"|\bat\.[a-z0-9_]+\.[a-z0-9_.]+"
    r"|\b\w*Exception\b|\bError while\b|\bstacktrace\b",
    re.IGNORECASE)


def foreign_mod(text: str) -> bool:
    """Строка принадлежит ЧУЖОМУ моду, а не Hypixel."""
    return bool(FOREIGN.search(text))


# ⚠️⚠️ ОБРЕЗКИ БОКОВОЙ ПАНЕЛИ. Панель приходит оборванной ПОСРЕДИ СЛОВА:
# « Bazaar Al», « Auction H», « The Garde», « Savanna W». Замер 13.08 по
# 73 установкам: таких строк 94, и все они просились в ПЛАТНУЮ покупку.
#
# ⚠️ Сперва я решил, что это SkyHanni перерисовывает панель, — проверка
# отменила: те же обрывки есть в НАШЕЙ чистой игре (« Combat Se», « Fashion S»),
# где чужих модов нет вовсе. Значит это шум чтения самой панели, а не сосед.
# Рядом с ними лежат слипшиеся хвосты — « Coal Minestrict», « Graveyardttlement»,
# « VillageAA»: старый суффикс плюс новый префикс.
#
# ⚠️ ПРИЗНАК «оборвано посреди слова» В ОДИНОЧКУ НЕВЕРЕН, и это замерено:
# в чистой игре он задевает 39 законных строк — римские уровни («Farmhand VII»
# против «Farmhand VIII»), множественное число («Upgrade Item» / «Items»),
# пары предметов («Black Wool» / «Black Woolen Yarn», «[Lvl {n}] Pig» /
# «Pigman»). Поэтому у признака ТРИ подпорки:
#   * длинная строка САМА прошла порог — иначе ею окажется мусор склейки,
#     который приходит от одной установки («VillageAA» прислала 1 против 76);
#   * продолжение не «s» — это множественное число, а не обрыв;
#   * строка не кончается римским уровнем.
#
# ⚠️ ОБЛАСТЬ — ТОЛЬКО ПАНЕЛЬ. В лоре и именах предметов те же подпорки
# не спасают: «Grappling Hook» / «Grappling Hooks!» и «Mining Fiesta» /
# «Mining Fiestas start when…» законны обе. Замер по чистой игре: в панели
# признак задевает 1 строку из 205, в лоре — 28 из 18329.
CUT_SOURCES = frozenset({"scoreboard"})
ROMAN_TAIL = re.compile(r"\b[IVXLC]{1,6}$")

# Хвост-СЧЁТЧИК: «Dark Oak Log» -> «Dark Oak Log x{n}». Обе строки законны,
# и вторая не делает первую обрывком — в отличие от «Collect Acacia Logs».
TAIL_COUNT = re.compile(r"^ (?:x\{n\}|x\d|\{n\}|\d|\(|\+|-)")


DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")


def our_dump() -> dict[str, set[str]]:
    """Наш локальный дамп по источникам — чистая игра, без чужих модов."""
    path = DUMP / "collected.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {source: set(rows)
            for source, rows in (data.get("sources") or {}).items()}


def panel_cuts(rows: list[tuple[str, int]], floor: int,
               trusted: set[str] = frozenset()) -> dict[str, str]:
    """
    Обрезки панели: {оборванная строка: та же строка целиком}.

    ⚠️ `trusted` — строки, которым верим как ЦЕЛЫМ без порога: это наш
    локальный дамп. Без него « Your Isla» (49 установок) не отсеивался,
    потому что целую « Your Island» прислали меньше трёх человек, — а у нас
    она лежит с самого начала. Замер 13.08: +17 обрезков, ложных 0.
    """
    index: dict[str, list[str]] = {}
    seen: dict[str, int] = {}
    for row, count in rows:
        seen[row] = max(seen.get(row, 0), count)
        if count >= floor:
            index.setdefault(row[:8], []).append(row)
    for row in trusted:
        index.setdefault(row[:8], []).append(row)

    out: dict[str, str] = {}
    for row, count in rows:
        if len(row) < 6 or not row[-1].isalpha() or ROMAN_TAIL.search(row):
            continue
        for other in index.get(row[:8], ()):
            if len(other) <= len(row) or not other.startswith(row):
                continue
            rest = other[len(row):]
            # ⚠️ ОБРЫВ БЫВАЕТ И ПО ГРАНИЦЕ СЛОВА, не только посреди него.
            # Панель режет задание по ширине: « Builder's» вместо
            # « Builder's House», «Collect Acacia» вместо «Collect Acacia Logs».
            # Признак «продолжение начинается с буквы» такие пропускал —
            # 90 строк заданий просились в перевод обрывками.
            #
            # ⚠️ Хвост-СЧЁТЧИК обрезком не делает: «Dark Oak Log» и «Dark Oak
            # Log x{n}» законны обе, и без этой оговорки имя предмета уехало бы
            # в отсев. Замер: с ней 90 находок, все до одной — настоящие
            # обрывки заданий (просмотрены глазами).
            word_edge = rest.startswith(" ") and len(rest) > 1 and not TAIL_COUNT.match(rest)
            if not ((rest[0].isalpha() and rest != "s") or word_edge):
                continue
            # ⚠️ ЧЕТВЁРТАЯ ПОДПОРКА, и без неё признак начал калечить данные.
            # С ростом числа игроков МУСОР СКЛЕЙКИ тоже проходит порог:
            # « Villageutpost» прислали 3 установки, и целая « Village»
            # (121 установка!) была объявлена её обрезком. Замер 13.08:
            # 4 законные строки панели из 245.
            #
            # Длинную строку принимаем, только если она ПОДТВЕРЖДЕНА:
            # либо есть в нашем чистом дампе, либо встречается НЕ РЕЖЕ
            # короткой. Мусор склейки не проходит ни то, ни другое —
            # он приходит в разы реже целой строки.
            if other not in trusted and seen.get(other, 0) < count:
                continue
            out[row] = other
            break
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Строки от игроков")
    parser.add_argument("--merge", action="store_true", help="записать в data/work")
    # ⚠️ ПОРОГ ПОДНЯТ 1 -> 3 (13.08), когда установок стало 73. При одном
    # игроке порог 1 был единственно возможным; теперь строка, присланная
    # ОДНИМ человеком, — это чаще всего его собственная комбинаторика:
    # цветовые коды красителей «(CRYSTAL - #C{n}A{n}D{n})», колонки полосы
    # над хотбаром, а то и поисковые запросы «Auctions: "hyperion"».
    # Замер: порог 1 давал 30994 строки к покупке, порог 3 — 7942, и выпадает
    # почти исключительно комбинаторика и семьи, закрываемые одним правилом.
    # ⚠️ Порог НИЧЕГО НЕ ТЕРЯЕТ НАВСЕГДА: пакеты лежат на сервере, и строка
    # пройдёт при следующем заборе, когда её пришлёт ещё кто-нибудь.
    parser.add_argument("--min", type=int, default=3,
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
    foreign: list[tuple[str, str]] = []
    for packet in packets:
        versions[(packet.get("mod") or "?", packet.get("game") or "?")] += 1
        here = set()
        for source, rows in (packet.get("lines") or {}).items():
            for row in rows:
                # ⚠️ Чужой мод отсекаем СРАЗУ, до подсчёта: иначе он попадёт
                # в очередь и однажды будет переведён за наши деньги.
                if foreign_mod(row):
                    foreign.append((source, row))
                    continue
                here.add((source, row))
        for key in here:
            seen[key] += 1

    by_source: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (source, row), count in seen.items():
        by_source[source].append((row, count))

    print(f"пакетов: {len(packets)}, разных строк: {len(seen)}")
    if foreign:
        uniq = sorted({row for _src, row in foreign})
        print(f"⚠️ отсеяно строк ЧУЖИХ МОДОВ: {len(uniq)} "
              f"(их переводить не наше дело)")
        for row in uniq[:6]:
            print(f"     {row[:88]}")
        if len(uniq) > 6:
            print(f"     … ещё {len(uniq) - 6}")
        print()
    print("версии, с которых слали:")
    for (mod, game), count in versions.most_common(5):
        print(f"   мод {mod:12} игра {game:10} — {count} пакетов")
    print()

    # обрезки считаем ОДИН раз и убираем и из отчёта, и из выгрузки
    # ⚠️ Наш дамп — чистая игра, его строки считаем целыми без порога:
    # он подтверждает « Your Island» там, где присланного не хватило.
    ours = our_dump()
    cuts: dict[str, dict[str, str]] = {
        source: panel_cuts(by_source[source], args.min, ours.get(source, frozenset()))
        for source in by_source if source in CUT_SOURCES}
    cut_total = sum(len(rows) for rows in cuts.values())
    if cut_total:
        print(f"⚠️ отсеяно ОБРЕЗКОВ панели: {cut_total} "
              f"(строка оборвана посреди слова — покупать её нечего)")
        shown = [(row, full) for rows in cuts.values() for row, full in rows.items()]
        for row, full in shown[:5]:
            print(f"     {row[:40]!r} -> целиком {full[:48]!r}")
        if len(shown) > 5:
            print(f"     … ещё {len(shown) - 5}")
        print()

    def kept(source: str) -> list[str]:
        drop = cuts.get(source) or {}
        return [row for row, count in by_source[source]
                if count >= args.min and row not in drop]

    total_keep = 0
    print(f"{'источник':14} {'всего':>6} {'прошли порог ' + str(args.min):>18}")
    for source in sorted(by_source):
        keep = kept(source)
        total_keep += len(keep)
        print(f"   {source:12} {len(by_source[source]):6} {len(keep):18}")

    # ⚠️ Одиночные строки показываем ОТДЕЛЬНО и не прячем: при одном игроке
    # это норма, а при сотне — первый признак, что кто-то шлёт своё.
    lonely = [(source, row) for (source, row), count in seen.items() if count == 1]
    if lonely and len(packets) > 3:
        print()
        print(f"прислали РОВНО ОДИН раз: {len(lonely)}")
        print("   при большом числе игроков это подозрительно — смотреть глазами")
        for source, row in lonely[:args.show]:
            print(f"      [{source}] {row[:80]}")

    # ⚠️ БЛОКИ ПОДСКАЗОК — то, ради чего затевалась правка 17.08. Строки
    # порознь не дают собрать абзац: сервер режет описание по ширине окна,
    # и без порядка склеить его нечем. Замер того дня: 13326 присланных строк
    # были обрывками с неизвестной склейкой — больше половины очереди, и среди
    # них все описания кнопок меню, которые игрок видел английскими.
    #
    # ⚠️ Порог тут ОДИН пакет, в отличие от строк. У блока структура, а не
    # текст: выдумать его сложнее, сервер уже отсеял мусор и личное, а редкий
    # предмет по природе приходит от одного человека — порог 3 выбросил бы
    # ровно то, чего у нас нет. Строки из блоков всё равно проходят обычные
    # фильтры покупки, когда корпус превращается в очередь.
    blocks: dict[str, list[str]] = {}
    for packet in packets:
        for block in packet.get("blocks") or []:
            if not isinstance(block, list) or len(block) < 3:
                continue
            rows = [x if isinstance(x, str) else "" for x in block]
            if any(foreign_mod(x) for x in rows):
                continue
            key = "\n".join(rows)
            blocks.setdefault(key, rows)
    print(f"\nблоков подсказок: {len(blocks)}")

    if not args.merge:
        print("\nсухой прогон. Записать: --merge")
        return 0

    if blocks:
        # формат тот же, что у dump/tooltips.json, — чтобы make_paragraphs
        # читал его тем же кодом, без особого случая
        packed = [{"item": rows[0], "lines": rows[1:], "ru": []}
                  for rows in blocks.values()]
        BLOCKS_OUT.parent.mkdir(parents=True, exist_ok=True)
        BLOCKS_OUT.write_text(json.dumps(
            {"id": "tooltips_from_players",
             "_comment": "Блоки подсказок, присланные игроками. Формат как "
                         "у dump/tooltips.json: сюда смотрит make_paragraphs "
                         "через --live.",
             "tooltips": packed}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print(f"записано: {BLOCKS_OUT}  ({len(packed)} блоков)")

    # ⚠️ Пишем СО СЧЁТЧИКОМ установок, а не голым списком: у дампа формат
    # такой же ({строка: сколько раз видели}), и очередь читает оба файла
    # одинаково. Прежний список приходилось бы разбирать особым случаем,
    # а особый случай однажды забывают.
    counts: dict[str, dict[str, int]] = {}
    for (source, row), count in seen.items():
        counts.setdefault(source, {})[row] = count
    payload = {source: {row: counts[source][row] for row in sorted(kept(source))}
               for source in by_source}
    payload = {source: rows for source, rows in payload.items() if rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано: {OUT}  ({total_keep} строк)")
    print("дальше — обычным путём: make_queue.py -> pick_queue.py")
    if blocks:
        print("а блоки — в корпус абзацев:")
        print("   python tools/make_paragraphs.py data/work/lore_tooltips.json"
              " --live <дамп>/tooltips.json data/work/blocks_from_players.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
