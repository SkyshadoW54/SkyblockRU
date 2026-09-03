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
