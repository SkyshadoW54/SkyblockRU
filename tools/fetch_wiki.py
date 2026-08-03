"""
Берёт статью термина с вики Hypixel SkyBlock — фактами, а не пересказом.

⚠️ Зачем инструмент. Справку в игре («что такое Overbloom») можно писать
по памяти, и это худший путь: выдуманное описание хуже отсутствующего, потому
что ему верят. Здесь факты приходят из вики: описание, значок, предел, откуда
берётся. Остаётся перевести и разметить цветом.

⚠️ WebFetch до fandom не достаёт — отдаёт 402. Обычный запрос с User-Agent
проходит, поэтому ходим напрямую в MediaWiki API:
    /api.php?action=parse&page=<термин>&prop=wikitext&format=json

Запуск:
  python tools/fetch_wiki.py Overbloom          показать, что говорит вики
  python tools/fetch_wiki.py Overbloom --raw    сырой wikitext целиком
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://hypixel-skyblock.fandom.com/api.php"
AGENT = "SkyblockRU-translation-mod/0.1 (personal, low-volume)"

# {{Stat|Overbloom}} -> Overbloom, [[Rare Crops]] -> Rare Crops, '''жирный''' -> жирный
TEMPLATE = re.compile(r"\{\{[Ss]tat\|([^}|]+)(?:\|[^}]*)?\}\}")
LINK = re.compile(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]")
BOLD = re.compile(r"'''([^']+)'''")
ITALIC = re.compile(r"''([^']+)''")
COMMENT = re.compile(r"<!--.*?-->", re.S)
TAG = re.compile(r"<[^>]+>")


def fetch(page: str) -> str:
    url = f"{API}?{urllib.parse.urlencode({'action': 'parse', 'page': page, 'prop': 'wikitext', 'format': 'json'})}"
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"].get("info", "вики не отдала страницу"))
    return data["parse"]["wikitext"]["*"]


def clean(text: str) -> str:
    """Разметку вики убираем, СМЫСЛ оставляем."""
    text = COMMENT.sub("", text)
    text = TEMPLATE.sub(r"\1", text)
    text = LINK.sub(r"\1", text)
    text = BOLD.sub(r"\1", text)
    text = ITALIC.sub(r"\1", text)
    text = TAG.sub("", text)
    text = text.replace("**", "")
    return re.sub(r"[ \t]+", " ", text).strip()


def infobox(raw: str) -> dict[str, str]:
    """Поля карточки: значок, предел, откуда берётся."""
    out: dict[str, str] = {}
    box = re.search(r"\{\{Infobox[^\n]*\n(.*?)\n\}\}", raw, re.S)
    if not box:
        return out
    for line in box.group(1).splitlines():
        pair = re.match(r"\s*\|\s*([A-Za-z_]+)\s*=\s*(.*)", line)
        if pair and pair.group(2).strip():
            out[pair.group(1).lower()] = clean(pair.group(2))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Статья термина с вики Hypixel SkyBlock")
    parser.add_argument("page", help="название термина, как на вики: Overbloom")
    parser.add_argument("--raw", action="store_true", help="сырой wikitext")
    args = parser.parse_args()

    try:
        raw = fetch(args.page)
    except (urllib.error.URLError, RuntimeError, KeyError) as error:
        print("не получилось:", error)
        return 1

    if args.raw:
        print(raw)
        return 0

    card = infobox(raw)
    print(f"=== {args.page} ===")
    for key in ("symbol", "unicode", "type", "uses", "increasing", "minvalue", "maxvalue"):
        if card.get(key):
            print(f"  {key:11} {card[key]}")

    body = clean(re.sub(r"\{\{Infobox.*?\n\}\}", "", raw, flags=re.S))
    print()
    print("--- текст статьи ---")
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("[[Category") or line.startswith("{{"):
            continue
        if line.startswith("=="):
            print()
            print("  " + line.strip("= "))
            continue
        print("    " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
