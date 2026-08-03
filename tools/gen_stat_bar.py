"""
Русские названия характеристик ТОЛЬКО для полосы над хотбаром, панели и таба.

⚠️ Зачем отдельный словарь. Решение игрока такое: в ОПИСАНИЯХ предметов
характеристики английские (по ним читают гайды и настраивают фильтры),
а над хотбаром — русские. Это не противоречие: подсказку предмета игрок
сверяет с гайдом, а полосу читает боковым зрением по сто раз за вечер,
и «83❈ Defense» там ничем не лучше «83❈ Защита».

Разделяет их ОБЛАСТЬ применения (`only`), а не отдельные записи: движок
спрашивает словарь с указанием источника строки, и одно и то же имя может
переводиться в полосе и оставаться английским в описании.

⚠️ Источник пар — сам `78-sb-stats.json`: там лежит русский перевод, который
переехал туда при переключении на английский. Второй список вести нельзя,
он разойдётся с первым.

Формы взяты из живой полосы: «83❈ Defense», «105/105✎ Mana», «1,234 Speed».

Запуск:  python tools/gen_stat_bar.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import terms  # noqa: E402

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
LANG = "ru_ru"
SOURCE = PACKS / LANG / "78-sb-stats.json"
OUT = PACKS / LANG / "12-stat-bar.json"
INDEX = PACKS / "index.json"

STRIP = re.compile("§.")

# ⚠️ Косая собирается через chr(92): написать её здесь буквой значит зависеть
# от того, как редактор поймёт escape-последовательность. На этом уже
# спотыкались — в шаблон приезжал текст вместо символа.
_BACKSLASH = chr(92)
ICON = "[" + _BACKSLASH + "uE000-" + _BACKSLASH + "uF8FF]"

# Значение колонки: «83», «105/105», «1,234», «12.5%»
VALUE = r"[\d,.]+(?:/[\d,.]+)?%?"


def pairs() -> dict[str, str]:
    """Английское имя -> русский перевод, из переключаемого словаря."""
    pack = json.loads(SOURCE.read_text(encoding="utf-8"))
    jargon = terms.of("stat_jargon")
    found: dict[str, str] = {}
    for name, value in (pack.get("glossary") or {}).items():
        if name in jargon and value and not value.startswith("@"):
            found[name] = STRIP.sub("", value).strip()
    for key, value in (pack.get("exact") or {}).items():
        head = re.match(r"^([A-Za-z][A-Za-z' -]{2,30}):", key)
        target = re.match(r"^([^:]{2,40}):", STRIP.sub("", value))
        if head and target and head.group(1) in jargon:
            found.setdefault(head.group(1), target.group(1).strip())
    return found


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not SOURCE.exists():
        print(f"нет {SOURCE.name} — сперва tools/split_sb_stats.py")
        return 1

    table = pairs()
    rules = []
    for english, russian in sorted(table.items()):
        name = re.escape(english)
        # «83❈ Defense» и «105/105✎ Mana» — значение, значок, имя
        rules.append({"p": f"^({VALUE} ?{ICON} ?){name}$", "r": f"$1{russian}"})
        # без значка: «1,234 Speed»
        rules.append({"p": f"^({VALUE} ){name}$", "r": f"$1{russian}"})
        # подпись со значением: «Defense: 83»
        rules.append({"p": f"^{name}: ({VALUE})$", "r": f"{russian}: $1"})

    pack = {
        "id": "stat_bar",
        # ⚠️ ВЫШЕ, чем у 11-stat-forms (12): у правил выигрывает то, что
        # добавлено раньше, а пакеты идут по убыванию priority. При равном
        # значении порядок решала бы сортировка имён файлов — то есть случай.
        "priority": 13,
        "_comment": "Русские названия характеристик ТОЛЬКО для полосы над "
                    "хотбаром, боковой панели и таба. В описаниях предметов они "
                    "остаются английскими (словарь sb_stats выключен) — это "
                    "решение игрока: подсказку сверяют с гайдом, а полосу читают "
                    "боковым зрением. Разделяет их поле only. "
                    "СГЕНЕРИРОВАНО tools/gen_stat_bar.py из 78-sb-stats.json.",
        # ⚠️ Область называется «scoreboard», а не «sidebar»: боковую панель мод
        # помечает именно так (ObjectiveMixin, PlayerTeamMixin). Имени «sidebar»
        # движок не выдаёт НИКОГДА, и правило с ним мертво по построению —
        # проверка `only.contains(origin)` не совпадёт ни разу. Опечатка тихая:
        # словарь грузится, ошибок нет, а панель остаётся английской.
        "only": ["action_bar", "scoreboard", "tab"],
        "regex": rules,
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.name}: правил {len(rules)}, характеристик {len(table)}")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    files = index["languages"][LANG]
    if OUT.name not in files:
        files.append(OUT.name)
        index["languages"][LANG] = sorted(files)
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        print("вписан в index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
