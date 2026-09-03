# -*- coding: utf-8 -*-
"""
Приёмник непереведённых строк от игроков.

⚠️ ЭТО ПОЧТОВЫЙ ЯЩИК, А НЕ ХРАНИЛИЩЕ. Сервер только принимает пакет,
проверяет и кладёт в файл. Разбор, отсев и перевод идут на рабочем ПК теми
инструментами, что уже написаны (`make_queue`, `pick_queue`, `merge_paragraphs`).
Чем меньше логики здесь, тем меньше поводов её чинить на боевой машине.

⚠️ Зависимостей НЕТ — только стандартная библиотека. На сервере с одним ядром
это заодно и защита от «а обновите питон до 3.13».

Запуск вручную:
    python3 receiver.py --port 8787 --dir /var/lib/skyblockru

Приём:
    POST /submit     тело — JSON (можно gzip), заголовок Content-Encoding: gzip
    GET  /health     «ok» для проверки, что жив

Формат тела:
    {"mod": "0.2.0", "game": "26.2", "lines": {"item_lore": ["...", ...], ...}}

⚠️ НИКАКИХ идентификаторов игрока мы НЕ ПРИНИМАЕМ: поля вроде `player`,
`uuid`, `profile` молча выбрасываются. Так их не появится в хранилище, даже
если однажды клиент начнёт их слать по ошибке.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ⚠️ Пределы — не паранойя, а условие выживания диска в 10 ГБ.
MAX_BODY = 2 * 1024 * 1024          # 2 МБ на пакет (замер: весь дамп игрока — 246 КБ в gzip)
MAX_UNPACKED = 16 * 1024 * 1024      # столько максимум после распаковки
MAX_LINES = 20000                    # строк в пакете
MAX_LINE = 500                       # знаков в строке
RATE_SECONDS = 60                    # не чаще раза в минуту с одного адреса

# ⚠️ Блоки подсказок — крупнее строк, поэтому у них свои пределы.
# Замер: 9711 блоков одного игрока это 3.3 МБ (657 КБ в gzip), клиент шлёт
# порциями по 1200. Берём с запасом вдвое, чтобы порция влезала целиком.
MAX_BLOCKS = 2500                    # блоков в пакете
MAX_BLOCK_LINES = 60                 # строк в одном блоке

# ⚠️ СУТОЧНАЯ КВОТА — последняя преграда для «залить диск».
#
# Всё остальное ограничивает ОДИН пакет, а слать их можно много и с разных
# адресов. Диск на сервере 10 ГБ, и на нём живёт ЧУЖОЙ рабочий сервис:
# переполнение уронило бы не только приём переводов.
#
# Замер: весь накопленный за месяцы дамп одного игрока — 776 КБ. Сотня
# игроков в сутки — единицы мегабайт. 200 МБ в день это стократный запас
# и одновременно потолок, при котором диск не кончится за год.
MAX_DAY_BYTES = 200 * 1024 * 1024

# Источники, которые мы вообще готовы принимать. Всё остальное отбрасываем
# ЗДЕСЬ ЖЕ: клиент может ошибиться или устареть, а сервер — последняя граница.
ALLOWED_SOURCES = {
    "item_lore", "item_name", "screen", "title", "action_bar", "boss_bar",
    "chat", "scoreboard", "tab", "name_tag",
    # заголовок подсказки БЕЗ строки редкости — подпись кнопки меню, а не имя
    # вещи. Мод отличает их по блоку (core/Titles.java), а нам иначе не узнать:
    # сюда приезжают строки, а не блоки, и «Accept Offer» неотличим от
    # «Ant Shard». ⚠️ Без этой строки пакет принялся бы, а источник молча
    # выбросился — то есть признак был бы сделан и не доехал.
    "menu_title",
}

# Поля, которые указывают на человека. Не принимаем никогда.
FORBIDDEN_KEYS = {"player", "uuid", "profile", "name", "nick", "ip", "email"}

# Метка установки: ровно UUID, ничего другого не принимаем.
INSTALL_ID = re.compile(r"^[0-9a-fA-F-]{36}$")

# ⚠️ ТЕ ЖЕ ПРИЗНАКИ, ЧТО В МОДЕ (`core/TelemetryFilter.java`), и дублирование
# здесь ОСОЗНАННОЕ. Обычно копия признака в этом проекте — беда: копии
# расходятся молча. Но тут вторая линия защиты, а не вторая реализация:
# клиент у игрока может быть старым, собранным до фильтра, или подменённым.
# Цена пропуска — чужая переписка на диске, цена дублирования — десять строк.
PLAYER_LINE = re.compile(r"^\[(?:\{n\}|\d+)\]\s*\S+.*:")
PRIVATE_LINE = re.compile(r"^(?:Party|Guild|Co-op|Officer)\s*>|^To\s+\S+\s*:")
FROM_LINE = re.compile(r"^From\s+(\S+)\s*:")
# «From stash:» — это выдача из хранилища, то есть сервер, а не человек.
SYSTEM_SENDERS = {"stash", "storage", "sacks"}


# ⚠️ ЧТО ЗАВЕДОМО НЕ ИЗ ИГРЫ.
#
# Клиенту доверять нельзя по построению: мод стоит у игрока, адрес виден,
# и отправить сюда можно что угодно любым curl. Полностью это не лечится —
# зато можно отсечь очевидное, чтобы мусор не доезжал до очереди перевода.
#
# ⚠️ Признаки НАРОЧНО грубые. Тонкие («похоже ли на текст Hypixel») отсекали
# бы настоящие строки: игра шлёт и значки приватной зоны, и латиницу,
# и кириллицу от нашего же перевода. Здесь только то, чего в интерфейсе
# SkyBlock не бывает совсем.
JUNK = (
    re.compile(r"https?://", re.I),          # ссылки — в подсказках их нет
    re.compile(r"<[a-z/][^>]*>", re.I),      # html
    re.compile(r"\{\s*[\"']\w+[\"']\s*:"),   # вложенный json
    re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]"),  # управляющие символы
)


# ⚠️ ЧУЖОЕ В БЛОКАХ ПОДСКАЗОК — своя граница, и вот почему она понадобилась.
#
# `personal()` работает только для чата (там признак — метка уровня в начале
# строки), а чужие моды приёмник не проверял вовсе: их отсеивала НАША сторона
# при разборе. Для строк этого хватало. Блок же приходит целой подсказкой,
# и в ней бывает и ник продавца («Seller: …» у лота аукциона), и приписка
# соседа («(From SkyHanni)»). Проверка поймала это до выкладки: два случая
# из пяти проходили насквозь.
#
# ⚠️ Признаки УЗКИЕ намеренно. «Player Trading» под них не попадает — нужен
# ИМЕННО «Player:» с двоеточием; «Source: Moby» тоже цел, потому что
# перечислены подписи владельца, а не любое двоеточие.
# ⚠️ «Seller: {s}» ПРОПУСКАЕМ: мод обобщает ники сам, и там уже не имя,
# а дырка — личного в такой строке нет. Замер по 9711 живым блокам: без этой
# оговорки признак выбрасывал 1913 блоков (20%), и почти все — лоты аукциона,
# то есть самый ценный источник абзацев. Ловим только НЕОБОБЩЁННЫЙ ник:
# он значит, что мод его не распознал, и уезжать такому нельзя.
OWNER_LINE = re.compile(
    r"^(?:Seller|Player|Buyer|Owner|Bidder|By)\s*:\s*"
    r"(?!\{s\}|Refreshing|None\b|\s*$)\S", re.I)
RANKED_NICK = re.compile(r"\[(?:MVP|VIP|ADMIN|MOD|GM|OWNER|YOUTUBE)[^\]]{0,4}\]\s*\S")
FOREIGN_MOD = re.compile(
    r"\b(?:SkyHanni|Skyblocker|NotEnoughUpdates|NEU|Firmament|Odin|Dandelion"
    r"|MarketGuard|RRV|BetterBazaar|btrbz|Bazaar Utils)\b"
    r"|\bat\.hannibal2\.|eliteskyblock\.com", re.I)


def foreign_or_personal(line: str) -> bool:
    """Строка блока, которой у нас быть не должно: чужой мод или чужой ник."""
    return bool(OWNER_LINE.search(line)
                or RANKED_NICK.search(line)
                or FOREIGN_MOD.search(line))


def gunzip_limited(raw: bytes, limit: int) -> bytes:
    """
    Распаковать gzip, НЕ ДАВ ему раздуться.

    ⚠️ Это защита от «gzip-бомбы»: два мегабайта сжатых нулей разворачиваются
    в гигабайты. Наивный `gzip.decompress(raw)` распаковывает ВСЁ в память
    и только потом позволяет проверить размер — то есть проверка стоит после
    того, как ущерб нанесён, а на сервере с 4 ГБ памяти это отказ всей машины
    вместе с чужим сервисом.

    `decompressobj.decompress(data, max_length)` останавливается на пределе:
    просим на байт больше лимита и, если получили — отказываем.
    """
    stream = zlib.decompressobj(16 + zlib.MAX_WBITS)   # 16 = заголовок gzip
    out = stream.decompress(raw, limit + 1)
    if len(out) > limit:
        raise ValueError("unpacked too large")
    return out


def junk(line: str) -> bool:
    """Строка заведомо не из интерфейса игры."""
    return any(rx.search(line) for rx in JUNK)


def personal(source: str, line: str) -> bool:
    """Строка касается другого человека — не храним."""
    if source != "chat":
        return False
    if PLAYER_LINE.search(line) or PRIVATE_LINE.search(line):
        return True
    found = FROM_LINE.search(line)
    return bool(found) and found.group(1).lower() not in SYSTEM_SENDERS

VERSION = re.compile(r"^[0-9A-Za-z._+-]{1,32}$")


class Store:
    """Складывает пакеты в файлы по дате. Один пакет — одна строка JSONL."""

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.seen: dict[str, float] = {}

    def path_for(self, when: float) -> pathlib.Path:
        day = time.strftime("%Y-%m-%d", time.gmtime(when))
        return self.root / f"{day}.jsonl"

    def too_soon(self, who: str, now: float) -> bool:
        last = self.seen.get(who, 0.0)
        if now - last < RATE_SECONDS:
            return True
        self.seen[who] = now
        # чистим память, чтобы словарь не рос вечно
        if len(self.seen) > 10000:
            for key in [k for k, v in self.seen.items() if now - v > 3600]:
                self.seen.pop(key, None)
        return False

    def over_quota(self, when: float) -> bool:
        """Сколько сегодня уже приняли — и не пора ли остановиться."""
        path = self.path_for(when)
        try:
            return path.stat().st_size >= MAX_DAY_BYTES
        except OSError:
            return False

    def write(self, record: dict, when: float) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self.path_for(when).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def clean(payload: dict) -> tuple[dict, list[str]]:
    """
    Оставляет только то, что мы готовы хранить. Возвращает (запись, жалобы).

    ⚠️ Чистим ПО БЕЛОМУ СПИСКУ, а не вычёркиваем плохое: список источников
    известен и конечен, а перечислять всё дурное — гонка, которую не выиграть.
    """
    notes = []
    for key in list(payload):
        if key.lower() in FORBIDDEN_KEYS:
            payload.pop(key)
            notes.append(f"выброшено поле {key}")

    mod = str(payload.get("mod", ""))[:32]
    game = str(payload.get("game", ""))[:32]
    if not VERSION.match(mod or "0"):
        mod = ""
    if not VERSION.match(game or "0"):
        game = ""

    lines = payload.get("lines")
    if not isinstance(lines, dict):
        raise ValueError("нет поля lines")

    kept: dict[str, list[str]] = {}
    total = 0
    for source, rows in lines.items():
        if source not in ALLOWED_SOURCES:
            notes.append(f"источник {source} не принимается")
            continue
        if not isinstance(rows, list):
            continue
        clean_rows = []
        for row in rows:
            if not isinstance(row, str):
                continue
            row = row.strip()
            if not row or len(row) > MAX_LINE:
                continue
            if personal(source, row):
                notes.append("отброшена строка про другого игрока")
                continue
            if junk(row):
                notes.append("отброшен мусор (не текст игры)")
                continue
            clean_rows.append(row)
            total += 1
            if total > MAX_LINES:
                notes.append("пакет обрезан по пределу строк")
                break
        if clean_rows:
            kept[source] = clean_rows
        if total > MAX_LINES:
            break

    # ⚠️ БЛОКИ ПОДСКАЗОК. Строки порознь не дают собрать абзац: сервер режет
    # описание по ширине окна, и без порядка склеить его нечем. Замер 17.08:
    # 13326 присланных строк — обрывки, склейка которых неизвестна навсегда,
    # то есть больше половины очереди. В блоке порядок есть.
    #
    # ⚠️ Блок берём ЦЕЛИКОМ или НИКАК: если хоть одна строка не прошла фильтр
    # (ник, чужой мод, идентификатор профиля), отбрасываем весь блок. Половина
    # блока бесполезна — абзац из неё всё равно не собрать, — а риск тот же.
    blocks_in = payload.get("blocks")
    blocks: list[list[str]] = []
    if isinstance(blocks_in, list):
        for block in blocks_in[:MAX_BLOCKS]:
            if not isinstance(block, list) or len(block) < 3:
                continue
            rows = []
            ok = True
            for row in block[:MAX_BLOCK_LINES]:
                if not isinstance(row, str) or len(row) > MAX_LINE:
                    ok = False
                    break
                row = row.strip()
                if row and (junk(row) or foreign_or_personal(row)):
                    ok = False
                    break
                rows.append(row)
            if ok and sum(1 for x in rows[1:] if x) >= 2:
                blocks.append(rows)
            elif not ok:
                notes.append("отброшен блок подсказки с личной строкой")

    if not kept and not blocks:
        raise ValueError("нечего сохранять")
    # ⚠️ Метка УСТАНОВКИ — единственное, что отличает отправителей.
    # Без неё сорок пакетов от одного человека выглядят как сорок игроков,
    # и на вопрос «сколькими людьми мод пользуется» ответить нечем.
    #
    # ⚠️ Это НЕ идентификатор человека: случайный UUID, придуманный на его
    # машине, не связанный ни с ником, ни с аккаунтом Minecraft. Поэтому он
    # и не попал в FORBIDDEN_KEYS рядом с «uuid»: там запрещён UUID ИГРОКА,
    # по которому человека можно найти, а этот живёт только в его конфиге.
    #
    # Формат проверяем строго: чужая строка тут стала бы способом записать
    # на диск что угодно под видом метки.
    install = str(payload.get("install", ""))[:36]
    if not INSTALL_ID.match(install):
        install = ""

    record = {"mod": mod, "game": game, "install": install, "lines": kept}
    if blocks:
        record["blocks"] = blocks
    return record, notes


class Handler(BaseHTTPRequestHandler):
    server_version = "skyblockru-receiver"
    store: Store

    def log_message(self, fmt, *args):
        # Свой лог: без адресов игроков, только факт и объём.
        print("[%s] %s" % (time.strftime("%H:%M:%S"), fmt % args), flush=True)

    def _answer(self, code: int, text: str, *, drain: bool = False) -> None:
        """
        Ответить клиенту.

        ⚠️ `drain` — дочитать тело запроса перед отказом. Без этого клиент
        получает не отказ, а ОБРЫВ СОЕДИНЕНИЯ: мы отвечаем и закрываем сокет,
        пока он ещё шлёт данные. Поймано локальной проверкой на большом пакете —
        мод увидел бы «connection aborted» вместо внятного «too large»
        и не понял бы, что делать. Читаем с ограничением: смысл отказа в том,
        чтобы НЕ глотать гигабайты.
        """
        if drain:
            left = min(int(self.headers.get("Content-Length") or 0), MAX_BODY * 4)
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    break
                left -= len(chunk)
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                                  # noqa: N802
        if self.path == "/health":
            self._answer(200, "ok")
        else:
            self._answer(404, "not found")

    def do_POST(self):                                 # noqa: N802
        if self.path != "/submit":
            self._answer(404, "not found")
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self._answer(400, "empty body")
            return
        if length > MAX_BODY:
            self._answer(413, "too large", drain=True)
            return

        # ⚠️ Адрес нужен ТОЛЬКО чтобы ограничить частоту, и в файл не пишется.
        # Храним его хеш, а не сам адрес: для счётчика этого хватает.
        who = hashlib.sha256(
            (self.client_address[0] or "").encode("utf-8")).hexdigest()[:16]
        now = time.time()
        if self.store.too_soon(who, now):
            self._answer(429, "slow down")
            return

        if self.store.over_quota(now):
            # ⚠️ Отказ ЧЕСТНЫЙ: лучше не принять сегодня, чем забить диск,
            # на котором работает не только этот сервис.
            self._answer(503, "daily quota reached, try tomorrow", drain=True)
            return

        raw = self.rfile.read(length)
        if (self.headers.get("Content-Encoding") or "").lower() == "gzip":
            try:
                raw = gunzip_limited(raw, MAX_UNPACKED)
            except ValueError:
                self._answer(413, "too large after unpacking")
                return
            except zlib.error:
                self._answer(400, "bad gzip")
                return

        try:
            payload = json.loads(raw.decode("utf-8"))
            record, notes = clean(payload)
        except (ValueError, UnicodeDecodeError) as error:
            self._answer(400, f"bad payload: {error}")
            return

        self.store.write(record, now)
        kept = sum(len(v) for v in record["lines"].values())
        self.log_message("принято %d строк, %d блоков, mod=%s game=%s%s", kept,
                         len(record.get("blocks") or []),
                         record["mod"] or "?", record["game"] or "?",
                         (" | " + "; ".join(notes)) if notes else "")
        self._answer(200, "thanks")


def main() -> int:
    parser = argparse.ArgumentParser(description="Приёмник строк для перевода")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--dir", default="/var/lib/skyblockru")
    args = parser.parse_args()

    Handler.store = Store(pathlib.Path(args.dir))
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"слушаю {args.host}:{args.port}, складываю в {args.dir}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
