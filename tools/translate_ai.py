"""
Переводит строки SkyBlock на русский через Claude.

Зачем нейронка, а не обычный переводчик: игровые тексты набиты терминами
(Strength, Reforge, Soulbound), сокращениями и разметкой. Обычный переводчик
ломает термины и не знает контекста игры. Claude получает наш глоссарий
и правила прямо в запросе, поэтому термины остаются едиными во всём словаре.

Как работает:
  - берёт файл-заготовку (строка -> пустой перевод), пропускает уже переведённое;
  - режет на пачки, каждую отправляет одним запросом со схемой ответа
    (structured outputs) — модель физически не может ответить не тем форматом;
  - глоссарий и правила лежат в начале запроса и помечены как кэшируемые:
    один и тот же префикс на все пачки — дешевле и терминология не плавает;
  - по умолчанию идёт через Batch API (вдвое дешевле, ответ в течение часа),
    ключ --sync шлёт запросы сразу (дороже, зато мгновенно).

Запуск:
  python tools/translate_ai.py data/skeleton/neu_lore.json
  python tools/translate_ai.py data/skeleton/neu_lore.json --limit 300 --sync
  python tools/translate_ai.py data/work/from_game.json --out data/work/from_game.json

Нужен ключ: переменная окружения ANTHROPIC_API_KEY, либо вход через `ant auth login`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from restore_icons import icons_of, restore_line  # noqa: E402
from protected import check_block, collect, resolve_collisions, term_of_rule  # noqa: E402
from translate_tooltips import mask_icons, unmask_icons  # noqa: E402

try:
    from anthropic import Anthropic
except ImportError:
    print("Нет библиотеки anthropic. Поставь её:", file=sys.stderr)
    print("    pip install anthropic", file=sys.stderr)
    raise SystemExit(1)

# Цена у Opus 5 та же, что у 4.8 ($5/$25 за миллион, кэш $0.50,
# в пачечном режиме $2.50/$12.50) — сверено с официальным прайсом
# 24.07.2026. Более новая модель досталась без доплаты.
MODEL = "claude-opus-5"
ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# Сколько строк в одном запросе. Больше — дешевле, но выше шанс, что модель
# устанет к концу списка и начнёт халтурить. 40 — рабочий компромисс.
BATCH_SIZE = 40

RULES = """Ты переводишь тексты мода Hypixel SkyBlock (Minecraft) с английского на русский.
Это интерфейс игры: описания предметов, сообщения чата, подписи кнопок.

Правила перевода:
1. Термины бери СТРОГО из глоссария ниже. Если термин есть в глоссарии — другой вариант недопустим.
2. Названия предметов, ников игроков, локаций и NPC НЕ переводи — оставляй как есть.
   Но обычное слово РЯДОМ с названием переводи: «Floor» это этаж, а не часть имени
   локации. «The Catacombs Floor VII» -> «The Catacombs, этаж VII».
2a. АНГЛИЙСКИЕ ИМЕНА НЕ СКЛОНЯЮТСЯ. Не приделывай к ним русские окончания и не
   пиши через апостроф. Строй фразу так, чтобы имя стояло в неизменном виде:
      «go and find Captain Baha in the Fishing Outpost!»
      ХОРОШО: «отправляйся и найди Captain Baha в Fishing Outpost!»
      ПЛОХО:  «...в Fishing Outpost'е», «...Captain Baha'у»
      ПЛОХО:  «найди Капитана Баху в Рыбацкой заставе»
   Если без падежа фраза разваливается, добавь русское слово-подпорку — падеж
   возьмёт оно, а имя останется как есть:
      «на острове Lotus Atoll», «у торговца Captain Baha»,
      «в локации Fishing Outpost», «существа Lotus Sea Creatures»
   Подпорку ставь ТОЛЬКО когда без неё плохо: лишние слова тоже мешают.
   Hypixel подсвечивает такие имена своим цветом прямо в игре — если слово
   выглядит как название места, существа или персонажа, считай его именем.
