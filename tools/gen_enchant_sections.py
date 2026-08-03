"""
Секции зачарований: «заголовок + описание» -> перевод, БЕЗ покупки.

⚠️ Зачем это, и почему деньги тут не нужны.

Абзац зачарований склеивается из НАБОРА, стоящего на предмете. Наборов столько,
сколько игроки собрали, поэтому целиком абзац почти никогда не совпадает: по
живому дампу из 480 блоков перевод есть у 89, а у 391 нет. Напрашивается
«докупить недостающие комбинации» — и это ложный путь: комбинаций бесконечно
много, а разного в них мало.

Разного ровно два вида, и оба конечны:
  * НАЗВАНИЕ зачарования — закрыто правилами (^Growth ([IVXLC]+)$ и т.п.);
  * ОПИСАНИЕ — их всего 121 на весь живой дамп, и они однотипны.

Описания переведены РУКАМИ (`BODIES` ниже), а этот скрипт перемножает их
с названиями и кладёт готовые секции в корпус. Одна и та же строка
«Grants +{n} ❤ Health.» обслуживает и Growth V, и Growth VI, и Growth VII —
уровень берёт на себя заголовок.

⚠️ Название зачарования НЕ переводим:
  * SkyBlock (`sb_enchants` выключен по умолчанию) — остаётся английским,
    по нему ищут вещи на аукционе;
  * ванильное — берём как его зовёт КЛИЕНТ игрока (@enchantment.minecraft.*),
    чтобы совпадало с инвентарём.

Запуск:
  python tools/gen_enchant_sections.py           показать, что выйдет
  python tools/gen_enchant_sections.py --apply   добавить в корпус
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pkey  # noqa: E402

CORPUS = ROOT / "data" / "work" / "paragraphs.json"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/tooltips.json")
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
LANG = "ru_ru"
OUT = "97-enchant-sections.json"
INDEX = PACKS / "index.json"

# ⚠️ Пишем СВОЙ СЛОВАРЬ, а не корпус. Первый заход клал секции в
# data/work/paragraphs.json — и следующая же пересборка корпуса стёрла все 29:
# make_paragraphs оставляет только то, что есть в источниках СЕЙЧАС, а секции
# там отдельными блоками не встречаются (они куски абзацев). Эта грабля в
# проекте записана — «пересборка корпуса стирает абзацы, которых нет в текущих
# источниках», — и я в неё влез, потому что решил, что корпус это хранилище.
# Корпус — рабочий файл, пересобираемый из дампа. Хранилище — словарь.

ENCHANT_HEAD = re.compile(r"^[A-Z][A-Za-z' -]*\s([IVXLC]+)$")

# ⚠️ УРОВЕНЬ — ЧАСТЬ КЛЮЧА, и он НЕ обобщается: `{n}` заменяет арабские числа,
# а уровень зачарования римский. Значит «Wisdom II» и «Wisdom V» — разные
# ключи, и купленный «Wisdom V» второму уровню не поможет ничем.
#
# Игрок прислал ровно это: на нагруднике «Wisdom II», а в корпусе лежит только
# «Wisdom V» — три строки описания остались английскими посреди переведённого
# блока. Само описание при этом ОДНО на все уровни: числа в нём уже обобщены
# («Gain {n} Intelligence for every {n} levels»), от уровня оно не зависит.
#
# Поэтому собранную секцию размножаем по всем уровням: цена — текст, который
# у нас уже есть, а закрывается любой уровень, какой попадётся игроку.
LEVELS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def spread_levels(made: dict[str, str], known: set[str]) -> int:
    """Размножить готовые секции на ОСТАЛЬНЫЕ уровни того же зачарования."""
    added = 0
    for key, value in list(made.items()):
        head = key.split(" ", 1)[0] if " " not in key else None
        match = re.match(r"^([A-Z][A-Za-z' -]*?)\s([IVXLC]+)\s(.+)$", key)
        if not match:
            continue
        name, level, body = match.groups()
        for other in LEVELS:
            if other == level:
                continue
            new_key = f"{name} {other} {body}"
            if new_key in made or new_key in known:
                continue
            # уровень стоит и в переводе — меняем ТОЛЬКО его, первое вхождение,
            # чтобы не задеть римские цифры внутри описания
            new_value = re.sub(rf"(?<![A-Za-z]){re.escape(level)}(?![A-Za-z])",
                               other, value, count=1)
            if new_value == value:
                # уровня в переводе нет — подставить некуда, пропускаем:
                # молча оставить старый уровень значило бы врать на экране
                continue
            made[new_key] = new_value
            added += 1
    return added

# Описания зачарований, переведённые РУКАМИ. Термины — по границе игрока:
# базовые переводим, кастомный жаргон (Mining Fortune, Magic Find, Overbloom,
# Respiration, Farming Fortune) остаётся английским.
#
# ⚠️ Ключ пишется БЕЗ значков (их снимает `without_icons`), а в переводе на их
# месте стоят метки {i1}, {i2}… — генератор подставит настоящие значки
# из оригинала. Печатать значок прямо здесь нельзя: он из приватной зоны,
# в исходнике невидим, и первая версия этого словаря именно так их и потеряла.
BODIES = {
    "Grants +{n} Health.":
        "Даёт +{n} {i1} к здоровью.",
    "Grants +{n} Defense.":
        "Даёт +{n} {i1} к защите.",
    "Grants a {n}% chance to rebound {n}% of damage dealt back at the attacker.":
        "Даёт {n}% шанс отразить {n}% полученного урона обратно в атакующего.",
    "Grants +{n} Health Regen.":
        "Даёт +{n}{i1} к восстановлению здоровья.",
    "Reduces how much you are slowed in the water by {n}%.":
        "Уменьшает замедление в воде на {n}%.",
    "Grants +{n} Farming Fortune and +{n} Bonus Pest Chance, which increases your "
    "chance to spawn bonus Pests on The Garden.":
        "Даёт +{n}{i1} Farming Fortune и +{n}{i2} Bonus Pest Chance, что повышает "
        "шанс появления дополнительных {i3} Pests в The Garden.",
    "Gain {n} Intelligence for every {n} levels of exp you have on you. "
    "Capped at {n} Intelligence.":
        "Даёт {n} к интеллекту за каждые {n} уровней опыта при тебе. "
        "Не более {n} интеллекта.",
    "Increases how high you can fall before taking fall damage by {n} and reduces "
    "fall damage by {n}%.":
        "Увеличивает высоту безопасного падения на {n} и уменьшает урон "
        "от падения на {n}%.",
    "During the day, +{n} Overbloom. During the night, -{n}% Visitor Cooldown.":
        "Днём +{n}{i1} Overbloom. Ночью -{n}% к перезарядке посетителей.",
    "Convert {n}% of Vitality used as Strength for {n}s. (Max {n} Strength).":
        "Преобразует {n}% использованной {i1} живучести в {i2} силу на {n} с. "
        "(Максимум {n}{i3} силы).",
    "Increases your underwater mining rate.":
        "Повышает скорость добычи под водой.",
    "Grants +{n} Respiration, which increases the amount of time you can stay "
    "under water.":
        "Даёт +{n}{i1} Respiration, что увеличивает время, которое ты можешь "
        "провести под водой.",
    "Increases all Combat stats and Magic Find by {n}% per player within {n} "
    "blocks of you, up to {n} players.":
        "Повышает все боевые характеристики и {i1} Magic Find на {n}% за каждого "
        "игрока в радиусе {n} блоков, вплоть до {n} игроков.",
    "Saves {n}% of your coins on death. Additionally, enemies drop +{n} coins "
    "when killed.":
        "Сохраняет {n}% твоих монет при смерти. Кроме того, враги роняют "
        "+{n} монет при убийстве.",
    "Grants +{n} True Defense against fire and lava.":
        "Даёт +{n}{i1} к истинной защите от огня и лавы.",
    "Automatically smelts broken blocks into their smelted form.":
        "Автоматически переплавляет добытые блоки.",
    "When falling below {n}% Health: - Gain +{n}% Defense for {n}s. "
    "- Regen {n} Vitality. Cooldown: {n}s":
        "При падении здоровья ниже {n}%{i1}: - даёт +{n}% к {i2} защите на {n} с. "
        "- восстанавливает {n}{i3} живучести. Перезарядка: {n} с",
    "Increases how quickly your tool breaks blocks.":
        "Повышает скорость, с которой инструмент ломает блоки.",
    "Grants +{n} Mining Fortune, which increases your chance for multiple drops.":
        "Даёт +{n}{i1} Mining Fortune, что повышает шанс получить больше ресурсов.",
    "Grants +{n} Cold Resistance.":
        "Даёт +{n}{i1} к сопротивлению холоду.",
    "Grants +{n} Vitality on weekdays and +{n} of a random Wisdom stat on weekends.":
        "Даёт +{n}{i1} живучести в будни и +{n}{i2} случайной характеристики "
        "Wisdom в выходные.",
    "Grants a {n}% chance for mobs and ores to drop double experience.":
        "Даёт {n}% шанс, что мобы и руда дадут вдвое больше опыта.",
    "Grants +{n} Intelligence.":
        "Даёт +{n}{i1} к интеллекту.",
    "Grants +{n} Health Regen while out of combat.":
        "Даёт +{n}{i1} к восстановлению здоровья вне боя.",
    "Grants +{n} Intelligence. Grants +{n} True Defense. When damaged by an arrow, "
    "deal {n}x your Intelligence to its shooter.":
        "Даёт +{n}{i1} к интеллекту. Даёт +{n}{i2} к истинной защите. При получении "
        "урона от стрелы наносит стрелявшему урон, равный {n}x твоего {i3} интеллекта.",
    "Heal +{n}% more from wands. Deal +{n}% damage with Slayer weapons. "
    "Gain +{n} Combat Wisdom with Slayer weapons. With Smoldering Polarization, "
    "gain +{n} Magic Find on your slayer weapon.":
        "ℏ Лечение от жезлов больше на +{n}%. ℏ Наносит на +{n}% больше урона "
        "оружием истребителя. ℏ Даёт +{n}{i1} Combat Wisdom оружию истребителя. "
        "ℏ С Smoldering Polarization даёт +{n}{i2} Magic Find твоему оружию "
        "истребителя.",
}


# Значок Hypixel: приватная зона юникода плюс обычные символы, которыми он
# помечает характеристики (❤ ❈ ☘ ✎ ⚔ …). Признак — КАТЕГОРИЯ символа, а не
# диапазон: это уже записано в граблях про restore_icons.
ICON = re.compile(r"[-☀-➿⬀-⯿]")


def without_icons(text: str) -> str:
    """
    Текст без значков и лишних пробелов — по нему сопоставляем описания.

    ⚠️ Зачем. Значки непечатаемы, и при переносе строки через терминал или
    буфер они молча превращаются в пробел. Первая версия `BODIES` была набрана
    именно так, и из 26 описаний совпало 9: ключи в дампе несут «Grants +{n}
     Health.», а в словаре лежало «Grants +{n}  Health.» — на глаз
    одно и то же. Поэтому сопоставляем по форме БЕЗ значков, а сами значки
    возвращаем из оригинала.
    """
    return re.sub(r"\s+", " ", ICON.sub(" ", text)).strip()


def put_icons(russian: str, original: str) -> str:
    """
    Возвращает значки оригинала в перевод — на места меток {i1}, {i2}, …

    Приём тот же, что при переводе (`translate_tooltips.mask_icons`): значок
    механически не поставить «по смыслу», зато метка переносится вместе
    со словом, и порядок значков в описании тот же, что в оригинале.
    """
    icons = ICON.findall(original)
    out = russian
    for number, icon in enumerate(icons, start=1):
        out = out.replace("{i%d}" % number, icon)
    # Метка без значка — лучше убрать, чем показать игроку «{i2}»
    return re.sub(r"\s*\{i\d}", "", out)


def cut_bought(paragraphs: list[dict]) -> dict[str, str]:
    """
    Нарезать купленные абзацы на отдельные зачарования.

    В корпусе лежит «Growth V Grants … Health. Protection V Grants … Defense.»
    -> «Growth V Даёт … к здоровью. Защита V Даёт … к защите.», то есть переводы
    ОБОИХ зачарований, просто слитые. Режем их обратно тем же приёмом, каким мод
    режет абзац на экране: позиция заголовка в переводе известна из словаря.
    """
    from split_enchant_sections import cut_points, variants_of

    dic = _dictionaries()
    out: dict[str, str] = {}
    for para in paragraphs:
        translated = para.get("ru") or ""
        rows = [str(row) for row in (para.get("lines") or [])]
        clean = [pkey.strip_codes(row).strip() for row in rows]
        heads = [i for i, row in enumerate(clean) if row and ENCHANT_HEAD.match(row)]
        if not translated or len(heads) < 2:
            continue
        points = cut_points(translated, [variants_of(clean[i], dic) for i in heads])
        if sum(1 for at, _ in points if at >= 0) < 2:
            continue
        for order, start in enumerate(heads):
            at, _length = points[order]
            if at < 0:
                continue
            stop = heads[order + 1] if order + 1 < len(heads) else len(rows)
            piece = rows[start:stop]
            if len([row for row in piece if pkey.strip_codes(row).strip()]) < 2:
                continue
            key = pkey.key_of(piece)
            end = len(translated)
            for later, _ in points[order + 1:]:
                if later >= 0:
                    end = later
                    break
            value = translated[at:end].strip()
            if key and value and key not in out:
                out[key] = value
    return out


def head_translation(head: str) -> str:
    """
    Как назвать зачарование в переводе.

    Ванильное — словом клиента (совпадает с инвентарём игрока), всё остальное
    оставляем ПО-АНГЛИЙСКИ: словарь SkyBlock-зачарований выключен, и по этим
    названиям ищут вещи на аукционе.
    """
    import status
    from check_sections import expand_keys

    dic = _dictionaries()
    hit = dic.exact.get(head)
    if hit and "@" in hit[0]:
        return expand_keys(hit[0]) or head
    for rule in dic.rules:
        pattern, replacement = rule.pattern, rule.replacement
        match = pattern.fullmatch(head)
        if match and "@" in replacement:
            try:
                filled = match.expand(re.sub(r"\$(\d)", r"\\\1", replacement))
            except (re.error, IndexError):
                return head
            return expand_keys(filled) or head
        if match:
            break
    return head


_DIC = None


def _dictionaries():
    global _DIC
    if _DIC is None:
        import status
        _DIC = status.Dictionaries()
    return _DIC


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Секции зачарований из готовых описаний")
    parser.add_argument("--apply", action="store_true", help="добавить в корпус")
    args = parser.parse_args()

    if not DUMP.exists():
        print("нет дампа подсказок:", DUMP)
        return 1

    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = data.get("paragraphs") or []
    known = {para["text"] for para in paragraphs}

    made: dict[str, str] = {}
    # ⚠️ Сперва режем УЖЕ КУПЛЕННЫЕ абзацы: переводы отдельных зачарований
    # там уже есть, просто слиты по нескольку в одну запись. Это бесплатно
    # и точнее ручного перевода — текст вычитан и размечен цветом.
    made.update(cut_bought(paragraphs))
    print(f"нарезано из купленных абзацев: {len(made)}")

    blocks = json.loads(DUMP.read_text(encoding="utf-8")).get("tooltips") or []
    seen_bodies: set[str] = set()
    for block in blocks:
        lines = [str(line) for line in block["lines"]]
        for run in pkey.runs(lines):
            clean = [pkey.strip_codes(row).strip() for row in run]
            heads = [i for i, row in enumerate(clean) if row and ENCHANT_HEAD.match(row)]
            if len(heads) < 2:
                continue
            for order, at in enumerate(heads):
                stop = heads[order + 1] if order + 1 < len(heads) else len(run)
                body_rows = [row for row in clean[at + 1:stop] if row]
                if not body_rows:
                    continue
                body = pkey.generalize(" ".join(body_rows))
                seen_bodies.add(body)
                # Сопоставляем по форме БЕЗ значков, значки вернём из оригинала
                russian = BODIES.get(without_icons(body))
                if not russian:
                    continue
                key = pkey.key_of(run[at:stop])
                if not key or key in known or key in made:
                    continue
                made[key] = f"{head_translation(clean[at])} {put_icons(russian, body)}"

    print(f"описаний переведено руками: {len(BODIES)}")
    print(f"описаний встретилось в дампе: {len(seen_bodies)}")
    print(f"собрано по встреченным уровням: {len(made)}")
    grown = spread_levels(made, known)
    print(f"добавлено ДРУГИХ УРОВНЕЙ тех же зачарований: {grown}")
    print(f"НОВЫХ секций собрано: {len(made)}")
    print()
    for key, value in list(made.items())[:6]:
        print(f"  {key[:70]}")
        print(f"    -> {value[:70]}")

    if not made:
        return 0
    if not args.apply:
        print()
        print("это СУХОЙ прогон — чтобы применить, добавь --apply")
        return 0

    # ⚠️ КЛЮЧИ, КОТОРЫЕ УЖЕ ЕСТЬ В КОРПУСЕ, СЮДА КЛАСТЬ НЕЛЬЗЯ.
    #
    # Абзацы движок раскладывает через put, а пакеты идут по priority ПО
    # УБЫВАНИЮ — значит побеждает тот, у кого priority МЕНЬШЕ. У этого пакета
    # 20, у 96-paragraphs 21, и наш плоский перевод молча затирал корпусный,
    # РАЗМЕЧЕННЫЙ ЦВЕТОМ: «§7§9Growth I§7 Даёт §a+{n}§7…» превращалось
    # в «Growth I Даёт +{n}…». Замер: пересекалось 23 ключа, у 15 из них
    # терялась вся разметка. Заметить это на экране почти нельзя — текст-то
    # русский, просто серый.
    #
    # Смысл пакета — закрывать то, чего в корпусе НЕТ, поэтому дубликаты
    # выбрасываем здесь, а не спорим приоритетами.
    corpus_ready = {para["text"]: para.get("ru") for para in paragraphs
                    if para.get("ru")}
    clash = [key for key in made if key in corpus_ready]
    for key in clash:
        del made[key]
    if clash:
        print(f"не беру (эти абзацы уже есть в корпусе, там перевод с цветом): {len(clash)}")

    pack = {
        "id": "enchant_sections",
        "priority": 20,
        "_comment": "Отдельные зачарования: «заголовок + описание» -> перевод. "
                    "Собирается автоматически (tools/gen_enchant_sections.py) из "
                    "двух источников: нарезки УЖЕ КУПЛЕННЫХ абзацев корпуса и "
                    "переведённых руками описаний (BODIES в скрипте). Нужен потому, "
                    "что абзац зачарований склеивается из НАБОРА на предмете, "
                    "а наборов бесконечно много: целиком такой абзац почти никогда "
                    "не совпадает, зато каждое зачарование по отдельности — всегда.",
        "only": ["item_lore"],
        "paragraphs": made,
    }
    out = PACKS / LANG / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(f"записано: {out.relative_to(ROOT)}  ({len(made)} зачарований)")

    # Не вписал в index.json — молча не загрузится. Эта грабля в проекте уже была.
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    listing = index.setdefault("languages", {}).setdefault(LANG, [])
    if OUT not in listing:
        listing.append(OUT)
        listing.sort()
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"вписано в index.json: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
