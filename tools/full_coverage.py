# -*- coding: utf-8 -*-
"""
Сколько ещё перевести, чтобы РЕЖИМ ПОЛНОГО ПЕРЕВОДА закрыл весь английский.

Вопрос игрока 23.08: «переводим прям ВСЁ, что видно на сервере, — покажи,
сколько осталось». Ответить числом из `refresh.py --dry` нельзя: там 25 147
«ждущих», и это РАЗМЕР ДАННЫХ, а не работа. Записанная грабля проекта,
повторённая четырежды: единственный надёжный ответ на вопрос «сколько
работы» — разбор по слоям, а не общий счётчик.

Что делает: берёт ВСЁ, что мод когда-либо видел на экране (наш дамп плюс
строки от игроков), спрашивает НАСТОЯЩИЙ движок с включённым режимом `full`
и раскладывает остаток по непересекающимся слоям.

⚠️ ОБЛАСТЬ СЛОВАРЯ УЧИТЫВАЕТСЯ, и без неё замер врёт в добрую сторону.
`81-item-names` объявлен только для `item_name`/`item_lore`, а инструменты
до 23.08 области не проверяли вовсе — то есть засчитывали его перевод и в
чате. Здесь каждая строка спрашивается с указанием ИСТОЧНИКА (`origin`),
ровно как это делает `Entry.allows` в моде.

⚠️ МЕХАНИКА МОДА — НЕ СЛОВАРЬ, и её надо вычитать отдельно. Имя вроде
«Heroic Hyperion ✪✪✪✪✪➎» в словаре не лежит и лежать не может: вариантов
у одной вещи десятки. Его собирает `core/Reforge.java` по NBT — снимает
хвост прокачки, переводит основу, возвращает хвост. Инструмент, меряющий
по одному словарю, объявил бы 353 такие строки работой (замер 23.08).

    python tools/full_coverage.py                 сводка по слоям
    python tools/full_coverage.py --layer ПЕРЕВОД показать строки слоя
    python tools/full_coverage.py --source chat   только один источник
    python tools/full_coverage.py --min 3         порог «прислали N установок»
    python tools/full_coverage.py --out FILE.json выгрузить остаток к работе
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import status  # noqa: E402
import make_queue  # noqa: E402
import pick_queue  # noqa: E402
import terms  # noqa: E402

try:
    import collect_server
except (ImportError, OSError):  # приёмника может не быть — признак уточняющий
    collect_server = None

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
PLAYERS = ROOT / "data" / "work" / "from_players.json"

LATIN = re.compile(r"[A-Za-z]")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")

# Хвост прокачки: звёзды за ковку, мастер-звёзды, значки. Задаётся КОДАМИ —
# записанная грабля: диапазон, набранный литералами, схлопывается в дефис.
UPGRADE_TAIL = re.compile("[\\s✪✦✧⭐➀-➓"
                          "❶-❿★☆]+$")
# Счётчик стопки в заголовке: «Dark Oak Log x64»
STACK_TAIL = re.compile(r"\s+x\s?[\d,]+$")

# ⚠️ Ведущий значок: «✿ Ancient Maxor's Boots», «☂ Perfect Aquamarine Gemstone».
# Признак ТОТ ЖЕ, что у мода (`Reforge.isLeadMark`): любой ведущий знак, кроме
# буквы и цифры, отделённый пробелом. Копию признака заводить нельзя —
# инструмент обязан повторять механику, а не приближать её.
LEAD_MARK = re.compile(r"^([^\w\s]+ +)")

# ⚠️ Полосу над хотбаром мод переводит ПО КОЛОНКАМ (translateColumns),
# а не строкой целиком. Считать строку непереведённой из-за одной колонки —
# то же завышение, на котором отчёт уже держал ложную верхушку.
COLUMNS = re.compile(r"\s{2,}")

WORK = "ПЕРЕВОД"


def gather(min_installs: int) -> dict[str, dict[str, int]]:
    """
    Всё, что мод видел: наш дамп плюс строки от игроков.

    ⚠️ Наш дамп ПРИОРИТЕТНЕЕ: там настоящие частоты показов, а у игроков
    счётчик значит «сколько установок прислали строку». Единицы разные,
    складывать их нельзя — от игроков берутся только НОВЫЕ строки.
    """
    merged: dict[str, dict[str, int]] = {}
    ours = make_queue.load("collected.json").get("sources") or {}
    for source, rows in ours.items():
        merged[source] = {line: int(count) for line, count in rows.items()}
    if PLAYERS.exists():
        players = json.loads(PLAYERS.read_text(encoding="utf-8"))
        for source, rows in (players or {}).items():
            if not isinstance(rows, dict):
                rows = {line: 1 for line in (rows or [])}
            target = merged.setdefault(source, {})
            for line, count in rows.items():
                # ⚠️ Порог применяем ТОЛЬКО к чужим строкам: свою мы видели
                # сами, и «прислал один человек» про неё ничего не значит.
                # Сверяем ПО ИСТОЧНИКУ, как make_queue: одна и та же надпись
                # в чате и в табе — разные строки, у них разные словари.
                if line in target:
                    continue
                if int(count) < min_installs:
                    continue
                target[line] = int(count)
    return merged


def reforge_prefixes() -> set[str]:
    """Названия перековок — у словаря режима, своей копии не заводим."""
    path = PACKS / "ru_ru" / "84-reforges.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set((data.get("reforges") or {}).keys())


def by_mechanics(line: str, dic: status.Dictionaries, prefixes: set[str],
                 origin: str) -> bool:
    """
    Имя соберёт МЕХАНИКА мода, а не словарь?

    Снимаем хвост прокачки и счётчик стопки, потом префикс перековки,
    и спрашиваем словарь про остаток — ровно так поступает `Reforge.compose`.

    ⚠️ Префикс отрезаем ТОЛЬКО когда остаток — известное имя вещи. Голое
    «первое слово это перековка» уже выбрасывало 18 законных имён: у «Blessed
    Frog» и «Lunar Rat Skin» первое слово ЧАСТЬ имени. Ровно поэтому сам
    `Reforge.compose` спрашивает NBT, а не форму строки.
    """
    bare = STACK_TAIL.sub("", UPGRADE_TAIL.sub("", line)).strip()
    if bare != line and bare and status.lookup(bare, dic, origin=origin):
        return True
    if _reforged(bare, dic, prefixes, origin):
        return True
    # ⚠️ Ведущий значок пробуем ВТОРЫМ заходом, как и мод: сперва имя ищется
    # целиком, и если словарь знает его вместе со значком, снимать нечего.
    lead = LEAD_MARK.match(bare)
    if lead:
        inner = bare[lead.end():]
        if inner and (status.lookup(inner, dic, origin=origin)
                      or _reforged(inner, dic, prefixes, origin)):
            return True
    return False


def _reforged(text: str, dic: status.Dictionaries, prefixes: set[str],
              origin: str) -> bool:
    """Первое слово — перековка, а остаток известен словарю?"""
    head, _, rest = text.partition(" ")
    return bool(head in prefixes and rest and status.lookup(rest, dic, origin=origin))


def translated(value: str, line: str) -> bool:
    """
    Движок вернул РУССКОЕ, а не то же самое английское?

    ⚠️ Тождественная запись законна и означает решение «оставить как есть»
    (имя предмета, метка). Считать её переводом нельзя: тогда счётчик мерил
    бы наличие записи, а не наличие русского на экране.

    ⚠️ `@ключ` — это перевод, который даёт КЛИЕНТ игрока: «@enchantment.
    minecraft.protection» превращается в «Защита». Кириллицы в нём нет,
    и без этой оговорки все ванильные названия числились бы работой.
    """
    if "@" in value:
        return True
    if value.strip() == line.strip():
        return False
    return bool(CYRILLIC.search(value))


def classify(line: str, source: str, dic: status.Dictionaries,
             prefixes: set[str], para: set[str], enchants: set[str],
             cuts: set[str]) -> str:
    """К какому слою относится строка. Слои НЕ пересекаются — иначе счёт врёт."""
    text = status.clean(line)
    if not LATIN.search(text):
        return "нет английского"

    # ⚠️ Обрезок панели (« Bazaar Al») — не работа и не строка вовсе: это шум
    # чтения панели в момент обновления. Признак живёт в приёмнике, копии
    # здесь не заводим.
    if line in cuts:
        return "обрезок панели"
    if collect_server is not None and collect_server.foreign_mod(text):
        return "чужой мод"
    if not make_queue.worth_translating(text, source):
        return "не перевод (ник, сервер)"

    found = status.lookup(text, dic, origin=source)
    if found:
        return "переводится" if translated(found[0], text) else "оставлено как есть"

    # ⚠️ ОТДЕЛЬНЫЙ СЛОЙ: перевод КУПЛЕН, а область словаря его сюда не пускает.
    # Это не работа переводчика, а одна строка в поле `only` — и цена ошибки
    # высокая: замер 23.08 нашёл 116 названий локаций, которые Hypixel пишет
    # крупной надписью при входе в зону, а `82-npc-places` был объявлен без
    # области `title`. Игрок видел английское на пол-экрана при готовом
    # переводе. Смешивать это с покупкой нельзя: список работы раздувается
    # тем, что чинится правкой генератора.
    anywhere = status.lookup(text, dic)
    if anywhere and translated(anywhere[0], text):
        return "область не пускает (%s)" % anywhere[1]

    # ⚠️ РЕШЕНИЕ УЖЕ ПРИНЯТО: помечено «переводить нечего» в рабочем файле
    # (`_asis`). В словарь такие не попадают — export_pack берёт только
    # непустые, — поэтому через `lookup` их не видно, и отчёт звал работой
    # то, что разобрано глазами. Замер: 700 строк в пяти заготовках.
    # ⚠️ Проверка стоит ПОСЛЕ словаря НАРОЧНО: пометка в одной заготовке
    # не отменяет перевода из другой, а поставленная выше она увела
    # 162 переведённые строки в «нечего».
    if text in status.all_asis() or line in status.all_asis():
        return "оставлено как есть"

    if source in ("item_name", "item_lore") and by_mechanics(text, dic, prefixes, source):
        return "механика (перековка, звёзды)"

    # ⚠️ Полоса над хотбаром: переведена, если переведена КАЖДАЯ колонка.
    if source == "action_bar" and COLUMNS.search(text):
        parts = [part.strip() for part in COLUMNS.split(text) if part.strip()]
        if parts and all(status.lookup(part, dic, origin=source) for part in parts):
            return "переводится"

    if source == "item_lore" and text in para:
        return "закрыто абзацем"

    layer = pick_queue.classify(text, enchants)
    # ⚠️ ПРИЗНАК ОБРЫВКА ГОДИТСЯ ТОЛЬКО ТАМ, ГДЕ ЕСТЬ ПЕРЕНОС. Он калиброван
    # под очередь, а она почти целиком лор: Hypixel режет описание по ширине
    # окна, и «Grants +5 Speed for» — правда полфразы. В ОДНОСТРОЧНОМ источнике
    # переноса нет вовсе, и порог «три слова и нет точки» записывает в обрывки
    # законные подписи кнопок: «Sell Sacks Now», «Confirm Instant Buy»,
    # «You have upgraded your Minion to Tier II». Замер 23.08: так пряталось
    # 509 строк в menu_title, 882 в screen и большая часть из 2733 в чате —
    # то есть настоящая работа не попадала в список работы.
    #
    # Надёжный край признака при этом остаётся: английское предложение
    # со строчной буквы не начинается, значит начало — верный знак хвоста.
    if layer == "обрывок" and source != "item_lore":
        first = next((ch for ch in text if ch.isalpha()), "")
        if not (first and first.islower()):
            layer = "покупка"
    # ⚠️ В ПОЛНОМ РЕЖИМЕ решения обычного режима не действуют: зачарования
    # и жаргон переводятся включёнными словарями, и раз движок их не нашёл —
    # это дырка покрытия, а не решение. Оставить их в своих слоях значило бы
    # спрятать работу ровно того режима, который мы меряем.
    if layer in ("зачарование", "жаргон", "решение игрока", "покупка"):
        return WORK
    return layer


ORDER = ["переводится", "механика (перековка, звёзды)", "закрыто абзацем",
         "оставлено как есть", "обрезок панели", "чужой мод",
         "не перевод (ник, сервер)", "техническое", "обрывок", WORK]

# Слой «область не пускает» именуется вместе со словарём-виновником, поэтому
# в ORDER его не перечислить — он печатается отдельным разделом.
BLOCKED = "область не пускает"

CLOSED = ("переводится", "механика (перековка, звёзды)", "закрыто абзацем")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--min", type=int, default=1,
                        help="порог: строку прислали N установок (для чужих строк)")
    parser.add_argument("--layer", help="показать строки слоя")
    parser.add_argument("--source", help="только один источник")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--out", help="выгрузить остаток к работе")
    parser.add_argument("--dump", help="выгрузить ВСЕ строки с их слоем "
                                       "(для разбора без повторного прогона)")
    args = parser.parse_args()

    dic = status.Dictionaries(groups={"full"})
    prefixes = reforge_prefixes()
    enchants = {name.lower() for name in terms.of("enchant")}
    para = make_queue.in_paragraphs(set(dic.paragraphs))
    rows = gather(args.min)
    if args.source:
        rows = {args.source: rows.get(args.source, {})}

    print(f"словарей в режиме full: точных {len(dic.exact)}, правил {len(dic.rules)}, "
          f"абзацев {len(dic.paragraphs)}")
    print(f"строк лора, закрытых абзацем: {len(para)}")

    cuts: set[str] = set()
    if collect_server is not None:
        pairs = sorted(rows.get("scoreboard", {}).items(), key=lambda kv: -kv[1])
        try:
            cuts = set(collect_server.panel_cuts(pairs, args.min))
        except Exception:
            cuts = set()

    layers: dict[str, list[tuple[str, str, int]]] = {}
    by_source: dict[str, dict[str, int]] = {}
    for source, lines in sorted(rows.items()):
        for line, count in lines.items():
            layer = classify(line, source, dic, prefixes, para, enchants, cuts)
            layers.setdefault(layer, []).append((source, line, count))
            counts = by_source.setdefault(source, {})
            counts[layer] = counts.get(layer, 0) + 1

    total = sum(len(v) for v in layers.values())
    english = total - len(layers.get("нет английского", []))
    done = sum(len(layers.get(name, [])) for name in CLOSED)
    work = len(layers.get(WORK, []))

    print(f"\nвсего строк: {total}, с английским: {english}")
    print("=" * 66)
    for name in ORDER:
        found = layers.get(name)
        if not found:
            continue
        mark = "  <- ЭТО И ЕСТЬ РАБОТА" if name == WORK else ""
        print("  %-30s %6d%s" % (name, len(found), mark))
    blocked = {name: rows_ for name, rows_ in layers.items()
               if name.startswith(BLOCKED)}
    for name in sorted(set(layers) - set(ORDER) - {"нет английского"} - set(blocked)):
        print("  %-30s %6d" % (name, len(layers[name])))
    if blocked:
        total_blocked = sum(len(rows_) for rows_ in blocked.values())
        print("  %-30s %6d  <- ЧИНИТСЯ ОБЛАСТЬЮ, а не переводом"
              % (BLOCKED, total_blocked))
        for name in sorted(blocked, key=lambda key: -len(blocked[key])):
            print("        %-40s %5d" % (name[len(BLOCKED) + 2:-1], len(blocked[name])))
    print("=" * 66)
    share = 100.0 * done / english if english else 0.0
    print(f"  закрыто режимом: {done} из {english} ({share:.0f}%)")
    print(f"  ОСТАЛОСЬ ПЕРЕВЕСТИ: {work}")

    print("\nпо источникам (работа / всего английского):")
    for source in sorted(by_source, key=lambda name: -by_source[name].get(WORK, 0)):
        counts = by_source[source]
        eng = sum(value for key, value in counts.items() if key != "нет английского")
        if eng:
            print("  %-12s %6d / %6d" % (source, counts.get(WORK, 0), eng))

    if args.layer:
        chosen = layers.get(args.layer)
        if chosen is None:
            print(f"\nслоя {args.layer!r} нет; есть: {', '.join(sorted(layers))}")
            return 1
        print(f"\n=== {args.layer}: {len(chosen)} ===")
        for source, line, count in sorted(chosen, key=lambda row: -row[2])[:args.limit]:
            print("  %5dx [%s] %s" % (count, source, line[:90]))

    if args.dump:
        # ⚠️ Замер идёт минут двадцать, а разбирать его хочется много раз:
        # «сколько тут дублей между источниками», «сколько семей», «сколько
        # видел один человек». Выгружаем разложенное ЦЕЛИКОМ, чтобы дальше
        # считать мгновенно и не гонять движок заново.
        Path(args.dump).write_text(json.dumps(
            {"rows": [{"source": source, "line": line, "count": count,
                       "layer": layer}
                      for layer, found in sorted(layers.items())
                      for source, line, count in found]},
            ensure_ascii=False), encoding="utf-8")
        print()
        print("выгружено:", args.dump)

    if args.out:
        picked = sorted(layers.get(WORK, []), key=lambda row: -row[2])
        # ⚠️ ФОРМАТ ОБЯЗАН НЕСТИ ИСТОЧНИК И ЧАСТОТУ, и это не украшение:
        # `full_batch` спрашивает словарь С УКАЗАНИЕМ ОБЛАСТИ (у `item_lore`
        # и `chat` разные словари), а порядок пачки берётся по частоте.
        # Прежний вид `{"exact": {строка: ""}}` их выбрасывал — и отбор падал
        # на первой же строке, потому что ждал другого. Записанная семья бед:
        # инструмент читает не тот формат, что пишет сосед.
        Path(args.out).write_text(json.dumps(
            [{"src": source, "line": line, "seen": count}
             for source, line, count in picked],
            ensure_ascii=False, indent=1), encoding="utf-8")
        print("\nзаписано:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
