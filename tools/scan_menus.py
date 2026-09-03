"""
ЛОСКУТ по блокам подсказок из дампа: где игрок увидит половину перевода.

Зачем отдельно от `scan.py` и `scan_all.py`. Первый читает `preview.json` —
там лежит только то, на что игрок НАВЁЛ КУРСОР за эту сессию (десятки
подсказок). Второй берёт лор аукциона — там ходовое оружие и броня, а меню,
настроек и справочников нет вовсе. Экран настроек SkyBlock не виден ни тому,
ни другому — и 17.08 игрок дважды прислал скриншот с непереведённым
описанием кнопки, которое ни один сторож не находил.

А данные были: `dump/tooltips.json` хранит БЛОКИ подсказок целиком — всё,
что игрок открывал за все сессии (9600+ блоков). Значит «часть строк блока
переводится, часть нет» считается без игры и по всему, что он видел.

Что показывает:
  ЛОСКУТ     в блоке есть и переведённые строки, и нет — игрок видит смесь
  ЗАГОЛОВОК  подпись кнопки не переводится, а описание под ней да (или наоборот)

⚠️ Имя ВЕЩИ не переводим намеренно, поэтому блок, где не переведён только
заголовок-предмет, лоскутом не считается. Отличает вещь от кнопки тот же
признак, что и везде: `Titles.java` пишет кнопки в источник `menu_title`.

⚠️ Строки, закрытые АБЗАЦЕМ, считаются переведёнными: мод склеит их и
подставит перевод целиком. Иначе инструмент краснел бы на каждом описании.

Запуск:
  python tools/scan_menus.py              список по убыванию размера
  python tools/scan_menus.py --show 40    сколько блоков печатать
  python tools/scan_menus.py --buttons    только кнопки меню (без вещей)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")
PLAYERS = ROOT / "data" / "work" / "from_players.json"


def buttons() -> set[str]:
    """Заголовки, которые мод назвал КНОПКОЙ, а не вещью."""
    out: set[str] = set()
    for path in (DUMP / "collected.json", PLAYERS):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        out |= {s for s in ((data.get("sources") or data).get("menu_title") or {})
                if isinstance(s, str)}
    return out


def paragraph_keys() -> set[str]:
    """Абзацы с переводом: их строки мод закроет склейкой."""
    path = ROOT / "data" / "work" / "paragraphs.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else (data.get("paragraphs")
                                                or list(data.values())[0])
    return {p["text"] for p in rows
            if isinstance(p, dict) and p.get("text") and p.get("ru")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", type=int, default=25)
    parser.add_argument("--buttons", action="store_true",
                        help="только кнопки меню, без подсказок вещей")
    parser.add_argument("--strict", action="store_true",
                        help="ЗАГОЛОВОК переводится, а описание нет — самый "
                             "чистый признак «половина по-русски»")
    args = parser.parse_args()

    import status
    # ⚠️ Ленивый импорт: pick_queue сам тянет status и очередь.
    import pick_queue
    import protected

    tips = json.loads((DUMP / "tooltips.json").read_text(encoding="utf-8"))
    blocks = tips.get("tooltips") if isinstance(tips, dict) else tips
    blocks = blocks if isinstance(blocks, list) else list(blocks.values())

    dic = status.Dictionaries()
    keys = buttons()
    paragraphs = paragraph_keys()

    names = protected.real_items() | protected.collect()
    CYRILLIC = re.compile("[А-Яа-яЁё]")

    def translated(line: str) -> bool:
        """Строка уже по-русски?

        ⚠️ Мало спросить словарь: в `tooltips.json` мод пишет ЗАГОЛОВОК
        подсказки уже ПЕРЕВЕДЁННЫМ («Категория острова»), а в словаре ключ
        английский — и проверка по словарю на нём молчит. Ровно поэтому
        сканер пропустил жалобу игрока про «Категорию острова»: там
        заголовок русский, описание английское, а `--strict` требовал
        совпадения по словарю и отбрасывал блок.
        """
        return bool(CYRILLIC.search(line)) or bool(status.lookup(line, dic))

    def worth(line: str) -> bool:
        """Это РАБОТА или наше решение?

        ⚠️ Без этой проверки отчёт краснеет на том, что мы не переводим
        НАМЕРЕННО: имена предметов в списках («- Kite Spray»), жаргон
        характеристик, имена мэров и питомцев. Первый прогон дал 923
        «лоскута», и почти все были такими. Записанная грабля проекта:
        отчёт, показывающий РЕШЕНИЯ бедой, приучает в него не смотреть.
        Спрашиваем тот же классификатор, что и очередь, — своей копии
        признаков не заводим.
        """
        if line in names:
            return False
        try:
            kind = pick_queue.classify(line, "item_lore")
        except Exception:
            return True
        # ⚠️ «ОБРЫВОК» здесь — РАБОТА, в отличие от очереди. Там его покупать
        # вредно (у полфразы нет своего смысла), а на экране игрок видит
        # именно его: описание кнопки разрезано переносом на три строки, и
        # все три — обрывки. Отсеяв их, сканер промолчал на «Категории
        # острова», которую игрок прислал скриншотом.
        return kind in ("покупка", "обрывок")

    found = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        title = block.get("item")
        raw = [x for x in (block.get("lines") or []) if isinstance(x, str)]
        lines = [x for x in raw if x.strip()]
        if not isinstance(title, str) or len(lines) < 2:
            continue
        # ⚠️ Заголовок, УЖЕ НАБРАННЫЙ КИРИЛЛИЦЕЙ, — это точно не вещь:
        # имена предметов мы не переводим по решению, значит перевели мы
        # его сознательно, то есть это подпись кнопки. Признак нужен потому,
        # что в блок мод пишет заголовок ПОСЛЕ перевода («Категория
        # острова»), а список `menu_title` держит оригинал («Island
        # Category») — сопоставить их нечем, и жалоба игрока про эту самую
        # подсказку проходила мимо сканера.
        is_button = title in keys or bool(CYRILLIC.search(title))
        if args.buttons and not is_button:
            continue

        # ⚠️ Мод режет подсказку на абзацы ПО ПУСТЫМ СТРОКАМ (Paragraphs.runs),
        # и склеивает только подряд идущие. Первая версия выбрасывала пустые
        # и склеивала всё тело в одну строку — ключ не совпадал с корпусом,
        # и переведённое описание объявлялось непереведённым. Повторяем
        # правило мода, а не своё.
        runs, current = [], []
        for line in raw[1:]:
            if line.strip():
                current.append(line)
            elif current:
                runs.append(current)
                current = []
        if current:
            runs.append(current)

        body = lines[1:]
        body_missing = []
        for run in runs:
            if len(run) > 1 and " ".join(run) in paragraphs:
                continue                       # абзац переведён — мод склеит
            body_missing += [x for x in run
                             if not translated(x) and worth(x)]
        head_missing = (not translated(title)) and is_button and worth(title)

        done = [x for x in body if translated(x)]
        if not body_missing and not head_missing:
            continue
        # ⚠️ САМЫЙ ЧИСТЫЙ СРЕЗ: подпись кнопки уже по-русски, а описание под
        # ней английское. Ровно это игрок и присылал скриншотами 17.08, и
        # шума тут почти нет — заголовок переводится, значит перед нами
        # НАСТРОЙКА, а не вещь с непереводимым именем.
        if args.strict:
            if head_missing or not translated(title) or not body_missing:
                continue
        # ЛОСКУТ — когда часть уже по-русски: именно это и видно глазами
        elif not done and not head_missing:
            continue
        found.append({
            "item": title,
            "button": is_button,
            "head": head_missing,
            "missing": body_missing,
            "done": len(done),
        })

    found.sort(key=lambda x: -(len(x["missing"]) + (1 if x["head"] else 0)))
    print("блоков подсказок: %d, ЛОСКУТОВ: %d" % (len(blocks), len(found)))
    print("   из них кнопок меню: %d"
          % sum(1 for x in found if x["button"]))
    print()
    for row in found[:args.show]:
        tag = "кнопка" if row["button"] else "вещь  "
        print("[%s] %r  (переведено строк: %d)" % (tag, row["item"][:52], row["done"]))
        if row["head"]:
            print("     ЗАГОЛОВОК не переводится")
        for line in row["missing"][:6]:
            print("     нет: %r" % line[:66])
    if len(found) > args.show:
        print("\n... ещё %d (--show больше)" % (len(found) - args.show))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
