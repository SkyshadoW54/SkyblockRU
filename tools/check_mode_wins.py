# -*- coding: utf-8 -*-
"""Режимный перевод обязан ПОБЕЖДАТЬ обычный. Иначе работа не видна.

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ СТОРОЖ. Все прежние спрашивают, ЕСТЬ ли перевод:
`check_shrink` — не пропал ли, `check_full_mode` — не гасит ли тождественная
запись, `check_corpus_lag` — переживёт ли пересборку. А беда 28.08 была иной:
перевод есть, он русский, на экране виден — просто НЕ ТОТ.

    режим: «Способность: Cropshot Даёт +{n}☘ к Удаче фермера»
    видно: «Способность: Cropshot Даёт +{n}☘ к Farming Fortune»

У корпуса короткие абзацы продублированы в секции `exact`, а `exact` движок
ищет РАНЬШЕ абзацев — независимо от priority секции `paragraphs`. У режимного
словаря своей `exact` не было, и обычный выигрывал ВСЕГДА: 945 абзацев
из 1298 (73% работы) не показывались НИКОГДА. Нашёл игрок скриншотом.

Проверяемое свойство: для каждой записи режимного словаря движок с включённым
режимом обязан вернуть ИМЕННО ЕЁ. Спрашиваем движок, а не считаем приоритеты
руками: копия арифметики приоритетов разошлась бы с ним при первой правке.

Запуск:
  python tools/check_mode_wins.py
"""
from __future__ import annotations


import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import status  # noqa: E402

# консоль Windows — cp1251: без этого печать значка роняет сторожа
# ровно тогда, когда он НАШЁЛ беду (записанная грабля проекта)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "ru_ru"
CODES = re.compile("§.")
CYR = re.compile("[а-яА-ЯёЁ]")


def mode_packs() -> list[Path]:
    """Словари режима: их и проверяем."""
    out = []
    for path in sorted(PACKS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("group") == "full":
            out.append(path)
    return out


def bare(text: str) -> str:
    return CODES.sub("", text).strip()


def losers(path: Path, dic) -> list[tuple[str, str, str, str]]:
    """Записи словаря, которые движок НЕ отдаёт: кто-то победил."""
    data = json.loads(path.read_text(encoding="utf-8"))
    origins = data.get("only") or [None]
    origin = origins[0]
    bad = []
    for section in ("exact", "paragraphs"):
        for key, mine in (data.get(section) or {}).items():
            if section == "paragraphs":
                # ⚠️ У АБЗАЦА СВОЙ ПУТЬ. Мод склеивает строки и зовёт
                # lookupParagraph — там только карта `paragraphs`, без правил
                # и глоссария. Спрашивать построчный lookup значило бы ловить
                # правило из 40-lore и звать бедой то, чего в игре не будет.
                got = dic.paragraphs.get(key)
                if not got:
                    continue
                got = (got[0], got[1]) if isinstance(got, tuple) else (got, "?")
            else:
                got = status.lookup(key, dic, origin=origin)
                if not got:
                    continue
            # ⚠️ Сравниваем БЕЗ §-кодов: разметка бывает разной у одного текста,
            # и краснеть на ней значило бы краснеть вечно.
            if bare(got[0]) == bare(mine):
                continue
            # ⚠️ Проигрыш ЧУЖОМУ РЕЖИМНОМУ словарю — не беда: у режима
            # несколько словарей, и они дополняют друг друга.
            if got[1] in {p.name for p in MODE_FILES}:
                continue
            # ⚠️ ЗАКОННЫЕ ПРОИГРЫШИ — ИМЕННОЙ список, а не признак.
            # Каждый пункт подтверждён разбором блока подсказки, потому что
            # по форме строки эти случаи от беды не отличить.
            if (key, got[1]) in LEGAL:
                continue
            bad.append((key, mine, got[0], got[1]))
    return bad



# ⚠️ ЗНАЧОК КАТЕГОРИИ ПОХОЖ НА ЗНАЧОК КОСМЕТИКИ, и развёртка обёрток
# (`gen_item_names.expand_seen_forms`) заводит по нему запись в словаре ИМЁН.
# Со значком это КАТЕГОРИЯ бестиария («Enemies of this type are typically
# found in The End» — блок подсказки говорит прямо), и побеждает верный
# перевод из словаря категорий. Голый ключ при этом ЖИВОЙ: «Ender» -> «Эндер»
# отдаёт сам 81-item-names, так что удалять запись нельзя — мертва только
# форма со значком.
LEGAL = {
    ('\ue078 Ender', '42-checklist.json'),
    ('\ue082 Spooky', '46-mob-categories.json'),
}

MODE_FILES: list[Path] = []


def main() -> int:
    global MODE_FILES
    MODE_FILES = mode_packs()
    if not MODE_FILES:
        print("режимных словарей нет — проверять нечего")
        return 0
    dic = status.Dictionaries(groups={"full"})

    problems = 0
    for path in MODE_FILES:
        bad = losers(path, dic)
        print(f"{path.name}: проигрывает {len(bad)}")
        for key, mine, got, where in bad[:4]:
            print(f"   ключ : {key[:70]}")
            print(f"   режим: {bare(mine)[:70]}")
            print(f"   видно: {bare(got)[:70]}   [{where}]")
        problems += len(bad)

    # ⚠️ ПРОВЕРКА НА УМЕНИЕ НАХОДИТЬ: сторож молчит почти всегда, и без
    # подсадки «молчит» неотличимо от «ослеп».
    blind = []
    if bare("§7Даёт §6+{n}") != "Даёт +{n}":
        blind.append("§-коды снимаются неверно")
    if bare("текст") != "текст":
        blind.append("чистый текст испорчен")
    print()
    if blind:
        for line in blind:
            print("   ⚠️ " + line)
        return 1
    print("подсадка: снятие разметки проверено на 2 случаях")

    print()
    if problems:
        print(f"СЛОМАНО: {problems} режимных записей не видны — побеждает обычный перевод")
        return 1
    print("СЛОМАНО: 0 — режимный перевод побеждает везде")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
