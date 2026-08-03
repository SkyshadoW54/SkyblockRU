"""
Возвращает английские названия характеристик ВЕЗДЕ: и в метках, и в прозе.

⚠️ Главный вопрос тут — «где термин, а где обычное слово», и решается он тем же
признаком, на котором стоит весь проект: **Hypixel пишет имя характеристики
с Заглавной, а обычное слово со строчной**.

    Increases ⛏ Mining Speed with part installed.   -> термин, меняем
    Deals +{n}% damage to Wither mobs.              -> обычное слово, не трогаем

Поэтому замена делается НЕ вслепую по русскому тексту, а только там, где
в ОРИГИНАЛЕ стоит имя характеристики. Иначе «даёт +{n} к урону» превратилось бы
в «+{n} к Damage» даже в тех фразах, где Hypixel говорил про урон обычным
словом, — и перевод стал бы рваным без всякой пользы для поиска.

⚠️ Почему заменой, а не переводом через API: английское слово не склоняется,
поэтому подставляется в любой падеж как есть, а разметка цветом и вычитанный
текст остаются на месте. Покупка перевода тут дала результат ХУЖЕ и стоила
$7.5 — см. грабли в CLAUDE.md.

Запуск:
  python tools/stats_to_english.py          сухой прогон
  python tools/stats_to_english.py --yes    применить
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
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
PACK = PACKS / "ru_ru" / "78-sb-stats.json"

STRIP = re.compile("§.")

# Между словами термина бывают §-коды, а не только пробел: Hypixel красит слова
# по отдельности («§bМагического§7 §bпоиска§7»). Один абзац пережил три захода
# замены, пока разделителем не стало вот это.
SEP = r"(?:§.|\s)+"


def stem(word: str) -> str:
    """Огрызок слова без окончания — зацепка для падежей, не морфология."""
    return word[:-1] if len(word) > 4 else word


# ⚠️ Пары, которые автопоиск НЕ НАХОДИТ, — их приходится называть руками.
#
# Автопоиск берёт перевод из sb_stats, но там термин должен стоять в узнаваемой
# форме («Mining Speed: +{n}» → «Скорость добычи: +{n}»). А «Mining Spread»
# и «Heat» встречаются только ВНУТРИ фраз («Даёт +{n} к разбросу добычи»,
# «за каждые {n} Жара»), и вытащить из них пару механически нельзя: непонятно,
# где кончается термин и начинается остальное предложение.
EXTRA_PAIRS = {
    "Mining Spread": "разброс добычи",
    "Gemstone Spread": "разброс самоцветов",
    "Heat": "Жара",
    "Hunter Fortune": "Удача охотника",
    "Hunt Wisdom": "Мудрость охотника",
    "Bonus Pest Chance": "доп. шанс Pests",
    "Runecrafting Wisdom": "Мудрость рунной магии",
    # ⚠️ Ниже — формы, поднятые из КОПИИ словарей, снятой до переноса.
    # Это тот же оплаченный перевод: он лежал в 11-stat-forms, пока термин
    # не сделали английским. Выдумывать их заново незачем.
    "Block Fortune": "Удача на блоки",
    "Carrot Fortune": "Удача на морковь",
    "Cocoa Beans Fortune": "Удача на какао-бобы",
    "Dwarven Metal Fortune": "Удача на гномий металл",
    "Fig Fortune": "Удача на инжир",
    "Gemstone Fortune": "Удача на самоцветы",
    "Mangrove Fortune": "Удача на мангры",
    "Mushroom Fortune": "Удача на грибы",
    "Ore Fortune": "Удача на руду",
    "Potato Fortune": "Удача на картофель",
    "Pumpkin Fortune": "Удача на тыквы",
    "Wheat Fortune": "Удача на пшеницу",
    "Cactus Fortune": "Удача на кактусы",
    "Melon Fortune": "Удача на арбузы",
    "Nether Stalk Fortune": "Удача на адский нарост",
    "Sugar Cane Fortune": "Удача на сахарный тростник",
    "Trophy Fish Chance": "Шанс трофейной рыбы",
    "Fear": "Страх",
    "Pull": "Притяжение",
    "Sweep": "Размах",
    "Tracking": "Отслеживание",
    "Swing Range": "Радиус удара",
    "Overbloom": "Редкий урожай",
    "Rift Damage": "Урон в Разломе",
    "Rift Health": "Здоровье в Разломе",
    "Rift Intelligence": "Интеллект в Разломе",
    "Rift Mana Regen": "Восстановление маны в Разломе",
    "Rift Walk Speed": "Скорость в Разломе",
}

# ⚠️ ДОПОЛНИТЕЛЬНЫЕ формы того же термина: один английский — несколько русских.
# «Bonus Pest Chance» переводили и как «доп. шанс Pests», и просто как
# «шанс Pests», и обе формы живут в корпусе. Одним шаблоном их не взять:
# короткая является куском длинной, и замена оставила бы «к доп. Bonus Pest
# Chance». Поэтому формы перечислены, а порядок — от длинной к короткой.
EXTRA_FORMS = [
    ("Bonus Pest Chance", "доп. шанс Pests"),
    ("Bonus Pest Chance", "шанс Pests"),
    # ⚠️ Один термин переводили ПО-РАЗНОМУ в разное время: «Удача на инжир»
    # в словаре и «Удача с фиг» в корпусе. Обе формы живые, обе надо ловить.
    ("Fig Fortune", "Удача с фиг"),
    ("Mangrove Fortune", "Удача с мангров"),
    ("Fishing Wisdom", "мудрость рыбалки"),
    ("Tracking", "отслеживание"),
    ("Swing Range", "дальность замаха"),
    ("Sweep", "Замах"),
    # ⚠️ Культуры переводили ДВАЖДЫ и по-разному: в словаре «Удача на морковь»,
    # а в корпусе «Удача моркови» — родительный падеж вместо предлога.
    # Живы обе формы, ловить надо обе.
    ("Cocoa Beans Fortune", "Удача какао-бобов"),
    ("Mushroom Fortune", "Удача грибов"),
    ("Nether Stalk Fortune", "Удача адского нароста"),
    ("Carrot Fortune", "Удача моркови"),
    ("Potato Fortune", "Удача картофеля"),
    ("Pumpkin Fortune", "Удача тыквы"),
    ("Wheat Fortune", "Удача пшеницы"),
    ("Cactus Fortune", "Удача кактуса"),
    ("Sugar Cane Fortune", "Удача сахарного тростника"),
    ("Melon Fortune", "Удача арбуза"),
    ("Fig Fortune", "Удача инжира"),
    ("Mangrove Fortune", "Удача мангров"),
    ("Gemstone Fortune", "Удача самоцветов"),
    ("Ore Fortune", "Удача руды"),
    ("Block Fortune", "Удача блоков"),
    ("Dwarven Metal Fortune", "Удача гномьего металла"),
    # ⚠️ И ТРЕТЬЯ форма: «Удача С кактусами» (творительный) — так переводили
    # строки зелий Turbo-*. Три написания одного термина в одном корпусе —
    # цена того, что перевод покупался порциями в разное время.
    ("Cactus Fortune", "Удача с кактусами"),
    ("Sugar Cane Fortune", "Удача с сахарным тростником"),
    ("Carrot Fortune", "Удача с морковью"),
    ("Cocoa Beans Fortune", "Удача с какао-бобами"),
    ("Mushroom Fortune", "Удача с грибами"),
    ("Potato Fortune", "Удача с картофелем"),
    ("Pumpkin Fortune", "Удача с тыквами"),
    ("Wheat Fortune", "Удача с пшеницей"),
    ("Melon Fortune", "Удача с арбузами"),
]

# Однословные переводы в ПРОЗЕ по умолчанию не трогаем («Сил\w*» подхватит
# «сильный» и «силуэт»). Здесь — те, где это проверено и безопасно: слово
# редкое и в наших текстах значит только характеристику.
PROSE_SAFE = {"Heat"}


def pairs() -> dict[str, str]:
    """Пары «английское имя -> русский перевод» из самого словаря sb_stats."""
    if not PACK.exists():
        return {}
    pack = json.loads(PACK.read_text(encoding="utf-8"))
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

    for name, value in EXTRA_PAIRS.items():
        if name in jargon:
            found.setdefault(name, value)

    # Перевод из одного слова слишком опасен для прозы: «Сила» подхватит
    # «сильный» и «силуэт». Такие меняем только в МЕТКАХ (там есть двоеточие),
    # а в прозе оставляем — цена ошибки выше выигрыша.
    return found


def rule(russian: str) -> re.Pattern:
    """Шаблон, ловящий русский перевод в любом падеже."""
    words = russian.split()
    return re.compile(SEP.join(stem(w) + r"\w*" for w in words), re.IGNORECASE)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="характеристики на английский")
    parser.add_argument("--yes", action="store_true", help="применить")
    parser.add_argument("--prose", action="store_true",
                        help="менять и в прозе абзацев, а не только в метках")
    args = parser.parse_args()

    table = pairs()
    single = {e: r for e, r in table.items() if len(r.split()) == 1}
    multi = {e: r for e, r in table.items() if len(r.split()) > 1}
    print(f"пар «английский -> русский»: {len(table)}"
          f"  (из них однословных, для прозы небезопасных: {len(single)})")

    # ⚠️ Порядок: ДЛИННЫЕ переводы первыми. Иначе «Heat» → «Жара» съест «жаре»
    # внутри «Сопротивление жаре», и Heat Resistance превратится
    # в «Сопротивление Heat». Короткий термин всегда кусок длинного.
    ordered = sorted(table.items(), key=lambda item: -len(item[1]))
    rules = {eng: rule(ru) for eng, ru in ordered}

    # Дополнительные формы идут ОТДЕЛЬНЫМ списком: у словаря ключ уникален,
    # а тут один термин имеет несколько русских написаний.
    extra = [(eng, rule(ru)) for eng, ru in EXTRA_FORMS
             if eng in terms.of("stat_jargon")]
    word = {eng: re.compile(r"(?<![A-Za-z])" + re.escape(eng) + r"(?![A-Za-z])")
            for eng in table}

    # --- словари: метки вида «Имя: значение» ---
    changed_files = 0
    changed_entries = 0
    for path in sorted(PACKS.rglob("*.json")):
        # ⚠️ 12-stat-bar.json НАМЕРЕННО русский: это полоса над хотбаром,
        # панель и таб. Замена там всё портит — она сделала бы английским
        # ровно то, ради чего словарь и заведён.
        if path.name in {"index.json", PACK.name, "12-stat-bar.json"}:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("default") is False:
            continue
        hits = 0

        def fix(key: str, value: str) -> str:
            nonlocal hits
            for eng, pattern in list(rules.items()) + extra:
                if not word[eng].search(key):
                    continue  # в оригинале этого термина нет — не наше дело
                new = pattern.sub(eng, value)
                if new != value:
                    hits += 1
                    value = new
            return value

        for section in ("exact", "paragraphs", "glossary"):
            block = data.get(section)
            if isinstance(block, dict):
                for key in list(block):
                    block[key] = fix(key, block[key])
        rules_list = data.get("regex")
        if isinstance(rules_list, list):
            for item in rules_list:
                item["r"] = fix(item.get("p", ""), item.get("r", ""))

        if hits:
            changed_files += 1
            changed_entries += hits
            print(f"  {path.name:<24} записей поправлено: {hits}")
            if args.yes:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                encoding="utf-8")

    print(f"  ИТОГО в словарях: {changed_entries} записей в {changed_files} файлах")

    # --- корпус абзацев: только там, где в ОРИГИНАЛЕ имя с заглавной ---
    if args.prose:
        data = json.loads(CORPUS.read_text(encoding="utf-8"))
        prose = 0
        for para in data["paragraphs"]:
            russian = para.get("ru")
            if not russian:
                continue
            for eng, pattern in list(rules.items()) + extra:
                if eng in single and eng not in PROSE_SAFE:
                    continue  # однословные в прозе не трогаем
                if not word[eng].search(para["text"]):
                    continue
                new = pattern.sub(eng, russian)
                if new != russian:
                    russian = new
                    prose += 1
            para["ru"] = russian
        print(f"  абзацев прозы поправлено: {prose}")
        if args.yes:
            CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                              encoding="utf-8")

    if not args.yes:
        print()
        print("сухой прогон — ничего не изменено. Применить: --yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
