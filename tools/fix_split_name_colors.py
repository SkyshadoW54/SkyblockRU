"""Цвет ИМЕНИ, оборванный §-кодом посреди имени.

Hypixel красит имя целиком, а в наших размеченных переводах код иногда
рвёт его пополам. Жалоба игрока 05.09 («слово hopper цвет потеряло»):

    §7Помести сюда §aBudget Hopper§7 или §9Enchanted§7 Hopper
                                              ^^^ синий кончился на первом слове

Видов ровно два, и оба — данные, а не догадка:

    A. выделение ЗАКРЫЛОСЬ рано:  §9Enchanted§7 Hopper  ->  §9Enchanted Hopper§7
    B. выделение ОТКРЫЛОСЬ поздно: Moonglade §2Marsh§7  ->  §2Moonglade Marsh§7

⚠️ ЧИНИМ ТОЛЬКО ТАМ, ГДЕ ПАРА ПОДТВЕРЖДЕНА СЛОВАРЁМ КАК ИМЯ. Признак «два
слова под разными кодами» сам по себе ничего не значит: у обычных слов такая
разметка законна. Источник имён — каталог сервера плюс защищённые имена.

⚠️ И ОБЯЗАТЕЛЬНО СМОТРИМ НА ЦВЕТ ТЕЛА. Без этого «Cocoa §6Beans Fortune§7»
чинилось бы в «Cocoa Beans§6 Fortune§7» — а там §6 красит ХАРАКТЕРИСТИКУ
«Cocoa Beans Fortune», которая ДЛИННЕЕ имени, и перенос ломает разметку.
Вид A требует, чтобы внутренний код возвращал к ТЕЛУ, вид B — чтобы возврат
к телу стоял сразу ЗА именем. Тогда выделение целиком лежит внутри имени,
и двигать его границу безопасно.

⚠️ ГРАНИЦА: тело считается по КУСКАМ (как `ParagraphColors.body`), и в
перечне «§aA§7, §aB§7, §aC§7» телом выходит ЗЕЛЁНЫЙ — цветных кусков там
больше, чем серых разделителей. Такие строки инструмент не трогает вовсе:
«§aDerelict§7 §aAshe§7» остаётся как есть. На экране это почти незаметно
(оба слова цветные, серым только пробел), а усложнять признак дороже.

⚠️ ТЕКСТ МЕНЯТЬСЯ НЕ СМЕЕТ: после каждой правки строка без кодов сверяется
со старой знак в знак, иначе правка не применяется вовсе.

    python tools/fix_split_name_colors.py          сухой прогон
    python tools/fix_split_name_colors.py --yes    применить
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import unicodedata

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
WORK = ROOT / "data" / "work"

COLOR = set("0123456789abcdef")
BODY_CODES = ("7", "8")  # ничья в пользу серого — как в ParagraphColors.body

# ⚠️ Файлы перечислены ИМЕНОВАННО, а не собраны глобом: в data/work лежат
# и скачанные данные, и разобранные пачки, и планки сторожей. «Что здесь
# перевод» из имени файла не выводится — проект на этом уже попадался.
SOURCES: list[tuple[str, str]] = [
    ("paragraphs.json", "корпус абзацев"),
    ("full_paragraphs_ru.json", "режимные абзацы"),
    ("from_game.json", "очередь строк"),
    ("queue_archive.json", "архив очереди"),
    ("full_strings.json", "режимные строки"),
    ("nametags.json", "надписи над головой"),
    ("buttons.json", "кнопки и экраны"),
    ("npc_dialogues.json", "реплики NPC"),
    ("lore_blocks.json", "блоки лора"),
    ("menu_paragraphs.json", "абзацы меню"),
]

# карты переводов: ключ английский, значение русское
VALUE_MAPS = {"exact", "strings", "ru", "glossary"}
MIN_WORDS = 2  # имя из одного слова разорвать нельзя по построению

# ⚠⚠ ОБЁРТКА — НЕ ИМЯ. В каталоге лежат развёрнутые формы со счётчиком
# стопки («Cobblestone x{n}») — их заводит expand_seen_forms. Граница такого
# «имени» захватывает счётчик, и здоровая разметка «§aEnchanted Cobblestone§8 x{n}»
# объявлялась оборванной. Дырка в имени — верный признак обёртки.
HOLE = re.compile(r"\{[nsi]\d*\}")

# ⚠ ЗВЁЗДЫ ПРОКАЧКИ И ЗНАЧОК КОСМЕТИКИ — ТОЖЕ ОБЁРТКА (538 имён
# в каталоге). Их снимает `Reforge.compose` по NBT, а цвет у звёзд СВОЙ:
# в «§dRenowned Superior Dragon Helmet§8 ✦» серая звезда законна, а правка
# покрасила бы её в цвет имени.
def _has_icon(name: str) -> bool:
    return any(unicodedata.category(ch) == "So" or 0xE000 <= ord(ch) <= 0xF8FF for ch in name)


def known_names() -> dict[str, list[str]]:
    """Имена, у которых цвет ЗНАЧИТ «имя»: каталог сервера + защищённые."""
    sys.path.insert(0, str(HERE))
    import protected  # noqa: PLC0415  (круговой импорт, поэтому лениво)

    names: set[str] = set()
    for name in protected.real_items():
        if len(name.split()) >= MIN_WORDS and not HOLE.search(name) and not _has_icon(name):
            names.add(name)
    for group, words in protected.collect_groups().items():
        if group in ("currency", "stat"):
            continue
        for word in words:
            if len(word.split()) >= MIN_WORDS and not _has_icon(word):
                names.add(word)
    by_first: dict[str, list[str]] = {}
    for name in names:
        by_first.setdefault(name.split()[0], []).append(name)
    # длинные вперёд: «Enchanted Hopper» раньше «Hopper»
    for key in by_first:
        by_first[key].sort(key=len, reverse=True)
    return by_first


def strip_codes(text: str) -> tuple[str, list[list]]:
    """Чистый текст и коды: [позиция в ЧИСТОМ тексте, код]."""
    plain: list[str] = []
    codes: list[list] = []
    i = 0
    while i < len(text):
        if text[i] == "§" and i + 1 < len(text):
            codes.append([len(plain), text[i + 1]])
            i += 2
            continue
        plain.append(text[i])
        i += 1
    return "".join(plain), codes


def rebuild(plain: str, codes: list[list]) -> str:
    by_pos: dict[int, list[str]] = {}
    for pos, ch in codes:
        by_pos.setdefault(pos, []).append(ch)
    out: list[str] = []
    for i in range(len(plain) + 1):
        for ch in by_pos.get(i, ()):
            out.append("§" + ch)
        if i < len(plain):
            out.append(plain[i])
    return "".join(out)


def body_colour(plain: str, codes: list[list]) -> str | None:
    """Цвет ТЕЛА — тот, которым набрано больше КУСКОВ (не знаков).

    Считаем по кускам, как `ParagraphColors.body`: длинная подсветка иначе
    перетягивает тело на себя. Ничья — в пользу серого.
    """
    colours = [(p, c) for p, c in codes if c in COLOR]
    if not colours:
        return None
    count: collections.Counter[str] = collections.Counter()
    for i, (pos, ch) in enumerate(colours):
        end = colours[i + 1][0] if i + 1 < len(colours) else len(plain)
        if plain[pos:end].strip():
            count[ch] += 1
    if not count:
        return None
    best = max(count.values())
    winners = [c for c, n in count.items() if n == best]
    for grey in BODY_CODES:
        if grey in winners:
            return grey
    return winners[0]


def colour_at(codes: list[list], pos: int) -> str | None:
    """Какой цвет действует непосредственно ПЕРЕД позицией pos."""
    seen = None
    for p, ch in codes:
        if p > pos:
            break
        if ch in COLOR:
            seen = ch
    return seen


def repair(text: str, by_first: dict[str, list[str]]) -> tuple[str, list[str]]:
    if "§" not in text:
        return text, []

    fixed: list[str] = []
    for _ in range(20):  # имён в строке бывает несколько
        plain, codes = strip_codes(text)
        body = body_colour(plain, codes)
        if body is None:
            break
        moved = None
        for word, group in by_first.items():
            at = 0
            while True:
                at = plain.find(word, at)
                if at < 0:
                    break
                here = at
                at += 1
                if here and (plain[here - 1].isalnum() or plain[here - 1] == "'"):
                    continue
                for name in group:
                    if not plain.startswith(name, here):
                        continue
                    end = here + len(name)
                    if end < len(plain) and (plain[end].isalnum() or plain[end] == "'"):
                        continue
                    inner = [c for c in codes if here < c[0] < end and c[1] in COLOR]
                    if not inner:
                        continue
                    before = colour_at(codes, here)
                    inside = inner[0][1]
                    # ⚠️ ИМЯ РВЁТСЯ И НА ТРИ КУСКА: «Golden §5Dragon§7 §5Egg§7».
                    # Тогда внутри чередуются ровно два цвета — тело и цвет
                    # имени, — и убрать надо ВСЕ внутренние коды, а не первый.
                    tones = {c[1] for c in inner}
                    if len(inner) > 1 and (len(tones) != 2 or body not in tones):
                        continue
                    if before == inside:
                        continue
                    if before is not None and before != body and inside == body:
                        if tones - {body, before}:
                            continue
                        # A: выделение закрылось рано — уносим возврат ЗА имя
                        moved = (inner, end, None)
                    elif before == body and inside != body:
                        # B: выделение открылось поздно — но только если оно
                        # кончается вместе с именем, иначе красит и хвост
                        after = [c for c in codes if c[0] >= end and c[1] in COLOR]
                        if not after or after[0][0] != end or after[0][1] != body:
                            continue
                        if tones - {body, inside}:
                            continue
                        moved = (inner, here, inside)
                    if moved:
                        break
                if moved:
                    break
            if moved:
                break
        if not moved:
            break
        group_codes, target, opening = moved
        rest = [c for c in codes if all(c is not g for g in group_codes)]
        if opening is None:
            rest.append([target, group_codes[0][1]])  # A: возврат к телу — за имя
        else:
            rest.append([target, opening])  # B: цвет имени — в начало имени
        rest.sort(key=lambda c: c[0])
        # два одинаковых кода подряд — лишний: убираем, чтобы не копить мусор
        clean: list[list] = []
        for code in rest:
            if clean and clean[-1][0] == code[0] and clean[-1][1] == code[1]:
                continue
            clean.append(code)
        rest = clean
        new = rebuild(plain, rest)
        if strip_codes(new)[0] != plain:  # текст меняться не смеет
            break
        if new == text:
            break
        text = new
        fixed.append(name)
    return text, fixed


def walk(node, by_first, hits: list[tuple[str, str]], key_name: str = ""):
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(key, str) and key.startswith("_"):
                continue
            if key == "ru" and isinstance(value, str):
                new, fixed = repair(value, by_first)
                if fixed:
                    hits.append((value, new))
                    node[key] = new
            elif key in VALUE_MAPS and isinstance(value, dict):
                for sub, text in list(value.items()):
                    if not isinstance(text, str):
                        continue
                    new, fixed = repair(text, by_first)
                    if fixed:
                        hits.append((text, new))
                        value[sub] = new
            elif isinstance(value, (dict, list)):
                walk(value, by_first, hits, key)
    elif isinstance(node, list):
        for value in node:
            if isinstance(value, (dict, list)):
                walk(value, by_first, hits, key_name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="применить (по умолчанию сухой прогон)")
    ap.add_argument("--show", type=int, default=6, help="сколько примеров печатать")
    args = ap.parse_args()

    by_first = known_names()
    print(f"имён для сверки: {sum(len(v) for v in by_first.values())}")

    total = 0
    for fname, title in SOURCES:
        path = WORK / fname
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        hits: list[tuple[str, str]] = []
        walk(data, by_first, hits)
        if not hits:
            print(f"  {title:22} чисто")
            continue
        total += len(hits)
        print(f"  {title:22} починено {len(hits)}")
        for was, now in hits[: args.show]:
            print(f"      было : {was[:120]}")
            print(f"      стало: {now[:120]}")
        if args.yes:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nвсего мест: {total}")
    if not args.yes:
        print("СУХОЙ ПРОГОН. Применить: --yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
