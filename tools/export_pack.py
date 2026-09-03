"""
Переносит готовые переводы из рабочего файла в словарь мода.

Рабочие файлы в data/work/ содержат всё подряд, включая непереведённое.
В мод попадает только готовое: пустые записи движок и так пропустит,
но незачем раздувать ими jar.

Запуск:
  python tools/export_pack.py from_game 90-from-game.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ⚠️ Консоль Windows — cp1251, и печать русского текста роняла инструмент
# ПОСРЕДИ работы: словарь при этом оставался НЕСОБРАННЫМ, а выглядело как
# «команда отработала». Записанная грабля проекта (та же, что в try_rule).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# Словари разложены по языкам: packs/<язык>/. Скрипты этого проекта делают
# русский, поэтому пишут сюда. Для другого языка — поменять одну строку.
LANG = "ru_ru"
INDEX = PACKS / "index.json"


def rescue(target: Path, fresh: dict[str, str],
           decided: set[str] | None = None) -> dict[str, str]:
    """
    Переводы, которые есть в СЛОВАРЕ, но выпали из состава рабочего файла.

    ⚠️⚠️ БЕЗ ЭТОГО ЭКСПОРТ МОЛЧА УРЕЗАЕТ СЛОВАРЬ. Состав очереди пересобирается
    из дампа, и строка, которую игрок больше не встретил, из неё выпадает —
    а `export_pack` пишет файл ЦЕЛИКОМ из того, что в очереди сейчас. Замер
    23.08: словарь похудел с 7081 записи до 7029, и 44 перевода не давал
    больше НИКТО — на экране они стали английскими.

    ⚠️ Возвращаем НЕ ВСЁ подряд, и это главное. Из 95 выпавших 37 давал тот же
    текст другой слой (возвращать незачем), а 14 — режимный словарь имён,
    и его перевод ЛУЧШЕ («Скин Black Widow» против «Скин «Чёрная вдова»»).
    Вернуть их значило бы заглушить правку: точная запись бьёт правила
    и словари с бо́льшим priority.

    Признак поэтому один и от ДВИЖКА: возвращаем строку, только если без неё
    перевода нет ВООБЩЕ. Тогда возврат ничего не подменяет — он лишь не даёт
    потерять оплаченное.

    ⚠️ Спрашиваем движок БЕЗ этого словаря (`without`): иначе он найдёт
    ту самую запись, которую мы и проверяем, и решит, что всё хорошо.
    Записанная грабля про генератор, который читает собственный выход.
    """
    if not target.exists():
        return {}
    old = json.loads(target.read_text(encoding="utf-8")).get("exact") or {}
    orphans = {k: v for k, v in old.items() if v and not fresh.get(k)}
    # ⚠️ РЕШЕНИЕ «ПЕРЕВОДИТЬ НЕЧЕГО» ОТМЕНЯТЬ НЕЛЬЗЯ. Запись, убранную из
    # рабочего файла ОСОЗНАННО, спасение вернёт: нигде больше её нет, значит
    # по признаку она «потеря». Отличает их штатный `_asis` — та же пометка,
    # которой очередь помнит «решение принято». Поймано 23.08 на «SkyBlock
    # Gems: {n}»: валюту мы не переводим, а спасение вернуло её обратно.
    # ⚠️⚠️ ПОМЕТКА ЛЕЖИТ В ИСТОЧНИКЕ, А НЕ В СОБРАННОМ СЛОВАРЕ. Раньше здесь
    # читался `target` — а `_asis` туда не пишется вовсе, и защита была
    # МЁРТВОЙ: замер 28.08 по `31-buttons` — в словаре 0 пометок против 195
    # в источнике, то есть спасение отменяло КАЖДОЕ решение «переводить
    # нечего» при первой же пересборке. Так вернулось «Combat» -> «Бой»,
    # снятое по решению игрока.
    decided = set(decided or ())
    if decided:
        orphans = {k: v for k, v in orphans.items() if k not in decided}
    if not orphans:
        return {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import status
        dictionaries = status.Dictionaries(without={target.name})
        full = status.Dictionaries(without={target.name}, groups={"full"})
    except Exception as bad:  # словарей нет — молчать нельзя, но и падать незачем
        print(f"! не смог спросить движок ({bad}); сохраняю все {len(orphans)} выпавших")
        return orphans
    keep, covered = {}, 0
    for key, value in orphans.items():
        if status.lookup(key, dictionaries) or status.lookup(key, full):
            covered += 1
            continue
        keep[key] = value
    print(f"выпало из состава: {len(orphans)}; закрыто другими слоями: {covered}; "
          f"СОХРАНЕНО, иначе перевода не было бы: {len(keep)}")
    for key in sorted(keep)[:8]:
        print(f"    {key[:60]!r}")
    if len(keep) > 8:
        print(f"    ... ещё {len(keep) - 8}")
    return keep


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    source = WORK / f"{sys.argv[1]}.json"
    target = PACKS / LANG / sys.argv[2]

    if not source.exists():
        print(f"нет файла: {source}")
        return 1

    pack = json.loads(source.read_text(encoding="utf-8"))
    exact = {k: v for k, v in (pack.get("exact") or {}).items() if v}
    rules = [r for r in (pack.get("regex") or []) if r.get("r")]
    keep = rescue(target, exact, set(pack.get("_asis") or ()))
    exact.update(keep)

    if not exact and not rules:
        print("переводов пока нет")
        return 1

    out = {
        "id": pack.get("id", target.stem),
        "priority": pack.get("priority", 20),
        "_comment": f"Собрано в игре и переведено. Файл собирается автоматически "
                    f"из data/work/{source.name} — правь рабочий файл, а не этот.",
    }
    # ⚠️ ОБЛАСТЬ ЕДЕТ ИЗ РАБОЧЕГО ФАЙЛА. Без этого её негде задать: словарь
    # собирается автоматически, и приписанное руками сотрёт первый же прогон.
    # Заведено 23.08 под `29-nametags` — надписи над головой, которые нельзя
    # пускать в остальные области: «Same!» и «Oi» одним словом переведутся
    # где угодно, а над головой это реплика.
    if pack.get("only"):
        out["only"] = list(pack["only"])
    # ⚠️ ГРУППА И УМОЛЧАНИЕ — ТОЖЕ ИЗ РАБОЧЕГО ФАЙЛА. Без них словарь режима,
    # собранный автоматически, включался бы у всех: `default` и `group`
    # приписывать в json бесполезно, первый же прогон их сотрёт.
    for field in ("default", "group", "about"):
        if field in pack:
            out[field] = pack[field]
    if exact:
        out["exact"] = exact
    if rules:
        out["regex"] = rules
    # ⚠️ Пометка «тождественность тут ОСОЗНАННА» едет из рабочего файла.
    #
    # Запись «A to Z» -> «A to Z» выглядит мусором, но держит построчный путь:
    # Paragraphs.listed спрашивает lookup у КАЖДОЙ строки куска, и пустой ответ
    # заставляет мод разрезать абзац вместо точного построчного перевода.
    # Без переноса пометка стиралась бы при каждой пересборке, и сторож
    # снова горел бы на решении игрока (tools/fix_identity.py).
    identity = [k for k in (pack.get("_identity") or []) if k in exact]
    if identity:
        out["allowIdentity"] = sorted(identity)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    # index.json теперь разложен по языкам: common — языконезависимые,
    # languages.<язык> — перевод. Файл мимо списка мод не загрузит.
    listing = index.setdefault("languages", {}).setdefault(LANG, [])
    if target.name not in listing:
        listing.append(target.name)
        listing.sort()
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"добавил {target.name} в index.json")

    print(f"перенесено: {len(exact)} строк, {len(rules)} правил")
    print(f"записано: {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
