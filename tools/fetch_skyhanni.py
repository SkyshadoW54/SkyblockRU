"""
Импортирует шаблоны сообщений чата из SkyHanni-REPO и готовит их к переводу.

Зачем: чат SkyBlock нигде не выложен готовым текстом, но сообщество SkyHanni
годами собирало РЕГУЛЯРКИ, описывающие форму каждого сообщения. Это карта
«какие сообщения вообще бывают» — по ней можно написать правила перевода,
не наигрывая сотни часов ради того, чтобы каждое сообщение встретилось.

Источник: https://github.com/hannibal002/SkyHanni-REPO (лицензия MIT)

Что делает:
  1. качает constants/regexesModern.json;
  2. отбирает шаблоны, в которых есть настоящий текст (а не только техника);
  3. превращает каждый в ЧИТАЕМЫЙ образец: скобки-группы заменяются на {1}, {2}
     — по такому образцу переводчику понятно, что переводить, а по регулярке нет;
  4. помечает подозрительно широкие шаблоны, чтобы их посмотрели глазами;
  5. складывает всё в data/work/chat_rules.json.

Дальше по этому файлу проходит tools/translate_ai.py, а готовый результат
кладётся в packs/ как обычный словарь.

Запуск:  python tools/fetch_skyhanni.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/hannibal002/SkyHanni-REPO/main/constants/regexesModern.json"

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "work" / "chat_rules.json"
RAW = ROOT / "data" / "en" / "skyhanni_regexes.json"

# Метасимволы, из-за которых образец перестаёт быть читаемым текстом
MESSY = re.compile(r"[\[\]|*+?{}\\]")

# Коды цвета в шаблонах SkyHanni.
# ⚠️ Снимать их ОБЯЗАТЕЛЬНО: SkyHanni сопоставляет шаблон со строкой вместе
# с кодами, а наш движок работает с чистым текстом. Шаблон с §-кодами
# не совпадёт никогда — так молча не работала почти половина импорта.
COLOR_CODE = re.compile("§.")


def fetch() -> dict:
    print(f"качаю {URL}")
    request = urllib.request.Request(URL, headers={"User-Agent": "SkyblockRU/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read().decode("utf-8")
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(data, encoding="utf-8")
    print(f"  сохранил: {RAW.relative_to(ROOT)} ({len(data) / 1024:.1f} КБ)")
    return json.loads(data)


def collect(node, path: str, out: dict[str, str]) -> None:
    """Собирает все шаблоны вместе с их путём-именем (он пригодится как метка)."""
    if isinstance(node, dict):
        for key, value in node.items():
            collect(value, f"{path}.{key}" if path else key, out)
    elif isinstance(node, str):
        out[path] = node


ESCAPE_CLASSES = set("dwsSDWbB")
QUANT = re.compile(r"[*+?]|\{\d+(?:,\d*)?\}")

# Максимум подстановок: больше — переводить бессмысленно, фраза расползается
MAX_HOLES = 6


def _find_close(pattern: str, start: int, open_ch: str, close_ch: str) -> int:
    """Ищет закрывающую скобку с учётом вложенности и экранирования."""
    depth = 0
    i = start
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            i += 2
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _eat_quantifier(pattern: str, i: int) -> int:
    """Сдвигает позицию за повторитель (*, +, ?, {2,5}) и его ленивую форму."""
    match = QUANT.match(pattern, i)
    if not match:
        return i
    i = match.end()
    if i < len(pattern) and pattern[i] in "?+":
        i += 1
    return i


def convert(pattern: str) -> tuple[str, str, int] | None:
    """
    Разбирает регулярку на «постоянный текст» и «переменные куски».

    Переменные куски (числа, ники, названия) оборачиваются в группы захвата,
    даже если в оригинале они не захватывались — иначе подставить их обратно
    в перевод было бы нечем, и число из сообщения потерялось бы.

    Возвращает (новый_шаблон, читаемый_образец, число_групп) либо None,
    если шаблон машинно в текст не превращается.
    """
    body = pattern
    prefix = ""
    suffix = ""
    if body.startswith("^"):
        prefix, body = "^", body[1:]
    if body.endswith("$") and not body.endswith("\\$"):
        suffix, body = "$", body[:-1]

    out_pattern = []
    out_sample = []
    holes = 0
    i = 0

    while i < len(body):
        ch = body[i]

        if ch == "|":
            return None  # перечисление на верхнем уровне: форма фразы плавает

        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            end = _eat_quantifier(body, i + 2)
            piece = body[i:end]
            if nxt in ESCAPE_CLASSES:
                if nxt == "s":
                    # пробелы — это не смысл, а вёрстка: в образце просто пробел
                    out_pattern.append(piece)
                    out_sample.append(" ")
                else:
                    holes += 1
                    out_pattern.append("(" + piece + ")")
                    out_sample.append(f"{{{holes}}}")
            else:
                out_pattern.append(piece)
                out_sample.append(nxt)  # экранированный знак препинания
            i = end
            continue

        if ch == "[":
            close = _find_close(body, i, "[", "]")
            if close < 0:
                return None
            end = _eat_quantifier(body, close + 1)
            holes += 1
            out_pattern.append("(" + body[i:end] + ")")
            out_sample.append(f"{{{holes}}}")
            i = end
            continue

        if ch == "(":
            close = _find_close(body, i, "(", ")")
            if close < 0:
                return None
            end = _eat_quantifier(body, close + 1)
            inner = body[i:close + 1]
            capturing = not (inner.startswith("(?:") or inner.startswith("(?=")
                             or inner.startswith("(?!") or inner.startswith("(?<="))
            holes += 1
            out_pattern.append(body[i:end] if capturing else "(" + body[i:end] + ")")
            out_sample.append(f"{{{holes}}}")
            i = end
            continue

        if ch == ".":
            end = _eat_quantifier(body, i + 1)
            holes += 1
            out_pattern.append("(" + body[i:end] + ")")
            out_sample.append(f"{{{holes}}}")
            i = end
            continue

        # обычный символ; если за ним повторитель — это тоже переменная часть
        end = _eat_quantifier(body, i + 1)
        if end > i + 1:
            holes += 1
            out_pattern.append("(" + body[i:end] + ")")
            out_sample.append(f"{{{holes}}}")
        else:
            out_pattern.append(ch)
            out_sample.append(ch)
        i = end
        continue

    sample = re.sub(r"\s+", " ", "".join(out_sample)).strip()
    letters = sum(1 for c in sample if c.isalpha())

    if not sample or holes > MAX_HOLES or letters < 6:
        return None
    # Проверяя на regex-мусор, сначала убираем НАШИ подстановки {1}, {2} —
    # иначе фильтр забракует ровно те шаблоны, ради которых всё и затевалось.
    residue = re.sub(r"\{\d+}", "", sample)
    if MESSY.search(residue):
        return None

    return prefix + "".join(out_pattern) + suffix, sample, holes


def main() -> int:
    try:
        data = fetch()
    except Exception as exception:
        print(f"не скачалось: {exception}", file=sys.stderr)
        return 1

    patterns: dict[str, str] = {}
    collect(data.get("regexes", data), "", patterns)
    print(f"шаблонов в файле: {len(patterns)}")

    rules = []
    skipped_messy = 0
    skipped_short = 0
    broad = 0

    # Переводы, сделанные раньше, переносим по ключу — переимпорт не должен
    # обнулять работу.
    done: dict[str, str] = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8")).get("regex") or []
            done = {r["_key"]: r["r"] for r in previous if r.get("_key") and r.get("r")}
        except (json.JSONDecodeError, OSError):
            done = {}
    if done:
        print(f"перенесу готовых переводов: {len(done)}")

    for name, pattern in sorted(patterns.items()):
        if len(pattern) < 8:
            skipped_short += 1
            continue
        pattern = COLOR_CODE.sub("", pattern)
        converted = convert(pattern)
        if converted is None:
            skipped_messy += 1
            continue
        new_pattern, sample, groups = converted

        # шаблон должен остаться рабочим после нашей переделки
        try:
            compiled = re.compile(new_pattern)
        except re.error:
            skipped_messy += 1
            continue
        # и число дырок в образце обязано совпасть с числом групп в шаблоне,
        # иначе подстановка $1/$2 при переводе съедет на соседнюю
        if compiled.groups != groups:
            skipped_messy += 1
            continue

        # Подозрительно широкий шаблон: текста мало, дырок много — такой поймает лишнее
        letters = sum(1 for c in sample if c.isalpha())
        wide = letters < 12 or groups >= 4
        if wide:
            broad += 1

        rule = {
            "p": new_pattern,
            "r": done.get(name, ""),
            "_sample": sample,
            "_key": name,
        }
        if wide:
            rule["_warn"] = "широкий шаблон — проверить глазами, может поймать лишнее"
        rules.append(rule)

    pack = {
        "id": "chat_rules",
        "priority": 20,
        "_comment": "Правила для сообщений чата. Шаблоны взяты из SkyHanni-REPO (MIT), "
                    "переводы наши. Поле _sample — читаемый вид шаблона, по нему и переводим: "
                    "{1}, {2} — куски, которые подставляет сервер (ники, предметы, числа). "
                    "В готовом переводе они записываются как $1, $2.",
        "_source": "https://github.com/hannibal002/SkyHanni-REPO (MIT)",
        "regex": rules,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")

    print()
    print(f"годных правил:            {len(rules)}")
    print(f"  из них широких:         {broad}  (помечены _warn)")
    print(f"пропущено (не текст):     {skipped_messy}")
    print(f"пропущено (слишком коротких): {skipped_short}")
    print()
    print(f"записано: {OUT.relative_to(ROOT)}")
    print()
    # путь к скрипту печатаем полностью: команду часто запускают не из папки проекта
    print("Дальше:")
    print(f'  python "{ROOT / "tools" / "translate_ai.py"}" data/work/chat_rules.json --limit 200')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
