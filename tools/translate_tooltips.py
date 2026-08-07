"""
Переводит описания предметов АБЗАЦАМИ.

Зачем отдельный инструмент: сервер режет описание на строки по ширине окна,
а не по смыслу. Раньше мы переводили построчно и вынуждены были повторять
чужие границы — отсюда целый класс поломок и заведомо худший перевод.

Теперь единица перевода — абзац целиком. Разрезать его обратно на строки
будет мод (Paragraphs.wrap), поэтому переводчику разрешено писать как удобно
по-русски: правило «границу переноса не двигай» отменено.

Работает с корпусом абзацев:
  data/work/paragraphs.json   (его делает tools/make_paragraphs.py)

Абзацы там уже сложены по убыванию частоты, так что --limit берёт самые
ходовые — те, что закрывают больше всего подсказок на экране.

Запуск:
  python tools/translate_tooltips.py data/work/paragraphs.json --limit 50
  python tools/translate_tooltips.py data/work/paragraphs.json --effort medium
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("Нет библиотеки anthropic:  pip install anthropic", file=sys.stderr)
    raise SystemExit(1)

# Цена у Opus 5 та же, что у 4.8 ($5/$25 за миллион, чтение кэша $0.50,
# запись кэша $6.25, в пачечном режиме вдвое дешевле) — сверено с официальным
# прайсом 25.07.2026. Более новая модель досталась без доплаты.
MODEL = "claude-opus-5"
ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# По сколько абзацев за запрос.
# Правила с глоссарием — это ~48 тысяч знаков, и они кэшируются, но кэш
# ПЕРЕЧИТЫВАЕТСЯ на каждый запрос: около цента за раз. При 50 абзацах на
# запрос это ~$1 на весь корпус, при 15 было бы втрое больше. Выше не берём:
# абзацы независимы, но чем длиннее список, тем небрежнее к его концу.
BATCH = 50

RULES = """Ты переводишь описания предметов Hypixel SkyBlock с английского на русский.

Тебе дают АБЗАЦ — законченный кусок текста. На экране сервер режет его на строки
по ширине окна, но эту разрезку сделает мод, а не ты. Значит подгонять русскую
фразу под чужие границы НЕ надо: пиши так, как естественнее читается по-русски.

Железные правила:
1. Ответ — один абзац ОДНОЙ строкой, без переносов.
2. {n} — любое число, {s} — ник игрока. Их должно остаться СТОЛЬКО ЖЕ и в ТОМ ЖЕ
   ПОРЯДКЕ. Мод подставляет числа в дырки по порядку, и переставленное {n}
   получит чужое число: «+{n} к силе на {n} секунд» с переставленными дырками
   даст «+30 к силе на 5 секунд» вместо «+5 к силе на 30 секунд».
3. {i1} {i2} {i3} — ЗНАЧКИ Hypixel (мана, защита, урон крита, сокровища).
   Перенеси КАЖДЫЙ, ни одного не потеряй и новых не выдумывай: сколько дано,
   столько и верни. Значок едет ВМЕСТЕ со своим словом — по-русски порядок слов
   другой, и маркер должен оказаться там, куда переехало его слово:
      «+{n} {i1} Crit Damage» -> «+{n} {i1} урона крита»
      «{i2} Mining Speed»     -> «{i2} скорость добычи»
   Выбросишь — в игре на этом месте будет дыра.
4. Названия предметов, имена NPC и названия локаций не переводи. Но обычное слово
   РЯДОМ с названием — переводи: «Floor» это этаж, а не часть имени локации.
      «Requires The Catacombs Floor VII Completion»
      ХОРОШО: «Требуется прохождение The Catacombs, этаж VII»
      ПЛОХО:  «Требуется прохождение The Catacombs Floor VII»
5. ИМЯ ПРЕДМЕТА ИЗ ЗАГОЛОВКА не переводи НИГДЕ — ни отдельным словом, ни внутри
   фразы. Даже если это обычное английское слово: кролика зовут Dash, и «Рывок» —
   уже другой кролик. По именам ищут вещи на аукционе.
   ⚠️ НО РЕШАЕТ РЕГИСТР. Hypixel пишет имена с Заглавной, а обычные слова —
   со строчной, даже если буквы те же. Слово со СТРОЧНОЙ буквы переводится
   всегда, хотя бы оно и встречалось в заголовке:
      предмет «Millennia-Old Blaze Ashes», текст «blaze ashes are eternal»
      ХОРОШО: «пепел ифрита вечен»
      ПЛОХО:  «пепел blaze вечен»
   Оставить английским слово со строчной — значит выдать полурусскую фразу,
   а это хуже и русского, и английского текста целиком.
6. АНГЛИЙСКИЕ ИМЕНА НЕ СКЛОНЯЮТСЯ. Не приделывай к ним русские окончания и не
   пиши через апостроф. Строй фразу так, чтобы имя стояло в неизменном виде:
      «go find Captain Baha in the Fishing Outpost»
      ХОРОШО: «найди Captain Baha в Fishing Outpost»
      ПЛОХО:  «найди Captain Baha в Fishing Outpost'е»
      ПЛОХО:  «найди Капитана Баху в Рыбацкой заставе»
   Если без падежа фраза разваливается, добавь русское слово-подпорку — падеж
   возьмёт оно, а имя останется как есть:
      «на острове Lotus Atoll», «у торговца Captain Baha»,
      «в локации Fishing Outpost», «существа Lotus Sea Creatures»
   Подпорку ставь ТОЛЬКО когда без неё плохо: лишние слова тоже мешают.
   Hypixel подсвечивает такие имена своим цветом прямо в игре — если слово
   выглядит как название места, существа или персонажа, считай его именем.
7. Термины бери из глоссария ниже.
7a. ЦВЕТ. Если рядом с абзацем дан список цветов ({c1}, {c2}…), расставь эти
   маркеры в переводе вокруг тех слов, В КОТОРЫЕ переведён подсвеченный кусок:
      «Grants a §a+20%§7 chance to catch §dSea Creatures§7»
      -> «Даёт {c1}+20%{/c1} шанс поймать {c2}морских существ{/c2}»
   Маркер едет ВМЕСТЕ со своим словом: порядок слов в русском другой. Каждый
   открытый маркер закрывай, вложенности не делай, номера не выдумывай.
   Списка цветов нет — значит и маркеров быть не должно.
   ⚠️ Без разметки цвет приходится УГАДЫВАТЬ по уцелевшим кускам, и переведённое
   слово подсветку теряет: «Grants a» стало «Даёт», привязать нечего. Маркер
   снимает это начисто — потому он и важнее прочих правил оформления.
8. Обращение к игроку — на «ты».
9. Если переводить нечего (только имена, числа или техническая метка) — верни
   абзац без изменений.

Отвечай только переводом."""

REVIEW_RULES = """Ты проверяешь чужой перевод описаний Hypixel SkyBlock с английского на русский.

Верни ТОЛЬКО те абзацы, где нашёл ошибку, и сразу исправленный вариант целиком.
Абзац в порядке — не возвращай его вовсе. Не переписывай ради вкуса: правь ошибки.

Что считается ошибкой:
1. Смысл искажён или потерян кусок фразы.
2. Термин переведён не так, как в глоссарии.
3. Согласование: род, число или падеж не сходятся; «кривая» русская фраза,
   которую носитель так не скажет.
4. Потерян или лишний маркер {n}, {s}, {i1} — либо они переставлены так, что
   число или значок встанут не к своему слову.
5. Переведено имя предмета, NPC или локации, которое трогать нельзя.
6. Остался английский кусок там, где его можно и нужно было перевести. Сюда же
   слово «Floor» рядом с названием локации: оно значит «этаж» и переводится —
   «The Catacombs Floor VII» это «The Catacombs, этаж VII».
7. Обращение к игроку не на «ты».

