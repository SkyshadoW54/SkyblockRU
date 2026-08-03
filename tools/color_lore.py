"""
Возвращает ЦВЕТА в готовые переводы абзацев — разметкой, а не угадыванием.

Зачем. Перевод хранится чистым текстом, и цвет к нему приходится восстанавливать:
кусок, уцелевший дословно (число, английское имя), красится своим прежним цветом,
остальное — цветом тела. Потолок этого приёма — 20–47% знаков: «Grants a» стало
«Даёт», и привязать цвет не к чему. Знает соответствие только тот, кто переводил.

Поэтому цвета расставляет модель, но НЕ переводит заново: ей дают оригинал
с §-кодами и уже готовый перевод, а она возвращает тот же перевод с маркерами
{c1}…{/c1}. Текст меняться не смеет, и это проверяется механически: снимаем
маркеры — результат обязан совпасть с прежним переводом ЗНАК В ЗНАК. Так модель
не сможет переписать оплаченное под видом раскраски.

⚠️ Маркеры, а не §-коды: код невидим в тексте, модель его теряет. Тот же приём
уже спас иконки — из 50 абзацев они терялись в 12, а с маркерами {i1} ни разу.

Источник цветов — репозиторий NEU (data/neu/repo.zip): там лор лежит с кодами,
в отличие от нашего дампа, который их снимает.

Запуск:
  python tools/color_lore.py                 посмотреть, скольким абзацам нужны цвета
  python tools/color_lore.py --apply         разметить (пачками, с проверкой)
  python tools/color_lore.py --apply --limit 100
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
REPO = ROOT / "data" / "neu" / "repo.zip"
# Второй источник цветов — ЖИВЫЕ подсказки из игры. В репозитории NEU лежат
# только предметы, поэтому меню, экраны и чужие профили красить больше неоткуда:
# у 1005 переведённых абзацев цветов нет ни в одном другом месте.
LIVE_COLORS = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump/"
                   "paragraph-colors.json")

# Имя цвета (так их пишет мод) -> §-код. Обратное преобразование нужно, чтобы
# живые куски легли в тот же вид, что и строки из NEU, и дальше работал один код.
COLOR_CODES = {
    "black": "§0", "dark_blue": "§1", "dark_green": "§2", "dark_aqua": "§3",
    "dark_red": "§4", "dark_purple": "§5", "gold": "§6", "gray": "§7",
    "dark_gray": "§8", "blue": "§9", "green": "§a", "aqua": "§b",
    "red": "§c", "light_purple": "§d", "yellow": "§e", "white": "§f",
}

sys.path.insert(0, str(Path(__file__).resolve().parent))

CODE = re.compile("§.")
# ⚠️ Обобщение чисел — из общего pkey: копий было шесть, и одна
# уже разошлась (в measure_color процент попадал внутрь числа).
from pkey import NUMBER  # noqa: E402
MARK = re.compile(r"\{/?c(\d+)\}")
# Пачка небольшая нарочно: ответ длиннее запроса — в нём весь перевод
# с разметкой, и на 25 абзацах он упирался в потолок и обрывался посередине.
BATCH = 12

RULES = """Ты сопоставляешь ПОДСВЕЧЕННЫЕ куски английского описания с их
переводом на русский. Описание — из Hypixel SkyBlock.

Тебе дают перевод и список подсвеченных кусков оригинала с номерами цветов.
Верни для каждого номера тот кусок ПЕРЕВОДА, в который он превратился.

Железные правила:
1. Кусок перевода пиши ДОСЛОВНО, как он стоит в тексте, — его будут искать
   поиском по строке. Ни склонять, ни сокращать, ни дописывать нельзя.
2. Бери минимальный кусок, который несёт смысл подсвеченного:
      подсвечено «§dSea Creatures», перевод «Даёт +20% шанс поймать морских
      существ при рыбалке» -> кусок «морских существ»
   Не захватывай соседние слова, которые в оригинале были другого цвета.
3. Порядок слов в русском другой — ищи по СМЫСЛУ, а не по месту в строке.
4. Если подсвеченному куску в переводе ничего не соответствует (его смысл
   растворился), номер просто не возвращай. Пустой кусок не выдумывай.
