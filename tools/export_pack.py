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
import re
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
# Области текста, которые знает мод (поле `only` словарей и `origin` в
# Translator): спасение считает строку закрытой другим словарём, только если
# тот даёт тот же текст в КАЖДОЙ из них — иначе запись с `only` закрывала бы
# строку там, где мод её не применит.
AREAS = ("item_lore", "screen", "menu_title", "item_name", "chat", "tab",
         "action_bar", "scoreboard", "name_tag", "boss_bar", "title")


def _own_rules(rules: list[dict]) -> list:
    """Скомпилированные правила НОВОГО состава этого же словаря."""
    out = []
    for rule in rules:
        try:
            out.append(re.compile(rule["p"]))
        except re.error:
            continue  # битый шаблон — забота check_rules, не наша
    return out


def rescue(target: Path, fresh: dict[str, str],
           decided: set[str] | None = None,
           rules: list[dict] | None = None) -> dict[str, str]:
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

    ⚠️⚠️ …НО ПРАВИЛА ЭТОГО ЖЕ СЛОВАРЯ ИСКЛЮЧАТЬ НЕЛЬЗЯ, и на этом спасение
    отменило осознанную правку. `without` убирает пакет ЦЕЛИКОМ, вместе
    с его `regex`, — а правила из рабочего файла никуда не выпадают, они
    рядом. 05.09: снял 14 точных «Hey! I'm a Redstone Minion» -> «Эй! Я
    Redstone Minion», чтобы заработало СВОЁ ЖЕ правило с `tg` (в режиме оно
    переводит имя миньона), и спасение вернуло все 14 обратно: без словаря
    строка «не переводится». Поэтому правила нового состава примеряются
    отдельно.
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
    own = _own_rules(rules or [])
    keep, covered, full_only = {}, 0, 0
    # ⚠️⚠️ «ЗАКРЫТО ДРУГИМ СЛОВАРЁМ» ЗНАЧИТ «ТОТ ЖЕ ТЕКСТ, И ВО ВСЕХ ОБЛАСТЯХ»
    # (19.10). Раньше хватало любого ответа движка, и спасение выбрасывало
    # 427 записей, из них 346 — честные дубли (`42-checklist` даёт то же
    # самое), но 33 были закрыты ТОЖДЕСТВОМ (правило со стрелкой «^(.+) ([⬆…])$»
    # с `tg` без этого словаря возвращает оригинал: «Иди в Dark Thicket ⬆»
    # стало бы «Travel to the Dark Thicket ⬆») и 48 — ДРУГИМ переводом из
    # правил, слабее точного («Профиль: Nothing going on!» вместо «Профиль:
    # ничего не происходит!»). Тождественная запись переводом не считается —
    # железное правило проекта, и здесь оно не выполнялось. Плюс движок
    # спрашивался БЕЗ области, а `allows(area, None)` в status — «разрешено»:
    # запись с `only` закрывала строку и там, где мод её не применит.
    # Поэтому выбрасываем только когда ВО ВСЕХ областях мода другой словарь
    # даёт тот же самый текст (без §-кодов). Всё прочее — сохраняем.
    stripped = re.compile("§.")

    def plain(text: str) -> str:
        return stripped.sub("", text or "").strip()

    def same_everywhere(line: str, value: str) -> bool:
        want = plain(value)
        for origin in AREAS:
            got = status.lookup(line, dictionaries, origin=origin)
            if not got or plain(str(got[0])) != want:
                return False
        return True

    not_same = 0
    for key, value in orphans.items():
        if same_everywhere(key, value):
            covered += 1
            continue
        if status.lookup(key, dictionaries):
            # другой словарь что-то отвечает, но не то же самое (или не везде)
            not_same += 1
        # ⚠️⚠️ РЕЖИМ FULL НЕ ЗАКРЫВАЕТ СТРОКУ ДЛЯ ОБЫЧНЫХ ИГРОКОВ (12.10). Раньше
        # здесь стояло `or status.lookup(key, full)`, и пересборка `90-from-game`
        # после `refresh --dry` молча выкинула 1147 переводов: 736 из них давал
        # ТОЛЬКО режим, которого у людей нет, — «Забрать всё», «Указать
        # количество», «Общий бонус: …» стали бы английскими у ~100 установок.
        # Поймано сверкой чисел до/после с копией из последней сборки, не
        # сторожем. Режимная запись и так побеждает точную запись этого словаря
        # (`check_mode_wins` следит), поэтому держать обе — безопасно.
        if status.lookup(key, full):
            full_only += 1
        if any(pattern.fullmatch(probe)
               for pattern in own for probe in status.probes(key)):
            covered += 1
            continue
        keep[key] = value
    print(f"выпало из состава: {len(orphans)}; закрыто тем же текстом везде: {covered}; "
          f"СОХРАНЕНО: {len(keep)} (из них {not_same} другой словарь переводит иначе, "
          f"тождеством или не во всех областях; {full_only} закрыл бы только режим full)")
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
    keep = rescue(target, exact, set(pack.get("_asis") or ()), rules)
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
    # ⚠️ ЧИСЛО ДО И ПОСЛЕ — ЖЕЛЕЗНОЕ ПРАВИЛО ПРОЕКТА, и здесь оно теперь
    # встроено: словарь похудел — это потерянный источник, а не «так и было»
    # (12.10: −1147 записей, сборка зелёная, ошибок нет). Усохший словарь не
    # записываем; осознанное сокращение — только с --allow-shrink.
    was = len((json.loads(target.read_text(encoding="utf-8")).get("exact") or {})
              if target.exists() else {})
    if "--dry" in sys.argv:
        print(f"сухой прогон: точных записей было {was}, стало бы {len(exact)} "
              f"({len(exact) - was:+d}); файл не тронут")
        return 0
    if len(exact) < was and "--allow-shrink" not in sys.argv:
        print(f"⚠️ СТОП: словарь усох бы с {was} до {len(exact)} точных записей "
              f"(−{was - len(exact)}). Источник потерял переводы — ищи, откуда "
              f"они выпали; осознанное сокращение: --allow-shrink. Файл не тронут.")
        return 2
    print(f"точных записей: было {was}, стало {len(exact)}")
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
