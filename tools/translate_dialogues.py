"""
Перевод реплик NPC — СРАЗУ С РАЗМЕТКОЙ ЦВЕТА.

⚠️ Главное отличие от `translate_ai.py`. Реплики взяты с вики в том виде,
в каком их шлёт Hypixel: «&e[NPC] &2Lumber Jack&f: We will be &aForaging&f!».
Значит разметка нам дана ДАРОМ, и терять её нельзя — иначе подсветку придётся
либо угадывать в моде (переведённое слово её теряет), либо покупать ОТДЕЛЬНЫМ
прогоном по всем девяти тысячам реплик (~$16 по замерам `color_lore`).

Три вещи, на которых здесь экономятся деньги, — и все три опираются на замер,
а не на предположение (352 реплики шести NPC):

 1. ПРЕФИКС «[NPC] Имя: » не отправляется вовсе. Имя не переводится, но занимало
    бы место и во входе, и в выходе: это 20% всех знаков. Возвращается
    механически — он постоянный, ошибиться негде.
 2. МАРКЕРЫ ЦВЕТА нужны не всем. У 209 реплик из 352 (59%) цвет стоит ТОЛЬКО
    в префиксе, то есть в теле красить нечего — такая реплика уходит как чистый
    текст. Маркеры получают лишь оставшиеся 41%.
 3. ГРУППИРОВКА ПО ГОВОРЯЩЕМУ. Реплики одного персонажа идут одной пачкой:
    модель видит его манеру речи целиком. Это не про цену, а про качество —
    но и кэш при этом стабильнее.

⚠️ Маркеры, а не §-коды. Код невидим в тексте, и модель его теряет: на иконках
это уже проверено — 12 потерь из 50, а после замены на «{i1}» ноль. Цвет прячем
тем же приёмом: «{c1}…{/c1}».

Запуск:
  python tools/translate_dialogues.py data/work/npc_test.json --limit 100 --sync
  python tools/translate_dialogues.py data/work/npc_dialogues.json --limit 500
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import protected  # noqa: E402
from translate_ai import MODEL, SCHEMA, note_usage, report_usage  # noqa: E402

_CLIENT = None


def client():
    """Подключение заводим ЛЕНИВО: сухой прогон не должен требовать ключа."""
    global _CLIENT
    if _CLIENT is None:
        from anthropic import Anthropic
        _CLIENT = Anthropic()
    return _CLIENT

# «&e[NPC] &2Lumber Jack&f: » — говорящий. Цвет имени бывает любой.
# ⚠️ Кодов подряд бывает НЕСКОЛЬКО: «&e[NPC] &d&k----&f:» — имя обфусцировано
# (§k), то есть код цвета плюс код начертания. С одиночным «&x» такая реплика
# не распознавалась вовсе, и «[NPC]» уезжало в переводимый текст.
PREFIX = re.compile(r"^&e\[NPC\]\s*(?:&[0-9a-fk-or])*[^&:]*(?:&[0-9a-fk-or])*:\s*",
                    re.IGNORECASE)
CODE = re.compile(r"&([0-9a-fk-orA-FK-OR])")
MARK_OPEN = re.compile(r"\{c(\d+)\}")
MARK_CLOSE = re.compile(r"\{/c(\d+)\}")
HOLE = re.compile(r"\{[ns]\}")

BATCH_SIZE = 40

RULES = """Ты переводишь РЕПЛИКИ ПЕРСОНАЖЕЙ (NPC) из Hypixel SkyBlock на русский.
Это живая речь в чате игры, а не подписи интерфейса.

1. Пиши так, как говорил бы человек. Не канцелярит: «Заходи ещё!», а не
   «Осуществите повторное посещение». У персонажа есть характер — если он
   балагурит или ворчит, это должно остаться и по-русски.
