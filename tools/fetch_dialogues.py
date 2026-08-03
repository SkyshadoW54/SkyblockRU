"""
Диалоги NPC с вики — реплики, которые в игре собираются только квестами.

⚠️ Зачем. Мод видит лишь то, мимо чего игрок ходил: реплику из квеста, который
не проходили, он не встретит никогда. А на вики диалоги выписаны целиком — и,
что важнее, С ЦВЕТАМИ: «&e[NPC] &2Lumber Jack&f: Timber!». Это ровно тот вид,
в котором строку шлёт Hypixel, поэтому разметку не придётся угадывать.

Что делает:
  * находит все страницы с шаблоном Dialogue (их около тысячи);
  * достаёт реплики вида «[NPC] Имя: текст»;
  * ЧИСТИТ их так же, как это делает мод: снимает цветовые коды, разворачивает
    ссылки и шаблоны вики;
  * помечает подозрительные — чтобы не тащить в перевод мусор.

⚠️ Проверка на мусор обязательна. Вики — не дамп: там встречаются заготовки,
служебные пометки, обрывки и строки, собранные из шаблонов, которых в игре
не существует. Признак «строка лежала в разделе Dialogue» сам по себе ничего
не доказывает.

Запуск:
  python tools/fetch_dialogues.py --limit 40    выборка, посмотреть глазами
  python tools/fetch_dialogues.py --all         все страницы (долго)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_wiki import API, AGENT, fetch  # noqa: E402

OUT = ROOT / "data" / "work" / "npc_dialogues.json"
PAGES = ROOT / "data" / "work" / "_dialogue_pages.json"

# «&e[NPC] &2Lumber Jack&f: Timber!» — реплика с говорящим
NPC_LINE = re.compile(r"&e\[NPC\][^\n}|]*")
CODE = re.compile(r"&[0-9a-fk-orA-FK-OR]")
LINK = re.compile(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]")
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
SPEAKER = re.compile(r"^\[NPC\]\s*([^:]{1,40}):\s*(.+)$")


def api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=30) as answer:
        return json.loads(answer.read().decode("utf-8"))


def dialogue_pages() -> list[str]:
    """Все страницы, где используется шаблон Dialogue."""
    if PAGES.exists():
        try:
            return json.loads(PAGES.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    pages: list[str] = []
    cont = None
    while True:
        params = {"action": "query", "list": "embeddedin",
                  "eititle": "Template:Dialogue", "eilimit": "500", "format": "json"}
        if cont:
            params["eicontinue"] = cont
        data = api(params)
        pages += [item["title"] for item in data["query"]["embeddedin"]]
        cont = data.get("continue", {}).get("eicontinue")
        if not cont:
            break
    PAGES.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages


def strip_wiki(raw: str) -> str:
    """
    Снимает разметку ВИКИ, но оставляет цветовые коды.

    ⚠️ Цвета отсюда выбрасывать нельзя, и это дороже, чем кажется. На вики
    реплика лежит ровно в том виде, в каком её шлёт Hypixel — «&e[NPC]
    &2Lumber Jack&f: We will be &aForaging&f!», — то есть разметка нам дана
    ДАРОМ. Сняв её при сборке, мы обрекли себя либо на подсветку по догадке
    (мод ищет уцелевшие дословно куски и переведённое слово теряет), либо
    на ОТДЕЛЬНЫЙ платный прогон раскраски по всем девяти тысячам реплик.
    """
    text = raw
    for _ in range(3):
        text = TEMPLATE.sub("", text)
    text = LINK.sub(r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def clean(raw: str) -> str:
    """Строка как её увидит мод: без цветовых кодов и разметки вики."""
    return re.sub(r"\s+", " ", CODE.sub("", strip_wiki(raw))).strip()


# ⚠️ Признаки МУСОРА. Вики — не дамп: рядом с настоящими репликами лежат
# заготовки, служебные пометки и куски, собранные из шаблонов. Каждый признак
# ниже пойман на живых данных, а не придуман.
def suspicious(line: str) -> str | None:
    if len(line) < 12:
        return "слишком короткая"
    if not SPEAKER.match(line):
        return "нет говорящего «[NPC] Имя:»"
    body = SPEAKER.match(line).group(2)
    if not re.search(r"[A-Za-z]{3}", body):
        return "в тексте нет слов"
    if re.search(r"\{|\}|\||=", body):
        return "остатки разметки вики"
    # ⚠️ ДЫРА ОТ ВЫРЕЗАННОГО ШАБЛОНА. Имя игрока и названия предметов вики
    # хранит шаблонами ({{PLAYER}}, {{RD|...}}), а мы их снимаем — и остаётся
    # «Твой был улучшен до !» или «идеальная работёнка для .». Переводить
    # такое нельзя: фраза бессмысленна, а деньги за неё платятся настоящие.
    # Признак — пробел перед ОДИНОЧНЫМ знаком препинания; многоточие в начале
    # реплики («...Or do it the long way») под него не попадает.
    if re.search(r"\s([.,!?])(?!\1)|\b(?:a|an|the|for|to|with)\s+[.,!?]|\s#\s", body):
        return "дыра от вырезанного шаблона вики"
    return None


def split_glued(line: str) -> list[str]:
    """
    Разбивает слипшиеся реплики: «…текст./[NPC] Имя: текст…».

    ⚠️ Сперва я такие ОТБРАСЫВАЛ как мусор — и терял 16 настоящих реплик
    из 155 в выборке. Слипаются они в разметке вики (две строки в одной
    ячейке таблицы), но текст в них живой.
    """
    # ⚠️ Между «/» и «[NPC]» стоит ЦВЕТОВОЙ КОД («…/&e[NPC] Имя: …»), потому что
    # режем мы теперь строку с разметкой. Без учёта кода склейка не разрывалась
    # вовсе: три реплики Tomioka уезжали в одну запись, и переводить их пришлось
    # бы как одну — с чужими именами внутри.
    parts = re.split(r"/(?=(?:&[0-9a-fk-orA-FK-OR])*\[NPC\])", line)
    return [p.strip() for p in parts if p.strip()]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Диалоги NPC с вики")
    parser.add_argument("--limit", type=int, default=40, help="сколько страниц взять")
    parser.add_argument("--all", action="store_true", help="все страницы")
    parser.add_argument("--page", action="append", default=[], metavar="ИМЯ",
                        help="конкретная страница (можно несколько раз)")
    parser.add_argument("--apply", action="store_true", help="записать файл")
    args = parser.parse_args()

    pages = dialogue_pages()
    print(f"страниц с диалогами: {len(pages)}")
    if args.page:
        chosen = args.page
    else:
        chosen = pages if args.all else pages[::max(1, len(pages) // args.limit)][:args.limit]
    print(f"беру: {len(chosen)}")

    good: dict[str, dict] = {}
    bad: dict[str, str] = {}
    speakers: dict[str, int] = {}
    failed = 0
    for number, title in enumerate(chosen, start=1):
        if number % 50 == 0:
            print(f"  … {number}/{len(chosen)}")
        try:
            raw = fetch(title)
        except Exception:  # noqa: BLE001 — сеть
            failed += 1
            continue
        for hit in NPC_LINE.findall(raw):
            # ⚠️ Режем ЦВЕТНУЮ строку, а чистую получаем снятием кодов — так
            # обе версии режутся в одних и тех же местах. Резать порознь нельзя:
            # ключ (чистый текст) и разметка разъедутся, и цвет ляжет не туда.
            for colored in split_glued(strip_wiki(hit)):
                line = re.sub(r"\s+", " ", CODE.sub("", colored)).strip()
                if not line or line in good or line in bad:
                    continue
                why = suspicious(line)
                if why:
                    bad[line] = why
                    continue
                who = SPEAKER.match(line).group(1).strip()
                speakers[who] = speakers.get(who, 0) + 1
                entry = {"npc": who, "page": title}
                # Цветную версию храним, только если цвет в ней есть: пустое
                # поле рядом с каждой репликой — лишний шум в файле.
                if CODE.search(colored):
                    entry["raw"] = colored
                good[line] = entry

    print()
    print(f"реплик годных     : {len(good)}")
    print(f"отсеяно как мусор : {len(bad)}")
    print(f"страниц не открылось: {failed}")
    print(f"разных говорящих  : {len(speakers)}")
    print()
    print("=== почему отсеивалось ===")
    counts: dict[str, int] = {}
    for why in bad.values():
        counts[why] = counts.get(why, 0) + 1
    for why, count in sorted(counts.items(), key=lambda item: -item[1]):
        example = next(line for line, reason in bad.items() if reason == why)
        print(f"  {count:>4}  {why}")
        print(f"        {example[:76]}")

    print()
    print("=== примеры годных ===")
    for line in list(good)[:8]:
        print(f"  {line[:88]}")

    if args.apply:
        OUT.write_text(json.dumps({"lines": good, "rejected": bad},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print()
        print(f"записано: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
