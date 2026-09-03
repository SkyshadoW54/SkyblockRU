# -*- coding: utf-8 -*-
"""Строки, где ЖАРГОН остался английским внутри русского перевода.

    python tools/gen_full_jargon.py            покажет
    python tools/gen_full_jargon.py --write    соберёт 03-full-jargon.json

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ СЛОВАРЬ. Перевод строки ЦЕЛИКОМ лежит точной записью
(«Ням-ням! Ты обновил +{n}⚡ Sweep на {n} часов»), а `exact` движок ищет РАНЬШЕ
правил — значит правила режима из `78-sb-stats` до дела не доходят, и в полном
режиме термин остаётся английским. Ровно та же грабля, что записана про
«Vitality»: точная запись перебивала правила режима.

⚠️ PRIORITY 3 — НИЖЕ ВСЕХ. У `exact` побеждает МЕНЬШИЙ, а обычные записи лежат
в `42-checklist` (5), `90-from-game` (10), `40-lore` (25). Чтобы режимная версия
победила их все, ей нужен priority меньше пяти.

⚠️ ПАДЕЖ МАШИНОЙ НЕ ВЫВОДИТСЯ — записанное правило проекта. Но и гадать тут
не надо: управляющее слово стоит рядом и его видно. Механически берётся только
самый частый случай — термин ПОСЛЕ ЧИСЛА («+{n}⚡ Sweep»), там именительный,
как в «+2 ❤ Здоровье». Остальные формы перечислены явно в HAND.
"""
import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import status  # noqa: E402
import check_nicknames  # noqa: E402
import terms  # noqa: E402

OUT = ROOT / "src/main/resources/assets/skyblockru/packs/ru_ru/03-full-jargon.json"
DUMP = pathlib.Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/collected.json")
CYR = re.compile("[а-яА-ЯёЁ]")
# перед термином — число или дырка, между ними разве что значок
AFTER_NUMBER = re.compile(r"[\d}]\s*\S{0,2}\s*$")

# ⚠️ ФОРМЫ, КОТОРЫЕ МАШИНА НЕ ВЫВЕДЕТ. Слева — что стоит в переводе сейчас,
# справа — чем заменить. Падеж задаёт слово ПЕРЕД термином.
HAND = {
    "к Tracking": "к Отслеживанию",
    "к Sweep": "к Размаху",
    "Звуки Ferocity": "Звуки свирепости",
    "Обогащено Ferocity": "Обогащено свирепостью",
    "Обогащено Magic Find": "Обогащено магическим поиском",
    "Обогащено Sea Creature Chance": "Обогащено шансом морских существ",
    "срабатывание Pristine": "срабатывание чистоты",
    "Срабатываний Pristine": "Срабатываний чистоты",
    "Дополнительная Farming Fortune": "Дополнительная удача фермера",
    "даёт  Magic Find": "даёт Магический поиск",
    "дают  Sea Creature Chance": "дают Шанс морских существ",
    "получил Pet Luck": "получил Удачу питомцев",
}

# ⚠️ НЕ ТРОГАТЬ — записанные решения и чужие слова.
SKIP = (
    # «Чат Pristine» — это чат о СРАБАТЫВАНИИ Pristine; «Чат чистоты» врёт
    # по смыслу, и решение оставить термин английским записано в gen_checklist.
    "Чат Pristine",
    # «Fear» сидит внутри имени NPC «Fear Mongerer», «Heat» — внутри перековки
    # «Heated», «Pet Luck Potion» — имя предмета. Признак без границы слова
    # задевает их; это записанная грабля проекта.
    "Fear Mongerer",
    "Бонус Heated",
    "Pet Luck Potion",
)


