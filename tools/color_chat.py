"""
Возвращает ПОДСВЕТКУ в готовые переводы реплик чата.

Зачем. Hypixel красит в реплике NPC не только имена, но и АКЦЕНТ: «If you
§cdon't open§f any, I collect and hoard them for you!». Имя, оставшееся
английским, свой цвет сохраняет само — мод ищет кусок оригинала в переводе
(TextTranslator.carryLegacyCodes). А вот переведённое слово так не найти,
и цвет пропадает: на экране акцент исчез, хотя в оригинале он был.

Починить это механически нельзя: где внутри русской фразы стоит «не откроешь»,
знает только тот, кто её переводил. Поэтому коды расставляет модель — но НЕ
переводит заново. Текст остаётся ровно тем, что уже куплен, и это проверяется:
снимаем коды из ответа и сравниваем с прежним переводом до знака.

Источник цвета — ЛОГИ Minecraft, а не дамп: дамп §-коды снимает при записи
(без этого не совпал бы словарь), а в логах чат лежит с кодами и за все прошлые
сессии. Тот же приём, что в tools/mine_logs.py.

Запуск:
  python tools/color_chat.py              посмотреть, чему не хватает цвета
  python tools/color_chat.py --apply      спросить модель и записать в корпус
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work" / "from_game.json"
LOGS = Path("C:/MultiMC/instances/26.2/.minecraft/logs")

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Кусок текста со своим §-кодом
RUN = re.compile(r"§([0-9a-fk-or])((?:(?!§).)*)")
CHAT = re.compile(r"\[CHAT\] (.*)$")
CODE = re.compile(r"§.")

BATCH = 40

RULES = """Ты расставляешь цветовые коды Minecraft в ГОТОВОМ переводе.

Тебе дают строку чата Hypixel SkyBlock с кодами вида §c §f §6 и её перевод
на русский БЕЗ кодов. Верни тот же перевод, добавив в него коды так, чтобы
подсвеченными оказались те же по смыслу слова, что и в оригинале.

Железные правила:
1. ТЕКСТ НЕ МЕНЯЙ. Ни слова, ни буквы, ни знака препинания. Ты только вставляешь
   коды. Ответ, из которого коды сняты, обязан совпасть с переводом ЗНАК В ЗНАК.
2. Коды бери ТОЛЬКО те, что есть в оригинале, и в том же смысле: чем подсвечено
   слово в оригинале, тем же подсвечено то слово, в которое оно переведено.
3. Цвет надо ЗАКРЫВАТЬ: после подсвеченного куска верни код основного цвета
   строки, иначе краска потечёт до конца.
      «If you §cdon't open§f any, I collect»
      -> «Если ты §cничего не откроешь§f, я собираю»
4. Если подсвеченное слово в переводе осталось английским (имя, название) —
   оставь его как есть и просто поставь вокруг те же коды.
5. Порядок слов в русском другой: код едет ВМЕСТЕ со своим словом, а не
   остаётся на прежнем месте.