Помни: строки нарезает мод, поэтому длина и переносы значения не имеют —
оценивай только текст."""

SCHEMA = {
    "type": "object",
    "properties": {
        "paragraphs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer", "description": "номер абзаца из запроса"},
                    "ru": {"type": "string", "description": "перевод одной строкой"},
                },
                "required": ["i", "ru"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["paragraphs"],
    "additionalProperties": False,
}

SEP = chr(10) + chr(10)

PLACEHOLDER = re.compile(r"\{[sn]}")

# Маркер значка в тексте, который уходит модели: {i1}, {i2}…
ICON_MARK = re.compile(r"\{i(\d+)}")

# Маркеры ЦВЕТА: {c1}…{/c1}. Тот же приём, что со значками, и по той же
# причине — §-код невидим в тексте, модель его теряет, а видимый маркер
# переносит вместе со словом.
COLOR_MARK = re.compile(r"\{/?c\d+}")
COLOR_MARK_OPEN = re.compile(r"\{c(\d+)}")
COLOR_MARK_CLOSE = re.compile(r"\{/c(\d+)}")

# ⚠️ ИСКАЖЁННЫЙ маркер чиним, а не бракуем абзац целиком.
#
# Приём подсмотрен у чужого мода (fridorin/Skyblock-Translator-Mod): он
# восстанавливает свои метки регуляркой, принимающей {F0}, (F0), [F0], F0,
# _F0_ и даже {ф0} с КИРИЛЛИЧЕСКОЙ буквой — машинный переводчик метку
# корёжит, и жёсткая сверка теряла бы каждый такой ответ.
#
# ⚠️ ЧЕСТНО ПРО МАСШТАБ: у нас переводит Claude, и он переносит маркеры
# точно. Замер 31.07 по всем 57 файлам данных: искажённых маркеров НОЛЬ.
# Но замер видит только тех, кто ПРОШЁЛ accept(), — забракованный абзац
# на диск не попадает вовсе, поэтому сказать «потерь нет» нельзя.
# Отсюда две правки сразу: эта страховка и учёт причин брака (REJECTED),
# который на следующем прогоне даст настоящую цифру вместо догадки.
#
# Для НАШЕГО языка риск особый и не такой, как у них: маркер {c1} пишется
# ЛАТИНСКОЙ «c», а перевод русский — кириллическая «с» неотличима на глаз.
LOOSE_COLOR = re.compile(
    r"[\{\(\[]\s*_*\s*(/?)\s*_*\s*[cCсС]\s*_*\s*(\d+)\s*_*\s*[\}\)\]]")
LOOSE_ICON = re.compile(
    r"[\{\(\[]\s*_*\s*[iIіІ]\s*_*\s*(\d+)\s*_*\s*[\}\)\]]")


def normalize_marks(text: str) -> str:
    """Привести искажённые маркеры к каноническому виду ({c1}, {/c1}, {i1})."""
    text = LOOSE_COLOR.sub(lambda m: "{%sc%s}" % (m.group(1), m.group(2)), text)
    return LOOSE_ICON.sub(lambda m: "{i%s}" % m.group(1), text)


# ⚠️ ПОЧЕМУ бракуем — по причинам, а не одним числом.
#
# Причина брака печаталась строкой на каждый абзац и терялась в выводе:
# после прогона нельзя было сказать, ЧТО именно нас отсекает. Отсюда
# и невозможность честно оценить, стоит ли чинить маркеры: масштаб
# неизвестен. Теперь причины считаются и печатаются сводкой в конце —
# следующий прогон даст цифру вместо догадки.
REJECTED: "collections.Counter[str]" = __import__("collections").Counter()


def rejection_summary() -> str:
    """Сводка причин брака — печатается в конце прогона."""
    if not REJECTED:
        return ""
    rows = ["", "почему абзацы не приняты:"]
    for reason, count in REJECTED.most_common():
        rows.append(f"  {count:5d}  {reason}")
    return "\n".join(rows)


def mask_icons(text: str) -> tuple[str, dict[str, str]]:
    """
    Прячет значки Hypixel за маркеры {i1}, {i2}…

    ⚠️ Зачем. Модель выбрасывает символы приватной зоны, сколько ей ни объясняй:
    на экране это мусор или пустой квадрат, и рука тянется убрать. На замере
    из 50 абзацев так потерялась ПЯТАЯ ЧАСТЬ — оплаченный и выброшенный перевод.
    Механически вернуть можно не всё: значок перед словом («◆ Mining Speed»)
    по-русски уезжает вместе со словом, и позиция не выводится.

    Маркер снимает проблему с другой стороны: {i1} — обычный текст, его видно,
    и модель переносит его так же надёжно, как {n}. Заодно значок едет ВМЕСТЕ
    со своим словом, а это ровно то, что нужно.
    """
    from restore_icons import is_icon

    mapping: dict[str, str] = {}
    out = []
    for char in text:
        if is_icon(char):
            mark = f"{{i{len(mapping) + 1}}}"
            mapping[mark] = char
            out.append(mark)
        else:
            out.append(char)
    return "".join(out), mapping


def unmask_icons(text: str, mapping: dict[str, str]) -> str:
    """Возвращает значки на места маркеров. Лишние маркеры (модель выдумала) убираем."""
    for mark, char in mapping.items():
        text = text.replace(mark, char)
    return ICON_MARK.sub("", text)


def glossary() -> str:
    terms: dict[str, str] = {}
    for path in sorted(PACKS.rglob("*.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for src, dst in (pack.get("glossary") or {}).items():
            if dst and not dst.startswith("@"):
                terms[src] = dst
        for src, dst in (pack.get("exact") or {}).items():
            if dst and len(src) <= 30 and not dst.startswith("@"):
                terms[src] = dst
    return "ГЛОССАРИЙ:\n" + "\n".join(f"{k} = {v}" for k, v in sorted(terms.items()))


def accept(para: dict, russian: str, guarded: set[str]) -> tuple[str | None, str]:
    """
    Проверяет перевод одного абзаца механически. Возвращает (перевод, причина).
    Перевод None — брать нельзя, причина объясняет почему.

    Отдельной функцией, потому что спорить с моделью бесполезно (проверено
    на иконках) — а раз проверки механические, их надо уметь прогнать без API.
    """
    from protected import check_block
    from restore_icons import restore_line, icons_of

    source = para["text"]

    # Искажённый маркер чиним ДО всех проверок — см. normalize_marks:
    # потерять абзац из-за кириллической «с» в «{с1}» было бы обидно,
    # а починка тут механическая и однозначная.
    russian = normalize_marks(russian)

    # ⚠️ МАРКЕРЫ ЦВЕТА снимаем ПЕРВЫМИ, а разметку собираем в конце.
    #
    # Все проверки ниже (дырки, имена, значки) писаны под чистый текст, и
    # маркер {c1} для них — посторонний мусор. Поэтому проверяем чистое,
    # а цвет возвращаем только тому переводу, который проверки прошёл.
    codes = para.get("_codes")
    marked_russian = ""
    if codes:
        opened = COLOR_MARK_OPEN.findall(russian)
        closed = COLOR_MARK_CLOSE.findall(russian)
        if sorted(opened) != sorted(closed):
            return None, "маркеры цвета не парные"
        marked_russian = russian
        russian = COLOR_MARK.sub("", russian)

    # Снимаем маску значков: модель работала с {i1}, а в словарь и на проверки
    # идёт настоящий символ. Делаем это ПЕРВЫМ делом — дальше все проверки
    # считают значки, и им нужен настоящий текст.
    _, mapping = mask_icons(source)
    russian = unmask_icons(russian, mapping)

    # Мод раскладывает абзац по словам через пробел: перенос строки внутри
    # перевода склеился бы с соседним словом. Чиним молча — спорить не о чем.
    russian = " ".join(russian.split())
    if not russian:
        return None, "пустой перевод"
    if russian == source:
        # «переводить нечего» — записывать тождество в словарь незачем
        return None, "перевод совпал с оригиналом"

    # Дырок должно остаться столько же: мод подставляет числа по порядку,
    # и лишняя дырка получит пустоту, а недостающая потеряет число.
    if len(PLACEHOLDER.findall(russian)) != len(PLACEHOLDER.findall(source)):
        return None, "изменилось число дырок {n}/{s}"

    # Имя NPC или место, исчезнувшее при переводе, — испорченный абзац, и лучше
    # оставить его непереведённым, чем показать игроку «Лагерь Лесозаготовки».
    # Имя самого предмета защищаем вместе с общим списком: у кроликов это
    # Dash, Bob, Beta — обычные слова, и без защиты «Dash» станет «Рывком»,
    # то есть другим кроликом.
    # ⚠️ Защищаем заголовок ТОЛЬКО если это настоящий предмет. У кнопки в меню
    # заголовок тоже есть («Weapons», «Shards», «Enchantments»), и такие слова
    # переводить как раз нужно — иначе защита бракует хороший перевод
    # (8 абзацев из 47 за один заход). Признак — protected.real_items().
    from protected import real_items

    own = set(guarded)
    item_name = (para.get("item") or "").strip()
    if len(item_name) >= 2 and item_name in real_items():
        own.add(item_name)
    lost = check_block([source], [russian], own)
    if lost:
        return None, "перевёл имена " + ", ".join(lost)

    # Иконки Hypixel модель выбрасывает, сколько ей ни объясняй. Спорить дороже,
    # чем вернуть: в скобках и после {n} позиция выводится из оригинала однозначно.
    russian = restore_line(source, russian)

    # А вот иконку перед словом («Increases ◆ Mining Speed») механически не
    # вернуть: по-русски слово уезжает, и значок должен уехать вместе с ним.
    # Тогда лучше не переводить абзац вовсе — на этом и стоит вся затея
    # с абзацами: нет перевода, подсказка остаётся как пришла, и ломать нечего.
    # Дыра посреди описания заметнее английской фразы.
    lost_icons = [c for c in icons_of(source) if russian.count(c) < source.count(c)]
    if lost_icons:
        return None, f"потеряно иконок: {len(lost_icons)}"

    # ⚠️ Разметку возвращаем ТОЛЬКО если проверки ничего не правили.
    #
    # `restore_line` и снятие маски значков меняют ЧИСТЫЙ текст, а маркеры
    # остались в другой строке — перенести правку туда механически нельзя.
    # В таком случае берём плоский, но верный перевод: цвет мод восстановит
    # догадкой, а вот дыра от потерянного значка видна сразу.
    if codes and marked_russian:
        from color_lore import unmark
        candidate = unmark(marked_russian, codes, para.get("_body") or "§7")
        from color_lore import CODE as SECTION_CODE
        if SECTION_CODE.sub("", candidate) == russian:
            return candidate, ""
        return russian, ""
    return russian, ""


def batch_params(system: list[dict], chunk: list[dict], full_glossary: str,
                 toggles: set[str], effort: str) -> dict:
    """Один запрос пачки — те же параметры, что в обычном режиме."""
    return {
        "model": MODEL, "max_tokens": 16000, "system": system,
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA},
                          "effort": effort},
        "messages": [{"role": "user",
                      "content": build_user(chunk, full_glossary, toggles)}],
    }


def run_batch(client, path: Path, data: dict, pending: list[dict], system: list[dict],
              full_glossary: str, toggles: set[str], guarded: set[str],
              by_group: set[str], effort: str) -> int:
    """
    Отправляет всё через Batch API: вдвое дешевле, ответ обычно за минуты.

    ⚠️ Состав пачек сохраняем НА ДИСК рядом с id. Забирать результат можно
    через час и в другом запуске, а к тому времени корпус изменится: пачки,
    собранные заново, разъедутся с отправленными, и переводы лягут не в те
    абзацы. Сопоставляем по КЛЮЧУ абзаца, а не по номеру в списке.
    """
    requests = []
    plan: list[list[str]] = []
    for start in range(0, len(pending), BATCH):
        chunk = pending[start:start + BATCH]
        colors_for(chunk)
        requests.append({
            "custom_id": f"chunk-{len(plan)}",
            "params": batch_params(system, chunk, full_glossary, toggles, effort),
        })
        plan.append([para["text"] for para in chunk])

    print(f"  отправляю {len(requests)} пачек через Batch API...")
    batch = client.messages.batches.create(requests=requests)
    print(f"  batch id: {batch.id}")
    plan_file = path.parent / f"batch_{batch.id}.json"
    plan_file.write_text(json.dumps({"plan": plan}, ensure_ascii=False), encoding="utf-8")
    print(f"  состав пачек: {plan_file.name}")
    print("  ждём. Обычно минуты, предел сутки. Прервать можно — забрать позже:")
    print(f"    python tools/translate_tooltips.py {path} --collect {batch.id}")

    while True:
        current = client.messages.batches.retrieve(batch.id)
        if current.processing_status == "ended":
            break
        counts = current.request_counts
        print(f"    статус: {current.processing_status}, "
              f"готово {counts.succeeded}/{len(requests)}", flush=True)
        time.sleep(30)
    return collect_batch(client, batch.id, path, data, guarded, toggles, by_group)


def collect_batch(client, batch_id: str, path: Path, data: dict, guarded: set[str],
                  toggles: set[str], by_group: set[str]) -> int:
    """Забирает готовый batch и раскладывает переводы по абзацам."""
    plan_file = path.parent / f"batch_{batch_id}.json"
    if not plan_file.exists():
        print(f"нет состава пачек: {plan_file}")
        print("Без него неизвестно, какой ответ какому абзацу принадлежит.")
        return 0
    plan = json.loads(plan_file.read_text(encoding="utf-8"))["plan"]
    by_key = {para["text"]: para for para in data["paragraphs"]}

    done = errors = 0
    for entry in client.messages.batches.results(batch_id):
        index = int(entry.custom_id.split("-")[1])
        if entry.result.type != "succeeded":
            errors += 1
            continue
        message = entry.result.message
        text = "".join(b.text for b in message.content if b.type == "text")
        # ⚠️ Абзацы берём ПО КЛЮЧУ из сохранённого состава: за час между
        # отправкой и забором корпус мог измениться, и номер в списке уже
        # ничего не значит.
        chunk = [by_key.get(key) for key in plan[index]]
        if any(para is None for para in chunk):
            print(f"  ! пачка {index}: часть абзацев исчезла из корпуса")
            chunk = [para for para in chunk if para is not None]
        # ⚠️ ЦВЕТА ГОТОВИМ ЗАНОВО, иначе разметка теряется молча.
        #
        # При отправке `run_batch` кладёт в абзац `_codes` и `_body` — по ним
        # `accept()` разворачивает маркеры {c1} обратно в §-коды. Но забор
        # идёт отдельным запуском, абзацы берутся из корпуса заново, и полей
        # этих у них нет: маркеры не разворачиваются, перевод ложится плоским.
        # Замер: из 1140 забранных переводов разметку сохранили 9.
        # Ошибка тихая — переводы-то правильные, просто без цвета.
        colors_for(chunk)
        raw = replies_of(text, len(chunk))
        taken, _ = apply_replies(chunk, raw, guarded, toggles, by_group)
        done += taken
    if errors:
        print(f"  ! пачек с ошибкой: {errors}")
    save(path, data)
    return done


def apply_replies(chunk: list[dict], raw: dict[int, str], guarded: set[str],
                  toggles: set[str], by_group: set[str]) -> tuple[int, int]:
    """
    Кладёт переводы пачки в абзацы — через те же механические проверки.

    Отдельной функцией, чтобы обычный режим и Batch API шли ОДНИМ путём.
    Разойдись они — и в пачечном режиме перевод попадал бы в корпус без
    проверок на дырки, значки и защищённые имена, то есть ровно то, ради
    чего accept() и написан.

    @return (сколько принято, сколько починили иконок)
    """
    # ⚠️ Импорт ЗДЕСЬ, а не наверху файла. Функция вынесена из main(), где
    # `icons_of` был импортирован локально, — и первый же забор batch упал
    # на NameError, уже ПОСЛЕ оплаты пачек. В этом файле такая грабля
    # записана дважды (review_batch, тот же случай): вынося код из main,
    # проверь, что все его имена уехали вместе с ним.
    from restore_icons import icons_of

    done = fixed = 0
    for index, russian in sorted(raw.items()):
        para = chunk[index]
        # имя зачарования защищаем только там, где оно стоит С УРОВНЕМ:
        # «Growth V» — зачарование, «growth» в описании зелья — нет
        checked, reason = accept(
            para, russian,
            (guarded - toggles) | enchants_in(para["text"], toggles) | by_group)
        if checked is None:
            REJECTED[reason] += 1
            if reason != "перевод совпал с оригиналом":
                print(f"    ! абзац {index} ({para.get('item')}): {reason} — пропускаю")
            continue
        if icons_of(para["text"]) and checked != " ".join(russian.split()):
            fixed += 1
        para["ru"] = checked
        done += 1
    return done, fixed


def replies_of(text: str, size: int) -> dict[int, str]:
    """Разбирает ответ модели в «номер абзаца -> перевод»."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        print("  ! ответ не разобрался")
        return {}
    raw: dict[int, str] = {}
    for item in payload.get("paragraphs") or []:
        index = item.get("i")
        russian = item.get("ru")
        if isinstance(index, int) and 0 <= index < size \
                and isinstance(russian, str) and russian.strip():
            raw[index] = russian
    return raw


