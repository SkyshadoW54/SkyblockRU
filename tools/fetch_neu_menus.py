"""
Абзацы МЕНЮ из репозитория NEU — с готовой разметкой цвета.

Зачем. Из NEU мы годами берём только описания ПРЕДМЕТОВ (`items/`), а рядом,
в `constants/`, лежат тексты ЭКРАНОВ: деревья перков Heart of the Mountain
и Heart of the Forest. Их нет ни в API Hypixel (там вообще нет текстов меню),
ни в нашем дампе — пока игрок не откроет это меню сам. И лежат они СРАЗУ
С §-КОДАМИ, то есть перевод можно сделать точным по цвету, а не угаданным.

⚠️ ПОДСТАНОВКИ NEU становятся дырками {n}. В репозитории на месте чисел стоят
«{stat}», «{statFortune}» — это места ЗНАЧЕНИЙ, которые сервер подставляет
в игре. Движок знает только {n} и {s}, поэтому ключ с «{stat}» не совпал бы
НИ РАЗУ. Проект на этом уже терял 70 абзацев.

⚠️ Ключ строим ТЕМ ЖЕ правилом, что мод (`Paragraphs.runs`): режем по пустым
строкам, склеиваем одним пробелом, числа обобщаем. Разойдётся правило —
перевод не найдётся, и беда будет тихой: ошибок нет, подсказки английские.

Запуск:
    python tools/fetch_neu_menus.py             собрать заготовку
    python tools/fetch_neu_menus.py --show 5    показать примеры
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / "data" / "neu" / "repo.zip"
OUT = ROOT / "data" / "work" / "menu_paragraphs.json"

SECTION = re.compile(r"§.")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")

# Файлы, где лежит лор экранов. Список явный: в constants есть и служебное
# (координаты, цены), и брать оттуда всё подряд значило бы натащить мусора.
MENU_FILES = ("hotmlayout.json", "hotflayout.json", "misc.json", "garden.json")


def plain(text: str) -> str:
    return SECTION.sub("", text)


def make_key(lines: list[str]) -> str:
    joined = " ".join(plain(line).strip() for line in lines if plain(line).strip())
    return NUMBER.sub("{n}", PLACEHOLDER.sub("{n}", joined)).strip()


def generalize_marked(text: str) -> str:
    """
    Обобщает числа в РАЗМЕЧЕННОЙ строке — по кускам, а не сразу.

    ⚠️ Прямой `NUMBER.sub` тут портит разметку: цифра §-кода для регулярки
    чисел неотличима от числа, и «§7Blocks» превращается в «§{n}Blocks».
    Проект на этом уже терял 191 шаблон из 850 — на экране вместо золотого
    имени выходило «§123». Поэтому §-коды переносим как есть, а числа меняем
    только в тексте МЕЖДУ ними.
    """
    out = []
    position = 0
    for code in SECTION.finditer(text):
        out.append(NUMBER.sub("{n}", text[position:code.start()]))
        out.append(code.group())
        position = code.end()
    out.append(NUMBER.sub("{n}", text[position:]))
    return "".join(out)


def lore_blocks(node, out: list[list[str]]) -> None:
    """Все поля `lore` — так NEU хранит описания."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "lore" and isinstance(value, list) and all(isinstance(x, str) for x in value):
                out.append(value)
            else:
                lore_blocks(value, out)
    elif isinstance(node, list):
        for value in node:
            lore_blocks(value, out)


def collect() -> dict[str, dict]:
    found: dict[str, dict] = {}
    with zipfile.ZipFile(REPO) as archive:
        for name in archive.namelist():
            if "/constants/" not in name or name.split("/")[-1] not in MENU_FILES:
                continue
            try:
                data = json.loads(archive.read(name).decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            blocks: list[list[str]] = []
            lore_blocks(data, blocks)
            for lines in blocks:
                chunk: list[str] = []
                for line in list(lines) + [""]:
                    if plain(line).strip():
                        chunk.append(line)
                        continue
                    if chunk:
                        add(found, name.split("/")[-1], chunk)
                    chunk = []
    return found


def add(found: dict[str, dict], source: str, chunk: list[str]) -> None:
    key = make_key(chunk)
    # Слишком короткое — это подпись или одно слово, абзацем оно не бывает.
    if len(key) <= 12 or not any(SECTION.search(line) for line in chunk):
        return
    # ⚠️ Разметку храним ОТДЕЛЬНО от ключа: ключ должен совпасть с тем,
    # что мод построит по экрану, а там §-кодов уже нет. Числа в ней
    # обобщаем так же, как в ключе, — иначе перевод намертво запомнит «16».
    marked = " ".join(generalize_marked(PLACEHOLDER.sub("{n}", line.strip()))
                      for line in chunk if line.strip())
    found.setdefault(key, {"source": source, "marked": marked, "ru": ""})


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Абзацы меню из NEU")
    parser.add_argument("--show", type=int, default=0, help="показать N примеров")
    args = parser.parse_args()

    if not REPO.exists():
        print(f"нет репозитория NEU: {REPO}")
        print("скачать: python tools/fetch_neu.py")
        return 1

    fresh = collect()

    # ⚠️ Сперва читаем СВОЁ — в файле может лежать ручной перевод.
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")).get("paragraphs", {})
        except (json.JSONDecodeError, OSError) as problem:
            print(f"прежняя заготовка нечитаема: {problem}")
            return 1
    for key, item in fresh.items():
        was = old.get(key)
        if was and was.get("ru"):
            item["ru"] = was["ru"]

    # Что из этого мод и так знает — считаем, чтобы не платить дважды.
    corpus_path = ROOT / "data" / "work" / "paragraphs.json"
    known = set()
    if corpus_path.exists():
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        known = {p.get("text", "") for p in corpus["paragraphs"]}
    already = sum(1 for key in fresh if key in known)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_comment": "Абзацы ЭКРАНОВ из constants/ репозитория NEU. Поле marked — "
                    "оригинал С §-КОДАМИ: переводить надо вместе с ними, тогда мод "
                    "выложит цвет точно, а не догадкой. Ключ построен правилом мода "
                    "(Paragraphs.runs), подстановки NEU заменены на {n}.",
        "paragraphs": fresh,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    waiting = sum(1 for item in fresh.values() if not item["ru"])
    by_file: dict[str, int] = {}
    for item in fresh.values():
        by_file[item["source"]] = by_file.get(item["source"], 0) + 1

    print(f"абзацев меню: {len(fresh)}, ждут перевода: {waiting}")
    print(f"  уже есть в корпусе (платить не надо): {already}")
    for source, count in sorted(by_file.items(), key=lambda kv: -kv[1]):
        print(f"    {count:4}  {source}")

    for key, item in list(fresh.items())[:args.show]:
        print(f"\n  [{item['source']}] {key[:90]}")
        print(f"      {item['marked'][:120]}")

    print(f"\nзаготовка: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