5. Куски не должны пересекаться между собой.
6. {n} {s} {i1} — дырки для чисел, ников и значков. Их можно включать в кусок,
   если они часть подсвеченного, но менять или выдумывать нельзя.

Отвечай только парами «номер цвета — кусок перевода»."""

# ⚠️ Модель возвращает ТОЛЬКО КУСКИ, а не весь абзац заново.
#
# Замер первой версии: вход 10375 токенов ($0.05), выход 9230 ($0.23) — то есть
# 80% денег уходило на то, что модель переписывала весь перевод целиком, хотя
# от неё нужны две-три пары «цвет — фрагмент». Ответ короче в разы, и цена
# падает вместе с ним.
#
# Заодно проверка становится строже даром: текст мы не переписываем вовсе,
# а только оборачиваем найденные фрагменты. Изменить перевод модель теперь
# не может физически — она его и не присылает.
SCHEMA = {
    "type": "object",
    "properties": {
        "spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer", "description": "номер абзаца из запроса"},
                    "c": {"type": "integer", "description": "номер цвета из списка"},
                    "t": {"type": "string",
                          "description": "кусок ПЕРЕВОДА, который надо покрасить, дословно"},
                },
                "required": ["i", "c", "t"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["spans"],
    "additionalProperties": False,
}


def strip_codes(text: str) -> str:
    return CODE.sub("", text)


def live_lore() -> dict[str, list[str]]:
    """
    Ключ абзаца -> его куски С §-кодами, из ЖИВОЙ игры.

    <p>Мод пишет каждый склеенный абзац вместе с ключом и цветами кусков.
    Ключ берём готовым, а не строим заново: он посчитан тем же кодом, что ищет
    перевод, поэтому совпадение с корпусом точное — угадывать по началу текста
    не нужно (раньше ключа в файле не было вовсе, и связать данные было нечем).
    """
    out: dict[str, list[str]] = {}
    if not LIVE_COLORS.exists():
        return out
    try:
        cases = json.loads(LIVE_COLORS.read_text(encoding="utf-8")).get("cases") or []
    except (json.JSONDecodeError, OSError):
        return out
    for case in cases:
        key = case.get("key")
        pieces = case.get("pieces") or []
        if not key or not pieces:
            continue
        # ⚠️ ГРАНИЦА СТРОК в кусках не отмечена, и склейка встык слепляет слова:
        # «to this» + «project and earn» давало «to thisproject». Внутри строки
        # куски граничат по пробелу или по знаку («§5Crystal Hollows§7.»), а вот
        # на переносе оба края буквенные — по этому признаку и вставляем пробел.
        # Раньше это было незаметно: склейка шла только на поиск подсвеченных
        # кусков, а теперь тот же текст уходит переводчику, и слипшееся слово
        # он переведёт слипшимся.
        parts: list[str] = []
        previous = ""
        for color, text in pieces:
            # Пробел нужен, когда предыдущий кусок им НЕ кончился, а следующий
            # начинается словом: «filter!» + «Right-Click», «to this» +
            # «project». А вот «Crystal Hollows» + «.» трогать нельзя — знак
            # препинания примыкает к слову, и лишний пробел там видно на экране
            # («Crystal Hollows .» уже было).
            if previous and text and not previous[-1].isspace() and text[0].isalnum():
                parts.append(" ")
            parts.append(COLOR_CODES.get(color, "§7") + text)
            previous = text
        line = "".join(parts)
        if not CODE.search(line):
            continue
        # ⚠️ Числа обобщаем, как это делает Translator при поиске. Мод пишет ключ
        # СЫРЫМ («…your first 2 million banked coins»), а корпус хранит его
        # с дырками («…your first {n} million…»). Без обобщения ключи не
        # совпадают ни разу, и живой источник цветов молча даёт ноль попаданий:
        # «ждут разметки: 0», а подсказка на экране по-прежнему без цвета.
        out.setdefault(NUMBER.sub("{n}", key).strip(), [line])
        out.setdefault(key, [line])
    return out


def coloured_lore() -> dict[str, list[str]]:
    """Ключ абзаца -> строки оригинала С §-кодами: репозиторий NEU и живая игра."""
    out: dict[str, list[str]] = {}
    if not REPO.exists():
        return dict(live_lore())
    with zipfile.ZipFile(REPO) as repo:
        for name in repo.namelist():
            if not (name.endswith(".json") and "/items/" in name):
                continue
            try:
                item = json.loads(repo.read(name).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            lore = [str(line) for line in (item.get("lore") or [])]
            if not any(CODE.search(line) for line in lore):
                continue
            # Режем ТОЧНО как мод: только по пустым строкам, короче двух не берём,
            # склейка одним пробелом. Ключ обобщаем по числам — так же, как
            # Translator при поиске.
            run: list[str] = []
            for line in lore + [""]:
                if strip_codes(line).strip():
                    run.append(line)
                    continue
                if len(run) >= 2:
                    key = NUMBER.sub("{n}", " ".join(
                        strip_codes(part).strip() for part in run)).strip()
                    out.setdefault(key, run.copy())
                run = []
    # Аукцион — ТРЕТИЙ источник, и самый крупный по цветам.
    #
    # ⚠️ Долго считалось, что источников два: NEU (исчерпан) и живая игра.
    # А официальный API аукциона отдаёт лор С §-кодами у всех 50 тысяч лотов —
    # проект просто не ходил в этот эндпоинт, хотя в два других ходил.
    # Замер на полном прогоне: 11280 абзацев, из них 404 закрывают наши плоские
    # переводы (20%) — против 29, доступных по живым цветам.
    #
    # Ценен он ещё и тем, что на аукционе лежат ПРОКАЧАННЫЕ предметы: с ковкой,
    # самоцветами и звёздами. В NEU только базовые, поэтому таких вариантов
    # лора у нас нет вовсе.
    for key, lines in auction_lore().items():
        out.setdefault(key, lines)
    # Живые подсказки ДОПОЛНЯЮТ, а не заменяют: у предмета все источники дают
    # одно и то же, а меню и экраны есть только в живом дампе.
    for key, lines in live_lore().items():
        out.setdefault(key, lines)
    return out


def auction_lore() -> dict[str, list[str]]:
    """Лор с цветами, скачанный из API аукциона (tools/fetch_auction.py)."""
    path = ROOT / "data" / "work" / "auction_lore.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("lore") or {}
    except (json.JSONDecodeError, OSError):
        return {}


def body_colour(pieces: list[tuple[str, str]]) -> str:
    """
    Цвет ТЕЛА абзаца: тот, что набрал больше всего КУСКОВ, а не знаков.

    ⚠️ Считали по знакам, и длинная подсветка перетягивала тело на себя:
    у «§9Ancient Bonus / §7Grants §a+1 §9Crit Damage §7per §cCatacombs §7level.»
    синего 26 знаков против серых 17 — и служебные «за», «уровень» уезжали
    в синий. Тело — это то, что ПОВТОРЯЕТСЯ между подсветками: проза разорвана
    на много кусков одного цвета, а подсветка — один-два куска.
    Замер по корпусу: серым тело выходит у 93% абзацев против 79% по знакам,
    починено 630 абзацев, испорчено 3 (и все три — таблицы, где тела нет вовсе).

    ⚠️ Смежные куски одного цвета склеиваем: перенос строки — чужая вёрстка,
    он режет «§f✦ Speed» на «✦» и «Speed», и счёт удваивал один кусок.
    У кроликов из-за этого белый обходил серый 3:2.

    Ничья — в пользу серого: у Hypixel описание набрано серым, а без явного
    правила победитель зависел бы от порядка обхода словаря.
    """
    runs: dict[str, int] = {}
    last: str | None = None
    for code, text in pieces:
        if not text.strip():
            continue
        if code != last:
            runs[code] = runs.get(code, 0) + 1
        last = code
    if not runs:
        return "§7"
    best = max(runs.values())
    winners = [code for code, count in runs.items() if count == best]
    for gray in ("§7", "§8"):
        if gray in winners:
            return gray
    return winners[0]


def pieces_of(lines: list[str]) -> list[tuple[str, str]]:
    """
    Разбор строк на куски «(код цвета, текст)».

    ⚠️ Вынесено отдельно, чтобы разбор был ОДИН. Им пользуются и разметка
    готовых переводов ({@link colours_of}), и подготовка размеченного оригинала
    для переводчика ({@link mark_original}). Копия этой логики разошлась бы
    молча — в проекте так уже случалось с ключом абзаца, где копий набралось
    шесть и одна успела разъехаться.
    """
    pieces: list[tuple[str, str]] = []
    for line in lines:
        colour, mods = "§7", ""
        rest = line
        while rest:
            match = CODE.search(rest)
            if match is None:
                pieces.append((colour + mods, rest))
                break
            head = rest[:match.start()]
            if head:
                pieces.append((colour + mods, head))
            code = match.group(0)
            # ⚠️ ЦВЕТ и МОДИФИКАТОР — разные вещи, и путать их нельзя.
            #
            # «§e§lRIGHT CLICK» — жёлтый ЖИРНЫЙ. Раньше кодом куска считался
            # последний перед текстом, то есть «§l», и в разметку уходила одна
            # жирность: «§lПКМ» вместо «§e§lПКМ». Цвет пропадал молча — на живом
            # дампе так испортились 288 абзацев, и заметно это стало только
            # по жалобе мода «потерян yellow» у подсказки способности.
            #
            # §0-§9, §a-§f — цвета, они сбрасывают модификаторы.
            # §k-§o — модификаторы (жирный, курсив, подчёркнутый…), они копятся.
            # §r — сброс всего.
            letter = code[1].lower()
            if letter == "r":
                colour, mods = "§7", ""
            elif letter in "0123456789abcdef":
                colour, mods = code, ""
            else:
                mods += code
            rest = rest[match.end():]
    return pieces


def colours_of(lines: list[str]) -> tuple[str, list[tuple[str, str]]]:
    """Цвет тела и подсвеченные куски (код, текст)."""
    pieces = pieces_of(lines)
    body = body_colour(pieces)
    # ⚠️ Куски для разметки берём НЕсклеенными: их ищет wrap_spans поиском
    # по строке перевода, и склейка через границу строк дала бы кусок,
    # которого в переводе нет («✦ Speed» с чужим пробелом).
    marks = [(code, text.strip()) for code, text in pieces
             if code != body and len(text.strip()) > 1]
    return body, marks


def mark_original(lines: list[str]) -> tuple[str, dict[int, str], str]:
    """
    Оригинал с маркерами {c1}…{/c1} вместо §-кодов — то, что уходит переводчику.

    Зачем маркеры, а не сами коды: §-код невидим в тексте, и модель его теряет.
    Маркер — обычные буквы, он переносится так же надёжно, как {n} и {i1}
    (проверено на значках: 12 потерь из 50 стали нулём). Это тот самый
    masking-подход, который в исследованиях обходит проецирование разметки
    обратно эвристикой.

    Возвращает: (размеченный текст, {номер: §-код}, цвет тела).
    """
    body = body_colour(pieces_of(lines))
    codes: dict[int, str] = {}
    number = 0
    rows: list[str] = []
    # ⚠️ Идём ПОСТРОЧНО и склеиваем строки ПРОБЕЛОМ — ровно так мод строит
    # ключ абзаца (`Paragraphs.runs`). Склейка встык давала «to thisproject»:
    # текст уезжал модели уже испорченным, и перевод пришлось бы выбрасывать.
    for line in lines:
        out: list[str] = []
        for code, text in pieces_of([line]):
            if not text.strip():
                out.append(text)
                continue
            stripped = text.strip()
            # Короткий кусок берём, только если это ЗНАЧОК, а не буква с цифрой.
            # Правило то же, что у мода в `carryLegacyCodes`: одиночное «❣»
            # свой цвет терять не должно, а вот дробить слова на буквы незачем.
            if code == body or (len(stripped) < 2 and stripped.isalnum()):
                out.append(text)
                continue
            number += 1
            codes[number] = code
            # Пробелы оставляем СНАРУЖИ маркера: иначе модель переносит их
            # вместе с ним и слова слипаются.
            head = text[:len(text) - len(text.lstrip())]
            tail = text[len(text.rstrip()):]
            out.append(f"{head}{{c{number}}}{stripped}{{/c{number}}}{tail}")
        rows.append("".join(out).strip())
    return " ".join(row for row in rows if row), codes, body


def unmark(text: str, codes: dict[int, str], body: str) -> str:
    """Разворачивает маркеры перевода обратно в §-коды."""
    def open_tag(match):
        return codes.get(int(match.group(1)), body)

    text = re.sub(r"\{c(\d+)\}", open_tag, text)
    text = re.sub(r"\{/c\d+\}", body, text)
    return body + text


def wrap_spans(ru: str, spans: list[tuple[int, str]], marks: list[tuple[str, str]],
               body: str) -> str | None:
    """
    Оборачивает найденные куски перевода их §-кодами.

    Куски ищем в тексте и вставляем коды по позициям, от конца к началу — так
    ранние позиции не съезжают. Пересечения отбрасываем: лучше не покрасить,
    чем покрасить внахлёст.
    """
    places: list[tuple[int, int, str]] = []
    for number, text in spans:
        piece = (text or "").strip()
        if not piece or not (1 <= number <= len(marks)):
            continue
        at = ru.find(piece)
        if at < 0:
            continue
        if any(at < end and start < at + len(piece) for start, end, _ in places):
            continue
        places.append((at, at + len(piece), marks[number - 1][0]))
    if not places:
        return None
    out = ru
    for start, end, code in sorted(places, reverse=True):
        out = out[:start] + code + out[start:end] + body + out[end:]
    return body + out


def premark(item: dict) -> tuple[str | None, list[int]]:
    """
    Механическая разметка: кусок оригинала, уцелевший в переводе ДОСЛОВНО.

    ⚠️ Спрашивать модель о таком незачем — число, процент и английское имя
    стоят в переводе как были, и место известно точно. Модель нужна только
    там, где кусок ПЕРЕВЕДЁН. Так из запроса уходит всё, что и так решается,
    а платим мы за оставшееся.

    @return (готовая разметка или None, номера цветов, которые не нашлись)
    """
    found: list[tuple[int, str]] = []
    left: list[int] = []
    for number, (_, text) in enumerate(item["marks"], 1):
        if text and text in item["ru"]:
            found.append((number, text))
        else:
            left.append(number)
    if not found:
        return None, left
    return wrap_spans(item["ru"], found, item["marks"], item["body"]), left


def build_user(chunk: list[dict]) -> str:
    # ⚠️ Иконки ПРЯЧЕМ за маркеры, а не просим не выбрасывать. Первый заход
    # потерял их в 36 абзацах из 50: символ приватной зоны для модели —
    # пустой квадрат, и она его молча убирает. Тем же приёмом уже спасён
    # перевод ({i1}, {i2}), здесь он нужен ровно так же.
    from translate_tooltips import mask_icons
    parts = []
    for index, item in enumerate(chunk):
        item["ru"], item["_icons"] = mask_icons(item["ru"])
        # Спрашиваем ТОЛЬКО про цвета, которые не нашлись механически.
        colours = "\n".join(f"   {n} = «{item['marks'][n - 1][1]}»" for n in item["ask"])
        parts.append(f"[{index}] ПЕРЕВОД: {item['ru']}\n"
                     f"ПОДСВЕЧЕНО В ОРИГИНАЛЕ:\n{colours}")
    return "\n\n".join(parts)


def accept(item: dict, answer: str) -> tuple[str | None, str]:
    """
    Проверяет ответ механически. Главное — текст не изменился.

    Снимаем маркеры и сравниваем с прежним переводом знак в знак: так модель
    не сможет переписать оплаченный текст, а мы не потеряем работу.
    """
    answer = (answer or "").strip()
    if not answer:
        return None, "пустой ответ"
    if "{c" not in answer:
        return None, "маркеров не добавлено"
    bare = MARK.sub("", answer).strip()
    if bare != item["ru"].strip():
        # ⚠️ Пробелы сравниваем МЯГКО. Модель схлопывает двойной пробел, который
        # у нас стоит на месте выброшенной иконки, — и строгая сверка забраковала
        # почти половину пачки, хотя текст тот же. Значимой разницы в абзаце
        # двойной пробел не несёт: строки всё равно переносит мод.
        squeeze = re.compile(r"\s+")
        if squeeze.sub(" ", bare) != squeeze.sub(" ", item["ru"]).strip():
            a, b = squeeze.sub(" ", bare), squeeze.sub(" ", item["ru"]).strip()
            at = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
            return None, ("текст изменён: «…" + b[max(0, at - 18):at + 18]
                          + "» -> «…" + a[max(0, at - 18):at + 18] + "»")
    opened = [n for n in re.findall(r"\{c(\d+)\}", answer)]
    closed = [n for n in re.findall(r"\{/c(\d+)\}", answer)]
    if sorted(opened) != sorted(closed):
        return None, "маркер не закрыт"
    limit = len(item["marks"])
    if any(int(n) < 1 or int(n) > limit for n in opened):
        return None, f"выдуман номер цвета (в абзаце их {limit})"
    return answer, ""


def expand(answer: str, item: dict) -> str:
    """Маркеры -> §-коды. Цвет тела возвращаем после каждого закрытия."""
    body = item["body"]
    out = answer
    for number, (code, _) in enumerate(item["marks"], 1):
        out = out.replace(f"{{c{number}}}", code).replace(f"{{/c{number}}}", body)
    return body + out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Разметка цветом готовых переводов")
    parser.add_argument("--apply", action="store_true", help="спросить модель и записать")
    parser.add_argument("--limit", type=int, default=0)
    # ⚠️ Разметку можно сделать и БЕЗ API: работа тут не творческая, а
    # сопоставительная — какой кусок русского перевода отвечает какому цветному
    # куску оригинала. `--export` выкладывает задание файлом, `--import` вливает
    # ответы через ТУ ЖЕ проверку `accept`, что и ответ модели: текст меняться
    # не смеет, маркеры обязаны сойтись. Просьба игрока 01.08 — «а мы это
    # не можем перевести просто через тебя, без API за деньги».
    parser.add_argument("--export", help="выгрузить задание в файл (без API)")
    parser.add_argument("--load", help="влить размеченное из файла")
    args = parser.parse_args()

    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = data.get("paragraphs") or []
    lore = coloured_lore()
    print(f"абзацев с цветами в репозитории NEU: {len(lore)}")

    todo = []
    for para in paragraphs:
        ru = para.get("ru")
        if not ru or CODE.search(ru):
            continue           # нет перевода либо он уже размечен
        lines = lore.get(para["text"])
        if not lines:
            continue
        body, marks = colours_of(lines)
        if not marks:
            continue           # одноцветный абзац — размечать нечего
        todo.append({"para": para, "ru": ru, "body": body, "marks": marks,
                     "raw": " ".join(lines)})

    # ⚠️ Сперва размечаем механически — и это БЕСПЛАТНО. Кусок, уцелевший
    # в переводе дословно (число, процент, английское имя), искать не надо:
    # он на месте. Модель нужна только тем цветам, что не нашлись.
    free = 0
    ask = []
    for item in todo:
        marked, left = premark(item)
        if marked and not left:
            item["para"]["ru"] = marked      # все цвета решились сами
            free += 1
            continue
        item["premarked"] = marked
        item["ask"] = left
        ask.append(item)
    if free:
        CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    todo = ask

    print(f"размечено БЕЗ модели (куски уцелели дословно): {free}")
    print(f"ждут разметки: {len(todo)}")
    if args.limit:
        todo = todo[:args.limit]
    for item in todo[:5]:
        print(f"  {item['ru'][:70]}")
        print(f"     цветов: {len(item['marks'])}, тело {item['body']!r}")
    if not todo:
        print("размечать нечего")
        return 0

    if args.export:
        from translate_tooltips import mask_icons
        out = []
        for index, item in enumerate(todo):
            ru, icons = mask_icons(item["ru"])
            out.append({
                "n": index,
                "key": item["para"]["text"],
                "ru": ru,
                "_icons": icons,
                "body": item["body"],
                # что подсвечено В ОРИГИНАЛЕ: номер -> кусок английского текста
                "highlighted": {str(n): item["marks"][n - 1][1] for n in item["ask"]},
                # сюда вписать: номер -> тот же кусок, но ИЗ ПЕРЕВОДА
                "answer": {},
            })
        Path(args.export).write_text(
            json.dumps({"_comment": "Заполни answer: номер -> кусок ПЕРЕВОДА,"
                                    " дословно как он стоит в ru. Потом --load.",
                        "items": out}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nвыгружено заданий: {len(out)} -> {args.export}")
        return 0

    if args.load:
        source = json.loads(Path(args.load).read_text(encoding="utf-8"))
        by_key = {item["para"]["text"]: item for item in todo}
        done = bad = 0
        for row in source.get("items") or []:
            item = by_key.get(row.get("key"))
            if not item or not row.get("answer"):
                continue
            item["ru"], item["_icons"] = row["ru"], row.get("_icons") or {}
            # ⚠️ Собираем ТУ ЖЕ строку с маркерами, что прислала бы модель:
            # пары «номер -> кусок перевода» превращает в неё `wrap_spans`.
            # Механически найденные куски (число, английское имя) добавляем
            # сюда же — иначе их цвет потеряется, хотя он известен точно.
            spans = [(int(n), text) for n, text in row["answer"].items()]
            for number, (_code, text) in enumerate(item["marks"], 1):
                if number not in {n for n, _ in spans} and text and text in item["ru"]:
                    spans.append((number, text))
            marked = wrap_spans(item["ru"], spans, item["marks"], item["body"])
            if not marked:
                bad += 1
                print(f"  отбраковано: ни один кусок не найден — {row['ru'][:50]}")
                continue
            # иконки возвращаем на место и проверяем, что ТЕКСТ не изменился —
            # та же защита, что у ответа модели: размечать можно, переписывать нет
            from translate_tooltips import unmask_icons
            marked = unmask_icons(marked, row.get("_icons") or {})
            was = unmask_icons(item["ru"], row.get("_icons") or {})
            if CODE.sub("", marked).strip() != was.strip():
                bad += 1
                print(f"  отбраковано: текст изменён — {row['ru'][:50]}")
                continue
            item["para"]["ru"] = marked
            done += 1
        CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nразмечено: {done}, отбраковано: {bad}")
        return 0

    if not args.apply:
        print(f"\nэто {(len(todo) + BATCH - 1) // BATCH} запрос(ов). Запуск: --apply")
        print("без API: --export FILE.json  ->  заполнить  ->  --load FILE.json")
        return 0

    from apikey import check as check_key
    if not check_key():
        return 1
    from anthropic import Anthropic
    from translate_ai import note_usage, report_usage

    client = Anthropic()
    system = [{"type": "text", "text": RULES, "cache_control": {"type": "ephemeral"}}]
    done = rejected = 0
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        print(f"  пачка {start // BATCH + 1}/{(len(todo) + BATCH - 1) // BATCH}"
              f" ({len(chunk)} абзацев)...")
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=16000,
            system=system,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": build_user(chunk)}],
        )
        note_usage(response)
        payload = json.loads("".join(block.text for block in response.content
                                     if getattr(block, "text", None)))
        # Куски раскладываем по абзацам, а вставляем их МЫ — значит текст
        # перевода не может измениться в принципе.
        by_item: dict[int, list[tuple[int, str]]] = {}
        for span in payload.get("spans") or []:
            index = span.get("i")
            if isinstance(index, int) and 0 <= index < len(chunk):
                by_item.setdefault(index, []).append((span.get("c") or 0, span.get("t") or ""))

        from translate_tooltips import unmask_icons
        for index, item in enumerate(chunk):
            found = by_item.get(index) or []
            # к найденному моделью добавляем то, что нашлось само
            for number, (_, text) in enumerate(item["marks"], 1):
                if number not in item["ask"] and text and text in item["ru"]:
                    found.append((number, text))
            marked = wrap_spans(item["ru"], found, item["marks"], item["body"])
            if not marked:
                print(f"    ! {item['ru'][:44]!r}: куски не нашлись в переводе")
                rejected += 1
                continue
            item["para"]["ru"] = unmask_icons(marked, item.get("_icons") or {})
            done += 1
        CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nразмечено: {done}, отбраковано: {rejected}")
    print(f"записано: {CORPUS.relative_to(ROOT)}")
    report_usage()
    print("\nДальше: python tools/merge_paragraphs.py && install.cmd")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
