"""
Единый индекс всего перевода — чтобы искать запросом, а не скриптом.

⚠️ ЭТО ПРОИЗВОДНАЯ КОПИЯ, А НЕ ИСТОЧНИК ПРАВДЫ. Источник — json-словари,
корпус и генераторы; база пересобирается из них одной командой и ничего
не хранит сама. Правило то же, что и для автословарей: правишь json —
пересобери базу, а не наоборот. Иначе получим две расходящиеся копии,
на чём проект уже обжигался (одно правило тела абзаца жило в трёх местах).

Зачем: вопрос «где лежит эта строка и включена ли она» требует обойти
17 словарей, учесть выключенные пакеты, секции exact/regex/glossary/paragraphs,
корпус абзацев и очередь строк. Каждый такой вопрос я писал одноразовым
скриптом; теперь это одна строка SQL.

Запуск:
  python tools/db.py --rebuild            собрать заново из json
  python tools/db.py --find "Огранка"     где встречается (везде сразу)
  python tools/db.py "SELECT ..."         произвольный запрос
  python tools/db.py --schema             какие есть таблицы и поля

Примеры, ради которых это писалось:
  -- какие переводы лежат в ВЫКЛЮЧЕННЫХ словарях
  SELECT pack, count(*) FROM entry WHERE NOT enabled GROUP BY pack;

  -- один термин переведён по-разному
  SELECT value, count(*) FROM entry WHERE key='Defense' GROUP BY value;

  -- абзацы, где имя зачарования переведено внутри текста
  SELECT key, ru FROM para WHERE key LIKE 'Growth %' AND marked;
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
WORK = ROOT / "data" / "work"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")
DB = WORK / "index.sqlite"

SCHEMA = """
DROP TABLE IF EXISTS entry;
DROP TABLE IF EXISTS para;
DROP TABLE IF EXISTS queue;
DROP TABLE IF EXISTS dump;

-- все записи всех словарей мода
CREATE TABLE entry (
    file    TEXT,     -- 96-paragraphs.json
    pack    TEXT,     -- id пакета
    enabled INTEGER,  -- 0 у переключаемых с "default": false
    section TEXT,     -- exact | regex | glossary | paragraphs
    key     TEXT,     -- оригинал (для regex — шаблон)
    value   TEXT      -- перевод (для regex — замена)
);
CREATE INDEX entry_key ON entry(key);
CREATE INDEX entry_value ON entry(value);

-- корпус абзацев: то, за что платили
CREATE TABLE para (
    key    TEXT,     -- ключ абзаца (чистый текст, числа как {n})
    ru     TEXT,     -- перевод
    marked INTEGER,  -- 1 — цвета лежат В переводе (masking), 0 — угадываются
    item   TEXT,     -- у какого предмета встречен
    cnt    INTEGER,  -- сколько раз встречен
    live   INTEGER   -- пришёл из живой игры, а не из NEU
);
CREATE INDEX para_key ON para(key);

-- очередь построчного перевода
CREATE TABLE queue (
    key   TEXT,
    ru    TEXT,
    state TEXT       -- ready | asis | waiting
);
CREATE INDEX queue_key ON queue(key);