2. Обращение к игроку — на «ты».
3. ИМЕНА НЕ ПЕРЕВОДИМ: персонажи, локации, предметы, мобы. По ним игрок ищет
   квесты и вещи на аукционе.
   АНГЛИЙСКОЕ ИМЯ НЕ СКЛОНЯЕТСЯ — не приделывай окончания и не пиши через
   апостроф. Нужен падеж — поставь русское слово-подпорку, падеж возьмёт оно:
      «go find Captain Baha in the Fishing Outpost!»
      ХОРОШО: «найди Captain Baha в локации Fishing Outpost!»
      ПЛОХО:  «в Fishing Outpost'е», «Captain Baha'у», «Капитана Баху»
   Подпорку ставь ТОЛЬКО когда без неё фраза разваливается.
4. МАРКЕРЫ ЦВЕТА «{c1}…{/c1}» перенеси: столько же, тех же номеров и вокруг ТЕХ
   ЖЕ слов по смыслу. Hypixel красит ими важное — название навыка, число, имя.
   Если слово переехало в другое место фразы, маркер едет вместе с ним.
   Не добавляй маркеров, которых не было.
5. Числа, проценты, {n}, {s} переноси без изменений — столько же и в том же
   порядке.
6. Значки и символы (✆ ✔ ❣ ⚔ и подобные) сохраняй на их местах.
7. Реплику, переводить которую нечего (одни имена, цифры, техническая метка),
   верни без изменений.
"""

REVIEW_RULES = """Ты проверяешь ЧУЖОЙ перевод реплик NPC из Hypixel SkyBlock.
Верни исправленный перевод для КАЖДОГО номера — даже если менять нечего.

