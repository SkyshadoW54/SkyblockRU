# -*- coding: utf-8 -*-
"""Строки, которые в ПОЛНОМ режиме обязаны быть русскими, а в обычном — нет.

    python tools/gen_full_strings.py            покажет
    python tools/gen_full_strings.py --write    соберёт 04-full-strings.json

⚠️ РЕШЕНИЕ ИГРОКА 25.08: «В обычном режиме Chocolate Factory должна быть
на английском, а в full — на русском». Разделение держится не на словарях,
а на КАЖДОЙ записи, поэтому такие переводы живут ОТДЕЛЬНО и только здесь.

⚠️ PRIORITY 4 — ниже обычных словарей (`42-checklist` 5, `90-from-game` 10,
`31-buttons` 31), но выше уже занятых режимных 1–3. У `exact` побеждает
МЕНЬШИЙ: иначе тождественная запись «Chocolate Factory» -> «Chocolate Factory»
из `31-buttons` снова победит.

⚠️ Источник правды — `data/work/full_strings.json`, правится РУКАМИ.
Этот словарь автосборный: правка в нём живёт до первой пересборки.
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

SRC = ROOT / "data" / "work" / "full_strings.json"
OUT = ROOT / "src/main/resources/assets/skyblockru/packs/ru_ru/04-full-strings.json"
PACKS = ROOT / "src/main/resources/assets/skyblockru/packs"
CYR = re.compile("[а-яА-ЯёЁ]")
LATIN = re.compile(r"(?<![A-Za-z])[A-Za-z]{3,}")
ROMAN = re.compile(r"(?<![A-Za-z])[IVXLC]{1,6}(?![A-Za-z])")


# ⚠️⚠️ ПАДЕЖ ИМЕНИ МИНЬОНА ЗДЕСЬ ВЫВОДИТСЯ, и это не спорит с записанным
# правилом проекта. «Падеж машинно не выводится» верно для ЗАМЕНЫ ТЕРМИНА
# В ПРОЗЕ, где неясно, чем он управляется. А тут управляющее слово известно
# заранее — «Рецепты» требует родительного, «К» дательного, — и само имя
# построено по двум нашим же схемам:
#     «Берёзовый миньон» -> «берёзового миньона» / «берёзовому миньону»
#     «Миньон коров»     -> «миньона коров»      / «миньону коров»
# Замер 05.09: выводится у 61 базы из 61, руками не осталось ни одной.
#
# ⚠️ ПЕРЕЧИСЛЕНИЕ, А НЕ ПРАВИЛО — потому что правило с `tg` подставит захват
# в ИМЕНИТЕЛЬНОМ («К Булыжниковый миньон I»), а падеж ему взять неоткуда.
# Тот же довод, по которому в проекте перечислены рецепты навыков и питомцы.
#
# ⚠️ РАЗВОРАЧИВАЕМ СТРОГО ПО КАТАЛОГУ СЕРВЕРА: у Spider Minion максимум XI,
# и выдумывать XII нельзя — записанное правило `expand_families`.
GEN = {"ый": "ого", "ий": "его", "ой": "ого"}
DAT = {"ый": "ому", "ий": "ему", "ой": "ому"}
ADJ_MINION = re.compile(r"^(.+?)(ый|ий|ой) миньон$")


def _case(russian: str, table: dict[str, str], head: str) -> str | None:
    """Родительный или дательный по схеме имени."""
    if russian.startswith("Миньон "):
        return f"{head} " + russian[len("Миньон "):]
    found = ADJ_MINION.match(russian)
    if not found:
        return None
    return f"{found.group(1)}{table[found.group(2)]} {head}".lower()


def base_nominative(russian: str) -> str:
    """Имя миньона как оно есть — панель показывает его в именительном."""
    return russian


def minion_cases(exact: dict[str, str]) -> dict[str, str]:
    """«X Minion Recipes» и «To X Minion N» — падежные формы имени миньона."""
    names = ROOT / "data" / "work" / "item_names_ru.json"
    catalog = ROOT / "data" / "work" / "item_names.json"
    if not names.exists() or not catalog.exists():
        return {}
    bases = json.loads(names.read_text(encoding="utf-8")).get("names") or {}
    cat = json.loads(catalog.read_text(encoding="utf-8"))
    cat = cat.get("names", cat)
    known = set(cat if isinstance(cat, list) else cat.values())

    out: dict[str, str] = {}
    for english, russian in bases.items():
        if not russian or not english.endswith(" Minion"):
            continue
        russian_name = russian
        genitive = _case(russian, GEN, "миньона")
        dative = _case(russian, DAT, "миньону")
        if genitive and f"{english} Recipes" not in exact:
            out[f"{english} Recipes"] = f"Рецепты {genitive}"
        if not dative:
            continue
        for level in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII",
                      "IX", "X", "XI", "XII"):
            full = f"{english} {level}"
            if full not in known:
                continue
            if f"To {full}" not in exact:
                out[f"To {full}"] = f"К {dative} {level}"
            # ⚠️⚠️ СТРОКА ПАНЕЛИ ЦЕЛИКОМ, а не через захват правила. Правило
            # с `tg` спрашивает словарь про КОРОТКУЮ форму («Chicken II»),
            # а этот ключ ЗАНЯТ бестиарием: в `31-buttons` он значит уровень
            # существа («Курица II»), и у `exact` побеждает МЕНЬШИЙ priority.
            # Победитель забирает ключ ВМЕСТЕ СО СВОЕЙ ОБЛАСТЬЮ, поэтому
            # в табе перевода не оставалось вовсе, а на экране выходило
            # «1x Курица II» вместо «1x Миньон кур II» — замер 05.09: так
            # ломались 19 мобных миньонов из 61.
            # Полная строка спорить не с кем: такого ключа нет ни у кого.
            short = f"{english[:-len(' Minion')]} {level}"
            for word, colour, russian in (("FULL", "c", "ЗАПОЛНЕН"),
                                          ("ACTIVE", "a", "АКТИВЕН"),
                                          ("SLOW", "e", "МЕДЛЕННО"),
                                          ("BLOCKED", "c", "ЗАБЛОКИРОВАН")):
                key = "{n}x " + short + f" [{word}]"
                if key not in exact:
                    out[key] = ("§f{n}x " + f"{base_nominative(russian_name)} {level} "
                                f"§7[§{colour}{russian}§7]")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not SRC.exists():
        print("нет заготовки:", SRC)
        return 1
    rows = json.loads(SRC.read_text(encoding="utf-8")).get("strings") or {}
    exact = {k: v for k, v in rows.items() if v and v != "-"}
    exact.update(minion_cases(exact))

    # ⚠️ ПРОВЕРЯЕМ ОБА КРАЯ. Наш перевод обязан отличаться от того, что видит
    # игрок БЕЗ режима: если обычный словарь уже даёт русский, запись здесь
    # лишняя, а если даёт ДРУГОЙ русский — это разнобой на одном экране.
    plain = status.Dictionaries()
    same, clash = [], []
    for key, value in exact.items():
        found = status.lookup(key, plain, origin="item_name")
        if not found:
            continue
        text = found[0]
        if not CYR.search(text):
            continue                      # обычный режим оставляет английский — так и надо
        # ⚠️ ЧАСТИЧНО русский перевод разнобоем НЕ является, и это смысл режима.
        # «Способность: Farmer's Grace» — рамка по-русски, имя английское
        # ПО РЕШЕНИЮ; наше «Способность: Милость фермера» его не оспаривает,
        # а дополняет. Прежний признак («в обычном есть кириллица») объявлял
        # такую пару разнобоем и НЕ ДАВАЛ собрать словарь — 26.08 на этом
        # встали 4 законные записи. Настоящий разнобой — когда обычный перевод
        # русский ЦЕЛИКОМ, а мы предлагаем для того же места другие слова.
        # Римские цифры латиницей не считаются: они одинаковы в любом языке.
        if LATIN.search(ROMAN.sub("", text)):
            continue
        (same if text == value else clash).append((key, text, value))

    print(f"переводов в заготовке: {len(exact)}")
    if same:
        print(f"  ⚠️ уже переводится в ОБЫЧНОМ так же ({len(same)}) — запись лишняя:")
        for k, t, _ in same[:5]:
            print(f"      {k!r} -> {t!r}")
    if clash:
        print(f"  ⚠️ РАЗНОБОЙ с обычным режимом ({len(clash)}):")
        for k, t, v in clash[:5]:
            print(f"      {k!r}: обычный {t!r} против нашего {v!r}")
    if not args.write:
        print("\nСУХОЙ ПРОГОН. Записать: --write")
        return 0
    if clash:
        print("\nНЕ ПИШУ: сперва развести разнобой")
        return 1

    pack = {
        "id": "full_strings",
        "priority": 4,
        "default": False,
        "group": "full",
        "about": "Имена мест, предметов и валют по-русски: «Chocolate Factory» -> "
                 "«Шоколадная фабрика». Часть полного перевода.",
        "_comment": "СГЕНЕРИРОВАНО tools/gen_full_strings.py из "
                    "data/work/full_strings.json — правь ЗАГОТОВКУ. "
                    "В обычном режиме эти строки остаются английскими "
                    "по решению игрока; здесь они русские.",
        "exact": dict(sorted(exact.items())),
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано: {OUT.name} ({len(exact)} записей)")
    index = PACKS / "index.json"
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
