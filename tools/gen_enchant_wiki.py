"""
Заготовка справки по ЗАЧАРОВАНИЯМ: список имён с пустыми статьями.

⚠️ Описания сюда НЕ выдумываются. Правило проекта: факты берём из источника,
а надёжного источника на 93 зачарования у мода нет — вики отдаёт их вразнобой,
а сочинённое пояснение хуже отсутствующего, потому что выглядит достоверно.
Поэтому скрипт готовит СКЕЛЕТ, а текст вписывает человек.

Что он делает:
  * собирает имена зачарований из словарей (включая выключенный `sb_enchants` —
    справка нужна как раз для тех, что остались английскими);
  * подставляет русское название, если оно у нас уже есть;
  * СОХРАНЯЕТ уже написанные статьи — перезапуск не стирает работу.

⚠️ Последнее не мелочь. В проекте уже дважды скрипт затирал ручную работу
(`make_paragraphs` стёр переводы, `--skeleton` обнулил 41 запись в заготовке
зачарований). Правило записано в граблях: скрипт, который переписывает файл
с ручной работой, обязан сперва его прочитать.

Запуск:
  python tools/gen_enchant_wiki.py           показать, чего не хватает
  python tools/gen_enchant_wiki.py --apply   создать/дополнить файл
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
WIKI = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "wiki"
LANG = "ru_ru"
OUT = WIKI / f"enchants_{LANG}.json"

HEADER = {
    "_comment": "Справка по ЗАЧАРОВАНИЯМ SkyBlock: что делает, где взять, до какого "
                "уровня качается. Показывается по отдельной клавише (по умолчанию Alt, "
                "меняется в Настройки -> Управление -> SkyblockRU). Название зачарования "
                "остаётся английским — по нему ищут вещи на аукционе, — а пояснение даётся "
                "рядом по-русски.",
    "_format": "ключ — имя зачарования, как его пишет Hypixel (без уровня); title — русское "
               "название; color — каким цветом Hypixel красит его В ИГРЕ (blue у большинства "
               "зачарований); lines — пояснение построчно. В строках можно ставить §-коды: "
               "§7 серый, §e жёлтый, §a зелёный, §b голубой, §l жирный.",
    "_rules": "Писать так, как объяснил бы игрок игроку: сперва ЧТО делает, потом сколько "
              "и откуда берётся. Строка не длиннее ~57 знаков без §-кодов, иначе панель "
              "разъедется. Факты не выдумывать. Пустой массив lines значит «статья ещё "
              "не написана» — такие мод пропускает, они не показываются.",
}


def enchant_names() -> dict[str, str]:
    """
    Имя зачарования -> русский перевод (если он у нас есть).

    ⚠️ Список берём из РЕЕСТРА ГРУПП (`terms.of("enchant")`), а не разбором
    словарей. Реестр для того и заведён: он отвечает на вопрос «что это
    за слово» — зачарование, характеристика, имя NPC.

    Первый заход я написал разбором словарей и получил 246 «зачарований»:
    туда попали «Attack Speed», «Applied To», «Apply Cost» — это ПОДПИСИ
    характеристик, по форме («Имя + римская цифра») неотличимые от зачарований.
    Реестр их различает: у него `stat` 156 слов, `enchant` 98, и лежат они
    в разных группах.

    **Мораль ровно та, ради которой реестр и делался: две сущности, неотличимые
    ПО ФОРМЕ, нельзя делить признаком по форме — нужен источник, который знает,
    что это.** Она записана в граблях, и я всё равно полез разбирать словари.
    """
    import terms

    names = set(terms.of("enchant"))
    # ⚠️ Реестр знает только те зачарования, что мы уже встречали и завели.
    # Вики знает ВСЕ: на ней 131 против наших 98, и среди недостающих есть
    # ходовые — Bank, Cayenne, Respite, Prosperity. «Bank V» стоял на шлеме
    # у игрока, а в нашем словаре его не было вовсе.
    # Поэтому список строим ОБЪЕДИНЕНИЕМ: реестр даёт русские названия,
    # вики — полноту.
    wiki = ROOT / "data" / "work" / "enchant_wiki_en.json"
    if wiki.exists():
        try:
            names |= set(json.loads(wiki.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    russian: dict[str, str] = {}
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for rule in pack.get("regex") or []:
            match = re.match(r"\^(.+?) \(\[IVXLC\]", rule.get("p", ""))
            if not match:
                continue
            name = match.group(1).replace("\\", "").strip()
            # @ключ — ванильное зачарование, его переводит сам клиент игрока,
            # и справка по нему не нужна: игрок и так видит русское название.
            if name not in names or "@" in rule.get("r", ""):
                continue
            value = re.sub(r"\$\d|§.|,|\s+$", "", rule.get("r", "")).strip()
            if value:
                russian.setdefault(name, value)
    return {name: russian.get(name, "") for name in sorted(names)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Заготовка справки по зачарованиям")
    parser.add_argument("--apply", action="store_true", help="записать файл")
    args = parser.parse_args()

    names = enchant_names()
    print(f"зачарований SkyBlock: {len(names)}")

    # ⚠️ Сперва ЧИТАЕМ уже написанное — иначе перезапуск сотрёт статьи.
    written: dict[str, dict] = {}
    if OUT.exists():
        try:
            written = json.loads(OUT.read_text(encoding="utf-8")).get("terms") or {}
        except (json.JSONDecodeError, OSError):
            written = {}

    ready = [name for name, item in written.items() if item.get("lines")]
    print(f"статей уже написано: {len(ready)}")

    # Описания с вики: их переводим, а не выдумываем. Пока перевода нет —
    # кладём английский оригинал в отдельное поле, чтобы было видно, что
    # переводить, и чтобы факт не потерялся.
    facts: dict[str, dict] = {}
    wiki = ROOT / "data" / "work" / "enchant_wiki_en.json"
    if wiki.exists():
        try:
            facts = json.loads(wiki.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            facts = {}

    # Ванильные названия — из локализации самой игры.
    try:
        from fix_enchant_names import vanilla_pairs
        vanilla = vanilla_pairs()
    except Exception:  # noqa: BLE001 — нет ресурсов игры, не беда
        vanilla = {}

    terms: dict[str, dict] = {}
    for name in sorted(names):
        old = written.get(name) or {}
        # Готовые статьи (перевод фактов с вики) лежат отдельным файлом:
        # так их видно как текст, а не как строки внутри json.
        from enchant_articles import ARTICLES, TITLES

        # ⚠️ У ванильного зачарования русское название берём У КЛИЕНТА игрока,
        # а не придумываем: в инвентаре он видит именно его. Своё название
        # здесь разошлось бы с игрой на ровном месте.
        entry = {
            "title": old.get("title") or names[name] or vanilla.get(name)
                     or TITLES.get(name, ""),
            "color": old.get("color") or "blue",
            # ⚠️ ARTICLES ВПЕРЕДИ старого json, а не наоборот. Было
            # «old or ARTICLES», и правка статьи в `enchant_articles.py`
            # молча не доезжала: в собранном файле уже лежали непустые lines,
            # и они побеждали. Я уточнил три статьи по вики, прогнал генератор
            # и получил на выходе ровно то, что было.
            #
            # Источник правды — СКРИПТ, это записано в CLAUDE.md про все
            # генераторы. Старое значение остаётся запасным: статьи, которых
            # в `enchant_articles.py` нет, не потеряются.
            "lines": ARTICLES.get(name) or old.get("lines") or [],
        }
        fact = facts.get(name)
        if fact and fact.get("desc"):
            entry["_wiki"] = fact["desc"]
            if fact.get("source"):
                entry["_source"] = "; ".join(fact["source"])
        terms[name] = entry
    # Написанное про то, чего больше нет в словарях, тоже сохраняем: имя могло
    # уехать в другой файл, а терять текст из-за этого нельзя.
    for name, item in written.items():
        terms.setdefault(name, item)

    empty = [name for name, item in terms.items() if not item["lines"]]
    print(f"ждут описания: {len(empty)}")
    print()
    print("первые, кого стоит описать (самые ходовые):")
    for name in list(empty)[:12]:
        print(f"   {name:<22} — {terms[name]['title']}")

    if not args.apply:
        print()
        print("это СУХОЙ прогон — чтобы записать файл, добавь --apply")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({**HEADER, "terms": terms}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print()
    print(f"записано: {OUT.relative_to(ROOT)}  ({len(terms)} зачарований)")
    print("Впиши пояснения в поле lines — пустые мод пропускает.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
