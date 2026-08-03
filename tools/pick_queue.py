# -*- coding: utf-8 -*-
"""
Отбор строк очереди, которые СТОИТ покупать, в отдельный файл-заготовку.

Зачем отдельный файл: очередь держит вперемешку то, за что платить надо,
и то, за что платить ВРЕДНО. Прогон по всей очереди покупает и обрывки —
полфразы, разрезанной переносом, — а у обрывка нет своего смысла: каждая
половина переводится «на глазок» и на стыке рождается «и даёт щит щит».
Это записанная беда Hyperion, и стоила она реальных денег дважды.

Что отсеиваем и почему (замер 31.07 на живой очереди, 459 строк):

  обрывок фразы        209   покупать вредно — лечится абзацем, а не строкой
  техническое / ники    68   «Sending to server mini5M», «Visit popgrain»
  жаргон                 8   решение игрока: остаётся английским
  зачарования            -   выключенный словарь, решение игрока

Остаётся законченная фраза и короткая метка — 174 строки, за них и платим.

    python tools/pick_queue.py                  показать, что отберётся
    python tools/pick_queue.py --out FILE.json  записать заготовку
    python tools/pick_queue.py --merge FILE.json  влить переводы обратно
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
import terms  # noqa: E402

QUEUE = ROOT / "data" / "work" / "from_game.json"

TECH = re.compile(r"^(minecraft:|/|\{s\}\.|Sending to server|Server:|Visit |FAST Portal)")
NICK = re.compile(r"^\S+ \(Offline \{n\}[dhm]\)$|\(More\.\.\.\)$")
# ⚠️ Двоеточие — тоже конец строки, а не разрыв. «Select an option:» и «Награды:»
# законченны сами по себе: это подпись, за которой идёт список. Без двоеточия
# в наборе они считались обрывками (три слова, точки нет) и молча выпадали
# из покупки — при том, что подпись видна на экране чаще любого описания.
ENDS = re.compile(r"[.!?:»)\]]\s*$")
# имя зачарованной книги: «Angler {n}», «Feast {n}-{n}»
BOOK = re.compile(r"^([A-Z][A-Za-z' \-]+?) (?:\d+(?:-\d+)?|\{n\}(?:-\{n\})?)$")
# ⚠️ Уровень бывает и РИМСКИЙ: у книги базара он арабский («Angler 6»), а на
# предмете — римский («Absorb IX», «Flowstate III»). BOOK знал только первый,
# и половина зачарований числилась работой, хотя sb_enchants выключен решением
# игрока. Замер 01.08: 516 таких строк в отчёте, все ложные.
LEVELLED = re.compile(r"^(.+?)\s+(?:[IVXLC]+|\d+(?:-\d+)?|\{n\}(?:-\{n\})?)$")
# Строка начинается с ДЫРКИ (с точностью до значков и знаков перед ней):
# «{s} joined the lobby!», «+{n} Foraging Experience», «({n}/{n}) Emblems»
STARTS_WITH_HOLE = re.compile(r"^[^\w{]*\{[ns]\}")


def is_enchant(text: str, enchants: set[str]) -> bool:
    """
    «Имя + уровень», где имя значится зачарованием У СЕРВЕРА.

    ⚠️ Признак по ФОРМЕ («имя + римский уровень») тут не годится в одиночку:
    под него попадают коллекции («Melon Slice VII»), уровни навыков и миньоны —
    правка по форме уже стоила проекту 179 абзацев. Поэтому имя обязано быть
    в списке зачарований, а список берётся у сервера, а не сочиняется.
    """
    match = LEVELLED.match(text.strip())
    return bool(match) and match.group(1).lower() in enchants


def classify(line: str, enchants: set[str]) -> str:
    """К какому слою относится строка. Слои не пересекаются — иначе счёт врёт."""
    text = line.strip()
    book = BOOK.match(text)
    if book and book.group(1).lower() in enchants:
        return "зачарование"
    # ⚠️ На предмете зачарования идут СПИСКОМ через запятую («Critical VII,
    # Cubism V, Drain V»), и каждый набор — новая строка: их столько, сколько
    # собрали игроки. Считать это работой значит гнаться за комбинаторикой.
    # Требуем, чтобы ВСЕ части были зачарованиями: одна чужая — и это уже
    # не набор, а перечисление чего-то другого.
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) > 1 and all(is_enchant(part, enchants) for part in parts):
        return "зачарование"
    if is_enchant(text, enchants):
        return "зачарование"
    if TECH.search(text) or NICK.search(text):
        return "техническое"
    if any(word in text for word in terms.STAT_JARGON):
        return "жаргон"
    # ⚠️ Обрывок узнаём по тому, что фраза НЕ ЗАВЕРШЕНА: перенос Hypixel режет
    # предложение посреди, и вторая половина начинается со строчной буквы или
    # служебного слова. Короткие метки («Back», «Diversity») сюда не попадают —
    # у них меньше трёх слов, и это осознанная граница: метка без точки
    # законченна сама по себе, а «Grants +5 Speed for» — нет.
    if not ENDS.search(text) and len(text.split()) >= 3:
        return "обрывок"
    # ⚠️ У обрывка ДВА края, и раньше проверялся только правый. Хвост переноса
    # кончается точкой и потому выглядел законченной фразой: «loot.», «up!»,
    # «them.», «water.» — 96 таких строк в отчёте 01.08. Английское предложение
    # со строчной буквы не начинается, значит начало — верный признак хвоста.
    #
    # ⚠️ Строка, НАЧИНАЮЩАЯСЯ с дырки, под этот признак не идёт: дырка стоит
    # вместо слова, и регистр следующего за ней ничего не говорит о разрыве.
    # «{s} joined the lobby!» и «+{n} Foraging Experience» законченны, а по
    # букве после дырки выглядели бы обрывками — проверено на 4564 купленных
    # переводах, ложных срабатываний было бы 2210.
    if not STARTS_WITH_HOLE.match(text):
        first = next((ch for ch in text if ch.isalpha()), "")
        if first and first.islower():
            return "обрывок"
    return "покупка"


def waiting_lines() -> list[str]:
    doc = json.loads(QUEUE.read_text(encoding="utf-8"))
    exact = doc.get("exact") or {}
    asis = set(doc.get("_asis") or [])
    rest = [k for k, v in exact.items() if not v and k not in asis]
    dictionaries = status.Dictionaries()
    queue, corpus = status.load_queue(), status.load_corpus()
    # ⚠️ Спрашиваем ДВИЖОК, а не свои признаки: строка, закрытая правилом или
    # купленным абзацем, до построчного перевода не доходит вовсе.
    return [line for line in rest
            if status.verdict(line, dictionaries, queue, corpus)["status"] == "ЖДЁТ В ОЧЕРЕДИ"]


def merge_back(source: Path) -> int:
    """Влить переводы из заготовки обратно в очередь."""
    done = json.loads(source.read_text(encoding="utf-8")).get("exact") or {}
    doc = json.loads(QUEUE.read_text(encoding="utf-8"))
    exact = doc.setdefault("exact", {})
    added = 0
    for key, value in done.items():
        if value and key in exact and not exact[key]:
            exact[key] = value
            added += 1
    QUEUE.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"влито переводов: {added} из {sum(1 for v in done.values() if v)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="куда записать заготовку")
    parser.add_argument("--merge", help="влить переводы из заготовки обратно в очередь")
    args = parser.parse_args()

    if args.merge:
        return merge_back(Path(args.merge))

    enchants = {name.lower() for name in terms.of("enchant")}
    groups: dict[str, list[str]] = {}
    for line in waiting_lines():
        groups.setdefault(classify(line, enchants), []).append(line)

    for name, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        mark = "  <- ПОКУПАЕМ" if name == "покупка" else ""
        print("  %-14s %4d%s" % (name, len(rows), mark))

    picked = sorted(groups.get("покупка", []))
    print("\nк покупке: %d строк" % len(picked))
    if not args.out:
        print("\nзаписать: python tools/pick_queue.py --out data/work/queue_pick.json")
        return 0

    Path(args.out).write_text(
        json.dumps({"_comment": "отобранные строки очереди, см. tools/pick_queue.py",
                    "exact": {line: "" for line in picked}},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print("записано:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
