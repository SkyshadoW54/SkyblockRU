# -*- coding: utf-8 -*-
"""
Сверка РАЗМЕТКИ цвета в переводах абзацев с цветным оригиналом — без игры.

Зачем. Игрок прислал 11.10 ожерелье: «Даёт §c{n}§c❤ за каждый уровень Рыбалки.
Рыбалка: §eуровень IX» — после сердца нет возврата §7, и красный тянется через
полпредложения. Это не догадка мода, а дырка в РАЗМЕТКЕ, то есть в данных,
и такие дырки можно найти механически: у нас есть оригинал с кусками и их
цветами (живые дампы всех инстансов, аукцион, репозиторий NEU — те же три
источника, что у `color_lore.py`, живая игра первой), и есть перевод
с §-кодами. Сравниваем ДОЛЮ видимых знаков каждого цвета:

  * утечка  — цвет занял в переводе заметно больше, чем в оригинале
              (красный на 40 знаков при 2 в оригинале);
  * потеря  — цвет оригинала в переводе отсутствует вовсе;
  * плоский — перевод без §-кодов при цветном оригинале (мод красит догадкой,
              потолок которой 20–47% знаков — записано в color_lore.py).

Самый частый механический случай утечки — ЦВЕТНОЕ ЧИСЛО БЕЗ ВОЗВРАТА:
«§c{n}❤ за каждый…», когда в оригинале кусок «6❤» красный, а следующий — серый.
`--fix-resets` вставляет код СЛЕДУЮЩЕГО куска оригинала сразу после числа.
Правится ИСТОЧНИК (корпус `data/work/paragraphs.json` и заготовка режима
`data/work/full_paragraphs_ru.json`), словари потом пересобираются
`merge_paragraphs.py` и `gen_full_paragraphs.py --write`. Текст не меняется —
только §-коды, и это проверяется: снятие кодов до и после обязано совпасть.

Как сторож в круге `refresh.py`: ругается только на РОСТ числа утечек и потерь
против базовой линии (`data/work/color_markup_baseline.json`); текущее число
принимается `--accept`. Подсадка при каждом запуске: синтетические утечка,
потеря и плоский обязаны ловиться, здоровый случай — проходить, починка —
восстанавливать возврат цвета.

Запуск:
  python tools/check_color_markup.py                 отчёт по 96 и 86
  python tools/check_color_markup.py --show 20       больше примеров
  python tools/check_color_markup.py --fix-resets    сухой прогон починки
  python tools/check_color_markup.py --fix-resets --write
  python tools/check_color_markup.py --accept        принять текущее за планку
  python tools/check_color_markup.py --keys FILE     выписать ключи с дефектом
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import color_lore  # noqa: E402
import pkey  # noqa: E402

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs" / "ru_ru"
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
SKELETON = ROOT / "data" / "work" / "full_paragraphs_ru.json"
BASELINE = ROOT / "data" / "work" / "color_markup_baseline.json"
LIVE_DUMPS = r"C:\MultiMC\instances\*\.minecraft\config\skyblockru\dump\paragraph-colors.json"
PACK_NAMES = ("96-paragraphs.json", "86-full-paragraphs.json")

CODE = re.compile("§.")
COLORS = "0123456789abcdef"
# цветное число с необязательным знаком, процентом, повтором кода и значком:
# «§c{n}❤», «§a+{n}%», «§c{n}§c❤», «§b{n}\ue003»
TOKEN = re.compile(r"§([0-9a-f])(\+?\{n\}%?(?:§\1)?[^§\s,.!;:)(]{0,2})")
# утечка считается, если доля цвета в переводе превысила долю в оригинале
# в LEAK_RATIO раз плюс LEAK_PAD; порог подобран так, чтобы живой случай
# ожерелья (2 знака против 40) ловился, а «§a+{n}% урона» (число плюс слово
# у Hypixel тоже цветные) — нет.
LEAK_RATIO = 2.5
LEAK_PAD = 0.08
LOSS_MIN_SHARE = 0.03


def shares_of_pieces(pieces: list[tuple[str, str]]) -> Counter:
    """Доля видимых знаков по цветам у оригинала (куски «§код», «текст»)."""
    out: Counter = Counter()
    for code, text in pieces:
        visible = re.sub(r"\s", "", text)
        if visible:
            out[code[:2] if code.startswith("§") else "§7"] += len(visible)
    return out


def shares_of_markup(text: str) -> Counter:
    """Доля видимых знаков по цветам у перевода с §-кодами."""
    out: Counter = Counter()
    colour = "§7"
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "§" and i + 1 < len(text):
            letter = text[i + 1].lower()
            if letter in COLORS:
                colour = "§" + letter
            elif letter == "r":
                colour = "§7"
            i += 2
            continue
        if not ch.isspace():
            out[colour] += 1
        i += 1
    return out


def originals() -> dict[str, list[tuple[str, str]]]:
    """Ключ абзаца -> куски оригинала (код, текст): живые дампы, аукцион, NEU."""
    out: dict[str, list[tuple[str, str]]] = {}
    # живые дампы ВСЕХ инстансов — первыми: это то, что игрок видит на экране
    for path in glob.glob(LIVE_DUMPS):
        try:
            cases = json.loads(Path(path).read_text(encoding="utf-8")).get("cases") or []
        except (json.JSONDecodeError, OSError):
            continue
        for case in cases:
            key = case.get("key")
            pieces = case.get("pieces") or []
            if not key or not pieces:
                continue
            converted = [(color_lore.COLOR_CODES.get(colour, "§7"), text) for colour, text in pieces]
            out.setdefault(pkey.generalize(key), converted)
    for key, lines in color_lore.coloured_lore().items():
        out.setdefault(key, color_lore.pieces_of(lines))
    return out


def judge(pieces: list[tuple[str, str]], ru: str) -> tuple[str, str]:
    """(вердикт, цвет): ok / leak / loss / plain / mono."""
    src = shares_of_pieces(pieces)
    if len(src) < 2:
        return "mono", ""
    if "§" not in ru:
        return "plain", ""
    dst = shares_of_markup(ru)
    total_s = sum(src.values()) or 1
    total_d = sum(dst.values()) or 1
    for colour, count in src.items():
        share_s = count / total_s
        share_d = dst.get(colour, 0) / total_d
        if share_d == 0 and share_s > LOSS_MIN_SHARE:
            return "loss", colour
        if colour not in ("§7", "§8") and share_d > share_s * LEAK_RATIO + LEAK_PAD:
            return "leak", colour
    return "ok", ""


def fix_resets(pieces: list[tuple[str, str]], ru: str) -> str | None:
    """Вставляет возврат цвета после цветного числа, если оригинал так красит.

    Кусок оригинала с числом берём по ТЕКСТУ: его обобщённый вид обязан
    совпасть с нашим токеном знак в знак («{n}❤» = «{n}❤»). Цвет следующего
    непустого куска и есть возврат. Если он совпадает с цветом токена —
    править нечего (у Hypixel число и слово одного цвета).
    """
    normalised = [(code, pkey.generalize(text).strip()) for code, text in pieces]
    out = ru
    offset = 0
    for match in TOKEN.finditer(ru):
        token_text = CODE.sub("", match.group(2))
        colour = "§" + match.group(1)
        if ru[match.end():match.end() + 1] == "§":
            continue  # возврат уже стоит
        if not re.match(r" ?[А-Яа-яёЁA-Za-z]", ru[match.end():]):
            continue  # дальше знак или конец — красить нечему
        next_colour = None
        for index, (code, text) in enumerate(normalised):
            if text != token_text or code[:2] != colour:
                continue
            for code2, text2 in normalised[index + 1:]:
                if text2:
                    next_colour = code2[:2]
                    break
            break
        if next_colour is None or next_colour == colour:
            continue
        at = match.end() + offset
        out = out[:at] + next_colour + out[at:]
        offset += 2
    return out if out != ru else None


def selftest() -> bool:
    """Подсадка: три беды обязаны ловиться, здоровый случай — проходить."""
    pieces = [("§7", "Gain "), ("§c", "6❤"), ("§7", " per Fishing level.")]
    cases = {
        "ok": "§7Даёт §c{n}❤§7 за каждый уровень Рыбалки.",
        "leak": "§7Даёт §c{n}❤ за каждый уровень Рыбалки.",
        "loss": "§7Даёт {n}❤ за каждый уровень Рыбалки.",
        "plain": "Даёт {n}❤ за каждый уровень Рыбалки.",
    }
    caught = 0
    healthy = 0
    for expect, ru in cases.items():
        verdict, _ = judge(pieces, ru)
        if verdict != expect:
            print(f"ПОДСАДКА ПРОВАЛЕНА: {ru!r} -> {verdict}, ждали {expect}")
            return False
        if expect == "ok":
            healthy += 1
        else:
            caught += 1
    fixed = fix_resets(pieces, cases["leak"])
    if fixed != cases["ok"]:
        print(f"ПОДСАДКА ПРОВАЛЕНА: починка дала {fixed!r}")
        return False
    print(f"подсадка: {caught} беды из {caught} поймано, {healthy} здоровый случай прошёл, "
          f"починка возврата 1 из 1")
    return True


def load_rows():
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    return data, rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Сверка разметки цвета с оригиналом")
    parser.add_argument("--show", type=int, default=5)
    parser.add_argument("--fix-resets", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--accept", action="store_true", help="принять текущее число за планку")
    parser.add_argument("--keys", help="выписать ключи с утечкой/потерей/плоские в файл (json)")
    args = parser.parse_args()

    if not selftest():
        return 1

    known = originals()
    print(f"оригиналов с цветными кусками: {len(known)}")

    totals: dict[str, int] = {}
    flagged: dict[str, dict[str, list[str]]] = {}
    for name in PACK_NAMES:
        pack = json.loads((PACKS / name).read_text(encoding="utf-8"))
        verdicts: Counter = Counter()
        examples: dict[str, list] = defaultdict(list)
        flagged[name] = defaultdict(list)
        for key, ru in (pack.get("paragraphs") or {}).items():
            pieces = known.get(key)
            if not pieces:
                continue
            verdict, colour = judge(pieces, ru)
            verdicts[verdict] += 1
            if verdict in ("leak", "loss", "plain"):
                flagged[name][verdict].append(key)
                if len(examples[verdict]) < args.show:
                    examples[verdict].append((colour, key[:60], CODE.sub("", ru)[:70] if verdict == "plain" else ru[:90]))
        compared = sum(verdicts.values()) - verdicts["mono"]
        print(f"\n{name}: сверено {compared}: в порядке {verdicts['ok']}, "
              f"утечка {verdicts['leak']}, потеря {verdicts['loss']}, плоских {verdicts['plain']}")
        totals[name] = verdicts["leak"] + verdicts["loss"]
        for kind in ("leak", "loss", "plain"):
            for colour, key, ru in examples[kind]:
                print(f"   {kind:5} {colour:3} «{key}» -> {ru}")

    if args.keys:
        Path(args.keys).write_text(json.dumps(flagged, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"ключи с дефектом записаны: {args.keys}")

    if args.fix_resets:
        data, rows = load_rows()
        fixed_corpus = 0
        samples = []
        for row in rows:
            ru = row.get("ru") or ""
            pieces = known.get(row.get("text") or "")
            if not pieces or "§" not in ru:
                continue
            new = fix_resets(pieces, ru)
            if new is None:
                continue
            if CODE.sub("", new) != CODE.sub("", ru):
                print(f"⚠️ текст изменился бы — пропуск: {ru[:60]!r}")
                continue
            fixed_corpus += 1
            if len(samples) < args.show:
                samples.append((ru[:80], new[:80]))
            if args.write:
                row["ru"] = new
        skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
        fixed_mode = 0
        for key, row in (skeleton.get("rows") or {}).items():
            ru = row.get("ru") or ""
            pieces = known.get(key)
            if not pieces or "§" not in ru:
                continue
            new = fix_resets(pieces, ru)
            if new is None or CODE.sub("", new) != CODE.sub("", ru):
                continue
            fixed_mode += 1
            if args.write:
                row["ru"] = new
        print(f"\nвозврат цвета после числа: корпус {fixed_corpus}, заготовка режима {fixed_mode}")
        for before, after in samples:
            print(f"   {before}\n   -> {after}")
        if args.write:
            CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            SKELETON.write_text(json.dumps(skeleton, ensure_ascii=False, indent=1), encoding="utf-8")
            print("записано; дальше: python tools/merge_paragraphs.py и "
                  "python tools/gen_full_paragraphs.py --write")
        else:
            print("СУХОЙ ПРОГОН, ничего не изменено. Записать: --write")

    worst = sum(totals.values())
    if args.accept:
        BASELINE.write_text(json.dumps(totals, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nпланка принята: {totals}")
        return 0
    if not BASELINE.exists():
        print(f"\nитого дефектов разметки: {worst}; планки нет — принять текущее: --accept")
        return 0
    known_line = json.loads(BASELINE.read_text(encoding="utf-8"))
    grew = {name: (known_line.get(name, 0), totals[name]) for name in totals
            if totals[name] > known_line.get(name, 0)}
    if grew:
        print(f"\nСЛОМАНО: дефектов разметки стало больше: {grew}")
        print("   новая разметка принесла утечку или потерю цвета — чинить источник "
              "(color_lore / --fix-resets); осознанный рост принять: --accept")
        return 1
    print(f"\nитого дефектов разметки: {worst} (планка {sum(known_line.values())}) — роста нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