def mark_nothing(paragraphs: list[dict]) -> int:
    """
    Помечает абзацы, где переводить нечего: кроме имён предметов там ничего нет.

    Живой вид такого абзаца — список наград коллекции: «▶ Snowball ▶ Snow Block
    ▶ Enchanted Snow Block». Имена предметов мы не переводим по замыслу (по ним
    ищут на аукционе), поэтому перевод либо не отличается от оригинала, либо
    портит имя — и абзац отбраковывается. Заход за заходом одно и то же.

    ⚠️ Признак — ПО СУЩЕСТВУ, а не по форме. Форму я сначала и взял («список
    через ▶ из слов с заглавной») и чуть не выбросил 18 переведённых абзацев:
    «Examples: ◼ Dyes ◼ Skins ◼ Runes» выглядит так же, но там КАТЕГОРИИ, и они
    переводятся. Правильно так: убрать из абзаца все известные имена предметов
    и защищённые слова — если букв не осталось, переводить нечего.

    Уже переведённые абзацы не трогаем: пометка меняет только то, что спрашивать.
    """
    from protected import collect, real_items, resolve_collisions

    names = real_items() | resolve_collisions(collect(), quiet=True)
    # длинные вперёд, иначе «Ice» съест половину «Packed Ice»
    ordered = sorted((n for n in names if n), key=len, reverse=True)
    marked = 0
    for para in paragraphs:
        if para.get("ru") or para.get("nothing"):
            continue
        rest = para["text"]
        for name in ordered:
            if name in rest:
                rest = rest.replace(name, " ")
        rest = re.sub(r"\{[ns]}|[\W\d_]+", " ", rest)
        if not [word for word in rest.split() if len(word) > 1]:
            para["nothing"] = True
            marked += 1
    return marked


def mark_lists(paragraphs: list[dict]) -> int:
    """
    Помечает абзацы-СПИСКИ: их мод не склеит никогда, платить за них незачем.

    ⚠️ Причина не в тексте, а в устройстве. `ColorLayout.repeatedMarker`
    отказывается склеивать кусок, у которого строки начинаются списочным
    знаком, — иначе «✔ Двойное нажатие ✔ Просмотр профиля ✔ Обмен» слипается
    в сплошную строку, которую невозможно читать. Значит перевод такого абзаца
    до экрана НЕ ДОЙДЁТ, сколько за него ни заплати.

    Строки при этом переводить надо, и они уходят в очередь построчно:
    `make_queue.in_paragraphs` такие абзацы из «закрытых» исключает. То есть
    работа не теряется, а меняет путь — с абзацного на построчный.

    Замер на живом корпусе: 26 из 34 ждущих абзацев — списки, и каждый заход
    они уезжали в запрос заново. Плюс 108 уже КУПЛЕННЫХ переводов лежат
    мёртвым грузом по той же причине; их пометка не трогает — деньги
    потрачены, а перевод мог бы пригодиться, если правило склейки изменится.

    Признак берётся у мода (`ColorLayout.CHOICE_MARKS`), а не выписывается
    заново: копия этого набора уже разъезжалась, теперь её сторожит
    `check_contract.py`.
    """
    from make_queue import LIST_MARK

    marked = 0
    for para in paragraphs:
        if para.get("ru") or para.get("nothing"):
            continue
        rows = [str(row).strip() for row in (para.get("lines") or []) if str(row).strip()]
        if len(rows) < 2:
            continue
        marks = [row[0] for row in rows if LIST_MARK.match(row)]
        # Знак повторяется — список наверняка. Одинокий знак считаем списком
        # только при трёх строках и больше: у прозы бывает значок в начале
        # первой строки, и на двух строках это ещё не список.
        if len(marks) >= 2 or (len(marks) == 1 and len(rows) >= 3):
            para["nothing"] = True
            marked += 1
    return marked


