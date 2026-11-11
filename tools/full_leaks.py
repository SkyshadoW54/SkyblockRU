# -*- coding: utf-8 -*-
"""
Утечки латиницы в РЕЖИМЕ FULL: какие английские слова останутся на экране,
хотя строка считается переведённой.

Беда, ради которой написано (11.10). Игрок прислал подсказку абифона в режиме
full: заголовок «Трио контактов абифона», а в абзаце «…к твоему тарифу
Abiphone, доступных со всеми текущими и будущими Abiphones…». Ни один
инструмент этого не видел: `why.py` ответил «английских строк 0»,
`full_coverage` считал абзац «закрытым», детектор смеси языков в моде
нарочно пропускает слова с Заглавной (в обычном режиме имена законны).
Покрытие мерилось по НАЛИЧИЮ кириллицы, а не по ОТСУТСТВИЮ латиницы —
для режима, который обещает перевести всё, это неверный вопрос.

Что делает: берёт словари ровно так, как их видит мод при включённом режиме
(`status.Dictionaries(groups={"full"})`), и в КАЖДОМ значении — точные
записи, шаблоны, абзацы, замены правил — ищет латинские фразы. Вес берёт
из живого дампа: для абзацев — сколько раз игрок их видел (`live`, `count`
в корпусе), для строк — счётчики `collected.json`. Так верхушка списка —
то, что на экране чаще всего.

⚠️ Это сканер СЛОВАРЕЙ, а не движка: он не знает, что движок подставит
поверх перевода в рантайме (глоссарий с областью). Поэтому у каждой фразы
печатается, есть ли её перевод ЦЕЛИКОМ в каком-то словаре: если есть —
семья «подставить внутрь» (генератор `gen_full_*`), если нет — слова нет
нигде, и это работа переводчика.

⚠️ Что оставлено английским ПО РЕШЕНИЮ (`protected.ALWAYS`: Gems, Bits,
Hypixel…, плюс клавиши Shift/Ctrl/Alt и римские уровни), в основной список
не попадает, но считается и печатается отдельной строкой — ничего не
прячем молча.

    python tools/full_leaks.py                 верхушка по весу
    python tools/full_leaks.py --show 80       длиннее
    python tools/full_leaks.py --word Abiphone все записи с этой фразой
    python tools/full_leaks.py --file 96-paragraphs.json   только один словарь
    python tools/full_leaks.py --out FILE.json  выгрузить всё к работе
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

import status  # noqa: E402
import make_queue  # noqa: E402
import protected  # noqa: E402
from pkey import NUMBER  # noqa: E402

CORPUS = ROOT / "data" / "work" / "paragraphs.json"

CODE = re.compile("§.")
# `@ключ` — перевод даёт клиент игрока: «@enchantment.minecraft.protection»
KEY_TOKEN = re.compile(r"@[A-Za-z0-9_.]+")
HOLE = re.compile(r"\{[ns]\}")
COMMAND = re.compile(r"/[A-Za-z][A-Za-z0-9_]*")
# звание в скобках: «[MVP+]», «[VIP]»
RANK = re.compile(r"\[[A-Z][A-Z+ ]{1,10}\]")
# группа правила: «$1», «${2}»
GROUP = re.compile(r"\$\{?\d\}?")
# адрес сайта: «mc.hypixel.net» — слово, а не слова
DOMAIN = re.compile(r"\b[A-Za-z][A-Za-z-]*(?:\.[A-Za-z][A-Za-z-]*)+\b")
# латинская фраза: слова через пробел, с апострофом и дефисом внутри
PHRASE = re.compile(r"[A-Za-z][A-Za-z'’\-]*(?: [A-Za-z][A-Za-z'’\-]*)*")
# «V», «III», и диапазон «I-V» в списке источников зачарования
ROMAN = re.compile(r"[IVXLC]{1,6}(?:-[IVXLC]{1,6})?")

# Клавиши называем латиницей по решению («Shift+ПКМ»), счётчик стопки «x64»,
# метка говорящего «[NPC]» остаётся и в режиме (NpcPrefix меняет только имя)
KEYS = {"Shift", "Ctrl", "Alt", "Tab", "Esc", "Enter", "Space", "x", "NPC"}

# Оставлено английским ПО ЗАПИСАННОМУ РЕШЕНИЮ и в режиме full (notes/full-mode.md,
# notes/decisions.md): мем, которого дословный перевод убивает; эффект, чьё имя
# даёт клиент через @ключ; событие Bingo; валюта события; «Set» вне строки;
# мини-игра Superpairs (её переводы в 04-full-strings держат имя латиницей).
DECIDED = {"Absolute Unit", "Absorption", "Bingo", "Mystery Dust", "Set", "Superpairs"}

# Аббревиатуры игрового жаргона (BIN, HOTM, HP, XP, RNG, ID…): решения нет —
# считаем и печатаем отдельной строкой, в основной список не мешаем.
ABBREVIATION = re.compile(r"^[A-Z]{2,5}$")

# ⚠️ Реплики NPC: имя В ТЕЛЕ реплики требует падежа и отложено решением игрока
# 22.08 («слой B»). В основной список их не мешаем — иначе 13 тысяч отложенных
# записей заслонят то, что чинится сейчас. Считаем и печатаем отдельно.
DEFERRED = {"62-npc-dialogues.json"}

# имя говорящего — как его видит NpcPrefix: до первого двоеточия
SPEAKER = re.compile(r"^\[NPC\]\s+([^:]{1,40}):")


# ⚠️ `protected.ALWAYS` — защита ОБЫЧНОГО режима. В режиме full часть её
# переводится: «Bazaar» — «Базар» в 219 абзацах `86-full-paragraphs` и
# 15 строках `04-full-strings` (замер 12.10), и считать его «оставленным по
# решению» значило прятать настоящие утечки режима («…Рыбалка, Bazaar»).
# Бренды игры (SkyBlock, Hypixel) и валюты (Gems, Bits) остаются.
TRANSLATED_IN_FULL = {"Bazaar"}


def allowed() -> set[str]:
    """Что оставлено английским по решению — в нижнем регистре."""
    return ({w.lower() for w in protected.ALWAYS - TRANSLATED_IN_FULL}
            | {k.lower() for k in KEYS} | {d.lower() for d in DECIDED})


def phrases(value: str) -> list[str]:
    """Латинские фразы в переводе, без служебного."""
    text = CODE.sub("", value)
    text = KEY_TOKEN.sub(" ", text)
    text = HOLE.sub(" ", text)
    text = COMMAND.sub(" ", text)
    text = RANK.sub(" ", text)
    text = GROUP.sub(" ", text)
    text = DOMAIN.sub(" ", text)
    out = []
    for found in PHRASE.findall(text):
        words = found.split(" ")
        # римский уровень по краям — не слово: «Growth V», «V Рост»
        # ⚠️ Одиночная буква по краям — не слово: суффикс числа после дырки
        # («{n}k Organic Matter», «{n}x Wheat»), метка «(ID R{n})».
        while words and (ROMAN.fullmatch(words[-1]) or len(words[-1]) == 1):
            words.pop()
        while words and (ROMAN.fullmatch(words[0]) or len(words[0]) == 1):
            words.pop(0)
        if not words:
            continue
        phrase = " ".join(words)
        if len(phrase) < 2:
            continue
        out.append(phrase)
    return out


def weights() -> tuple[dict[str, int], dict[str, tuple[int, int]]]:
    """Сколько раз что видели: строки из дампа, абзацы из корпуса."""
    lines: dict[str, int] = defaultdict(int)
    for rows in (make_queue.load("collected.json").get("sources") or {}).values():
        for line, count in rows.items():
            lines[line] += int(count)
            shaped = NUMBER.sub("{n}", line)
            if shaped != line:
                lines[shaped] += int(count)
    paras: dict[str, tuple[int, int]] = {}
    if CORPUS.exists():
        for para in json.loads(CORPUS.read_text(encoding="utf-8")).get("paragraphs") or []:
            paras[para.get("text", "")] = (int(para.get("live") or 0), int(para.get("count") or 0))
    return lines, paras


_REFORGES: dict[str, str] | None = None


def reforges() -> dict[str, str]:
    """Перековки режима: имя -> мужская форма. Своя секция, в `exact` её нет."""
    global _REFORGES
    if _REFORGES is None:
        path = status.PACKS / "ru_ru" / "84-reforges.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        _REFORGES = {name: forms[0] for name, forms in (data.get("reforges") or {}).items()
                     if isinstance(forms, list) and forms}
    return _REFORGES


def whole_translation(phrase: str, dic: status.Dictionaries) -> tuple[str, str] | None:
    """
    Есть ли перевод этой фразы ЦЕЛИКОМ — тогда беда в подстановке, а не в словах.

    ⚠️ Смотрим не только `exact`: перековки лежат своей секцией в
    `84-reforges` («Fabled» -> «Сказочный», четыре формы рода), глоссарий —
    своей. Без этого «Бонус Fabled» числился работой переводчика, хотя слово
    переведено, а не подставлено (`gen_full_bonuses`).
    """
    for candidate in (phrase, phrase.rstrip("s"), phrase.lower(), phrase.title()):
        found = dic.exact.get(candidate)
        if found and found[0] and found[0] != candidate:
            return found[1], found[0]
        if candidate in reforges():
            return "84-reforges.json", reforges()[candidate]
        term = dic.glossary.get(candidate)
        if term and term != candidate and not term.startswith("@"):
            return "глоссарий", term
    return None


def without_speaker(key: str, value: str, dic: status.Dictionaries) -> str:
    """
    Реплика NPC без подписи говорящего — если её подменит сам мод.

    ⚠️ `core/NpcPrefix` в режиме меняет имя ДО первого двоеточия на русское
    из словарей с областью `name_tag` («[NPC] Karis:» -> «[NPC] Карис:»).
    Сканер словарей этого не видит и записывал бы 9 тысяч подписей утечками.
    Спрашиваем словарь так же, как мод: имя как надпись над головой.
    """
    plain = CODE.sub("", value)
    speaker = SPEAKER.match(CODE.sub("", key))
    if not speaker or not plain.startswith("[NPC]"):
        return value
    found = status.lookup(speaker.group(1).strip(), dic, origin="name_tag")
    if not found or not re.search("[А-Яа-яЁё]", found[0]):
        return value
    return plain.partition(":")[2]


def scan(dic: status.Dictionaries, only_file: str | None, with_deferred: bool):
    lines_w, paras_w = weights()
    skip = allowed()
    hits: dict[str, list[dict]] = defaultdict(list)
    decided: dict[str, int] = defaultdict(int)
    abbrev: dict[str, int] = defaultdict(int)
    deferred: dict[str, int] = defaultdict(int)
    scanned = 0
    leaking = 0

    def take(kind: str, key: str, value: str, file: str, weight: int) -> None:
        nonlocal scanned, leaking
        if only_file and file != only_file:
            return
        scanned += 1
        if kind == "exact":
            value = without_speaker(key, value, dic)
        found = phrases(value)
        if not found:
            return
        real = []
        for phrase in found:
            if phrase.lower() in skip:
                decided[phrase] += 1
            elif ABBREVIATION.fullmatch(phrase):
                abbrev[phrase] += 1
            else:
                real.append(phrase)
        if not real:
            return
        if file in DEFERRED and not with_deferred:
            deferred[file] += 1
            return
        leaking += 1
        for phrase in dict.fromkeys(real):
            hits[phrase].append({"kind": kind, "file": file, "key": key,
                                 "value": value, "weight": weight})

    for key, (value, file) in dic.exact.items():
        take("exact", key, value, file, lines_w.get(key, 0))
    for key, (value, file) in dic.templates.items():
        take("template", key, value, file, lines_w.get(key, 0))
    for key, (value, file) in dic.paragraphs.items():
        live, count = paras_w.get(key, (0, 0))
        take("paragraph", key, value, file, live * 10 + count)
    for rule in dic.rules:
        take("regex", rule.pattern.pattern, rule.replacement, rule.where, 0)
    return hits, decided, abbrev, deferred, scanned, leaking


def cut(text: str, width: int) -> str:
    text = CODE.sub("", text).replace("\n", " ")
    return text if len(text) <= width else text[:width - 1] + "…"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--show", type=int, default=40, help="сколько фраз показать")
    parser.add_argument("--word", help="все записи с этой фразой")
    parser.add_argument("--file", help="только этот словарь (имя файла)")
    parser.add_argument("--out", help="выгрузить находки в JSON")
    parser.add_argument("--all", action="store_true",
                        help="включить отложенное: тела реплик NPC (слой B)")
    parser.add_argument("--missing", action="store_true",
                        help="только фразы БЕЗ перевода целиком — работа переводчика")
    args = parser.parse_args()

    dic = status.Dictionaries(groups={"full"})
    hits, decided, abbrev, deferred, scanned, leaking = scan(dic, args.file, args.all)

    if args.missing:
        # ⚠️ Семья «слова нет нигде»: подстановкой не чинится, нужен перевод
        # термина — в 04-full-strings / 03-full-jargon / 85-mob-names по роду.
        hits = {p: es for p, es in hits.items() if whole_translation(p, dic) is None}

    ranked = sorted(hits.items(),
                    key=lambda kv: (-sum(e["weight"] for e in kv[1]), -len(kv[1]), kv[0]))

    if args.word:
        want = args.word.lower()
        rows = [(p, e) for p, es in hits.items() if p.lower() == want for e in es]
        rows.sort(key=lambda r: -r[1]["weight"])
        print(f"«{args.word}»: записей {len(rows)}")
        for phrase, e in rows:
            print(f"  [{e['kind']:9}] {e['file']}  вес {e['weight']}")
            print(f"      {cut(e['key'], 110)}")
            print(f"   -> {cut(e['value'], 110)}")
        return 0

    print(f"=== УТЕЧКИ ЛАТИНИЦЫ В РЕЖИМЕ FULL ===")
    print(f"    записей просмотрено: {scanned}, с латиницей: {leaking}, разных фраз: {len(hits)}")
    print(f"    оставлено по решению (не в списке): записей {sum(decided.values())}, "
          f"слова: {', '.join(sorted(decided, key=lambda w: -decided[w])[:8])}")
    for file, n in sorted(deferred.items()):
        print(f"    отложено решением 22.08 (имя в теле реплики, нужен падеж): "
              f"{file} — записей {n}; показать: --all")
    if abbrev:
        top = ", ".join(f"{w} ({n})" for w, n in sorted(abbrev.items(), key=lambda kv: -kv[1])[:10])
        print(f"    аббревиатуры — остаются по решению игрока 11.10 (не в списке): "
              f"записей {sum(abbrev.values())} — {top}")
    print(f"    вес = показы в игре (абзац: live×10 + count; строка: счётчик дампа)")
    print()
    print(f"  {'вес':>7} {'зап.':>5}  фраза                       перевод целиком          пример")
    for phrase, entries in ranked[:args.show]:
        weight = sum(e["weight"] for e in entries)
        whole = whole_translation(phrase, dic)
        whole_s = f"{whole[0][:14]}→{whole[1][:10]}" if whole else "—"
        top = max(entries, key=lambda e: e["weight"])
        files = sorted({e["file"] for e in entries})
        print(f"  {weight:7} {len(entries):5}  {cut(phrase, 27):27} {cut(whole_s, 24):24} "
              f"{top['file']}: {cut(top['value'], 60)}")
        if len(files) > 1:
            print(f"  {'':14}  словари: {', '.join(f[:22] for f in files[:5])}"
                  f"{' …' if len(files) > 5 else ''}")
    if len(ranked) > args.show:
        print(f"\n  ... ещё {len(ranked) - args.show} фраз (--show N)")

    by_file: dict[str, int] = defaultdict(int)
    for entries in hits.values():
        for e in entries:
            by_file[e["file"]] += 1
    print("\n  по словарям (записей с утечкой):")
    for file, n in sorted(by_file.items(), key=lambda kv: -kv[1])[:12]:
        print(f"    {n:6}  {file}")

    if args.out:
        out = {phrase: {"whole": whole_translation(phrase, dic), "entries": entries}
               for phrase, entries in ranked}
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(f"\nвыгружено: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