-- что мод собрал в игре
CREATE TABLE dump (
    source TEXT,     -- item_lore | chat | sidebar | action_bar | ...
    line   TEXT,
    cnt    INTEGER
);
CREATE INDEX dump_line ON dump(line);
"""


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def fill_entries(db: sqlite3.Connection) -> int:
    rows = []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        pack = load(path)
        name = path.name
        pid = pack.get("id") or name
        # ⚠️ Выключенность запоминаем ПОЛЕМ, а не пропуском записи: «выключено»
        # значит «решили не переводить», и такие записи надо видеть — именно
        # их незнание привело к «Огранке V» в обход переключателя.
        enabled = 0 if pack.get("default") is False else 1
        for section in ("exact", "glossary", "paragraphs"):
            for key, value in (pack.get(section) or {}).items():
                rows.append((name, pid, enabled, section, key, str(value)))
        for rule in pack.get("regex") or []:
            rows.append((name, pid, enabled, "regex",
                         rule.get("p", ""), rule.get("r", "")))
    db.executemany("INSERT INTO entry VALUES (?,?,?,?,?,?)", rows)
    return len(rows)


def fill_paragraphs(db: sqlite3.Connection) -> int:
    data = load(WORK / "paragraphs.json").get("paragraphs") or []
    rows = []
    for item in data:
        ru = item.get("ru") or ""
        rows.append((item.get("text", ""), ru, 1 if "§" in ru else 0,
                     item.get("item") or "", int(item.get("count") or 0),
                     1 if item.get("live") else 0))
    db.executemany("INSERT INTO para VALUES (?,?,?,?,?,?)", rows)
    return len(rows)


def fill_queue(db: sqlite3.Connection) -> int:
    data = load(WORK / "from_game.json")
    rows = []
    for key, value in (data.get("exact") or {}).items():
        rows.append((key, str(value), "ready" if value else "waiting"))
    asis = data.get("_asis")
    if isinstance(asis, list):
        rows += [(key, "", "asis") for key in asis]
    elif isinstance(asis, dict):
        rows += [(key, "", "asis") for key in asis]
    db.executemany("INSERT INTO queue VALUES (?,?,?)", rows)
    return len(rows)


def fill_dump(db: sqlite3.Connection) -> int:
    data = load(DUMP / "collected.json")
    sources = data.get("sources") or data
    rows = []
    for source, lines in sources.items():
        if not isinstance(lines, dict):
            continue
        for line, count in lines.items():
            if isinstance(count, int):
                rows.append((source, line, count))
    db.executemany("INSERT INTO dump VALUES (?,?,?)", rows)
    return len(rows)


def sources() -> list[Path]:
    """Файлы, из которых собрана база. Ровно те, что читают fill_*."""
    return [*PACKS.rglob("*.json"),
            WORK / "paragraphs.json",
            WORK / "from_game.json",
            DUMP / "collected.json"]


def stale() -> list[str]:
    """
    Какие источники новее базы.

    ⚠️ Зачем. База пересобиралась ТОЛЬКО по явному --rebuild или когда файла
    нет вовсе, а свежесть не проверялась ничем — и поиск молча отдавал то,
    чего в словарях давно нет. На живом примере: `--find "Milestone"` показал
    «Прогресс до рубежа III» из 11-stat-forms.json, хотя в самом файле слова
    «рубеж» нет ни разу. По этому ответу я чуть не выбрал термин для нового
    правила, то есть внёс бы разнобой, опираясь на несуществующую запись.

    Врущий индекс хуже отсутствующего: отсутствие видно сразу, а расхождение
    выглядит как факт. Тем более что в CLAUDE.md этот инструмент стоит ПЕРВЫМ
    в порядке поиска — «где лежит строка».

    Пересобрать стоит 0.4 секунды, так что выбор между «чинить» и «предупредить»
    тут даже не стоит: предупреждение можно пропустить, а починку нет.
    """
    if not DB.exists():
        return ["базы нет"]
    made = DB.stat().st_mtime
    return [p.name for p in sources() if p.exists() and p.stat().st_mtime > made]


def rebuild() -> int:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    with sqlite3.connect(DB) as db:
        db.executescript(SCHEMA)
        print(f"  словарные записи: {fill_entries(db)}")
        print(f"  абзацы корпуса:   {fill_paragraphs(db)}")
        print(f"  очередь строк:    {fill_queue(db)}")
        print(f"  собрано в игре:   {fill_dump(db)}")
        db.commit()
    print(f"готово: {DB.relative_to(ROOT)}")
    return 0


def show(rows: list, header: list[str], limit: int) -> None:
    if not rows:
        print("  ничего не нашлось")
        return
    widths = [min(64, max(len(str(h)), max((len(str(r[i])) for r in rows[:limit]), default=0)))
              for i, h in enumerate(header)]
    print("  " + " | ".join(str(h).ljust(w) for h, w in zip(header, widths)))
    print("  " + "-+-".join("-" * w for w in widths))
    for row in rows[:limit]:
        cells = []
        for value, width in zip(row, widths):
            text = re.sub(r"\s+", " ", str(value))
            cells.append((text[:width - 1] + "…" if len(text) > width else text).ljust(width))
        print("  " + " | ".join(cells))
    if len(rows) > limit:
        print(f"  … ещё {len(rows) - limit}")


def find(needle: str, limit: int) -> int:
    like = f"%{needle}%"
    with sqlite3.connect(DB) as db:
        print(f"=== СЛОВАРИ (что видит игрок) ===")
        rows = db.execute(
            "SELECT file, section, key, value, enabled FROM entry "
            "WHERE key LIKE ? OR value LIKE ? ORDER BY enabled DESC, file",
            (like, like)).fetchall()
        off = [r for r in rows if not r[4]]
        show([r[:4] for r in rows], ["файл", "секция", "оригинал", "перевод"], limit)
        if off:
            print(f"  ⚠️ из них в ВЫКЛЮЧЕННЫХ словарях: {len(off)} "
                  f"(перевод есть, но игрок его не увидит)")

        print(f"\n=== КОРПУС АБЗАЦЕВ ===")
        rows = db.execute(
            "SELECT key, ru, marked FROM para WHERE key LIKE ? OR ru LIKE ?",
            (like, like)).fetchall()
        show([(k, r, "цвет внутри" if m else "цвет угадывается") for k, r, m in rows],
             ["ключ", "перевод", "разметка"], limit)

        print(f"\n=== ОЧЕРЕДЬ СТРОК ===")
        rows = db.execute(
            "SELECT key, ru, state FROM queue WHERE key LIKE ? OR ru LIKE ?",
            (like, like)).fetchall()
        show(rows, ["строка", "перевод", "состояние"], limit)

        print(f"\n=== СОБРАНО В ИГРЕ ===")
        rows = db.execute(
            "SELECT source, line, cnt FROM dump WHERE line LIKE ? ORDER BY cnt DESC",
            (like,)).fetchall()
        show(rows, ["источник", "строка", "показов"], limit)
    return 0


def query(sql: str, limit: int) -> int:
    with sqlite3.connect(DB) as db:
        try:
            cur = db.execute(sql)
        except sqlite3.Error as error:
            print("SQL не выполнился:", error)
            return 1
        rows = cur.fetchall()
        header = [d[0] for d in cur.description] if cur.description else []
        show(rows, header, limit)
        print(f"\nстрок: {len(rows)}")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Единый индекс перевода (производный от json)")
    parser.add_argument("sql", nargs="?", help="запрос SQL")
    parser.add_argument("--rebuild", action="store_true", help="собрать базу заново из json")
    parser.add_argument("--find", help="искать текст во всех источниках сразу")
    parser.add_argument("--schema", action="store_true", help="показать таблицы и поля")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    if args.rebuild:
        return rebuild()
    if args.schema:
        print(SCHEMA)
        return 0
    outdated = stale()
    if outdated:
        shown = ", ".join(outdated[:3]) + (f" и ещё {len(outdated) - 3}"
                                           if len(outdated) > 3 else "")
        print(f"источники новее базы ({shown}) — пересобираю")
        rebuild()
        print()
    if args.find:
        return find(args.find, args.limit)
    if args.sql:
        return query(args.sql, args.limit)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
