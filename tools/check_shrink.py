# -*- coding: utf-8 -*-
"""
СЛОВАРЬ ВДРУГ ПОХУДЕЛ — не потерялся ли перевод при пересборке.

Беда, ради которой написано. В проекте ТРИ случая подряд, и все три поймала
не проверка, а сверка чисел руками:

  * круг `gen_checklist` и корпуса съел 55 переводов;
  * `export_pack` молча урезал `90-from-game` на 44 записи;
  * 24.08 корпус абзацев потерял 1860 переводов, и `merge_paragraphs`
    честно отразил это в словаре: 8605 -> 6745. Проверка движком показала,
    что 1733 строки перестали переводиться ВООБЩЕ.

Признак беды один и тот же: генератор читает то, что сам же вытесняет, либо
пересобирается из источника, который успел усохнуть. Ошибки при этом нет,
файл на месте, сборка зелёная — просто на экране снова английский.

⚠️ ЭТАЛОН — СОБРАННЫЙ JAR, а не снимок в отдельном файле. Причин две:
jar есть всегда и не требует, чтобы кто-то помнил про `--save`; и он отвечает
ровно на нужный вопрос — «что работало у игрока до этой правки». Снимок же
устаревает молча, а забытый `--save` превращает сторожа в вечно красного.

⚠️ ПАДЕНИЕ ЧИСЛА — ЕЩЁ НЕ ПОТЕРЯ, и без этой оговорки сторож шумел бы.
24.08 `41-headers` законно похудел с 1503 до 1428: все 101 выпавшая запись
оказались дублями, закрытыми `70-enchants`. Поэтому по каждому выпавшему
ключу СПРАШИВАЕМ ДВИЖОК — переводится ли он ещё хоть чем-нибудь. Красным
считается только то, где перевод пропал.

⚠️ Рост словаря беды не значит и не проверяется вовсе.

Запуск:
    python tools/check_shrink.py
    python tools/check_shrink.py --show 40    сколько потерянных показать
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
VERSIONS = ROOT / "versions"
INSIDE = "assets/skyblockru/packs/"

# Секции, где лежат переводы. `regex` сверяем отдельно: там список правил,
# а не пары «ключ — перевод».
SECTIONS = ("exact", "paragraphs", "glossary", "byItem")

# Подстановка, которой движок не знает: «{STRENGTH}», «{FARMING_FORTUNE}».
# Наши — только {n} и {s}.
# ⚠️ МАСКА ЗНАЧКА «{i1}» — тоже недостижимый ключ. Она живёт только в ВЫГРУЗКЕ
# на ручной перевод: значки Hypixel лежат в приватной зоне юникода, из терминала
# копируются пробелом, и перед вливанием маска обязана смениться настоящим
# значком. Не сменилась — запись мертва, на экране такой строки не бывает.
# 26.08 одна такая нашлась в `04-full-strings`; её уборка — не потеря,
# и сторож не должен звать это пропавшим переводом.
import re as _re
CYR = _re.compile("[а-яА-ЯёЁ]")
UNREACHABLE = _re.compile(r"\{(?![ns]\})[A-Za-z_0-9]+\}")


def plain(text: str) -> str:
    """Текст без §-кодов — сравнивать надо его, а не сырую строку."""
    return _re.sub("§.", "", str(text)).strip()


def newest_jar() -> Path | None:
    """
    Самый свежий собранный jar. Версию в имени НЕ зашиваем: записанная грабля
    проекта — после первого же `--bump` такой поиск молча перестаёт работать.
    """
    jars = sorted(VERSIONS.glob("*/build/libs/*.jar"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    return jars[0] if jars else None


def packs_from_jar(jar: Path) -> dict[str, dict]:
    """Словари, лежащие в jar: имя файла -> разобранный json."""
    out: dict[str, dict] = {}
    with zipfile.ZipFile(jar) as zf:
        for name in zf.namelist():
            if not name.startswith(INSIDE) or not name.endswith(".json"):
                continue
            if name.endswith("index.json"):
                continue
            try:
                out[Path(name).name] = json.loads(zf.read(name).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return out


def packs_from_source() -> dict[str, dict]:
    """Те же словари, но из исходников — то, что уедет в следующий jar."""
    out: dict[str, dict] = {}
    for path in PACKS.rglob("*.json"):
        if path.name == "index.json":
            continue
        try:
            out[path.name] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def area_of(pack: dict) -> str | None:
    """
    Первая область словаря — с ней и спрашиваем движок.

    ⚠️ Спрашивать БЕЗ области нельзя: `status.lookup` тогда не проверяет
    `only` вовсе, и запись, до которой мод не дотянется, засчиталась бы
    живой. А спрашивать с чужой областью — наоборот, назвать потерей то,
    что работает в своём месте.
    """
    only = pack.get("only")
    return only[0] if isinstance(only, list) and only else None


_DECIDED: set[str] = set()


def decided_keys() -> set[str]:
    """Ключи, помеченные «переводить нечего» в рабочих файлах.

    ⚠️ Пометка живёт в ИСТОЧНИКЕ (`data/work/*.json`), а не в собранном
    словаре — туда `_asis` не пишется вовсе. Ровно на этом 28.08 оказалась
    мёртвой такая же защита в `export_pack.rescue`.
    """
    if not _DECIDED:
        work = ROOT / "data" / "work"
        for path in work.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                _DECIDED.update(str(k) for k in (data.get("_asis") or ()))
    return _DECIDED


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Не похудел ли словарь")
    parser.add_argument("--show", type=int, default=15, help="сколько строк показать")
    args = parser.parse_args()

    jar = newest_jar()
    if jar is None:
        print("нет собранного jar — сравнивать не с чем, пропускаю")
        return 0
    print(f"эталон: {jar.relative_to(ROOT)}")

    was, now = packs_from_jar(jar), packs_from_source()
    if not was:
        print("в jar нет словарей — сравнивать нечем")
        return 0

    import status
    # ⚠️ Ленивый импорт, как у соседей: check_hole_rules сам тянет status.
    from check_hole_rules import live_line
    dic = full = None
    shrunk: list[tuple[str, str, int, int]] = []
    lost: list[tuple[str, str]] = []
    only_full: list[tuple[str, str, str]] = []
    weakened: list[tuple[str, str, str]] = []

    for name, before in sorted(was.items()):
        after = now.get(name)
        if after is None:
            print(f"⚠️ СЛОВАРЬ ИСЧЕЗ из исходников: {name}")
            lost.append((name, "<весь словарь>"))
            continue
        for section in SECTIONS:
            old = before.get(section) or {}
            new = after.get(section) or {}
            if not isinstance(old, dict) or not isinstance(new, dict):
                continue
            gone = [k for k in old if k not in new]
            # ⚠️ У РЕЖИМНОГО словаря «переводится» — НЕ ТО ЖЕ, что «переводится
            # ПО-РЕЖИМНОМУ». Режимная версия отличается от обычной одним
            # термином; выпадет она — движок молча подставит обычную, и на
            # экране снова «Angler IV» вместо «Рыболов IV». Сторож при этом
            # честно скажет «переводится» и промолчит. 26.08 так выпали
            # 173 абзаца из `86-full-paragraphs`, и заметить это удалось
            # только сверкой ТЕКСТА с последним jar.
            if after.get("group") == "full":
                # ⚠️ ЖАЛУЕМСЯ, ТОЛЬКО ЕСЛИ РЕЖИМ И ПРАВДА ОСЛАБ. Запись
                # выпадает и по замыслу: ручной перевод полнее машинной
                # подстановки, и генератор ему уступает («дружок Blacksmith
                # из Village» -> «дружок Кузнеца из Деревни»). Спрашиваем
                # движок С РЕЖИМОМ: даёт ли кто-то другой русский текст.
                # Без этого сторож краснел на 29 записях, где стало ЛУЧШЕ.
                if full is None:
                    full = status.Dictionaries(groups={"full"})
                for key in gone:
                    got = status.lookup(key, full, origin=(after.get("only") or [None])[0])
                    if got and (CYR.search(got[0] or "") or "@" in (got[0] or "")):
                        continue
                    weakened.append((name, key, old[key]))
            if not gone:
                continue
            shrunk.append((name, section, len(old), len(new)))
            if dic is None:
                dic = status.Dictionaries()
                # ⚠️ Спрашиваем ОБА режима. Строка, намеренно убранная из
                # обычного словаря в режимный (так поступают с именами
                # предметов), переводится только при включённом `full` —
                # и без этого опроса сторож звал бы её потерянной.
                full = status.Dictionaries(groups={"full"})
            origin = area_of(after)
            for key in gone:
                # ⚠️ Ключ с ЧУЖОЙ подстановкой недостижим по построению:
                # движок знает только {n} и {s}, а «Strength: +{STRENGTH}» —
                # это шаблон NEU, и на экране на его месте живое число.
                # Такая запись не переводила НИЧЕГО и в jar — снимать её
                # не потеря, а уборка мусора.
                if UNREACHABLE.search(key):
                    continue
                # ⚠️ ТОЖДЕСТВЕННАЯ ЗАПИСЬ ПЕРЕВОДОМ НЕ БЫЛА — снять её
                # не потеря. Записанное правило проекта («она означает
                # решение оставить как есть»), нарушенное здесь: сторож
                # спрашивал «вернул ли lookup непустое», а тождественная
                # запись возвращает саму строку. 27.08 он объявил потерей
                # 12 таких записей `41-headers`, снятых ОСОЗНАННО, — при том
                # что резка не изменилась ни на одну подсказку (проверено
                # настоящей Java: check_sections 45/45, check_list_cuts
                # 313/888, числа ДО и ПОСЛЕ совпали до знака).
                #
                # Признак узкий: смотрим ЗНАЧЕНИЕ В JAR, а не в исходниках.
                # Настоящая потеря («Peasant's Bonus» -> «Крестьянский
                # бонус») по-прежнему находится — там значение не равно ключу.
                if plain(old[key]) == plain(key):
                    continue
                # ⚠️ АБЗАЦНЫЙ ПУТЬ — ТОЖЕ ПЕРЕВОД, и `lookup` его не видит:
                # он повторяет ПОСТРОЧНЫЙ поиск движка, а склеенный абзац
                # мод ищет отдельно (`Translator.lookupParagraph`).
                #
                # Без этой оговорки сторож объявил потерей 2374 ключа, снятых
                # ОСОЗНАННО: `96-paragraphs` держал каждый абзац дважды —
                # в `paragraphs` и в `exact`, — и порог длины убрал из второй
                # секции то, что целой строкой не приходит никогда (замер по
                # 60 606 живым строкам: максимум 64 знака).
                if key in dic.paragraphs:
                    continue
                # ⚠️ «ПЕРЕВОДИТЬ НЕЧЕГО» — ЭТО РЕШЕНИЕ, А НЕ ПОТЕРЯ. Запись,
                # помеченную `_asis` в рабочем файле, мы убрали ОСОЗНАННО:
                # на экране она и должна остаться английской. 28.08 сторож
                # объявил потерей `Combat`, `Lapis`, `Redstone`, `Superpairs`,
                # снятые по решению игрока, и заблокировал круг сборки.
                if key in decided_keys():
                    continue
                hit = status.lookup(key, dic, origin=origin)
                if hit and hit[0]:
                    continue
                in_full = status.lookup(key, full, origin=origin)
                if in_full and in_full[0]:
                    only_full.append((name, key, in_full[1]))
                    continue
                lost.append((name, key))
        # ⚠️ ПРАВИЛА ТОЖЕ СПРАШИВАЕМ У ДВИЖКА, а не считаем по числу.
        #
        # Раньше здесь стояло только сравнение количеств, и вывод «ПОТЕРЬ НЕТ»
        # относился к `exact`/`glossary`/`paragraphs` — про `regex` сторож
        # молчал по построению. 26.08 из `76-enchant-names` выпали 7 подписей
        # («Enchanting:», «Difficulty:», «Dungeon:», «Boss:», «Combat:»),
        # пять перестали переводиться ВООБЩЕ, а сторож напечатал «потерь нет».
        # Записанная семья бед проекта: сторож отвечает на СВОЙ вопрос.
        #
        # У правила нет ключа, зато из шаблона строится ЖИВАЯ строка — тем же
        # `check_hole_rules.sample`, что уже проверен на дырках. Копии не
        # держим: разошлись бы при первой правке разбора.
        old_by_pattern = {r.get("p"): r for r in (before.get("regex") or []) if r.get("p")}
        new_patterns = {r.get("p") for r in (after.get("regex") or [])}
        vanished = [p for p in old_by_pattern if p not in new_patterns]
        if vanished:
            shrunk.append((name, "regex", len(old_by_pattern), len(new_patterns)))
            if dic is None:
                dic = status.Dictionaries()
                full = status.Dictionaries(groups={"full"})
            origin = area_of(after)
            for pattern in vanished:
                line = live_line(pattern)
                # Шаблон, из которого живой строки не построить (сложные
                # классы, просмотры), пропускаем: судить о нём нечем.
                if not line:
                    continue
                hit = status.lookup(line, dic, origin=origin)
                if hit and hit[0]:
                    continue
                in_full = status.lookup(line, full, origin=origin)
                if in_full and in_full[0]:
                    only_full.append((name, line, in_full[1]))
                    continue
                lost.append((name, line))

    if shrunk:
        # ⚠️ Заголовок про КЛЮЧИ, а не про размер: словарь может
        # вырасти целиком и всё же потерять запись — так и было 24.08
        # (946 -> 1197 при двух выпавших ключах).
        print("\n=== ИЗ СЛОВАРЕЙ ВЫПАЛИ КЛЮЧИ ===")
        for name, section, old, new in shrunk:
            print(f"  {name:28} {section:11} {old} -> {new}")
    else:
        print("\nни один ключ не выпал")

    if weakened:
        print("")
        print(f"=== ⚠️ РЕЖИМ ОСЛАБ: {len(weakened)} ===")
        print("  Записи выпали из РЕЖИМНОГО словаря. Они, может быть,")
        print("  и переводятся — но ОБЫЧНОЙ версией, то есть в режиме")
        print("  на экране снова английский термин.")
        by_pack: dict[str, int] = {}
        for name, _, _ in weakened:
            by_pack[name] = by_pack.get(name, 0) + 1
        for name, count in sorted(by_pack.items(), key=lambda x: -x[1]):
            print(f"    {count:6}  {name}")
        for name, key, was_text in weakened[:args.show]:
            print(f"    {key[:70]}")
            print(f"        было: {was_text[:70]}")
    if not lost:
        if weakened:
            return 1
        print("\nПОТЕРЬ НЕТ: всё выпавшее по-прежнему переводится "
              "(дубли и переезды между словарями — это норма)")
        return 0

    print(f"\n=== ⚠️ ПЕРЕВОД ПРОПАЛ: {len(lost)} ===")
    print("  Эти строки переводились в собранном jar, а теперь их не переводит")
    print("  НИ ОДИН словарь. Скорее всего пересборка съела источник.")
    by_pack: dict[str, int] = {}
    for name, _ in lost:
        by_pack[name] = by_pack.get(name, 0) + 1
    for name, count in sorted(by_pack.items(), key=lambda x: -x[1]):
        print(f"    {count:6}  {name}")
    print()
    for name, key in lost[:args.show]:
        print(f"    {key[:90]}")
    if len(lost) > args.show:
        print(f"    ... ещё {len(lost) - args.show}")
    print("\n  Вернуть можно из этого же jar — там перевод ещё лежит.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
