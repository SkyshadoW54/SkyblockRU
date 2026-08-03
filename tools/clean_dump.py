"""
Чистит собранный дамп, не выбрасывая полезное.

Зачем: до фикса мод записывал каждое значение числа как отдельную строку
(один таймер над головой дал 308 записей) и подбирал чужие реплики из чата.
Команда /skyblockru clear стёрла бы всё разом, включая нормальные строки.
Этот скрипт схлопывает мусор и оставляет дело.

Что делает:
  - числа заменяет на {n} — «Time left: 2d 5h» и «Time left: 2d 4h» становятся одной строкой;
  - выбрасывает чужие реплики вида «[VIP] Ник: текст»;
  - выбрасывает таблицы лидеров и одиночные ники;
  - складывает результат в рабочий файл, готовый к переводу.

Запуск:  python tools/clean_dump.py
         python tools/clean_dump.py --in путь/к/untranslated.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "work" / "from_game.json"

NUMBERS = re.compile(r"\d+(?:[.,]\d+)*")

# ⚠️ Под этот шаблон подходят не только реплики игроков, но и диалоги NPC
# («[NPC] Biblio: ...»), и обычные подписи в описаниях («Source:», «Requires:»).
# Поэтому применяем его ТОЛЬКО к чату и только если это не NPC.
PLAYER_CHAT = re.compile(r"^(?:\[[^\]]{1,24}\]\s*)*[A-Za-z0-9_]{3,16}:\s")
NPC_LINE = re.compile(r"^\[NPC\]\s")

# Ники игроков: на аукционе каждая строка «Seller: ...» иначе уходит отдельной
# записью — за один заход набежало 482 штуки вместо одной.
# (?!NPC\]) — «[NPC]» это не ранг игрока: без оговорки метка съедалась вместе
# с первым словом имени, и «[NPC] Clerk Seraphine:» превращалось в «{s} Seraphine:»
RANKED_NAME = re.compile(r"\[(?!NPC\])[A-Za-z+]{2,10}\]\s*[A-Za-z0-9_]{3,16}")

# Испорченные прежним фильтром реплики NPC: подстановка в НАЧАЛЕ строки.
# У нормальных строк вроде «Seller: {s}» подстановка стоит в конце.
MANGLED = re.compile(r"^\{s\}\s")
NAME_LABEL = re.compile(r"^(Seller|Buyer|Owner|Bidder|Highest Bidder|Bid by):\s+\S.*$")
LEADERBOARD = re.compile(r"^\d+\.\s")
BARE_TOKEN = re.compile(r"^[A-Za-z0-9_]{3,16}$")
CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")


def default_dump() -> Path | None:
    for base in (
        Path(r"C:\MultiMC\instances\26.2\.minecraft"),
        Path(os.environ.get("APPDATA", "")) / ".minecraft",
    ):
        path = base / "config" / "skyblockru" / "dump" / "untranslated.json"
        if path.exists():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Чистка собранного дампа")
    parser.add_argument("--in", dest="source", help="путь к untranslated.json")
    parser.add_argument("--out", help="куда писать результат")
    args = parser.parse_args()

    dump = Path(args.source) if args.source else default_dump()
    if dump is None or not dump.exists():
        print("не нашёл дамп — укажи путь через --in")
        return 1
    out = Path(args.out) if args.out else OUT

    data = json.loads(dump.read_text(encoding="utf-8"))
    strings = list(data.get("exact") or {})
    contexts = data.get("_contexts") or {}
    print(f"в дампе: {len(strings)}")

    # Понять, какая строка из чата, а какая из описания, по JSON нельзя —
    # разделение есть только в текстовом отчёте рядом.
    chat_lines: set[str] = set()
    report = dump.with_suffix(".txt")
    if report.exists():
        block = re.search(r"### chat\n(.*?)(?=\n### |\Z)",
                          report.read_text(encoding="utf-8"), re.S)
        if block:
            chat_lines = {line.split("\t", 1)[-1]
                          for line in block.group(1).strip().splitlines() if "\t" in line}
    print(f"из них строк чата: {len(chat_lines)}")

    kept: dict[str, str] = {}
    kept_context: dict[str, str] = {}
    dropped = {"чужая реплика": 0, "таблица лидеров": 0, "одиночный ник": 0,
               "уже по-русски": 0, "схлопнуто по числам": 0}

    for text in strings:
        # только в чате и только если это не NPC — иначе выбросим и диалоги,
        # и обычные подписи описаний вида «Source:»
        if text in chat_lines and not NPC_LINE.match(text) and PLAYER_CHAT.match(text):
            dropped["чужая реплика"] += 1
            continue
        if LEADERBOARD.match(text):
            dropped["таблица лидеров"] += 1
            continue
        if BARE_TOKEN.match(text):
            dropped["одиночный ник"] += 1
            continue
        if MANGLED.match(text):
            # прежний фильтр срезал «[NPC] Имя» — восстановить нельзя,
            # но и переводить нечего: в игре такой строки не существует
            dropped.setdefault("испорчено прежним фильтром", 0)
            dropped["испорчено прежним фильтром"] += 1
            continue
        if CYRILLIC.search(text):
            dropped["уже по-русски"] += 1
            continue

        # ники — раньше чисел: цифра внутри ника иначе сломает сопоставление
        shape = RANKED_NAME.sub("{s}", text)
        labelled = NAME_LABEL.match(shape)
        if labelled:
            shape = labelled.group(1) + ": {s}"
        shape = NUMBERS.sub("{n}", shape)
        if shape in kept:
            dropped["схлопнуто по числам"] += 1
            continue
        kept[shape] = ""
        hint = contexts.get(text)
        if hint:
            kept_context[shape] = hint

    # ДОПОЛНЯЕМ, а не заменяем: уже сделанные переводы и строки прошлых заходов
    # должны пережить повторный запуск. Перезапись стоила нам нескольких тысяч строк.
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            old_exact = old.get("exact") or {}
            old_ctx = old.get("_contexts") or {}
            added = sum(1 for k in kept if k not in old_exact)
            for key, value in old_exact.items():
                # перевод из прошлого файла сохраняем, пустые не затирают новые
                kept[key] = value or kept.get(key, "")
            for key, value in old_ctx.items():
                kept_context.setdefault(key, value)
            print(f"дополняю прежний файл: было {len(old_exact)}, новых {added}")
        except (json.JSONDecodeError, OSError) as exception:
            print(f"! прежний файл не прочитался, пишу заново: {exception}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "id": "from_game",
        "priority": 20,
        "_comment": "Собрано в живой игре и почищено tools/clean_dump.py. "
                    "{n} — любое число: один перевод закроет все значения.",
        "_contexts": kept_context,
        "exact": kept,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"осталось к переводу: {len(kept)}")
    print(f"  с подсказкой о предмете: {len(kept_context)}")
    print("выброшено:")
    for reason, count in sorted(dropped.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"  {reason}: {count}")
    print()
    print(f"записано: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