def russian_terms() -> dict[str, str]:
    """Именительный падеж каждого жаргонного термина — СПРАШИВАЕМ У ДВИЖКА.

    ⚠️ Свой список тут завести нельзя: он разойдётся с `78-sb-stats` при первой
    же правке, и абзац показывал бы одно слово, а подпись рядом другое.
    """
    full = status.Dictionaries(without={OUT.name}, groups={"full"})
    out = {}
    for term in terms.of("stat_jargon"):
        for probe in (f"{term}: +5", f"+5 {term}"):
            found = status.lookup(probe, full, origin="item_lore")
            if not found or not CYR.search(found[0]):
                continue
            text = found[0].replace("+5", "").replace(":", "").strip()
            text = re.sub(r"^[^\wа-яА-ЯёЁ]+|[^\wа-яА-ЯёЁ]+$", "", text)
            text = re.sub(r"\s*\+?\{?n?$", "", text).strip()
            if text and CYR.search(text):
                out[term] = text
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    if not DUMP.exists():
        print("нет дампа:", DUMP)
        return 1
    ru_of = russian_terms()
    jargon = sorted(terms.of("stat_jargon"), key=len, reverse=True)
    # ⚠️⚠️ СЕБЯ ИЗ ОПРОСА ИСКЛЮЧАЕМ, иначе генератор съедает сам себя.
    # На ВТОРОМ прогоне он находит в 03-full-jargon.json свои же записи —
    # там жаргон уже русский, — решает, что работы нет, и пишет ПУСТОЙ
    # словарь: 76 записей -> 0, без единой жалобы. Проверено на первом же
    # повторе. Та же грабля была у gen_headers (1385 -> 0) и split_sb_stats.
    full = status.Dictionaries(without={OUT.name}, groups={"full"})
    dump = json.loads(DUMP.read_text(encoding="utf-8"))

    # ⚠️ ИСТОЧНИКА ДВА, и второй крупнее. `collected.json` хранит строки,
    # а `tooltips.json` — БЛОКИ подсказок целиком, и там строк вдвое больше:
    # замер 25.08 — по строкам находилось 76 мест, по блокам 242. Сбор
    # по одному источнику теряет целые формы; записанная грабля проекта.
    pairs = []
    for origin, lines in (dump.get("sources") or {}).items():
        rows = lines.items() if isinstance(lines, dict) else ((x, 1) for x in lines)
        pairs.extend((origin, line) for line, _ in rows)
    blocks_file = DUMP.parent / "dump" / "tooltips.json"
    if not blocks_file.exists():
        blocks_file = DUMP.with_name("tooltips.json")
    if blocks_file.exists():
        data = json.loads(blocks_file.read_text(encoding="utf-8"))
        blocks = data.get("tooltips") if isinstance(data, dict) else data
        for block in blocks or []:
            lines = block.get("lines") if isinstance(block, dict) else block
            for line in lines or []:
                if isinstance(line, str) and line.strip():
                    pairs.append(("item_lore", line.strip()))

    exact, hand_used, skipped = {}, 0, 0

    known_names = check_nicknames.known_names()

    nicknamed = 0
    handmade = 0
    _hand = OUT.parent / "04-full-strings.json"
    by_hand = set()
    if _hand.exists():
        by_hand = set(json.loads(_hand.read_text(encoding="utf-8"))
                      .get("exact", {}))
    seen_keys = set()
    for origin, line in pairs:
        if (origin, line) in seen_keys:
            continue
        seen_keys.add((origin, line))
        if True:
            found = status.lookup(line, full, origin=origin)
            if not found or not CYR.search(found[0]):
                continue
            text = found[0]
            if any(bad in text for bad in SKIP):
                skipped += 1
                continue
            hit = next((t for t in jargon if t in text), None)
            if not hit or hit not in ru_of:
                continue
            new = text
            for src, dst in HAND.items():
                if src in new:
                    new = new.replace(src, dst)
                    hand_used += 1
            if hit in new:
                at = new.find(hit)
                if AFTER_NUMBER.search(new[:at]):
                    new = new[:at] + ru_of[hit] + new[at + len(hit):]
            if new != text and not any(t in new for t in jargon):
                # ⚠️ ключ из ЖИВОЙ строки бывает с чужим ником
                key = check_nicknames.safe_key(line, new, known_names)
                if key is None:
                    nicknamed += 1
                    continue
                # ⚠️ РУЧНОЙ ПЕРЕВОД СИЛЬНЕЕ: у нас priority 3, у него 4,
                # и у `exact` побеждает МЕНЬШИЙ — то есть наша подстановка
                # перебила бы более полный перевод («на Грифоне» -> «on
                # Griffin»). Мы меняем ОДИН термин, руками переведено всё.
                if key in by_hand:
                    handmade += 1
                    continue
                exact[key] = new

    # ⚠️⚠️ ПЕРЕНОС ПРЕЖНИХ ЗАПИСЕЙ. Генератор видит только то, что лежит
    # в ДАМПЕ СЕЙЧАС, а дамп чистится и редеет — созданное месяц назад он
    # больше не встретит и молча выбросит. У соседнего `gen_full_names`
    # так усохло 549 -> 198, и 295 строк перестали переводиться ВООБЩЕ.
    # ⚠️ Переносим НЕ ВСЁ: что закрыто ручным переводом или несёт чужой ник —
    # не возвращаем, иначе правка отменится сама при первой пересборке.
    carried = 0
    if OUT.exists():
        _before = json.loads(OUT.read_text(encoding="utf-8")).get("exact", {})
        for _key, _value in _before.items():
            if _key in exact or _key in by_hand:
                continue
            if check_nicknames.nicks_in(_key, known_names):
                continue
            exact[_key] = _value
            carried += 1
    if carried:
        print(f"перенесено из прежней сборки: {carried}")

    print(f"строк с английским жаргоном в русском переводе: {len(exact)}")
    if nicknamed:
        print(f"  чужой ник в строке — обобщено либо отброшено: {nicknamed}")
    print(f"  из них правкой падежа (HAND): {hand_used}")
    print(f"  пропущено по решениям (SKIP): {skipped}")
    for key, value in list(exact.items())[:8]:
        print(f"   {key[:40]!r}")
        print(f"      -> {value[:64]!r}")
    if not args.write:
        print()
        print("СУХОЙ ПРОГОН. Записать: --write")
        return 0

    pack = {
        "id": "full_jargon",
        "priority": 3,
        "default": False,
        "group": "full",
        "about": "Строки, где жаргон характеристик остаётся английским: "
                 "«+{n} Sweep» -> «+{n} Размах». Часть полного перевода.",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_full_jargon.py — правь СКРИПТ. "
                    "Нужен потому, что перевод строки целиком лежит ТОЧНОЙ "
                    "записью, а exact движок ищет раньше правил: правила режима "
                    "из 78-sb-stats до дела не доходят. priority 3 — ниже всех, "
                    "у exact побеждает МЕНЬШИЙ.",
        "exact": dict(sorted(exact.items())),
    }
    # ⚠️ ПУСТОЙ ВЫХОД — ВСЕГДА ОШИБКА, а не «работы не осталось»: строки
    # с английским жаргоном из дампа никуда не деваются. Молча записанный
    # пустой словарь означал бы, что режим перестал их переводить.
    if not exact:
        print("ПУСТО — не найдено ни одной строки, файл НЕ переписан:")
        print("  скорее всего прочитан собственный выход (см. without=).")
        return 1
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано: {OUT.name} ({len(exact)} записей)")

    index = ROOT / "src/main/resources/assets/skyblockru/packs/index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    files = data["languages"]["ru_ru"]
    if OUT.name not in files:
        files.append(OUT.name)
        files.sort()
        index.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print("вписан в index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