3. Сохраняй знаки в начале и конце строки: ✔ ✖ ❣ ✎ ❈ ● ■ [ ] ( ) * - и подобные.
4. Сохраняй все числа, проценты и единицы ровно как в оригинале.
5. Плейсхолдеры вида {STRENGTH}, {n}, %s, $1 переноси без изменений.
5a. В строках попадаются символы приватной зоны Unicode (U+E000..U+F8FF) — это
   ИКОНКИ Hypixel: сердце, мана, защита, значки категорий. Выглядят как мусор или
   пустой квадрат, но выбрасывать их НЕЛЬЗЯ: в игре на их месте будет дыра.
   Переноси каждую иконку в перевод, ставя её перед тем словом, к которому она
   относится (в русском порядок слов другой — значок едет вместе со своим словом).
6. Это подписи в игре, а не проза: пиши коротко. Точку в конце короткой строки не ставь,
   если её нет в оригинале.
7. Строка может быть обрывком фразы, разрезанной на несколько строк подсказки.
   Переводи такой обрывок так, чтобы он читался куском предложения, а не отдельной фразой.
8. Если строку переводить бессмысленно (только цифры, символы, техническая метка) —
   верни её без изменений.
9. Обращение к игроку — на «ты»: так принято в русских переводах Minecraft.
10. Коды цвета §a §c §l и подобные оставляй ровно там, где они стоят в оригинале.

КОНТЕКСТ. Перед строкой в квадратных скобках может стоять пометка — откуда она:
имя предмета или раздел игры (подземелья, рыбалка, ковка). Это подсказка,
а НЕ часть текста: переводить её не надо, но учитывать надо. Одно и то же
английское слово в разных разделах переводится по-разному.

СВЯЗНЫЕ БЛОКИ. Идущие подряд строки с ОДИНАКОВОЙ пометкой — это одна подсказка
предмета, разрезанная на строки. Переводи их как единый текст, а потом разложи
обратно по строкам: читаться подряд они должны связно, без обрывов посередине
фразы. Число строк менять нельзя — сколько дано, столько и верни.

Отвечай только переводом, без пояснений."""

REVIEW_RULES = """Ты проверяешь чужой перевод игровых строк с английского на русский.
Верни ТОЛЬКО те строки, где нашёл ошибку, и сразу исправленный вариант.
Если строка в порядке — не возвращай её вовсе.