def mark_enchant_combos(paragraphs: list[dict]) -> int:
    """
    Помечает абзацы-КОМБИНАЦИИ зачарований: покупать их не надо никогда.

    ⚠️ Такой абзац склеен из НАБОРА, который стоит на предмете: «Habanero
    Tactics V + Growth VI + Protection VI + Thorns III» — один ключ, а стоит
    игроку сменить одно зачарование, и ключ уже другой. Наборов столько,
    сколько их собрали игроки, поэтому купленный перевод закрывает ровно
    ОДИН предмет и никогда не встретится второй раз. Это путь без дна.

    ⚠️ Платить и не нужно: мод собирает такой абзац сам. `Paragraphs.bySections`
    режет его по заголовкам и ищет перевод КАЖДОЙ секции отдельно, а секции
    уже куплены — «Growth VI Grants +{n} ❤ Health.» лежит в корпусе своим
    абзацем. Замер по живому дампу: 716 абзацев с заголовками зачарований,
    и на всех них не хватает лишь 7 разных описаний.

    Значит недостающее закрывается покупкой ОПИСАНИЯ (одно на все наборы),
    а не комбинации. Пометка ставится независимо от того, все ли секции
    переведены: комбинация не тот товар, который стоит покупать.

    Признак — тот же `ENCHANT_HEAD`, что у мода, и та же оговорка: заголовком
    считается строка «Имя УРОВЕНЬ» при ДВУХ И БОЛЕЕ таких строках в абзаце.
    Одиночную от имени предмета не отличить («Sharpness I» против
    «Sheep Minion I»), и в проекте это уже записано в граблях.

    ⚠️ **Считаем зачарования и ВНУТРИ строки, через запятую.** Признак «строка
    целиком есть Имя УРОВЕНЬ» покрывает подсказку дрели, где каждое зачарование
    на своей строке. А на оружии Hypixel пишет их СПИСКОМ, по три в строку:

        Combo V, Bane of Arthropods V, Cleave V
        Critical VI, Cubism V, Ender Slayer V

    Такой абзац под прежний признак не попадал ни разу, и он уезжал в покупку.
    Замер по лору аукциона: из 9647 новых абзацев прежний признак поймал 1375,
    с сегментами — **4525**, то есть 3150 наборов просились за деньги напрасно
    (около $6). А платить за них не надо совсем: описания уже куплены поштучно,
    мод собирает набор сам через `Paragraphs.bySections`.

    ⚠️ Проза под это не попадает по построению: сегмент «Grants +{n} Health»
    не имеет вида «Имя УРОВЕНЬ» — там число, а не римская цифра. Проверено
    на корпусе: среди УЖЕ ПЕРЕВЕДЁННЫХ абзацев признак не задевает ни одного
    (перевод — это оплаченная работа, и правило, задевающее её, неверно,
    сколько бы ни было логично).
    """
    from make_queue import ENCHANT_HEAD

    marked = 0
    for para in paragraphs:
        if para.get("ru") or para.get("nothing"):
            continue
        rows = [str(row).strip() for row in (para.get("lines") or []) if str(row).strip()]
        if count_enchants(rows) >= 2:
            para["nothing"] = True
            marked += 1
    return marked


# §-коды: в лоре с аукциона они есть, в корпусе нет — снимаем в любом случае
CODES = re.compile("§.")

_LINE_RULES = None


def line_covered(line: str) -> bool:
    """
    Про строку УЖЕ всё решено: она либо переводится, либо намеренно английская.

    ⚠️ Спрашиваем `make_queue.already_translated`, а не свой список словарей,
    и причина не в экономии кода. Там учтено то, что легко забыть: у пакетов
    с `"default": false` берётся ВСЁ, потому что **выключено — это решение
    НЕ ПЕРЕВОДИТЬ, а не отсутствие перевода**. Свой список этого не знал бы,
    и фильтр требовал бы покупать абзац ради строки «Mining Speed: +{n}»,
    которую игрок сам оставил английской.

    ⚠️ И вторая половина той же грабли: у ВКЛЮЧЁННЫХ словарей секция `regex`
    тоже читается — правил там около двух тысяч, и однажды очередь не видела
    ни одного, прося денег за 139 строк из 144.
    """
    global _LINE_RULES
    if _LINE_RULES is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from make_queue import already_translated
        from pkey import NUMBER
        import terms as terms_module
        exact, templates, rules = already_translated()
        _LINE_RULES = (exact, templates, rules, NUMBER,
                       set(terms_module.STAT_JARGON))
    exact, templates, rules, number, jargon = _LINE_RULES
    probe = CODES.sub("", line).strip()
    if not probe:
        return True
    template = number.sub("{n}", probe)
    if probe in exact or template in exact:
        return True
    for pattern in list(templates) + list(rules):
        try:
            if pattern.fullmatch(probe) or pattern.fullmatch(template):
                return True
        except (AttributeError, TypeError):
            continue
    # ⚠️ Подпись — ЖАРГОН? Значит решение по ней уже принято: остаётся
    # английской. Записи в словаре может не быть вовсе — её никогда
    # не покупали, — но платить за такую строку всё равно не надо.
    #
    # Это оказалось важнее, чем выглядит. Строка «Gemstone Fortune: +{n}»
    # держала в очереди на покупку 89 абзацев, «Bonus Pest Chance» — 113,
    # и все они — блоки характеристик без единого слова прозы. Причина была
    # не в решении (жаргон весь перечислен в terms.STAT_JARGON), а в том, что
    # фильтр смотрел только в СЛОВАРИ и о списке решений не знал.
    label = LABEL_HEAD.match(probe)
    if not label:
        return False
    head = label.group(1).strip()
    if head in jargon:
        return True
    # ⚠️ ПРЕФИКС «Bonus » ЛОМАЛ ПРИЗНАК. Hypixel пишет и «Farming Fortune: +30»,
    # и «Bonus Farming Fortune: +48» — характеристика одна и та же, решение
    # по ней одно (остаётся английской), а в списке жаргона лежит короткая
    # форма. Из-за этого блок «Bonus Defense / Bonus Speed / Bonus Farming
    # Fortune» считался незакрытым и просился в ПЛАТНУЮ покупку целиком.
    # Замер 08.08: так в отбор попадало 66 абзацев из 622.
    # Снимаем только этот префикс: «Bonus Defense» -> «Defense» жаргоном
    # не станет и переводиться не перестанет.
    if head.startswith("Bonus "):
        return head[len("Bonus "):].strip() in jargon
    return False


# Подпись характеристики в начале строки: «Gemstone Fortune: +12 (+3)»
LABEL_HEAD = re.compile(r"^([A-Z][A-Za-z' ]{2,30}?): *[+\-]?[\d,.{-]")


def mark_stat_tables(paragraphs: list[dict]) -> int:
    """
    Помечает абзацы, целиком состоящие из ЗАКРЫТЫХ строк характеристик.

    ⚠️ Живой вид такого абзаца — блок характеристик прокачанного предмета:
    «Damage: +{n} / Mining Speed: +{n} / Mining Fortune: +{n} / Gemstones: []».
    Прозы там нет ни слова, каждая строка уже переводится построчным правилом
    (`gen_stat_forms` знает все формы, включая скобки ковки и самоцветов),
    и цельный перевод абзаца не добавил бы ничего — только счёт.

    ⚠️ Признак «мод не склеит» тут НЕ РАБОТАЕТ, и это стоит записать, потому
    что выглядит он убедительно. `Paragraphs.looksLikeTable` требует три строки
    ОДНОЙ ФОРМЫ, а форма считается по числу слов: «Damage: +#» и «Mining Speed:
    +#» — разные скелеты («W: +#» против «W W: +#»). Значит мод такой абзац
    как раз СКЛЕИТ, и отсеивать его «потому что не применится» было бы ложью.
    Отсеиваем по другой причине: покупать нечего, всё уже переведено построчно.

    ⚠️ Порог — ДВЕ строки: абзац из одной строки в корпус и не попадает.
    Требуем, чтобы закрыты были ВСЕ: одна незакрытая строка означает, что
    на экране останется английский, и абзац стоит купить.
    """
    marked = 0
    for para in paragraphs:
        if para.get("ru") or para.get("nothing"):
            continue
        rows = [str(row).strip() for row in (para.get("lines") or []) if str(row).strip()]
        if len(rows) >= 2 and all(line_covered(row) for row in rows):
            para["nothing"] = True
            marked += 1
    return marked


NUMBERED = re.compile(r"^\{n\}\.\s*")
UPGRADE_TAIL = re.compile(r"[\s✪➊-➓]+$")