Смотри в таком порядке:
1. Смысл не переврали? Обрывки и шутки — частый источник ошибок.
2. Английское имя не просклоняли и не перевели?
3. Маркеры {c1}…{/c1} на месте, вокруг тех же слов, номера те же?
4. Живая ли речь? Канцелярит в устах персонажа — ошибка, даже если смысл верен.
"""


def spans(colored: str, start: str = "") -> list[tuple[str, str]]:
    """
    Разбор строки с &-кодами на куски «код → текст».

    @param start код, действующий ДО первого символа. Для тела реплики это
                 последний код префикса: «…&f: » красит всё, что идёт дальше,
                 и без него первый кусок оказывался «без цвета» — а он-то
                 обычно и есть тело.
    """
    out: list[tuple[str, str]] = []
    colour = start
    mods = ""
    buffer = ""
    i = 0
    while i < len(colored):
        if colored[i] == "&" and i + 1 < len(colored) and CODE.match(colored[i:i + 2]):
            if buffer:
                out.append((colour + mods, buffer))
                buffer = ""
            code = colored[i + 1].lower()
            # ⚠️ Код бывает ЦВЕТОМ и НАЧЕРТАНИЕМ, и путать их дорого. В проекте
            # это уже стоило 288 испорченных абзацев: разбор брал последний код
            # и у «&e&lRIGHT CLICK» сохранял одну жирность, теряя жёлтый.
            # Цвет сбрасывает начертание, начертания копятся, «&r» сбрасывает всё.
            if code == "r":
                colour, mods = "", ""
            elif code in "klmno":
                mods += code if code not in mods else ""
            else:
                colour, mods = code, ""
            i += 2
            continue
        buffer += colored[i]
        i += 1
    if buffer:
        out.append((colour + mods, buffer))
    return out


def to_markers(body: str, start: str = "f") -> tuple[str, str, dict[int, str]]:
    """
    Тело реплики -> текст с маркерами.

    ⚠️ Цвет ТЕЛА (обычно «f») маркерами не помечаем: им покрашено почти всё,
    и разметка вокруг каждого слова только раздувала бы запрос. Помечаем ровно
    то, что от него отличается, — это и есть подсветка.

    @return текст с маркерами, код цвета тела, номер маркера -> код цвета
    """
    parts = spans(body, start)
    if not parts:
        return body, start, {}
    weight: dict[str, int] = defaultdict(int)
    for code, text in parts:
        weight[code] += len(text)
    base = max(weight, key=lambda c: weight[c])

    numbers: dict[str, int] = {}
    out: list[str] = []
    for code, text in parts:
        if code == base or not text.strip():
            out.append(text)
            continue
        number = numbers.setdefault(code, len(numbers) + 1)
        # Хвостовой пробел оставляем СНАРУЖИ маркера: он не часть подсветки,
        # а разделитель слов, и внутри маркера мешал бы искать границы.
        lead = text[:len(text) - len(text.lstrip())]
        tail = text[len(text.rstrip()):]
        out.append(f"{lead}{{c{number}}}{text.strip()}{{/c{number}}}{tail}")
    return "".join(out), base, {n: c for c, n in numbers.items()}


def codes(combo: str) -> str:
    """«fl» -> «§f§l». Пустая комбинация кодов не даёт."""
    return "".join("§" + c for c in combo)


def from_markers(text: str, base: str, palette: dict[int, str]) -> str:
    """Маркеры обратно в §-коды. Цвет тела возвращаем после каждой подсветки."""
    def open_code(match: re.Match) -> str:
        return codes(palette.get(int(match.group(1)), base))

    result = MARK_OPEN.sub(open_code, text)
    return MARK_CLOSE.sub(codes(base), result)


def accept(source_body: str, translated: str, marks: dict[int, str],
           guarded: set[str]) -> str | None:
    """Проверки на приёме. Возвращает причину отказа или None."""
    if not translated.strip():
        return "пустой перевод"
    opened = [int(n) for n in MARK_OPEN.findall(translated)]
    closed = [int(n) for n in MARK_CLOSE.findall(translated)]
    if sorted(opened) != sorted(closed):
        return "маркеры цвета не парные"
    # ⚠️ Сравниваем НАБОР номеров, а не их количество. Один и тот же маркер
    # законно встречается дважды: подсвеченное слово в переводе может
    # разъехаться на два места («…64 Birch Logs… эти брёвна…»). Строгая
    # сверка по количеству отбраковала 6 хороших переводов из 100 —
    # и это была придирка инструмента, а не ошибка модели.
    if set(opened) != set(marks):
        return f"маркеры не совпали: было {sorted(marks)}, стало {sorted(set(opened))}"
    # ⚠️ Вложенность запрещена: разворот в §-коды её не выразит.
    depth = 0
    for token in re.finditer(r"\{c(\d+)\}|\{/c(\d+)\}", translated):
        depth += 1 if token.group(1) else -1
        if depth > 1 or depth < 0:
            return "маркеры вложены друг в друга"
    if HOLE.findall(source_body) != HOLE.findall(translated):
        return "дырки {n}/{s} не совпали"
    clean = MARK_CLOSE.sub("", MARK_OPEN.sub("", translated))
    broken = protected.check_block(source_body, clean, guarded)
    if broken:
        return f"испорчено защищённое имя: {broken}"
    return None


def drop_speaker(item: dict, translated: str) -> str:
    """
    Снимает имя говорящего, если модель повторила его в начале реплики.

    ⚠️ Страховка НУЖНА, даже когда запрос составлен верно: имя приезжает
    вместе с подсказкой, и соблазн его повторить у модели остаётся. Проверка
    буквальная — «[Имя]» или «Имя:» ровно в начале, — чтобы не срезать
    имя, законно стоящее внутри фразы.
    """
    name = (item.get("npc") or "").strip()
    if not name:
        return translated
    for form in (f"[{name}]", f"{name}:"):
        if translated.startswith(form):
            return translated[len(form):].lstrip()
    return translated


def assemble(item: dict, translated: str) -> str:
    """
    Готовая строка для словаря: префикс + тело с вернувшимися §-кодами.

    ⚠️ Коды ТЕЛА выписываем в начало, если они отличаются от того, что задал
    префикс. Обычно тело белое («f»), и код не нужен — цвет уже действует.
    Но реплика бывает целиком ЖИРНОЙ («&f&l3 days later…»): тогда «fl» —
    самая частая комбинация, маркерами она не помечается, и без явного кода
    начертание пропадало бы молча. Круговой тест ловил ровно эти 30 реплик.
    """
    body = from_markers(drop_speaker(item, translated), item["base"], item["marks"])
    if item["base"] != item["start"]:
        body = codes(item["base"]) + body
    return item["prefix"].replace("&", "§") + body


def prepare(entries: dict[str, dict], limit: int) -> list[dict]:
    """Что отправляем: тело без префикса, с маркерами, сгруппировано по NPC."""
    todo: list[dict] = []
    for line, meta in entries.items():
        if meta.get("ru"):
            continue
        colored = meta.get("raw") or line
        match = PREFIX.match(colored)
        prefix = colored[:match.end()] if match else ""
        body = colored[match.end():] if match else colored
        # ⚠️ Цвет тела задаёт ПОСЛЕДНИЙ код префикса: «…&f: » красит всё
        # дальнейшее. Отрезав префикс, мы отрезали и его — и тело оказывалось
        # «без цвета», а разворот подставлял пустой «§».
        tail = spans(prefix)
        start = tail[-1][0] if tail else "f"
        marked, base, palette = to_markers(body, start)
        todo.append({
            "key": line, "npc": meta.get("npc") or "", "prefix": prefix,
            "text": marked, "base": base, "start": start, "marks": palette,
            "plain": CODE.sub("", body),
        })
    todo.sort(key=lambda item: (item["npc"], item["key"]))
    return todo[:limit] if limit else todo


def build_user(chunk: list[dict]) -> str:
    """
    ⚠️ Имя говорящего стоит В ШАПКЕ, а не перед каждой репликой.
    Сперва было «0. [Elle] текст», и модель приняла скобки за часть реплики:
    56 переводов из 94 начинались с лишнего «[Elle] ». Причём у другого NPC
    в той же пачке всё было чисто — то есть признак «иногда работает»,
    а это худший вид: на глаз не заметишь, пока не сверишь все.
    """
    who = chunk[0]["npc"]
    lines = [f"{i}. {item['text']}" for i, item in enumerate(chunk)]
    return (f"Говорит персонаж по имени {who}. Это подсказка о его характере "
            f"и манере речи — САМО ИМЯ в перевод не переноси.\n\n"
            "Переведи реплики. Верни перевод для КАЖДОГО номера, ничего "
            "не пропуская.\n\n" + "\n".join(lines))


def ask(system: list[dict], user: str) -> dict[int, str]:
    response = client().messages.create(
        model=MODEL, max_tokens=8000, system=system,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA},
                       "effort": "high"},
        messages=[{"role": "user", "content": user}])
    note_usage(response)
    text = "".join(block.text for block in response.content if hasattr(block, "text"))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        print("  ! ответ не разобрался как JSON")
        return {}
    return {item["i"]: (item.get("ru") or "").strip()
            for item in payload.get("translations") or []
            if isinstance(item.get("i"), int)}


STATE = ROOT / "data" / "work" / "_dialogue_batch.json"

# Batch API — та же модель и тот же запрос, но вдвое дешевле. Цены с прайса:
# вход $2.50, выход $12.50, чтение кэша $0.25, запись кэша $3.125 за миллион.
BATCH_PRICE = {"in": 2.50, "out": 12.50, "cache_read": 0.25, "cache_write": 3.125}


def batch_cost(totals: dict) -> float:
    return sum(totals.get(key, 0) * price / 1_000_000
               for key, price in BATCH_PRICE.items())


def send_batch(jobs: list[tuple[str, dict]]) -> str:
    """Отправляет пачки одним заданием. Возвращает его номер."""
    batch = client().messages.batches.create(requests=[
        {"custom_id": name, "params": params} for name, params in jobs])
    return batch.id


def wait_batch(batch_id: str, every: int = 30) -> None:
    """
    Ждёт готовности. ⚠️ Задание УЖЕ ОПЛАЧЕНО в момент отправки: бросить его
    на полпути значит выбросить деньги. Поэтому номер задания лежит на диске
    (`_dialogue_batch.json`) — прогон можно продолжить ключом --collect.
    """
    import time
    while True:
        state = client().messages.batches.retrieve(batch_id)
        status = getattr(state, "processing_status", "")
        counts = getattr(state, "request_counts", None)
        done = getattr(counts, "succeeded", "?") if counts else "?"
        print(f"    задание {batch_id}: {status}, готово {done}")
        if status == "ended":
            return
        time.sleep(every)


def read_batch(batch_id: str) -> dict[str, dict[int, str]]:
    """Ответы задания: custom_id -> {номер строки: перевод}."""
    out: dict[str, dict[int, str]] = {}
    for entry in client().messages.batches.results(batch_id):
        result = getattr(entry, "result", None)
        if getattr(result, "type", "") != "succeeded":
            print(f"    ! пачка {entry.custom_id}: {getattr(result, 'type', 'ошибка')}")
            continue
        message = result.message
        note_usage(message)
        text = "".join(block.text for block in message.content if hasattr(block, "text"))
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            print(f"    ! пачка {entry.custom_id}: ответ не разобрался как JSON")
            continue
        out[entry.custom_id] = {
            item["i"]: (item.get("ru") or "").strip()
            for item in payload.get("translations") or []
            if isinstance(item.get("i"), int)}
    return out


def apply_answers(chunk: list[dict], answers: dict[int, str], entries: dict,
                  guarded: set[str], refused: list) -> int:
    """Проверяет и раскладывает ответы по репликам. Возвращает, сколько легло."""
    done = 0
    for index, russian in answers.items():
        if not (0 <= index < len(chunk)) or not russian:
            continue
        item = chunk[index]
        why = accept(item["text"], drop_speaker(item, russian), item["marks"], guarded)
        if why:
            refused.append((item["key"], why))
            continue
        entries[item["key"]]["ru"] = assemble(item, russian)
        done += 1
    return done


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Перевод реплик NPC с разметкой цвета")
    parser.add_argument("file")
    parser.add_argument("--limit", type=int, default=0)
    # По умолчанию Batch API: та же модель и тот же запрос, но вдвое дешевле.
    # Ответ обычно в течение часа, предел — сутки.
    parser.add_argument("--sync", action="store_true",
                        help="слать сразу, без Batch API (вдвое дороже, зато видно тут же)")
    parser.add_argument("--collect", metavar="ID",
                        help="забрать результат уже отправленного задания")
    parser.add_argument("--no-review", action="store_true", help="без проверяющего прохода")
    parser.add_argument("--dry", action="store_true", help="ничего не отправлять")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("lines") or {}
    todo = prepare(entries, args.limit)
    if not todo:
        print("переводить нечего")
        return 0

    with_marks = sum(1 for item in todo if item["marks"])
    chars = sum(len(item["text"]) for item in todo)
    # ⚠️ Пачка — ОДИН говорящий. Иначе шапка «говорит такой-то» врёт про
    # половину реплик, а модель видит чужую манеру речи вперемешку.
    by_npc: dict[str, list[dict]] = defaultdict(list)
    for item in todo:
        by_npc[item["npc"]].append(item)
    chunks = [group[i:i + BATCH_SIZE]
              for group in by_npc.values()
              for i in range(0, len(group), BATCH_SIZE)]
    print(f"реплик к переводу: {len(todo)}  (с разметкой цвета: {with_marks})")
    print(f"знаков в запросе:  {chars}  пачек: {len(chunks)}"
          f"{'' if args.no_review else ' + столько же на проверку'}")
    if args.dry:
        print("сухой прогон: ничего не отправлено")
        return 0

    guarded = protected.collect()
    system = [{"type": "text", "text": RULES, "cache_control": {"type": "ephemeral"}}]
    review_system = [{"type": "text", "text": REVIEW_RULES + "\n\n" + RULES,
                      "cache_control": {"type": "ephemeral"}}]

    done = 0
    refused: list[tuple[str, str]] = []

    if not args.sync:
        # ⚠️ ДВА ЗАДАНИЯ ПОДРЯД, а не одно: проверяющий проход должен видеть
        # готовый перевод, значит отправить его раньше нельзя. Переводы кладём
        # в файл СРАЗУ после первого задания — если второе сорвётся, работа
        # уже сохранена и деньги не пропадут.
        def params(system_part, user_text):
            return {"model": MODEL, "max_tokens": 8000, "system": system_part,
                    "output_config": {"format": {"type": "json_schema",
                                                 "schema": SCHEMA}, "effort": "high"},
                    "messages": [{"role": "user", "content": user_text}]}

        batch_id = args.collect or send_batch(
            [(f"c{i}", params(system, build_user(chunk)))
             for i, chunk in enumerate(chunks)])
        STATE.write_text(json.dumps({"batch": batch_id, "file": str(path)},
                                    ensure_ascii=False), encoding="utf-8")
        print(f"задание отправлено: {batch_id}")
        print(f"  номер записан в {STATE.name} — забрать можно ключом --collect")
        wait_batch(batch_id)
        answers = read_batch(batch_id)

        first: dict[int, dict[int, str]] = {}
        for name, got in answers.items():
            index = int(name[1:])
            first[index] = got
            done += apply_answers(chunks[index], got, entries, guarded, refused)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"перевод получен: {done} реплик, записаны в файл")

        if not args.no_review and first:
            jobs = []
            for index, got in first.items():
                chunk = chunks[index]
                lines = [f"{i}. БЫЛО: {chunk[i]['text']}\n   СТАЛО: {ru}"
                         for i, ru in sorted(got.items()) if i < len(chunk)]
                if lines:
                    jobs.append((f"c{index}", params(
                        review_system, "Проверь перевод:\n\n" + "\n".join(lines))))
            if jobs:
                review_id = send_batch(jobs)
                print(f"проверяющее задание: {review_id}")
                wait_batch(review_id)
                for name, got in read_batch(review_id).items():
                    index = int(name[1:])
                    apply_answers(chunks[index], got, entries, guarded, [])
                path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                encoding="utf-8")

        print()
        print(f"переведено: {sum(1 for v in entries.values() if v.get('ru'))} всего")
        if refused:
            print(f"отбраковано: {len(refused)}")
            for key, why in refused[:10]:
                print(f"  {why}: {key[:70]}")
        from translate_ai import USAGE
        print(f"запросов: {USAGE['requests']}  "
              f"(вход {USAGE['in']}, из кэша {USAGE['cache_read']}, выход {USAGE['out']})")
        print(f"стоимость захода (Batch, вдвое дешевле): ${batch_cost(USAGE):.3f}")
        return 0

    for number, chunk in enumerate(chunks, start=1):
        print(f"  пачка {number}/{len(chunks)} ({len(chunk)} реплик)…")
        got = ask(system, build_user(chunk))
        if got and not args.no_review:
            review = [f"{i}. [{chunk[i]['npc']}] БЫЛО: {chunk[i]['text']}\n   СТАЛО: {ru}"
                      for i, ru in sorted(got.items()) if i < len(chunk)]
            checked = ask([{"type": "text", "text": REVIEW_RULES + "\n\n" + RULES,
                            "cache_control": {"type": "ephemeral"}}],
                          "Проверь перевод:\n\n" + "\n".join(review))
            got.update({i: ru for i, ru in checked.items() if ru})

        for index, russian in got.items():
            if not (0 <= index < len(chunk)):
                continue
            item = chunk[index]
            why = accept(item["text"], russian, item["marks"], guarded)
            if why:
                refused.append((item["key"], why))
                continue
            entries[item["key"]]["ru"] = assemble(item, russian)
            done += 1

        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print()
    print(f"переведено: {done} из {len(todo)}")
    if refused:
        print(f"отбраковано: {len(refused)}")
        for key, why in refused[:10]:
            print(f"  {why}: {key[:70]}")
    report_usage()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