Что считается ошибкой:
0. Английское имя просклоняли: приделали русское окончание, апостроф или
   перевели его («в Fishing Outpost'е», «Капитан Баха»). Имя обязано остаться
   в исходном виде; если фраза без падежа не читается, нужна русская подпорка
   («на острове Lotus Atoll»).
1. Потерян символ приватной зоны Unicode (иконка Hypixel) — он есть в оригинале, но нет в переводе.
2. Потеряна или продублирована подстановка {1}, {2}, {STRENGTH} и подобная.
3. Потерян или сдвинут код цвета §a §c §l.
4. Термин переведён не так, как в глоссарии.
5. Согласование: род, число или падеж не сходятся.
6. Строка осталась английской, хотя её надо было перевести.
7. Соседние строки одной подсказки не читаются связно."""

SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer", "description": "номер строки из запроса"},
                    "ru": {"type": "string", "description": "перевод на русский"},
                },
                "required": ["i", "ru"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}


def load_glossary() -> str:
    """Собирает термины из встроенных словарей — это и есть общий контекст для модели."""
    terms: dict[str, str] = {}
    for path in sorted(PACKS.rglob("*.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for source, target in (pack.get("glossary") or {}).items():
            if target:
                terms[source] = target
        for source, target in (pack.get("exact") or {}).items():
            # короткие строки — это фактически тоже термины
            if target and len(source) <= 30:
                terms[source] = target
        # ⚠️ И ПРАВИЛА тоже: половина терминов живёт именно там.
        #
        # Классы подземелий («Archer -> Лучник»), подписи характеристик и
        # зачарования лежат в секции regex, а глоссарий читал только exact
        # и glossary. Модель их не видела и оставляла английскими: в одной
        # подсказке «Танк» по-русски, а «Berserk», «Healer», «Mage», «Archer»
        # нет. Термин достаётся из самого шаблона.
        for rule in pack.get("regex") or []:
            name = term_of_rule(rule.get("p", ""))
            # Подстановки $1 бывают и в начале (у правил со значком),
            # и в конце — снимаем с обеих сторон.
            target = rule.get("r", "")
            target = re.sub(r"^(?:\s*\$\d)+", "", target)
            target = re.sub(r"(?::?\s*\$\d)+\s*$", "", target)
            target = target.strip().rstrip(":").strip()
            if name and target and not target.startswith("@"):
                terms.setdefault(name, target)

    lines = [f"{src} = {dst}" for src, dst in sorted(terms.items())]
    return "ГЛОССАРИЙ (обязателен к соблюдению):\n" + "\n".join(lines)


def build_system(glossary: str) -> list[dict]:
    """
    Системная часть запроса. Она одинакова для всех пачек, поэтому помечаем её
    как кэшируемую: повторные запросы читают её из кэша, а не оплачивают заново.
    """
    # ВНИМАНИЕ. Список защищённых имён модели ПОКАЗЫВАЕМ, а не только
    # проверяем потом. Раньше его тут не было вовсе: скрипт молча ловил
    # порчу на приёме и отбраковывал строку. Модель при этом не знала,
    # чего трогать нельзя, и «Auction House» становился «Аукционом» раз
    # за разом, сколько ни перезапускай. Проверка без подсказки
    # превращается в вечный отказ, а не в исправление.
    from protected import as_prompt
    # ⚠️ ГЛОССАРИЙ СЮДА НЕ КЛАДЁМ.
    #
    # Системная часть кэшируется и перечитывается КАЖДЫМ запросом. С полным
    # глоссарием она весила 158 тысяч токенов, и на 113 запросах это дало
    # $8.95 из $13.47 — две трети счёта ушли на пересылку словаря, а не
    # на перевод. При этом из 6370 терминов в пачке из 40 строк встречается
    # от силы полсотни: остальные 6300 оплачивались впустую 113 раз подряд.
    #
    # Теперь тут только правила и защищённые имена — они действительно одни
    # и те же для всех пачек. Нужные термины приезжают вместе с самой пачкой
    # (build_user), где стоят копейки: их мало.
    parts = [RULES]
    if GUARDED:
        parts.append(as_prompt(GUARDED))
    return [{
        "type": "text",
        "text": (chr(10) + chr(10)).join(parts),
        "cache_control": {"type": "ephemeral"},
    }]


def terms_for(chunk: list[dict], glossary: str) -> str:
    """
    Термины глоссария, которые ВСТРЕЧАЮТСЯ в этой пачке.

    Термин, которого в исходных строках нет, помочь переводу не может —
    значит и посылать его незачем. Отбор буквальный: ищем термин в тексте
    пачки как есть.
    """
    blob = chr(10).join(item["text"] for item in chunk).lower()
    picked = [line for line in glossary.splitlines()
              if " = " in line and line.split(" = ", 1)[0].lower() in blob]
    if not picked:
        return ""
    return "ГЛОССАРИЙ (термины из этих строк):" + chr(10) + chr(10).join(picked)


def build_user(chunk: list[dict], glossary: str = "") -> str:
    lines = []
    for i, item in enumerate(chunk):
        hint = item.get("context")
        # ⚠️ Значки прячем за {i1}, {i2}. Просить «не выбрасывай» бесполезно:
        # символ приватной зоны для модели — мусор или пустой квадрат, и рука
        # тянется убрать. На первой же пачке из 40 строк значки потерялись
        # в трёх. Маркер — обычный видимый текст, его модель переносит так же
        # надёжно, как {n}, и переносит ВМЕСТЕ со словом, что нам и нужно.
        masked, item["_icons"] = mask_icons(item["text"])
        lines.append(f"{i}. [{hint}] {masked}" if hint else f"{i}. {masked}")
    return ("Переведи строки. Верни перевод для КАЖДОГО номера, ничего не пропуская.\n\n"
            + "\n".join(lines))


def request_params(system: list[dict], chunk: list[dict]) -> dict:
    return {
        "model": MODEL,
        "max_tokens": 8000,
        "system": system,
        "output_config": {
            "format": {"type": "json_schema", "schema": SCHEMA},
            # high вместо medium: строки короткие, но с разметкой и терминами —
            # на них аккуратность важнее экономии
            "effort": "high",
        },
        "messages": [{"role": "user", "content": build_user(chunk, GLOSSARY)}],
    }


def review_params(system: list[dict], chunk: list[dict], translated: dict[str, str]) -> dict:
    """Второй проход: отдельный запрос ищет ошибки в уже готовом переводе."""
    lines = []
    for i, item in enumerate(chunk):
        russian = translated.get(item["text"])
        if russian is None:
            continue
        hint = f"[{item['context']}] " if item.get("context") else ""
        lines.append(f"{i}. {hint}БЫЛО: {item['text']}\n   СТАЛО: {russian}")
    if not lines:
        return {}
    return {
        "model": MODEL,
        "max_tokens": 8000,
        "system": [{"type": "text", "text": REVIEW_RULES + "\n\n" + system[0]["text"],
                    "cache_control": {"type": "ephemeral"}}],
        "output_config": {
            "format": {"type": "json_schema", "schema": SCHEMA},
            "effort": "high",
        },
        "messages": [{"role": "user", "content": "Проверь перевод:\n\n" + "\n".join(lines)}],
    }


def parse_reply(text: str, chunk: list[dict]) -> dict[str, str]:
    """Раскладывает ответ модели обратно по исходным строкам."""
    out: dict[str, str] = {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        print("  ! ответ не разобрался как JSON, пачка пропущена")
        return out

    for item in payload.get("translations") or []:
        index = item.get("i")
        translated = (item.get("ru") or "").strip()
        if not isinstance(index, int) or not (0 <= index < len(chunk)) or not translated:
            continue
        source = chunk[index]["text"]
        translated = unmask_icons(translated, chunk[index].get("_icons") or {})
        translated = restore_line(source, translated)
        # ⚠️ Значок, который вернуть не удалось, отбраковывает строку целиком.
        # Дыра посреди фразы заметнее английского текста, а незачёт ничего
        # не ломает: строка просто останется на следующий заход.
        if len(icons_of(source)) > len(icons_of(translated)):
            print(f"    ! {source[:44]!r}: потерян значок — пропускаю")
            continue
        # ⚠️ Защищённое имя пропало — строку не берём. Этой проверки тут
        # не было вообще, и «Auction House» превращался в «Аукционом»,
        # а «Visitor's Logbook» в «Журнал посетителей». Спорить с моделью
        # бесполезно, дешевле поймать механически — ровно как с иконками.
        if GUARDED and check_block([source], [translated], GUARDED):
            print(f"    ! {source[:44]!r}: потеряно защищённое имя — пропускаю")
            continue
        # Двойной пробел от возвращённого значка. Схлопываем ТОЛЬКО если
        # в оригинале двойных пробелов не было: полоса над хотбаром и боковая
        # панель разделяют колонки именно пробелами, и там это не мусор.
        if "  " not in source:
            translated = re.sub(r" {2,}", " ", translated).strip()
        # ⚠️ Перевод, совпавший с оригиналом, — это ответ «переводить нечего»
        # (правило 8), и его надо ЗАПОМНИТЬ, а не молча выбросить. Иначе такая
        # строка снова попадёт в очередь следующим заходом — и так каждый раз.
        # Замер: из 599 строк очереди 472 оказались именами предметов, NPC
        # и техническими метками, то есть четыре пятых пачки оплачивались
        # заново без всякой надежды на перевод.
        if translated != source:
            out[source] = translated
        else:
            AS_IS.add(source)
    return out


# Строки, которые модель признала непереводимыми (вернула как есть). Ложатся
# в секцию «_asis» файла-заготовки, и следующий заход их уже не спрашивает.
# Решение обратимо руками: удалить строку из «_asis» — и её спросят снова.
AS_IS: set[str] = set()

# ⚠️ Расход СЧИТАЕМ, а не прикидываем на глаз.
#
# Этот скрипт долго не считал ничего вовсе, и я на голубом глазу назвал прогон
# «копейками». По счёту вышло около доллара: системная часть запроса — правила
# плюс глоссарий из 4188 терминов, это ~65 тысяч токенов. Одна запись в кэш
# стоит $0.41, и умножается всё ещё на два, потому что после перевода идёт
# второй запрос-проверяющий. Незамеренное всегда кажется бесплатным.
USAGE = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0, "requests": 0}

# Opus 5: вход / выход / чтение кэша / запись кэша, долларов за миллион
PRICE = {"in": 5.0, "out": 25.0, "cache_read": 0.5, "cache_write": 6.25}


def note_usage(response) -> None:
    USAGE["requests"] += 1
    USAGE["in"] += getattr(response.usage, "input_tokens", 0)
    USAGE["out"] += getattr(response.usage, "output_tokens", 0)
    USAGE["cache_read"] += getattr(response.usage, "cache_read_input_tokens", 0)
    USAGE["cache_write"] += getattr(response.usage, "cache_creation_input_tokens", 0)


def spent() -> float:
    return sum(USAGE[part] / 1e6 * price for part, price in PRICE.items())


def report_usage() -> None:
    if not USAGE["requests"]:
        return
    print()
    print(f"запросов: {USAGE['requests']}  "
          f"(вход {USAGE['in']}, из кэша {USAGE['cache_read']}, "
          f"в кэш {USAGE['cache_write']}, выход {USAGE['out']})")
    print(f"стоимость захода: ${spent():.3f}")
    if USAGE["cache_write"]:
        print(f"  из них ${USAGE['cache_write'] / 1e6 * PRICE['cache_write']:.3f} — "
              f"разовая запись правил и глоссария в кэш")


def call(client: Anthropic, params: dict, chunk: list[dict]) -> dict[str, str]:
    """Один запрос к модели с разбором ответа. Пустой словарь — если не вышло."""
    if not params:
        return {}
    response = client.messages.create(**params)
    note_usage(response)
    if response.stop_reason == "refusal":
        print("  ! модель отказалась обрабатывать пачку")
        return {}
    text = "".join(block.text for block in response.content if block.type == "text")
    return parse_reply(text, chunk)


def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def run_sync(client: Anthropic, system: list[dict], batches: list[list[dict]],
             review: bool = True) -> dict[str, str]:
    # ⚠️ Запросов ВДВОЕ больше числа пачек, когда включён проверяющий.
    # Пока это не печаталось, я называл пользователю число пачек и был
    # уверен, что назвал число запросов.
    print(f"  пачек: {len(batches)}, запросов будет: "
          f"{len(batches) * (2 if review else 1)}"
          f"{' (перевод + проверяющий)' if review else ' (без проверяющего)'}")
    result: dict[str, str] = {}
    for number, chunk in enumerate(batches, 1):
        print(f"  пачка {number}/{len(batches)} ({len(chunk)} строк)...", flush=True)
        try:
            got = call(client, request_params(system, chunk), chunk)
        except Exception as exception:  # сеть/лимиты — не роняем всю работу
            print(f"  ! ошибка: {exception}")
            # А вот доступ к API само не починится: смысла долбиться
            # в оставшиеся пачки нет, и настоящая причина тонет в повторах.
            text = str(exception).lower()
            if any(stop in text for stop in
                   ("credit balance", "authentication", "invalid x-api-key",
                    "permission", "billing")):
                print()
                print("Дальше идти незачем — это не сбой запроса, а доступ к API.")
                print("Пополнить: console.anthropic.com -> Plans & Billing")
                print("(баланс API отдельный от подписки Claude Code)")
                break
            continue
        print(f"    переведено {len(got)}/{len(chunk)}")

        # Второй проход: свежий запрос ищет потерянные иконки, съехавшие
        # подстановки и расхождения с глоссарием. Проверяющий не видит,
        # что переводил он же, — поэтому замечает больше.
        if review and got:
            try:
                fixes = call(client, review_params(system, chunk, got), chunk)
            except Exception as exception:
                print(f"    ! проверка не прошла: {exception}")
                fixes = {}
            if fixes:
                print(f"    проверка исправила: {len(fixes)}")
                got.update(fixes)

        result.update(got)
    return result


def run_batch(client: Anthropic, system: list[dict], batches: list[list[str]]) -> dict[str, str]:
    requests = [
        {"custom_id": f"chunk-{i}", "params": request_params(system, chunk)}
        for i, chunk in enumerate(batches)
    ]
    print(f"  отправляю {len(requests)} пачек через Batch API...")
    batch = client.messages.batches.create(requests=requests)
    print(f"  batch id: {batch.id}")
    print("  ждём. Обычно минуты, максимум 24 часа. Прервать можно — id выше,")
    print(f"  забрать позже: python tools/translate_ai.py --collect {batch.id} <файл>")

    while True:
        current = client.messages.batches.retrieve(batch.id)
        if current.processing_status == "ended":
            break
        counts = current.request_counts
        print(f"    статус: {current.processing_status}, готово {counts.succeeded}/{len(requests)}",
              flush=True)
        time.sleep(30)

    return collect_batch(client, batch.id, batches)


def collect_batch(client: Anthropic, batch_id: str, batches: list[list[str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    errors = 0
    for entry in client.messages.batches.results(batch_id):
        # результаты приходят в произвольном порядке — сопоставляем по custom_id
        index = int(entry.custom_id.split("-")[1])
        if entry.result.type != "succeeded":
            errors += 1
            continue
        message = entry.result.message
        text = "".join(block.text for block in message.content if block.type == "text")
        result.update(parse_reply(text, batches[index]))
    if errors:
        print(f"  ! пачек с ошибкой: {errors}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Перевод строк SkyBlock через Claude")
    parser.add_argument("file", help="файл-заготовка со строками (exact: строка -> перевод)")
    parser.add_argument("--out", help="куда писать (по умолчанию — в тот же файл)")
    parser.add_argument("--limit", type=int, default=0,
                        help="перевести только первые N непереведённых (0 = все)")
    parser.add_argument("--no-review", action="store_true",
                        help="без второго прохода-проверяющего (вдвое меньше запросов)")
    parser.add_argument("--sync", action="store_true",
                        help="слать сразу, не через Batch API (быстрее, дороже вдвое)")
    parser.add_argument("--collect", metavar="BATCH_ID",
                        help="забрать результат ранее отправленного batch")
    parser.add_argument("--forbid", default="", metavar="ГРУППЫ",
                        help="не переводить группы терминов через запятую "
                             "(python tools/terms.py — какие есть)")
    args = parser.parse_args()

    # ⚠️ Опечатку в имени группы ловим ДО ключа API: ошибка ввода не должна
    # требовать внешних зависимостей, чтобы обнаружиться.
    if args.forbid:
        import terms
        unknown = [name.strip() for name in args.forbid.split(",")
                   if name.strip() and not terms.of(name.strip())]
        if unknown:
            print(f"нет таких групп: {', '.join(unknown)}")
            print(f"есть: {', '.join(sorted(terms.all_groups()))}")
            return 1

    source_path = Path(args.file)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    out_path = Path(args.out) if args.out else source_path
    if not out_path.is_absolute():
        out_path = ROOT / out_path

    pack = json.loads(source_path.read_text(encoding="utf-8"))
    exact: dict[str, str] = pack.get("exact") or {}
    rules: list[dict] = pack.get("regex") or []

    # Правила чата переводим по их читаемому образцу: «{1} нашёл {2}!» понятно,
    # а сырая регулярка — нет. Обратно результат кладётся в поле r, где
    # подстановки записываются как $1, $2.
    rule_by_sample = {r["_sample"]: r for r in rules if r.get("_sample") and not r.get("r")}

    # Каждой строке даём подсказку, откуда она. Для правил чата это ключ SkyHanni
    # (dungeon.croesus.chest... — сразу видно, что подземелья, а не рыбалка),
    # для описаний предметов — имя предмета, если оно известно.
    contexts: dict[str, str] = pack.get("_contexts") or {}
    # Модель уже сказала про эти строки «переводить нечего» — второй раз
    # не спрашиваем и второй раз не платим.
    AS_IS.update(pack.get("_asis") or [])
    known_asis = len(AS_IS)
    pending: list[dict] = []
    for source, target in exact.items():
        if not target and source not in AS_IS:
            pending.append({"text": source, "context": contexts.get(source)})
    for sample, rule in rule_by_sample.items():
        key = rule.get("_key") or ""
        hint = ".".join(key.split(".")[:2]) if key else None
        pending.append({"text": sample, "context": hint})

    total = len(exact) + len(rules)
    print(f"файл: {source_path.relative_to(ROOT)}")
    print(f"всего записей: {total}, ждут перевода: {len(pending)}")
    if known_asis:
        print(f"  не спрашиваю: {known_asis} — модель признала их непереводимыми"
              f" (секция _asis, убрать строку оттуда = спросить снова)")
    if rule_by_sample:
        print(f"  из них правил чата: {len(rule_by_sample)}")
    if not pending:
        print("переводить нечего")
        return 0

    if args.limit:
        pending = pending[:args.limit]
        print(f"беру первые {len(pending)} (--limit)")

    with_context = sum(1 for item in pending if item.get("context"))
    print(f"с подсказкой о контексте: {with_context}/{len(pending)}")

    batches = chunks(pending, BATCH_SIZE)
    global GUARDED
    GUARDED = resolve_collisions(collect(), quiet=True)
    # ⚠️ Характеристики-жаргон защищаем ОТДЕЛЬНО и мимо resolve_collisions:
    # тот выбрасывает слова, которые переводит наш же словарь, — а здесь ровно
    # это и нужно, «перестань переводить то, что переводил». Без запрета
    # 72 строки очереди («+{n}☯ Combat Wisdom», «+{n} Mining Speed when mining»)
    # вернулись бы с русскими названиями, и разнобой начался бы заново.
    if args.forbid:
        import terms
        asked = [name.strip() for name in args.forbid.split(",") if name.strip()]
        by_group = terms.forbidden(asked) - terms.forbidden()
        GUARDED |= by_group
        print(f"запрещено группами {', '.join(asked)}: {len(by_group)} слов")
    print(f"защищённых имён: {len(GUARDED)}")
    global GLOSSARY
    glossary = load_glossary()
    GLOSSARY = glossary
    print(f"глоссарий: {glossary.count(chr(10))} терминов")

    # Ключ проверяем до первого запроса — понятная ошибка вместо череды 401
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from apikey import check as check_key
    if not check_key():
        return 1

    client = Anthropic()
    system = build_system(glossary)

    try:
        if args.collect:
            translated = collect_batch(client, args.collect, batches)
        elif args.sync:
            translated = run_sync(client, system, batches, review=not args.no_review)
        else:
            translated = run_batch(client, system, batches)
    except Exception as exception:
        message = str(exception)
        if "authentication" in message.lower() or "api_key" in message.lower():
            print("Нет доступа к API. Поставь ANTHROPIC_API_KEY или выполни `ant auth login`",
                  file=sys.stderr)
        else:
            print(f"Сорвалось: {exception}", file=sys.stderr)
        return 1

    rules_done = 0
    for source, target in translated.items():
        rule = rule_by_sample.get(source)
        if rule is not None:
            # {1} — понятный вид для перевода, $1 — то, что понимает движок мода
            rule["r"] = re.sub(r"\{(\d+)}", r"$\1", target)
            rules_done += 1
        else:
            exact[source] = target

    if exact:
        pack["exact"] = exact
    if rules:
        pack["regex"] = rules
    # Правила чата в «_asis» не кладём: там переводится образец, а не строка,
    # и «вернул как есть» значит промах модели, а не «переводить нечего».
    fresh_asis = {s for s in AS_IS if s not in rule_by_sample}
    if fresh_asis:
        pack["_asis"] = sorted(fresh_asis)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")

    done = sum(1 for value in exact.values() if value) + sum(1 for r in rules if r.get("r"))
    print()
    print(f"переведено за этот заход: {len(translated)} (из них правил чата: {rules_done})")
    if len(fresh_asis) > known_asis:
        print(f"признано непереводимыми: {len(fresh_asis) - known_asis}"
              f" (всего в _asis: {len(fresh_asis)}) — больше их не спрашиваем")
    print(f"итого в файле: {done}/{total}")
    print(f"записано: {out_path.relative_to(ROOT)}")
    report_usage()
    print()
    print("Проверь перевод глазами, потом скопируй файл в")
    print("  %APPDATA%\\.minecraft\\config\\skyblockru\\packs\\")
    print("и выполни в игре /skyblockru reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