# ⚠️ ПРИЗНАК «ВСЕ СЛОВА С ЗАГЛАВНОЙ» ЗДЕСЬ ПРОБОВАЛСЯ И ОТВЕРГНУТ.
#
# Он напрашивается: имя предмета бывает разрезано переносом («…Crab Hat of» /
# «Celebration»), и в каталоге такого куска нет. Но замер по УЖЕ КУПЛЕННОМУ
# показал 234 задетых абзаца — «Cost {n} Coins», «Sell Price {n} Coins»,
# «Reward {n} Bingo Point». Это ровно та грабля, что записана в CLAUDE.md
# про Title Case (516 переведённых записей), просто с другой стороны.
# Витрина музея остаётся в очереди — она стоит одного лишнего абзаца
# в списке, а порча двухсот тридцати четырёх не стоит ничего.


def name_line(line: str, names: set[str]) -> bool:
    """
    Строка — это ИМЯ (предмета или игрока), а не текст.

    Снимаем номер списка («{n}. ») и наряд прокачки (звёзды, ступень ковки):
    имя от них не меняется, и по нему всё так же ищут на аукционе.
    """
    from make_queue import NICKNAME

    bare = UPGRADE_TAIL.sub("", NUMBERED.sub("", line.strip()))
    bare = bare.lstrip("- ").strip()
    if not bare:
        return True
    # Дырка {s} — это НИК по построению: мод подставляет туда имя игрока.
    if bare == "{s}":
        return True
    return bare in names or bool(NICKNAME.match(bare))


def mark_name_lists(paragraphs: list[dict]) -> int:
    """
    Помечает абзацы-ПЕРЕЧНИ имён: витрина музея, список игроков в саду.

    ⚠️ Почему их нельзя переводить, хотя слова там есть. Ключ абзаца строится
    по тексту, а текст у каждого игрока СВОЙ: «Top Items {n}. Snowman Mask
    {n} Coins {n}. Buzzing InfiniVacuum™ Hooverius…». Купленный перевод
    подойдёт ровно одному музею на свете и не совпадёт больше НИКОГДА —
    это та же комбинаторика, что у наборов зачарований.

    А переводить там и нечего: подписи («Top Items», «{n} Coins», «Players:»)
    закрыты построчно, остальное — имена предметов и ники, которые мы
    не переводим по решению игрока.

    ⚠️ Имена спрашиваем у КАТАЛОГА СЕРВЕРА (`protected.collect`), а не
    угадываем по форме: признак «строка с Заглавной» ловил бы и прозу.

    ⚠️ ИМЁН ДОЛЖНО БЫТЬ ДВА И БОЛЬШЕ — это перечень, а не подпись. Порог
    в одно имя проверку по уже купленному НЕ ПРОШЁЛ: под него попадали
    «Source: Moby» и «Source: Rosemary», где имя одно, а «Source:»
    переводится, — то есть законно купленные абзацы. Прогон признака
    по сделанному и нужен ровно для этого.
    """
    from protected import collect

    names = collect()
    marked = 0
    for para in paragraphs:
        if para.get("ru") or para.get("nothing"):
            continue
        rows = [str(row).strip() for row in (para.get("lines") or []) if str(row).strip()]
        if len(rows) < 2:
            continue
        named = [row for row in rows if name_line(row, names)]
        if len(named) < 2:
            continue
        if all(line_covered(row) or name_line(row, names) for row in rows):
            para["nothing"] = True
            marked += 1
    return marked


def count_enchants(rows: list[str]) -> int:
    """
    Сколько зачарований в абзаце — по строкам И по сегментам через запятую.

    Отдельной функцией, чтобы признак был один и его можно было прогнать
    по корпусу без API: фильтр «переводить нечего» опаснее отсутствия перевода —
    он делает строку невидимой для всех отчётов, и в проекте это уже стоило
    824 спрятанных строк.
    """
    from make_queue import ENCHANT_HEAD

    found = 0
    for row in rows:
        if ENCHANT_HEAD.match(row):
            found += 1
            continue
        # Список через запятую: каждый сегмент обязан быть «Имя УРОВЕНЬ».
        # Требуем ДВУХ сегментов и чтобы подошли ВСЕ — иначе проза с запятой
        # («Grants +5 Health, which increases…») сошла бы за список.
        parts = [part.strip() for part in row.split(",") if part.strip()]
        if len(parts) >= 2 and all(ENCHANT_HEAD.match(part) for part in parts):
            found += len(parts)
    return found


def toggle_names() -> set[str]:
    """
    Названия из ВЫКЛЮЧЕННЫХ словарей: переводить их нельзя.

    ⚠️ «Выключено» — это решение игрока НЕ переводить, а не отсутствие перевода.
    Модель об этом знать неоткуда: она видит голый английский текст. Так «Growth V
    Grants +5 Health» и превратилось в «Рост V Даёт +5 к здоровью» — 175 абзацев,
    где имя кастомного зачарования вшито в оплаченный перевод, и строчные правила
    туда не достают.

    Берём только имена (glossary), а не шаблоны: шаблон не подставишь в текст.
    """
    packs = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
    names: set[str] = set()
    for path in packs.rglob("*.json"):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if pack.get("default") is not False:
            continue
        # ⚠️ Ванильные названия (значение «@block.minecraft.anvil») сюда НЕ идут:
        # их выключатель работает уже в моде, а корпус абзацев их и не содержит
        # (перевод берётся у самой игры). Защищаем только текстовые имена.
        names.update(key for key, value in (pack.get("glossary") or {}).items()
                     if isinstance(value, str) and not value.startswith("@")
                     and len(key) > 2)

    # ⚠️ Слово, которое переводит ВКЛЮЧЁННЫЙ словарь, защищать нельзя: среди
    # имён зачарований есть «Wisdom», «Experience», «Growth», «Forest»,
    # «Blacksmith», и те же слова живут в прозе как характеристики и места
    # («Wisdom Stats» — это «Мудрость»). 14 абзацев ушли в брак за правильный
    # перевод, пока фильтра не было.
    #
    # ⚠️ А общий protected.resolve_collisions тут НЕ ГОДИТСЯ: он видит имя
    # в глоссарии выключенного пакета и считает, что «словарь его переводит», —
    # и выбрасывает ВСЕ 93 до единого (проверено: стало 0, и беда вернулась).
    # Смотреть надо только на включённые словари. Та же ловушка, что была
    # с «термин — кусок более длинного»: защита, растущая вместе со словарём.
    translated: set[str] = set()
    for path in packs.rglob("*.json"):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if pack.get("default") is False:
            continue
        translated.update(pack.get("exact") or {})
        translated.update(pack.get("glossary") or {})
        # ⚠️ И ПРАВИЛА тоже: подписи характеристик живут именно в regex, поэтому
        # «Wisdom» и «Experience» иначе считались бы только зачарованиями —
        # а «Combat Wisdom» надо переводить. Разбор шаблона уже написан
        # в protected для той же беды («Held Item» попадал в защищённые).
        from protected import term_of_rule
        for rule in pack.get("regex") or []:
            term = term_of_rule(rule.get("p", ""))
            if term:
                translated.add(term)
    return {name for name in names if name not in translated}


def terms_for(chunk: list[dict], glossary_text: str) -> str:
    """Термины глоссария, встречающиеся в этой пачке. Остальные — деньги на ветер."""
    blob = SEP.join(item["text"] for item in chunk).lower()
    picked = [line for line in glossary_text.splitlines()
              if " = " in line and line.split(" = ", 1)[0].lower() in blob]
    if not picked:
        return ""
    return "ГЛОССАРИЙ (термины из этих абзацев):" + chr(10) + chr(10).join(picked) + SEP


LEVELLED = "([IVXLC]{1,6})\\b"


def enchants_in(text: str, names: set[str]) -> set[str]:
    """
    Имена, которые в ЭТОМ тексте стоят как зачарования, — то есть с уровнем.

    ⚠️ Слово само по себе ничего не решает: «Growth V» на броне — зачарование,
    а «growth» в описании зелья — обычный рост. Защищая имя целиком, мы держали
    10 абзацев непереведёнными («Rosewater Flask», «Bitter Iced Tea»), потому
    что модель совершенно правильно перевела там «Experience» как «опыт».
    Уровень римской цифрой — признак механический, и он различает оба случая.
    """
    return {name for name in names
            if re.search(re.escape(name) + r"\s+" + LEVELLED, text)}


def keep_for(chunk: list[dict], keep: set[str]) -> str:
    """
    Названия зачарований, встреченные В ЭТОЙ пачке: их переводить нельзя.

    ⚠️ Общего списка в системной части НЕ ХВАТИЛО — проверено на живой пачке:
    модель видела все 93 имени и всё равно перевела «Growth» как «Рост»
    в 9 абзацах из 12. Среди имён есть обычные слова (Growth, Wisdom, Compact),
    и в сплошном списке они теряются. Названные ПОИМЁННО рядом с текстом,
    где они встретились, работают — тот же приём, что с терминами глоссария.
    """
    blob = SEP.join(item["text"] for item in chunk)
    picked = sorted(enchants_in(blob, keep))
    if not picked:
        return ""
    return ("НЕ ПЕРЕВОДИТЬ (названия зачарований, игрок ищет по ним на аукционе): "
            + ", ".join(picked)
            + ". Оставь их латиницей КАК ЕСТЬ, вместе с римской цифрой уровня."
            + " ⚠️ Это НЕ относится к ванильным зачарованиям Minecraft"
            + " (Protection, Sharpness, Efficiency, Thorns, Smite, Growth Vanilla"
            + " и прочим из самой игры) — их переводи как обычно, «Protection V»"
            + " это «Защита V». В игре они и так показаны по-русски, и оставить"
            + " их латиницей значит выдать разнобой: у одной вещи «Защита V»,"
            + " у соседней «Protection V»." + SEP)


