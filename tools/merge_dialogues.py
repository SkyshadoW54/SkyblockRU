"""
Переводы реплик NPC -> словарь мода.

⚠️ Область — ТОЛЬКО чат (`only: ["chat"]`). Реплика вида «[NPC] Ryan: …»
в описании предмета не встречается, а вот словарь без области применяется
везде и может перебить чужую строку. Ограничение бесплатное, а бед снимает
целый класс.

⚠️ Испорченные исходником реплики сюда НЕ ПОПАДАЮТ, хотя перевод у них
куплен. Их два вида, и обе беды пришли с вики, а не от модели:
  * ДЫРА ОТ ШАБЛОНА: «&7 &6Coins» — пустой кусок там, где Hypixel подставляет
    число. На экране вышло бы «вернул тебе  монет». В чистом ключе дыра
    не видна: снятие кодов схлопывает пробелы — потому и не ловилась раньше.
  * ЗАДВОЕННЫЙ ПРЕФИКС: «[NPC] Brian:[NPC] Brian: …» — сборщик склеил две
    строки таблицы.
Их 36 из 9357 (0.4%). Деньги за них потрачены, но показывать такое нельзя:
испорченная фраза заметнее английской.

Запуск:
  python tools/merge_dialogues.py
  python tools/merge_dialogues.py --out 62-npc-dialogues.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
LANG = "ru_ru"
INDEX = PACKS / "index.json"

SOURCE = WORK / "npc_dialogues.json"
CODE = re.compile(r"[&§][0-9a-fk-orA-FK-OR]")


PLAYER_HOLE = re.compile(r"\[player\]", re.IGNORECASE)
OTHER_HOLE = re.compile(r"\[(item|amount|number|npc_name)\]", re.IGNORECASE)


def substitute(text: str) -> str:
    """
    Заглушку вики «[player]» превращаем в дырку мода «{s}».

    ⚠️ Без этого 79 реплик не работают ВООБЩЕ: вики пишет «[player]»,
    а сервер подставляет ник («'Tis the Season of Jerry, Player_123!»),
    и точная запись не совпадает никогда. Замена безопасна механически:
    все 79 переводов заглушку сохранили, значит дырка встаёт на своё место
    и в оригинале, и в переводе.
    """
    return PLAYER_HOLE.sub("{s}", text)


def damaged(key: str, meta: dict) -> str | None:
    """Почему реплику нельзя показывать. None — можно."""
    raw = meta.get("raw") or ""
    if raw.count("[NPC]") > 1 or key.count("[NPC]") > 1:
        return "задвоенный префикс"
    if raw and re.search(r"\s{2,}", CODE.sub("", raw)):
        return "дыра от вырезанного шаблона"
    russian = meta.get("ru") or ""
    if re.search(r"\s{2,}", CODE.sub("", russian)):
        return "дыра в переводе"
    # ⚠️ Прочие заглушки вики («[item]», «[amount]») мод подставить не умеет:
    # дырки у него только {n} и {s}. Показать «Мне нужно вот это: [item]»
    # хуже, чем оставить строку английской — она хотя бы осмысленна.
    if OTHER_HOLE.search(key):
        return "заглушка вики, которую мод не подставит"
    # Число дырок должно совпасть, иначе {s} подставится не туда.
    if PLAYER_HOLE.findall(key) and \
            len(PLAYER_HOLE.findall(key)) != len(PLAYER_HOLE.findall(russian)):
        return "заглушка [player] потерялась в переводе"
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Реплики NPC в словарь мода")
    parser.add_argument("--out", default="62-npc-dialogues.json")
    parser.add_argument("--priority", type=int, default=15)
    args = parser.parse_args()

    lines = json.loads(SOURCE.read_text(encoding="utf-8")).get("lines") or {}
    exact: dict[str, str] = {}
    skipped: dict[str, int] = {}
    for key, meta in lines.items():
        russian = meta.get("ru")
        if not russian:
            continue
        why = damaged(key, meta)
        if why:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        exact[substitute(key)] = substitute(russian)

    out = PACKS / LANG / args.out
    out.write_text(json.dumps({
        "id": "npc_dialogues",
        "priority": args.priority,
        "_comment": "Реплики NPC, собранные с вики и переведённые с СОХРАНЕНИЕМ "
                    "РАЗМЕТКИ ЦВЕТА: §-коды стоят прямо в переводе, поэтому мод "
                    "ничего не угадывает. Собирается tools/merge_dialogues.py, "
                    "править надо data/work/npc_dialogues.json.",
        "only": ["chat"],
        "exact": exact,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    marked = sum(1 for v in exact.values() if "§" in v)
    print(f"переводов в словаре: {len(exact)}")
    print(f"  из них С РАЗМЕТКОЙ цвета: {marked} ({100 * marked // max(1, len(exact))}%)")
    for why, count in sorted(skipped.items(), key=lambda x: -x[1]):
        print(f"  не взято ({why}): {count}")
    print(f"записано: {out.relative_to(ROOT)}")

    # Регистрация: без неё словарь молча не загрузится — так уже терялись
    # 36 зачарований.
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    languages = index.setdefault("languages", {})
    packs = languages.setdefault(LANG, [])
    if args.out not in packs:
        packs.append(args.out)
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"вписан в index.json (languages.{LANG})")
    else:
        print("в index.json уже вписан")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
