"""
Раскладывает переведённые подсказки обратно в словарь мода.

Блок переведён целиком, а движок ищет перевод построчно — значит блок надо
разобрать на пары «строка → перевод».

⚠️ Одна и та же строка встречается у разных предметов и может быть переведена
по-разному. Словарь такую вилку выразить не может, поэтому берётся вариант,
который встретился ЧАЩЕ. Спорные случаи выводятся списком — их стоит посмотреть.

Запуск:
  python tools/merge_tooltips.py lore_tooltips.json
  python tools/merge_tooltips.py tooltips.json --out 95-tooltips.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import packs as packlib  # noqa: E402
from make_queue import covered_by_rule  # noqa: E402

WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# Словари разложены по языкам: packs/<язык>/. Скрипты этого проекта делают
# русский, поэтому пишут сюда. Для другого языка — поменять одну строку.
LANG = "ru_ru"
INDEX = PACKS / "index.json"


def coloured_rules() -> list[re.Pattern]:
    """
    Правила ВКЛЮЧЁННЫХ словарей, замена которых несёт §-коды.

    ⚠️ Зачем. Движок ищет ТОЧНУЮ ЗАПИСЬ раньше правил и перебивает их
    независимо от priority. Значит плоская запись, попавшая сюда, гасит
    размеченное правило — и подсветка пропадает молча: строка-то переведена.

    Живой случай: «❣ Requires Combat Skill 20.» Hypixel красит тремя цветами
    (зелёным — сам навык), правило это умеет, а запись из 95-tooltips была
    плоской и побеждала. `preview.py --broken` показал «цвета стало МЕНЬШЕ:
    green», а `status.py` — что перевод берётся из 95-tooltips.json.

    Поэтому строку, которую закрывает РАЗМЕЧЕННОЕ правило, сюда не берём:
    правило и переведёт, и покрасит.
    """
    out: list[re.Pattern] = []
    for pack in packlib.load(include_disabled=False):
        for rule in pack.regex:
            replacement = rule.get("r") or ""
            if "§" not in replacement or not rule.get("p"):
                continue
            try:
                out.append(re.compile(rule["p"]))
            except re.error:
                continue
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Перенос переведённых подсказок в словарь")
    parser.add_argument("file", help="имя файла в data/work или полный путь")
    parser.add_argument("--out", default="95-tooltips.json", help="имя словаря в packs/")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = WORK / path if (WORK / path).exists() else Path(args.file)
    if not path.exists():
        print(f"нет файла: {path}")
        return 1

    blocks = json.loads(path.read_text(encoding="utf-8")).get("tooltips") or []
    translated = [b for b in blocks if b.get("ru")]
    print(f"блоков переведено: {len(translated)} из {len(blocks)}")
    if not translated:
        return 1

    variants: dict[str, Counter] = defaultdict(Counter)
    # кто как перевёл: строка -> перевод -> список предметов
    owners: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for block in translated:
        lines, ru = block["lines"], block["ru"]
        if len(lines) != len(ru):
            continue
        for source, target in zip(lines, ru):
            source, target = source.strip(), target.strip()
            # пустые строки — это отступы, переводить нечего
            if not source or not target or source == target:
                continue
            variants[source][target] += 1
            owners[source][target].append(block.get("item") or "")

    exact: dict[str, str] = {}
    by_item: dict[str, dict[str, str]] = defaultdict(dict)
    disputed = []

    # ⚠️ Характеристики-жаргон сюда не пускаем: их перевод живёт в переключаемом
    # sb_stats, а этот словарь включён всегда. Иначе выключатель не работает —
    # ровно та утечка, что уже была с зачарованием «Lapidary V». Проверять надо
    # КАЖДЫЙ генератор, который переносит переводы в общий словарь.
    import re as _re
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    import terms as _terms
    jargon = _terms.of("stat_jargon")

    def has_jargon(text: str) -> bool:
        return any(_re.search(r"(?<![A-Za-z])" + _re.escape(name) + r"(?![A-Za-z])", text)
                   for name in jargon)

    skipped_jargon = 0
    skipped_coloured = 0
    coloured = coloured_rules()

    for source, options in variants.items():
        best, _ = options.most_common(1)[0]
        if has_jargon(source):
            skipped_jargon += 1
            continue
        # ⚠️ Строку закрывает РАЗМЕЧЕННОЕ правило — плоская запись только
        # погасила бы подсветку, потому что exact ищется раньше правил.
        #
        # ⚠️ Сверяем через `covered_by_rule`, а не своим `match`: в словаре
        # строка лежит ОБОБЩЁННОЙ («Skill {n}.»), а правила писаны под живую
        # («Skill ([\d,]+)»), и прямое сравнение не совпадает НИКОГДА. Эту
        # задачу проект уже решил один раз — подставить в дырки правдоподобное
        # число; второй копии признака здесь заводить нельзя.
        if "§" not in best and covered_by_rule(source, coloured):
            skipped_coloured += 1
            continue
        exact[source] = best
        if len(options) == 1:
            continue
        disputed.append((source, options))
        # Расхождение — не повод терять вариант: меньшинство уходит в привязку
        # к конкретному предмету и побьёт общий перевод именно у него.
        for target, items in owners[source].items():
            if target == best:
                continue
            for item in items:
                if item:
                    by_item[item][source] = target

    if skipped_jargon:
        print(f"не взято (характеристики-жаргон, их место в sb_stats): {skipped_jargon}")
    if skipped_coloured:
        print(f"не взято (закрыто РАЗМЕЧЕННЫМ правилом, плоская запись "
              f"погасила бы цвет): {skipped_coloured}")

    out = PACKS / LANG / args.out
    pack = {
        "id": "tooltips",
        "priority": 22,
        "_comment": "Переводы подсказок, разобранные на строки. Собирается автоматически "
                    "из блоков — правь рабочий файл, а не этот. "
                    "byItem — переводы, привязанные к предмету: они побеждают общий словарь "
                    "там, где одна и та же строка у разных предметов значит разное.",
        "exact": exact,
    }
    if by_item:
        pack["byItem"] = {k: v for k, v in by_item.items()}
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    # index.json теперь разложен по языкам: common — языконезависимые,
    # languages.<язык> — перевод. Файл мимо списка мод не загрузит.
    listing = index.setdefault("languages", {}).setdefault(LANG, [])
    if out.name not in listing:
        listing.append(out.name)
        listing.sort()
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"добавил {out.name} в index.json")

    print(f"строк в словаре: {len(exact)}")
    if by_item:
        personal = sum(len(v) for v in by_item.values())
        print(f"привязано к предметам: {personal} строк у {len(by_item)} предметов")
    if disputed:
        print(f"\nстрок с разными переводами: {len(disputed)} — общий вариант самый частый, "
              f"остальные привязаны к своим предметам")
        for source, options in disputed[:10]:
            variants_text = "  |  ".join(f"{t} ({c})" for t, c in options.most_common(3))
            print(f"  {source[:44]!r}")
            print(f"      {variants_text}")
    print(f"\nзаписано: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