def jargon_for(chunk: list[dict]) -> str:
    """
    Характеристики-жаргон, встреченные В ЭТОЙ пачке.

    ⚠️ Отдельно от {@link keep_for}, потому что признак другой: зачарование
    узнаётся по римскому уровню («Growth V»), а «Treasure Chance» стоит в прозе
    как обычное словосочетание и ничем не помечено. Без поимённого напоминания
    модель переводит его совершенно естественно — на живом прогоне так ушло
    в брак 11 абзацев подряд («Fishing Rod», «Junk Sinker», шесть «Enchanted
    Book»), причём перевод был правильный, а забраковала его наша же защита.

    ⚠️ Общий список в системной части не работает — это уже проверено на
    зачарованиях: модель видела все 93 имени и всё равно переводила. Названные
    рядом с текстом, где встретились, работают.
    """
    import terms
    jargon = terms.of("stat_jargon")
    blob = SEP.join(item["text"] for item in chunk)
    picked = sorted(name for name in jargon
                    if re.search(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])", blob))
    if not picked:
        return ""
    return ("НЕ ПЕРЕВОДИТЬ (названия характеристик, игрок знает их по-английски "
            "и ищет по ним гайды): " + ", ".join(picked)
            + ". Оставь их латиницей КАК ЕСТЬ, даже если рядом стоит русский текст"
            + " и по-русски они звучали бы естественнее. Падеж должен брать"
            + " соседнее русское слово: «+{n} к характеристике Magic Find»,"
            + " а не «+{n} магического поиска»." + SEP)


def colors_for(chunk: list[dict]) -> None:
    """
    Кладёт каждому абзацу разметку оригинала — если цвета для него известны.

    ⚠️ Это та самая связка, которой не было. Правило про маркеры {c1} в RULES
    стояло с самого начала, но список цветов в запрос никогда не подавали —
    значит условие «списка цветов нет, маркеров быть не должно» срабатывало
    ВСЕГДА, и каждый прогон пополнял дыру плоскими переводами. Разметку потом
    докупали вторым проходом (color_lore.py) по $0.0018 за абзац — и только
    там, куда доходили руки: 62% размечено, остальное мод угадывает.

    Цвета берутся оттуда же, откуда их берёт color_lore: репозиторий NEU
    и живой дамп игры. Одна реализация на оба инструмента — копия разошлась бы.
    """
    try:
        from color_lore import coloured_lore, mark_original
    except ImportError:
        return
    lore = coloured_lore()
    if not lore:
        return
    for para in chunk:
        lines = lore.get(para["text"])
        if not lines:
            continue
        marked, codes, body = mark_original(lines)
        if not codes:
            continue          # одноцветный абзац — размечать нечего
        # ⚠️ ЧИСЛА В РАЗМЕТКЕ ОБЯЗАНЫ БЫТЬ ОБОБЩЕНЫ, как в ключе абзаца.
        #
        # Ключ строится по обобщённому тексту («+{n} Speed for {n} seconds»),
        # а источники цвета — NEU, аукцион, живой дамп — хранят строки
        # с НАСТОЯЩИМИ числами. Отправляя разметку как есть, мы показывали
        # модели «+20 Speed for 10 seconds», и она честно возвращала перевод
        # с числами: «+20 к скорости на 10 секунд». Дырок в нём не оставалось,
        # и accept() браковал такой перевод целиком.
        #
        # Цена промаха измерена: из пачечного прогона на 1781 абзац принято
        # было 633, а 1139 отбраковано «изменилось число дырок» — то есть
        # две трети оплаченной работы. Это третий раз, когда обобщение
        # применили к одной стороне из двух (см. граблю про имя предмета
        # в ключе и про сбор корпуса).
        marked = generalize(marked)
        if HOLES.findall(marked) != HOLES.findall(para["text"]):
            # Разметка не сошлась с ключом — отправлять её опаснее, чем
            # остаться без цвета: перевод вернётся с чужими числами.
            continue
        para["_marked"] = marked
        para["_codes"] = codes
        para["_body"] = body


# Маркеры разметки: внутри них цифры («{c1}», «{i2}»), и обобщать их нельзя
MARKERS = re.compile(r"\{/?[ci]\d+\}")
HOLES = re.compile(r"\{[ns]\}")


def generalize(text: str) -> str:
    """
    Числа -> {n}, но маркеры разметки не трогаем.

    ⚠️ Обобщать строку целиком нельзя: «{c1}» содержит цифру, и общий проход
    превратил бы маркер в «{c{n}}». Та же грабля, что в моде, где обобщение
    шаблона съедало §-коды: режем строку на куски и обобщаем только текст
    между маркерами.
    """
    from pkey import NUMBER
    out, last = [], 0
    for match in MARKERS.finditer(text):
        out.append(NUMBER.sub("{n}", text[last:match.start()]))
        out.append(match.group())
        last = match.end()
    out.append(NUMBER.sub("{n}", text[last:]))
    return "".join(out)


def build_user(chunk: list[dict], glossary_text: str = "", keep: set[str] | None = None) -> str:
    parts = []
    for i, para in enumerate(chunk):
        # Предмет тут — ПРИМЕР, а не единственный владелец: один и тот же абзац
        # встречается у сотни предметов. Частота как раз и подсказывает модели,
        # что фраза общая и переводить её надо нейтрально.
        item = para.get("item") or "неизвестно"
        count = para.get("count") or 1
        head = f"АБЗАЦ {i} — предмет: {item}"
        if count > 1:
            head += f" (и ещё {count - 1} предметов)"
        # ⚠️ Если цвета известны — показываем оригинал С МАРКЕРАМИ. Модель
        # переносит {c1} вместе со словом, в которое оно превратилось, и цвет
        # выходит точным вместо угаданного. Стоит это почти ничего: маркеры
        # короче любого пояснения, а второй платный проход отпадает целиком.
        source = para.get("_marked") or para["text"]
        masked, _ = mask_icons(source)
        parts.append(head + "\n" + masked)
    return (keep_for(chunk, keep or set())
            + jargon_for(chunk)
            + terms_for(chunk, glossary_text)
            + "Переведи каждый абзац целиком. Верни по одному переводу на каждый номер." + SEP
            + (chr(10) + chr(10)).join(parts))


def build_review(chunk: list[dict], translated: dict[int, str]) -> str:
    """Показывает проверяющему пары «было — стало». Значки не маскируем:
    их целость всё равно перепроверит accept(), а лишний слой тут только мешал бы."""
    parts = []
    for i, para in enumerate(chunk):
        if i not in translated:
            continue
        parts.append(f"АБЗАЦ {i}\nБЫЛО:  {para['text']}\nСТАЛО: {translated[i]}")
    return "Проверь перевод. Верни только те номера, где есть ошибка.\n\n" + "\n\n".join(parts)


def review_batch(client, args, chunk: list[dict], raw: dict[int, str],
                 guarded: set[str], usage: dict) -> int:
    """
    Второй проход: свежий запрос ищет искажённый смысл, расхождения с глоссарием
    и несогласованность. Проверяющий не знает, что переводил он же, — поэтому
    замечает больше, чем самопроверка.

    Правки идут через те же механические проверки, что и перевод: «исправление»,
    потерявшее значок или дырку {n}, принято не будет.

    Возвращает, сколько абзацев поправил. Меняет raw на месте.
    """
    if not raw:
        return 0
    # ⚠️ Импорт ЗДЕСЬ. Функцию вынесли из main(), а имя as_prompt осталось
    # видно только внутри main() — и весь проход из 112 запросов упал на
    # NameError, не отправив ни одного. Стоило это не денег, а часа времени
    # и доверия к отчёту «переведено 0».
    from protected import as_prompt
    try:
        response = client.messages.create(
            model=MODEL, max_tokens=16000,
            system=[{"type": "text",
                     "text": REVIEW_RULES + SEP + as_prompt(guarded) + SEP + glossary(),
                     "cache_control": {"type": "ephemeral"}}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA},
                           "effort": args.effort},
            messages=[{"role": "user", "content": build_review(chunk, raw)}],
        )
        usage["requests"] += 1
        usage["in"] += getattr(response.usage, "input_tokens", 0)
        usage["out"] += getattr(response.usage, "output_tokens", 0)
        usage["cache_read"] += getattr(response.usage, "cache_read_input_tokens", 0)
        usage["cache_write"] += getattr(response.usage, "cache_creation_input_tokens", 0)
        fixes = json.loads("".join(b.text for b in response.content if b.type == "text"))
        changed = 0
        for item in fixes.get("paragraphs") or []:
            index, russian = item.get("i"), item.get("ru")
            if isinstance(index, int) and index in raw                     and isinstance(russian, str) and russian.strip()                     and russian.strip() != raw[index].strip():
                raw[index] = russian
                changed += 1
        print(f"    проверка поправила: {changed} из {len(raw)}")
        return changed
    except (json.JSONDecodeError, Exception) as exception:
        print(f"    ! проверка не прошла: {exception}")
        return 0


