"""
Уровни КОЛЛЕКЦИЙ — правилом по списку ОТ СЕРВЕРА, а не по форме строки.

Беда, ради которой это написано. В очереди на перевод лежало 296 строк вида
«Bone I», «Coal VII», «Lapis Lazuli VI» — это уровни коллекций, и они плодятся
комбинаторикой: 87 коллекций на десяток уровней каждая. Покупать их поштучно
бессмысленно вдвойне: во-первых, это одно правило; во-вторых, имена там
ВАНИЛЬНЫЕ, а ванильные названия живут в переключаемом `vanilla_names`,
выключенном по умолчанию, — то есть по решению игрока на экране и должно
остаться «Coal VII».

⚠️ **ПРИЗНАК ПО ФОРМЕ ТУТ НЕ ГОДИТСЯ, И ЭТО ПРОВЕРЕНО ДВАЖДЫ.** Шаблон
«любое имя + римский уровень» ловит в живом дампе 1403 строки и портит 122:

    Sheep Minion I           -> «Sheep миньон I»        имя предмета!
    Forbidden Intelligence I -> «Forbidden Интеллект I»
    Minion Slots I           -> «миньон Slots I»

Ровно на этом проект уже обжигался (в граблях: «по ОДИНОЧНОЙ строке коллекцию
от имени предмета не отличить», правка тогда была откачена, 179 абзацев
потеряли соответствие). Поэтому список берётся У СЕРВЕРА: эндпоинт
`resources/skyblock/collections` отдаёт канонические 87 имён, и правило
перечисляет ИХ. Замер после сужения: ловит 385 строк дампа, портит 0.

⚠️ Правило стоит ЗАПАСНЫМ путём (priority 11 — ниже всех прочих правил):
точные записи движок ищет раньше, купленные переводы остаются на месте,
а правило подхватывает уровни, которых мы не видели.

⚠️ Замена — «$1 $2» с `tg`. Сама строка не меняется, переводится только
захваченное имя, и только если словарь его знает. Выключен `vanilla_names` —
на экране «Coal VII», как и решено; включит игрок — станет «Уголь VII».
Возможность не пропадает, а появляется.

Запуск:
  python tools/fetch_collections.py          обновить список и словарь
  python tools/fetch_collections.py --offline собрать словарь из сохранённого
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
LANG = "ru_ru"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
OUT = PACKS / LANG / "47-collections.json"
SAVED = WORK / "collections.json"

API = "https://api.hypixel.net/v2/resources/skyblock/collections"

# Уровень коллекции Hypixel пишет римской цифрой. Границу ставим по всей
# строке: «Bone V» — коллекция, а «Bone V Rewards:» уже другая семья.
LEVEL = r"([IVXLC]{1,7})"


def fetch() -> dict[str, list[str]]:
    """Канонический список коллекций от сервера."""
    with urllib.request.urlopen(API, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("success"):
        raise SystemExit("API ответил success=false")
    out: dict[str, list[str]] = {}
    for category, body in (data.get("collections") or {}).items():
        names = [item.get("name") for item in (body.get("items") or {}).values()
                 if item.get("name")]
        out[category] = sorted(names)
    return out


def load_saved() -> dict[str, list[str]]:
    try:
        return json.loads(SAVED.read_text(encoding="utf-8")).get("collections") or {}
    except (json.JSONDecodeError, OSError):
        return {}


def merge(old: dict[str, list[str]], new: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    Копим, а не заменяем.

    ⚠️ Hypixel коллекции добавляет и переименовывает, а выпавшее из ответа имя
    в игре у кого-то ещё показывается. Терять его нельзя: та же беда, на которой
    пересборка корпуса однажды срезала 1610 переводов.
    """
    merged = {key: list(values) for key, values in old.items()}
    for category, names in new.items():
        have = set(merged.get(category) or [])
        merged[category] = sorted(have | set(names))
    return merged


def build_rule(names: list[str]) -> dict:
    # длинные вперёд: иначе «Ice» откусит начало «Ice» внутри другого имени
    ordered = sorted(names, key=len, reverse=True)
    pattern = "^(" + "|".join(re.escape(name) for name in ordered) + f") {LEVEL}$"
    return {
        "_": "Уровень коллекции: «Bone V», «Coal VII». Имена ПЕРЕЧИСЛЕНЫ по списку"
             " сервера (resources/skyblock/collections), а не пойманы по форме:"
             " шаблон «имя + римский уровень» портит имена предметов"
             " («Sheep Minion I» -> «Sheep миньон I»), это проверено на дампе."
             " Замена не меняет строку — с tg переводится только имя, и только"
             " если словарь его знает. Выключен vanilla_names — остаётся"
             " «Coal VII», как и решено; включат — станет «Уголь VII».",
        "p": pattern,
        "r": "$1 $2",
        "tg": True,
        # ⚠️ Пометка ДЛЯ ИНСТРУМЕНТОВ, движок её не читает (разбор берёт только
        # p/r/tg). Очередь по общему правилу не считает `tg` закрывающим —
        # непереведённый захват дал бы смесь языков. Здесь смеси не будет:
        # захват это ванильное имя, а они лежат в переключаемом словаре,
        # выключенном по решению игрока, и строка остаётся английской целиком.
        # Без пометки очередь просила бы за эти 296 строк деньги каждый прогон.
        "toggle": True,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Коллекции Hypixel -> правило уровней")
    parser.add_argument("--offline", action="store_true",
                        help="не ходить в сеть, взять сохранённый список")
    args = parser.parse_args()

    saved = load_saved()
    if args.offline:
        collections = saved
        if not collections:
            print(f"нет сохранённого списка: {SAVED}")
            return 1
    else:
        collections = merge(saved, fetch())
        WORK.mkdir(parents=True, exist_ok=True)
        SAVED.write_text(json.dumps({"collections": collections},
                                    ensure_ascii=False, indent=1),
                         encoding="utf-8")

    names = sorted({name for values in collections.values() for name in values})
    print(f"коллекций: {len(names)} в {len(collections)} категориях")
    was = len({n for v in saved.values() for n in v})
    if was and len(names) != was:
        print(f"  список изменился: было {was}, стало {len(names)}")

    pack = {
        "id": "collections",
        "priority": 11,
        "_comment": "Уровни коллекций одним правилом. Priority 11 — ЗАПАСНЫЙ путь:"
                    " ниже всех прочих правил (у правил выигрывает больший"
                    " priority), чтобы точные записи и частные правила"
                    " срабатывали раньше. Собирается tools/fetch_collections.py"
                    " — правь СКРИПТ, а не этот файл.",
        "regex": [build_rule(names)],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"записано: {OUT.relative_to(ROOT)}")

    index_path = PACKS / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if OUT.name not in (index.get("languages") or {}).get(LANG, []):
        print(f"⚠️ впиши {OUT.name} в index.json -> languages.{LANG},"
              " иначе словарь молча не загрузится")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