Отвечай только строкой с кодами."""

SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer", "description": "номер строки из запроса"},
                    "ru": {"type": "string", "description": "перевод с §-кодами"},
                },
                "required": ["i", "ru"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lines"],
    "additionalProperties": False,
}


def strip_codes(text: str) -> str:
    return CODE.sub("", text)


def chat_with_colours() -> dict[str, str]:
    """Строка без кодов -> та же строка с кодами, из логов Minecraft."""
    found: dict[str, str] = {}
    if not LOGS.exists():
        return found
    for path in list(LOGS.glob("*.log")) + list(LOGS.glob("*.log.gz")):
        opener = gzip.open if path.suffix == ".gz" else open
        try:
            with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    match = CHAT.search(line)
                    if not match:
                        continue
                    raw = match.group(1).rstrip()
                    if "§" not in raw:
                        continue
                    clean = strip_codes(raw).strip()
                    if clean:
                        found.setdefault(clean, raw)
        except OSError:
            continue
    return found


def background(runs: list[tuple[str, str]]) -> str:
    """
    Основной цвет строки — тот, которым набрано БОЛЬШЕ ВСЕГО знаков.

    ⚠️ Не цвет первого куска: у реплики NPC первым идёт жёлтое «[NPC] », и по
    первому куску белое тело реплики само сошло бы за подсветку. Тот же приём,
    что в Highlights.java.
    """
    weight: collections.Counter = collections.Counter()
    for code, text in runs:
        weight[code] += len(text)
    return weight.most_common(1)[0][0] if weight else "f"


def needs_colour(raw: str, russian: str) -> list[str]:
    """Подсвеченные куски, которые в переводе потеряют цвет."""
    runs = [(code, text) for code, text in RUN.findall(raw) if text.strip()]
    if len(runs) < 2:
        return []
    main = background(runs)
    return [text.strip() for code, text in runs
            if code != main and len(text.strip()) > 2 and text.strip() not in russian]


def accept(original: str, russian: str, answer: str) -> tuple[str | None, str]:
    """
    Проверяет ответ модели механически. Возвращает (строка, причина отказа).

    Главная проверка: снимаем коды — обязан получиться ТОТ ЖЕ перевод. Так модель
    не сможет переписать текст под видом раскраски, а мы не потеряем оплаченное.
    """
    answer = answer.strip()
    if not answer:
        return None, "пустой ответ"
    if "§" not in answer:
        return None, "кодов не добавлено"
    if strip_codes(answer).strip() != russian.strip():
        return None, "текст изменён, а должен был остаться прежним"
    own = set(re.findall(r"§(.)", answer))
    theirs = set(re.findall(r"§(.)", original))
    extra = own - theirs
    if extra:
        return None, "выдуманы цвета: " + ", ".join(sorted(extra))
    return answer, ""


def build_user(chunk: list[dict]) -> str:
    parts = []
    for index, item in enumerate(chunk):
        parts.append(f"[{index}]\nОРИГИНАЛ С ЦВЕТОМ: {item['raw']}\n"
                     f"ПЕРЕВОД БЕЗ ЦВЕТА: {item['ru']}")
    return "\n\n".join(parts)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Возврат подсветки в переводы чата")
    parser.add_argument("--apply", action="store_true", help="спросить модель и записать")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    pack = json.loads(WORK.read_text(encoding="utf-8"))
    exact: dict[str, str] = pack.get("exact") or {}
    coloured = chat_with_colours()
    print(f"строк чата с §-кодами в логах: {len(coloured)}")

    todo = []
    for clean, raw in coloured.items():
        russian = exact.get(clean)
        if not russian or "§" in russian:
            continue  # перевода нет или цвет уже расставлен
        lost = needs_colour(raw, russian)
        if lost:
            todo.append({"clean": clean, "raw": raw, "ru": russian, "lost": lost})

    todo.sort(key=lambda item: item["clean"])
    if args.limit:
        todo = todo[:args.limit]

    print(f"переводов без подсветки: {len(todo)}")
    for item in todo[:10]:
        print(f"  {item['clean'][:74]}")
        print(f"     потеряли цвет: {', '.join(repr(x) for x in item['lost'][:3])}")
    if not todo:
        print("нечего красить")
        return 0
    if not args.apply:
        print(f"\nэто {(len(todo) + BATCH - 1) // BATCH} запрос(ов). Запуск: --apply")
        return 0

    from apikey import check as check_key
    if not check_key():
        return 1
    from anthropic import Anthropic
    from translate_ai import note_usage, report_usage

    client = Anthropic()
    system = [{"type": "text", "text": RULES, "cache_control": {"type": "ephemeral"}}]
    done = 0
    rejected = 0
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        print(f"  пачка {start // BATCH + 1}: {len(chunk)} строк...")
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=8000,
            system=system,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": build_user(chunk)}],
        )
        note_usage(response)
        payload = json.loads("".join(block.text for block in response.content
                                     if getattr(block, "text", None)))
        for line in payload.get("lines") or []:
            index = line.get("i")
            if not isinstance(index, int) or not (0 <= index < len(chunk)):
                continue
            item = chunk[index]
            result, why = accept(item["raw"], item["ru"], line.get("ru") or "")
            if not result:
                print(f"    ! {item['clean'][:52]!r}: {why}")
                rejected += 1
                continue
            exact[item["clean"]] = result
            done += 1

    pack["exact"] = exact
    WORK.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nраскрашено: {done}, отбраковано: {rejected}")
    print(f"записано: {WORK.relative_to(ROOT)}")
    report_usage()
    print("\nДальше: python tools/export_pack.py from_game 90-from-game.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