def save(path: Path, data: dict) -> None:
    """
    Сохранение ПОСЛЕ КАЖДОЙ ПАЧКИ, и атомарно.

    Прогон всего корпуса — это 105 запросов и около часа. Файл писался один раз
    в самом конце: обрыв сети, Ctrl+C или упавший процесс выбрасывали всё
    оплаченное разом. Атомарно — потому что при обрыве прямо во время записи
    на диске остался бы обрезанный json, а это хуже потери одного захода:
    следующий запуск не поднял бы вообще ничего.
    """
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    temp.replace(path)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Перевод описаний абзацами")
    parser.add_argument("file")
    parser.add_argument("--limit", type=int, default=0, help="сколько абзацев перевести")
    parser.add_argument("--recheck", action="store_true",
                        help="не переводить, а ПРОВЕРИТЬ уже переведённое вторым проходом")
    parser.add_argument("--review", action="store_true",
                        help="второй проход: модель проверяет свой же перевод (дороже, качественнее)")
    parser.add_argument("--redo", action="append", default=[], metavar="ТЕКСТ",
                        help="сбросить перевод у абзацев с этим текстом и перевести заново")
    parser.add_argument("--effort", default="high",
                        choices=["low", "medium", "high", "xhigh", "max"],
                        help="глубина размышлений: дешевле/дороже (по умолчанию high)")
    parser.add_argument("--forbid", default="", metavar="ГРУППЫ",
                        help="не переводить группы терминов через запятую "
                             "(python tools/terms.py — какие есть)")
    # ⚠️ Batch API — не сторонний сервис, а асинхронный режим той же Anthropic:
    # та же модель и тот же запрос за −50%. Ответ обычно за минуты, предел сутки.
    # Плата за это одна: результат нельзя посмотреть сразу, поэтому режим
    # НЕ по умолчанию — на новом материале сперва хочется взглянуть глазами.
    parser.add_argument("--batch", action="store_true",
                        help="через Batch API: вдвое дешевле, ответ до часа")
    parser.add_argument("--collect", metavar="BATCH_ID",
                        help="забрать готовый batch, отправленный раньше")
    args = parser.parse_args()

    # ⚠️ Опечатку в имени группы ловим ЗДЕСЬ, до ключа API и чтения корпуса:
    # ошибка ввода не должна требовать внешних зависимостей, чтобы обнаружиться.
    if args.forbid:
        import terms
        unknown = [name.strip() for name in args.forbid.split(",")
                   if name.strip() and not terms.of(name.strip())]
        if unknown:
            print(f"нет таких групп: {', '.join(unknown)}")
            print(f"есть: {', '.join(sorted(terms.all_groups()))}")
            return 1

    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path
    data = json.loads(path.read_text(encoding="utf-8"))
    paragraphs = data.get("paragraphs") or []
    if not paragraphs:
        print(f"в файле нет абзацев: {path}")
        print("корпус делается так:  python tools/make_paragraphs.py data/work/lore_tooltips.json")
        return 1

    # Пересмотр решения о термине. Заменять слово в готовом переводе НЕЛЬЗЯ:
    # английское слово не склоняется, а русское склоняется, и «в своём Bestiary»
    # тупой заменой станет «в своём Бестиарий». Поэтому не правим, а переводим
    # такие абзацы заново — их обычно десятки, это копейки.
    if args.redo:
        dropped = 0
        for para in paragraphs:
            if not para.get("ru"):
                continue
            haystack = para["text"] + "\n" + para["ru"]
            if any(needle in haystack for needle in args.redo):
                para.pop("ru")
                dropped += 1
        print(f"сброшено переводов под --redo: {dropped}")
        if dropped:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # ⚠️ Проверка идёт по УЖЕ переведённому, а перевод — по пустому.
    #
    # Отдельным режимом, а не ключом к прогону, нарочно: проверяющий внутри
    # прогона видит только то, что перевели ПРЯМО СЕЙЧАС. Всё, что переведено
    # раньше, он не увидел бы никогда — а именно там и накопились сомнительные
    # места. Плюс так проверку можно повторить после правки правил, ничего
    # не переводя заново.
    if args.recheck:
        # ⚠️ keep — «решено, не трогать». Ставится, когда перевод выбран
        # человеком: проверяющий об этом не знает и переправит обратно, а выбор
        # молча потеряется. Это уже третий случай в проекте, когда скрипт
        # норовит затереть ручную работу (первые два — make_paragraphs.py
        # и заготовка зачарований), и каждый раз пропажу замечали не сразу.
        pinned = [p for p in paragraphs if p.get("ru") and p.get("keep")]
        pending = [p for p in paragraphs if p.get("ru") and not p.get("keep")]
        if pinned:
            print(f"не трогаю (решено человеком): {len(pinned)}")
        occurrences = sum(p.get("count") or 1 for p in paragraphs)
        print(f"файл: {path}")
        print(f"абзацев всего: {len(paragraphs)}, ПРОВЕРЯЕМ переведённые: {len(pending)}")
    else:
        # ⚠️ Абзац, в котором кроме ИМЁН ПРЕДМЕТОВ ничего нет, отправлять нельзя:
        # переводить там нечего по замыслу, а любой перевод портит имя и абзац
        # отбраковывается. Такие абзацы возвращались в запрос каждый заход —
        # 36 бесполезных из 47 в последнем, то есть почти весь его $1.09.
        marked = mark_nothing(paragraphs)
        # ⚠️ И абзацы-СПИСКИ: мод их не склеит, значит перевод не дойдёт
        # до экрана, а строки уже уходят в очередь построчно.
        lists = mark_lists(paragraphs)
        # ⚠️ И абзацы-КОМБИНАЦИИ зачарований: мод собирает их из купленных
        # секций сам, а наборов у игроков бесконечно много.
        combos = mark_enchant_combos(paragraphs)
        # ⚠️ И абзацы, все строки которых УЖЕ закрыты построчно: блок
        # характеристик прокачанного предмета («Damage: +{n} / Mining Speed:
        # +{n} / Gemstones: []») прозы не содержит вовсе, а каждая его строка
        # переводится правилом. Цельный перевод не добавил бы ничего.
        tables = mark_stat_tables(paragraphs)
        # ⚠️ И абзацы-ПЕРЕЧНИ имён (витрина музея, список игроков в саду):
        # ключ у них свой у каждого игрока, купленный перевод не совпадёт
        # больше никогда, а переводить там нечего — подписи закрыты построчно.
        name_lists = mark_name_lists(paragraphs)
        if marked or lists or combos or tables or name_lists:
            if marked:
                print(f"помечено «переводить нечего» (одни имена предметов): {marked}")
            if lists:
                print(f"помечено «список» (мод не склеит, идут построчно): {lists}")
            if combos:
                print(f"помечено «комбинация зачарований» (мод соберёт по секциям): {combos}")
            if tables:
                print(f"помечено «всё закрыто построчно» (характеристики): {tables}")
            if name_lists:
                print(f"помечено «перечень имён» (ключ у каждого игрока свой): {name_lists}")
            path.write_text(json.dumps({"paragraphs": paragraphs}, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        skipped = sum(1 for p in paragraphs if p.get("nothing") and not p.get("ru"))
        pending = [p for p in paragraphs if not p.get("ru") and not p.get("nothing")]
        occurrences = sum(p.get("count") or 1 for p in paragraphs)
        print(f"файл: {path}")
        print(f"абзацев всего: {len(paragraphs)}, ждут перевода: {len(pending)}")
        if skipped:
            print(f"  не спрашиваю: {skipped} — в них только имена предметов"
                  f" (поле nothing, убрать = спросить снова)")
    if not pending:
        return 0
    if args.limit:
        # Корпус отсортирован так: сперва абзацы, которые игрок ВИДЕЛ в игре,
        # потом остальные по частоте. Значит первые N — это лучшее, что можно
        # купить на эти деньги, а не случайные предметы из выгрузки.
        pending = pending[:args.limit]
        covers = sum(p.get("count") or 1 for p in pending)
        live = sum(1 for p in pending if p.get("live"))
        print(f"беру первые {len(pending)} — это {covers * 100 // occurrences}% всех вхождений")
        if live:
            print(f"  из них {live} мод уже показывал в игре")

    # Ключ проверяем ДО первого запроса: иначе получаем четыре подряд 401
    # с невнятным текстом вместо одной понятной подсказки.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from apikey import check as check_key
    if not check_key():
        return 1

    # Имена NPC и названия мест: модель видит голый текст без цвета, по которому
    # их узнаёт игрок, — значит нужен явный список, а не надежда на догадку.
    from protected import collect, resolve_collisions, as_prompt
    from restore_icons import icons_of
    guarded = resolve_collisions(collect())
    # ⚠️ Имена из выключенных словарей защищаем ТАК ЖЕ, как имена NPC: и то,
    # и другое — решение не переводить, а модель видит только голый текст.
    # Проверку делает accept() через check_block: имя пропало — абзац в брак.
    # ⚠️ Через resolve_collisions — иначе защита накрывает ОБЫЧНЫЕ слова.
    # Среди имён зачарований есть «Wisdom», «Experience», «Growth», «Forest»,
    # «Blacksmith», и те же слова живут в прозе как характеристики и места:
    # «Wisdom Stats» — это «Мудрость», а не зачарование. Без фильтра 14 абзацев
    # ушли в брак за то, что их перевели ПРАВИЛЬНО. Та же грабля, что с
    # подсвеченным «Defense»: свой словарь важнее списка имён.
    toggles = toggle_names()
    guarded |= toggles
    print(f"защищено имён из выключенных словарей: {len(toggles)}")

    # Запрет ЦЕЛОЙ ГРУППОЙ: «--forbid enchant» вместо перечисления 93 названий,
    # которые вдобавок разъедутся со словарём при первом же пополнении.
    #
    # ⚠️ Мимо resolve_collisions, как и toggles: тот выбрасывает слова, которые
    # переводит наш же словарь, — а здесь ровно это и просят, «перестань
    # переводить то, что переводил».
    #
    # ⚠️ И ОТДЕЛЬНОЙ переменной, потому что в accept() уходит не весь guarded,
    # а «(guarded - toggles) | enchants_in(...)». Стоило вынести перевод жаргона
    # в словарь с «default»: false — и те же слова попали в toggles, вычитание
    # выбросило их из защиты, а enchants_in берёт только имена с римским уровнем
    # («Growth V»), которого у характеристик не бывает. Защита отключала сама
    # себя: на живом прогоне 105 абзацев вернулись с «магическим поиском»,
    # хотя check_block такой перевод бракует — его просто не спрашивали.
    by_group: set[str] = set()
    if args.forbid:
        import terms
        asked = [name.strip() for name in args.forbid.split(",") if name.strip()]
        by_group = terms.forbidden(asked) - terms.forbidden()
        guarded |= by_group
        print(f"запрещено группами {', '.join(asked)}: {len(by_group)} слов")

    # ВНИМАНИЕ. Глоссарий в КЭШ НЕ КЛАДЁМ: системная часть перечитывается
    # каждым запросом, и полный словарь весит больше всего остального вместе
    # взятого. Нужные термины уезжают вместе с самой пачкой — их там единицы.
    # Тот же приём в translate_ai.py срезал две трети счёта.
    full_glossary = glossary()
    system = [{"type": "text", "text": RULES + SEP + as_prompt(guarded),
               "cache_control": {"type": "ephemeral"}}]
    client = Anthropic()

    done = 0
    icons_fixed = 0
    reviewed = 0
    # Считаем реальный расход: цена прогона должна быть измерена, а не угадана
    usage = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0, "requests": 0}

    if args.collect:
        taken = collect_batch(client, args.collect, path, data,
                              guarded, toggles, by_group)
        print(f"\nзабрано из batch: {taken} переводов")
        print("Дальше: python tools/merge_paragraphs.py")
        return 0

    if args.batch:
        if args.recheck or args.review:
            print("--batch пока без проверяющего прохода: он требует ответа "
                  "на первый запрос, а тут ответа ждать до часа")
            return 1
        taken = run_batch(client, path, data, pending, system, full_glossary,
                          toggles, guarded, by_group, args.effort)
        print(f"\nпереведено: {taken}")
        print("Дальше: python tools/merge_paragraphs.py")
        return 0

    for start in range(0, len(pending), BATCH):
        chunk = pending[start:start + BATCH]
        print(f"  абзацы {start + 1}-{start + len(chunk)} из {len(pending)}...", flush=True)
        # ⚠️ Цвета готовим ДО запроса: тогда модель сразу вернёт размеченный
        # перевод, и второй платный проход не понадобится. Раньше этого шага
        # не было вовсе, и каждый прогон пополнял дыру плоскими переводами.
        if not args.recheck:
            colors_for(chunk)
        # В режиме проверки переводить нечего: перевод уже лежит в корпусе,
        # первый запрос был бы выброшенными деньгами.
        if args.recheck:
            raw = {i: para["ru"] for i, para in enumerate(chunk) if para.get("ru")}
            reviewed += review_batch(client, args, chunk, raw, guarded, usage)
            for index, russian in sorted(raw.items()):
                para = chunk[index]
                # имя зачарования защищаем только там, где оно стоит С УРОВНЕМ:
                # «Growth V» — зачарование, «growth» в описании зелья — нет
                checked, reason = accept(
                    para, russian,
                    (guarded - toggles) | enchants_in(para["text"], toggles) | by_group)
                if checked is None:
                    REJECTED[reason] += 1
                    print(f"    ! абзац {index}: правка отбракована ({reason}) — оставляю прежнюю")
                    continue
                if checked != para["ru"]:
                    para["ru"] = checked
                    done += 1
            save(path, data)
            continue

        try:
            response = client.messages.create(
                model=MODEL, max_tokens=16000, system=system,
                output_config={"format": {"type": "json_schema", "schema": SCHEMA},
                               "effort": args.effort},
                messages=[{"role": "user",
                           "content": build_user(chunk, full_glossary, toggles)}],
            )
        except Exception as exception:
            print(f"  ! {exception}")
            # ⚠️ Кончились деньги или сломан ключ — само не починится.
            # Без этой проверки скрипт честно долбился во все оставшиеся пачки
            # с одной и той же ошибкой: на 300 абзацах это 6 бессмысленных
            # запросов, на всём корпусе — 110, и настоящая причина тонет
            # в простыне одинаковых сообщений.
            text = str(exception).lower()
            if any(stop in text for stop in
                   ("credit balance", "authentication", "invalid x-api-key",
                    "permission", "billing")):
                print("\nДальше идти незачем — это не сбой запроса, а доступ к API.")
                print("Пополнить: console.anthropic.com -> Plans & Billing")
                print("(баланс API отдельный от подписки Claude Code)")
                break
            continue
        if response.stop_reason == "refusal":
            print("  ! модель отказалась")
            continue
        if response.stop_reason == "max_tokens":
            # У Opus 5 размышления включены по умолчанию и тоже едят max_tokens
            print("  ! ответ обрезан по max_tokens — часть абзацев потеряна")

        usage["requests"] += 1
        usage["in"] += getattr(response.usage, "input_tokens", 0)
        usage["out"] += getattr(response.usage, "output_tokens", 0)
        usage["cache_read"] += getattr(response.usage, "cache_read_input_tokens", 0)
        usage["cache_write"] += getattr(response.usage, "cache_creation_input_tokens", 0)

        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            print("  ! ответ не разобрался")
            continue

        raw: dict[int, str] = {}
        for item in payload.get("paragraphs") or []:
            index = item.get("i")
            russian = item.get("ru")
            if isinstance(index, int) and 0 <= index < len(chunk) \
                    and isinstance(russian, str) and russian.strip():
                raw[index] = russian

        # Второй проход: свежий запрос ищет искажённый смысл, расхождения
        # с глоссарием и несогласованность. Проверяющий не знает, что переводил
        # он же, — поэтому замечает больше. Правки идут через те же механические
        # проверки: «исправление», потерявшее значок, принято не будет.
        if args.review and raw:
            reviewed += review_batch(client, args, chunk, raw, guarded, usage)

        taken, fixed = apply_replies(chunk, raw, guarded, toggles, by_group)
        done += taken
        icons_fixed += fixed

        # Пачка разобрана — кладём на диск сразу, не дожидаясь конца прогона
        save(path, data)

    save(path, data)
    if icons_fixed:
        print(f"иконок восстановлено в абзацах: {icons_fixed}")

    total_done = sum(1 for p in paragraphs if p.get("ru"))
    covered = sum(p.get("count") or 1 for p in paragraphs if p.get("ru"))
    left = len(paragraphs) - total_done
    print(f"\n{'исправлено' if args.recheck else 'переведено'} за заход: {done}")
    print(f"всего в файле: {total_done}/{len(paragraphs)} абзацев "
          f"— это {covered * 100 // occurrences}% вхождений в подсказках")

    if done:
        # чтение кэша — вдесятеро дешевле входных, запись — в 1.25 раза дороже
        cost = ((usage["in"] / 1e6 * 5)
                + (usage["out"] / 1e6 * 25)
                + (usage["cache_read"] / 1e6 * 0.5)
                + (usage["cache_write"] / 1e6 * 6.25))
        print(f"\nрасход: вход {usage['in']}, из кэша {usage['cache_read']}, "
              f"в кэш {usage['cache_write']}, выход {usage['out']}")
        print(f"стоимость захода: ${cost:.3f}  (~${cost / done:.4f} за абзац)")

        # ⚠️ Прикидку НЕЛЬЗЯ считать «цена захода × сколько осталось».
        # Правила с глоссарием пишутся в кэш ОДИН раз, а стоит запись в 12 раз
        # дороже чтения. Первый запрос платит её целиком, и наивная экстраполяция
        # завышала остаток вдвое-впятеро — на такой цифре легко отказаться
        # от прогона, который на самом деле по карману.
        requests = max(usage["requests"], 1)
        prefix = usage["cache_write"] or (usage["cache_read"] // requests)
        per_request = ((usage["in"] / requests / 1e6 * 5)
                       + (usage["out"] / requests / 1e6 * 25)
                       + (prefix / 1e6 * 0.5))
        if left:
            need = -(-left // BATCH)          # округление вверх
            rest = need * per_request
            print(f"\nостаток: {left} абзацев = {need} запросов по ~${per_request:.3f}")
            print(f"  обычным режимом: ${rest:.2f}")
            print(f"  через Batch API: ${rest / 2:.2f}  (вдвое дешевле, ответ в течение часа)")
            print(f"  (в цене запроса ${prefix / 1e6 * 0.5:.3f} — перечитывание кэша правил)")
        print(f"эффект от --effort {args.effort}: размышления идут в выход по $25/млн, "
              f"так что medium стоит замерить отдельно")
    # ⚠️ Сводка причин брака. Без неё «отбраковано N» — число без смысла:
    # непонятно, промах модели это, наша защита или устаревший фильтр.
    # Оплаченный и выброшенный абзац стоит ровно столько же, сколько принятый.
    summary = rejection_summary()
    if summary:
        print(summary)
    print("\nДальше: разложить абзацы в секцию paragraphs словаря")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
