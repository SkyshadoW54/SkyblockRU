"""
Правила для строк характеристик ЛЮБОЙ формы.

Проблема, ради которой это написано. Hypixel пишет характеристику по-разному:
    Health: +293
    Health: +293 (+40)
    Health: +293 (+40) (+432)
    Health: +293 (+40) (+432) (+120)
Словарь держал первые две формы точными записями, и на поножах с тремя группами
перевод молча пропадал: в одной подсказке «Здоровье», в соседней «Health».
В живом дампе 266 таких строк, а групп бывает до четырёх — перечислять формы
руками значит проигрывать гонку, Hypixel добавит пятую.

Решение: на каждую ИЗВЕСТНУЮ характеристику одно регулярное правило, которое
принимает сколько угодно скобочных групп. Названия и переводы берутся из уже
существующих словарей — источник правды один, руками ничего дублировать не надо.

Точные записи не трогаем: движок сперва ищет точное совпадение, и правило
срабатывает только там, где точного нет. То есть это чистое дополнение.

⚠️ Двоеточие — не единственная форма, и это выяснилось по жалобе на экран
профиля: «Health 1,234» там без двоеточия, зато с иконкой. Формы взяты из
живого дампа (сколько раз встретились — в скобках), выдумывать тут нечего:

    иконка Имя значение      «\\ue010 Health 1,234»        51
    +значение иконка Имя     «+5\\ue015 Mining Speed»      25
    Имя: иконка значение     «Speed: \\ue022100»            5  (список игроков)

⚠️ Число в конце обязательно. Иконка сама по себе НЕ признак характеристики:
в дампе 35 строк вида «\\ue067 Foraging Camp» — это места, а их не переводят.
Разделяет их именно число: у характеристики оно есть всегда, у названия места
не бывает никогда.

Запуск:  python tools/gen_stat_forms.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protected  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
LANG = "ru_ru"
OUT = PACKS / LANG / "11-stat-forms.json"
INDEX = PACKS / "index.json"

# «Health: +{n}» и «Health: +{n}%» — из них берём пару «название -> перевод»
STAT_ENTRY = re.compile(r"^(.+?): [+\-]?\{n\}%?$")

# Значение: число со знаком, процентом или единицей, дальше сколько угодно
# скобочных групп. Числа Hypixel пишет с запятыми и точками: 1,250 и 160.5
# ⚠️ Скобки бывают КРУГЛЫЕ и КВАДРАТНЫЕ, и это разные вещи: в круглых Hypixel
# пишет прибавку от звёзд и самоцветов, в квадратных — от КОВКИ. Правило знало
# только круглые, поэтому «Health: +{n} (+{n}) [+{n}] (+{n})» не переводилось
# вовсе — а квадратная скобка есть у каждого прокачанного предмета. В живом
# дампе таких строк 15, и это ровно те вещи, на которые игрок смотрит чаще
# всего. Порядок скобок любой: «Mining Speed: +{n} [+{n}] [+{n}] (+{n})».
VALUE = (r"([+\-]?[\d,.]+[%s]?"
         r"(?:\s*[\(\[][+\-]?[\d,.]+[%s]?[\)\]])*)")

# Иконка Hypixel - символ приватной зоны Unicode.
#
# ВНИМАНИЕ. В шаблон уходит ТЕКСТ из шести знаков: косая, u, E, 0, 0, 0.
# json.dumps удвоит косую при записи в файл, Gson при чтении вернёт одну,
# и Java-регулярка поймёт это как символ приватной зоны. Поэтому косая
# собирается через chr(92): написать её здесь буквой - значит зависеть
# от того, как редактор и инструменты поймут escape-последовательность,
# а на этом уже спотыкались (в ключе оказывался текст вместо символа).
_BACKSLASH = chr(92)
ICON = "[" + _BACKSLASH + "uE000-" + _BACKSLASH + "uF8FF]"

# Короткое значение: одно число, без скобочных групп
NUMBER = r"[+\-]?[\d,.]+%?"


def collect_stats() -> dict[str, str]:
    """Название характеристики -> перевод. Из точных записей и глоссария."""
    stats: dict[str, str] = {}
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json" or path.name == OUT.name:
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # ⚠️ ПЕРЕКЛЮЧАЕМЫЙ словарь берём только если он включён по умолчанию.
        # Иначе повторяется история с валютой Bits: имя лежит в выключенном
        # слое, а генератор делает из него правило С ОБЛАСТЬЮ, то есть всегда
        # включённое, — и выключатель перестаёт работать. Так 38 кастомных
        # зачарований («Lapidary» -> «Огранка») переводились вопреки тому,
        # что игрок их отключил.
        if pack.get("default") is False:
            continue
        for source, target in (pack.get("exact") or {}).items():
            left = STAT_ENTRY.match(source)
            right = STAT_ENTRY.match(target)
            if left and right:
                stats[left.group(1)] = right.group(1)
        # Подписи из tools/gen_enchants.py: там они лежат правилом «^Имя:$»
        # (голая подпись без значения). Значение к ней приделываем мы —
        # иначе перевод есть, но виден только когда строка пустая.
        for rule in pack.get("regex") or []:
            label = re.match(r"^\^(.+?):\(\\s\*\)\$$", rule.get("p", ""))
            if label:
                name = label.group(1).replace("\\", "")
                target = re.sub(r":\$\d\s*$", "", rule.get("r", "")).strip()
                if target and name not in stats:
                    stats[name] = target
        # глоссарий: там голые названия, они же нужны для форм, которых
        # в точных записях ещё нет
        for source, target in (pack.get("glossary") or {}).items():
            if target and not target.startswith("@") and source not in stats:
                if re.fullmatch(r"[A-Za-z' ]{3,28}", source):
                    stats[source] = target

    # ⚠️ Защищённые слова выкидываем ЗДЕСЬ, а не надеемся на глоссарий.
    #
    # Живой случай: в общем глоссарии лежало «Bits -> биты», и скрипт делал из
    # этого правило «^Bits: значение$ -> биты: $1». В глоссарии оно было
    # выключено флагом glossaryPass, а тут становилось всегда включённым — то
    # есть скрипт сам, молча, включал перевод валюты, которую переводить нельзя.
    # ⚠️ Жаргон убираем ТУТ ЖЕ и по той же причине, хотя пришёл он иначе.
    # «Overbloom», «Ferocity», «Pristine» лежат подписями в 76-enchant-names,
    # а тот словарь включён всегда — значит формы для них попали бы в общий
    # 11-stat-forms и переводились бы вопреки выключенному sb_stats. Ровно
    # та же утечка, что была с «Bits», только зашедшая с другой стороны:
    # мало вынести перевод в выключенный словарь, надо ещё закрыть все
    # генераторы, которые собирают названия по всем словарям сразу.
    import terms
    guarded = protected.collect() | terms.of("stat_jargon")
    for word in list(stats):
        if word in guarded:
            del stats[word]
    return stats


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    stats = collect_stats()
    if not stats:
        print("не нашёл ни одной характеристики — словари на месте?")
        return 1

    # Длинные названия вперёд: «Bonus Attack Speed» должен победить «Attack Speed»,
    # иначе короткое правило откусит хвост от длинного.
    rules = []
    for name in sorted(stats, key=len, reverse=True):
        source = re.escape(name)
        target = stats[name]
        # Health: +293 (+40) (+432)
        rules.append({"p": f"^{source}: {VALUE}$", "r": f"{target}: $1"})
        # ❤ Health 1,234 — иконку и число переносим как есть
        rules.append({"p": f"^({ICON} ?){source} ({NUMBER})$", "r": f"$1{target} $2"})
        # +5⸸ Mining Speed
        rules.append({"p": f"^({NUMBER} ?{ICON} ?){source}$", "r": f"$1{target}"})
        # Speed: ⸸100 — список игроков
        rules.append({"p": f"^{source}: ({ICON}{NUMBER})$", "r": f"{target}: $1"})

    # ⚠️ ПРЕЖНИЕ ПРАВИЛА СОХРАНЯЕМ, а не выбрасываем.
    #
    # Файл собирается из названий, которые лежат в словарях СЕЙЧАС. Но часть
    # названий пришла из источников, которых уже нет: строка выпала из дампа,
    # очередь пересобралась, подсказки перемержились. Перезапуск генератора
    # такие правила молча стирал — замер: 1284 -> 856, то есть 428 правил
    # («Открыто коллекций», «Выполнено поручений», «Всего опыта Enchanting»)
    # исчезали за один прогон, и заметить это можно было только по счётчику
    # шаблонов в check_rules.
    #
    # Та же грабля уже записана про корпус абзацев: «переводы сохраняются»
    # и «корпус не поредеет» — РАЗНЫЕ обещания. Здесь поступаем как
    # make_paragraphs: старое переносим по ключу, новое добавляем сверху.
    kept = 0
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")).get("regex") or []
        except (json.JSONDecodeError, OSError):
            old = []
        fresh = {rule["p"] for rule in rules}
        for rule in old:
            if rule.get("p") and rule["p"] not in fresh:
                rules.append(rule)
                kept += 1

    pack = {
        "id": "stat_forms",
        "priority": 12,
        "_comment": "Строки характеристик ЛЮБОЙ формы: с двоеточием и без, с иконкой "
                    "и без, с любым числом групп в скобках. Собирается автоматически "
                    "скриптом tools/gen_stat_forms.py из названий, уже лежащих "
                    "в словарях, — правь их, а не этот файл. Точные записи важнее: "
                    "движок ищет их первыми, и правило срабатывает только там, "
                    "где точного нет.",
        # Характеристики попадаются везде: в подсказке, в меню, в списке игроков,
        # в полосе над хотбаром, в чате («+10 ❤ Health») и над головой.
        # Правило привязано к известному названию И к числу, так что расширение
        # области ничего лишнего не зацепит.
        "only": ["item_lore", "screen", "tab", "action_bar", "chat", "name_tag"],
        "regex": rules,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"характеристик: {len(stats)}")
    print(f"правил собрано: {len(rules) - kept}"
          + (f", сохранено прежних: {kept}" if kept else ""))
    print(f"записано: {OUT.relative_to(ROOT)}")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    listing = index.setdefault("languages", {}).setdefault(LANG, [])
    if OUT.name not in listing:
        listing.append(OUT.name)
        listing.sort()
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"добавил {OUT.name} в index.json")

    print("\nпримеры правил:")
    for rule in rules[:3]:
        print(f"  {rule['p'][:70]}")
        print(f"    -> {rule['r']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
