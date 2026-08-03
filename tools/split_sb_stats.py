"""
Выносит характеристики-жаргон в ПЕРЕКЛЮЧАЕМЫЙ словарь sb_stats.

Зачем. «Magic Find», «Overbloom» и ещё пять характеристик игроки называют
по-английски: по ним читают гайды и настраивают фильтры. Решение игрока —
оставить их английскими по умолчанию, а перевод отдать переключателем:
  /skyblockru pack sb_stats on

⚠️ Просто «убрать перевод» нельзя, и это главная тонкость. Выключенный словарь
НЕ ЗАЩИЩАЕТ строку: `make_queue.py` увидит её как непереведённую, отправит
в очередь, и перевод вернётся вторым слоем — в `90-from-game.json`, у которого
выключателя нет. Так уже было с зачарованием «Lapidary V»: игрок его отключил,
а на дрели стояла «Огранка V». Поэтому перевод не удаляется, а ПЕРЕЕЗЖАЕТ
в словарь с «default»: false — тогда инструменты считают строку закрытой.

⚠️ Формы («Magic Find: +7 (+2)») переезжают вместе с точными записями.
`gen_stat_forms.py` выключенные пакеты не читает намеренно, поэтому заново
он их не создаст — а без них включённый переключатель переводил бы только
часть строк.

Чего этот скрипт НЕ делает: абзацы корпуса. Там термин вшит внутрь русской
прозы («даёт +7 магического поиска»), и вынуть его подстановкой нельзя —
падеж. Их надо переводить заново:
  python tools/translate_tooltips.py data/work/paragraphs.json --forbid stat_jargon

Запуск:
  python tools/split_sb_stats.py          сухой прогон: что переедет
  python tools/split_sb_stats.py --yes    применить
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import terms  # noqa: E402

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
LANG = "ru_ru"
OUT = PACKS / LANG / "78-sb-stats.json"
INDEX = PACKS / "index.json"

JARGON = sorted(terms.STAT_JARGON)

# Словари, откуда забираем. Автоматические (95-tooltips, 96-paragraphs)
# не трогаем: их пересоберут генераторы, править надо источник.
SOURCES = ["00-glossary.json", "10-stats.json", "11-stat-forms.json",
           "40-lore.json", "90-from-game.json"]


def mentions(text: str) -> bool:
    """Термин встречается как ОТДЕЛЬНОЕ слово, а не внутри другого."""
    for term in JARGON:
        if re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", text):
            return True
    return False


def already_english(source: str, target: str) -> bool:
    """
    Перевод УЖЕ оставляет термин латиницей — забирать такую запись нельзя.

    ⚠️ Живой случай: «Enriched with Ferocity» → «Обогащено Ferocity». Проза
    переведена, термин английский — ровно то, чего мы добиваемся. А перенос
    видел в ключе слово из жаргона и утаскивал запись в выключенный словарь,
    после чего строка переставала переводиться вовсе.
    """
    clean = re.sub("§.", "", target)
    for term in JARGON:
        pattern = r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])"
        if re.search(pattern, source) and not re.search(pattern, clean):
            return False  # хоть один термин переведён — запись наша
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="вынести жаргон в sb_stats")
    parser.add_argument("--yes", action="store_true", help="применить, а не показать")
    args = parser.parse_args()

    print(f"термины: {', '.join(JARGON)}")
    print()

    moved = {"exact": {}, "regex": [], "glossary": {}}
    plan: list[tuple[Path, str, int]] = []

    for name in SOURCES:
        path = PACKS / LANG / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = 0

        for section in ("exact", "glossary"):
            block = data.get(section)
            if not isinstance(block, dict):
                continue
            take = {k: v for k, v in block.items()
                    if mentions(k) and not already_english(k, str(v))}
            for key in take:
                del block[key]
            moved[section].update(take)
            changed += len(take)

        rules = data.get("regex")
        if isinstance(rules, list):
            take = [r for r in rules if mentions(r.get("p", ""))]
            data["regex"] = [r for r in rules if not mentions(r.get("p", ""))]
            moved["regex"].extend(take)
            changed += len(take)

        if changed:
            plan.append((path, name, changed))
            if args.yes:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                encoding="utf-8")

    for path, name, count in plan:
        print(f"  {name:<24} забрано записей: {count}")
    total = sum(count for _, _, count in plan)
    print(f"  {'ИТОГО':<24} {total}")
    print()
    print(f"  в словарь sb_stats: exact {len(moved['exact'])}, "
          f"regex {len(moved['regex'])}, glossary {len(moved['glossary'])}")

    if not args.yes:
        print()
        print("сухой прогон — ничего не изменено. Применить: --yes")
        return 0

    # ⚠️ ДОБАВЛЯЕМ к тому, что уже перенесено, а не пишем файл заново.
    #
    # Скрипт собирает записи из общих словарей — но на втором запуске их там
    # уже нет, они переехали в прошлый раз. Перезапись обнулила словарь:
    # 241 точная запись и 22 термина глоссария исчезли, и включённый
    # переключатель перестал бы что-либо переводить. Беда тихая — файл на
    # месте, ошибок нет, просто пустой.
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        merged_exact = dict(old.get("exact") or {})
        merged_exact.update(moved["exact"])
        moved["exact"] = merged_exact
        merged_gloss = dict(old.get("glossary") or {})
        merged_gloss.update(moved["glossary"])
        moved["glossary"] = merged_gloss
        seen = {json.dumps(r, sort_keys=True) for r in moved["regex"]}
        for rule in old.get("regex") or []:
            if json.dumps(rule, sort_keys=True) not in seen:
                moved["regex"].append(rule)

    pack = {
        "id": "sb_stats",
        "priority": 14,
        "default": False,
        "about": "Перевод характеристик, которые игроки называют по-английски: "
                 "«Magic Find» -> «Магический поиск». Выключен по умолчанию: "
                 "по этим названиям читают гайды и настраивают фильтры",
        "_comment": "ПЕРЕКЛЮЧАЕМЫЙ словарь: /skyblockru pack sb_stats on. "
                    "Собран tools/split_sb_stats.py из общих словарей. "
                    "⚠️ Перевод не удалён, а перенесён сюда намеренно: "
                    "выключенный словарь считается «закрытым» для make_queue, "
                    "иначе строку переведут заново вторым слоем и выключатель "
                    "перестанет работать (так было с «Lapidary V»).",
        "only": ["item_lore", "chat", "action_bar", "sidebar", "screen"],
        "exact": dict(sorted(moved["exact"].items())),
        "regex": moved["regex"],
        "glossary": dict(sorted(moved["glossary"].items())),
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  записан {OUT.name}")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    files = index["languages"][LANG]
    if OUT.name not in files:
        # ⚠️ Необязательный словарь ВСЁ РАВНО вписывают в index.json: «выключить»
        # значит не применять, а не «не грузить». Не вписал — возможность
        # пропадает совсем, и вернуть её можно только пересборкой мода.
        files.append(OUT.name)
        index["languages"][LANG] = sorted(files)
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        print(f"  вписан в index.json")

    print()
    print("Дальше: абзацы корпуса переводить заново —")
    print("  python tools/translate_tooltips.py data/work/paragraphs.json "
          "--forbid stat_jargon --redo \"Magic Find\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
