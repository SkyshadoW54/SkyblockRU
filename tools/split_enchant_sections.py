"""
Нарезать УЖЕ КУПЛЕННЫЕ абзацы зачарований на отдельные зачарования.

⚠️ Зачем, и почему это не стоит ни копейки.

Абзац зачарований склеивается из НАБОРА, который стоит на предмете:
«Bank V + Growth VI + Protection VI» — один ключ, «Bank V + Aqua Affinity I +
Growth V» — уже другой. Наборов столько, сколько игроки собрали, поэтому целиком
абзац почти никогда не совпадает: по живому дампу из 480 блоков перевод есть
у 89, а у 391 нет.

Напрашивается «докупить недостающие комбинации». Это ложный путь: комбинаций
бесконечно много, а купленное уже содержит нужное. В корпусе лежит

    «Growth V Grants +{n} ❤ Health. Protection V Grants +{n} ❈ Defense.»
    -> «Growth V Даёт +{n} ❤ к здоровью. Защита V Даёт +{n} ❈ к защите.»

то есть переводы ОБОИХ зачарований — просто слитые в одну запись. Разрезав её,
получаем два самостоятельных абзаца, которые подойдут ЛЮБОМУ набору:

    «Growth V Grants +{n} ❤ Health.»      -> «Growth V Даёт +{n} ❤ к здоровью.»
    «Protection V Grants +{n} ❈ Defense.» -> «Защита V Даёт +{n} ❈ к защите.»

Режем ровно тем же приёмом, каким мод режет абзац на экране
(`ParagraphColors.sections`): позиция заголовка в переводе известна из словаря,
а не угадывается.

⚠️ Новые записи ДОБАВЛЯЮТСЯ, старые не трогаются: абзац целиком тоже нужен —
он точнее и найдётся первым, когда набор совпал.

Запуск:
  python tools/split_enchant_sections.py           показать, что выйдет
  python tools/split_enchant_sections.py --apply   добавить в корпус
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pkey  # noqa: E402

CORPUS = ROOT / "data" / "work" / "paragraphs.json"

ENCHANT_HEAD = re.compile(r"^[A-Z][A-Za-z' -]*\s[IVXLC]+$")
# Между словом и уровнем разметка вставляет §-коды — та же грабля, что
# с «§bМагического§7 §bпоиска§7»: обычный \s+ не совпадёт.
GAP = r"(?:§.|\s)+"


def variants_of(head: str, dic) -> list[str]:
    """Как заголовок может выглядеть в переводе: сам по себе и переводом."""
    from check_sections import expand_keys

    out = [head]

    def add(value: str) -> None:
        if not value:
            return
        if "@" in value:
            value = expand_keys(value) or ""
        if value and value not in out:
            out.append(value)

    hit = dic.exact.get(head)
    if hit:
        add(hit[0])
        return out
    for rule in dic.rules:
        pattern, replacement = rule.pattern, rule.replacement
        match = pattern.fullmatch(head)
        if match:
            try:
                add(match.expand(re.sub(r"\$(\d)", r"\\\1", replacement)).strip())
            except (re.error, IndexError):
                pass
            break
    return out


def cut_points(translated: str, groups: list[list[str]]) -> list[tuple[int, int]]:
    """
    Позиции заголовков в переводе — как ParagraphColors.sections.

    Ищем ПО ПОРЯДКУ, каждый следующий правее предыдущего: иначе «Growth V»,
    встретившееся дважды, дало бы две метки на одном месте.
    """
    plain = pkey.strip_codes(translated)
    # карта «позиция в чистом -> позиция в исходном»
    where: list[int] = []
    i = 0
    while i < len(translated):
        if translated[i] == "§" and i + 1 < len(translated):
            i += 2
            continue
        where.append(i)
        i += 1
    where.append(len(translated))

    found: list[tuple[int, int]] = []
    edge = 0
    for group in groups:
        at = -1
        length = 0
        for variant in group:
            head = (variant or "").strip()
            if not head:
                continue
            spot = plain.find(head, edge)
            if spot >= 0 and (at < 0 or spot < at):
                at = spot
                length = len(head)
        if at < 0:
            found.append((-1, 0))
            continue
        found.append((where[at], where[at + length] - where[at]))
        edge = at + length
    return found


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Нарезка абзацев зачарований")
    parser.add_argument("--apply", action="store_true", help="добавить в корпус")
    args = parser.parse_args()

    import status
    dic = status.Dictionaries()

    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = data.get("paragraphs") or []
    known = {p["text"] for p in paragraphs}

    made: dict[str, str] = {}
    skipped = 0
    for para in paragraphs:
        translated = para.get("ru") or ""
        rows = [str(row) for row in (para.get("lines") or [])]
        clean = [pkey.strip_codes(row).strip() for row in rows]
        heads = [i for i, row in enumerate(clean) if row and ENCHANT_HEAD.match(row)]
        if not translated or len(heads) < 2:
            continue

        groups = [variants_of(clean[i], dic) for i in heads]
        points = cut_points(translated, groups)
        if sum(1 for at, _ in points if at >= 0) < 2:
            skipped += 1
            continue

        for order, start in enumerate(heads):
            at, length = points[order]
            if at < 0:
                continue
            stop = heads[order + 1] if order + 1 < len(heads) else len(rows)
            piece = rows[start:stop]
            if len([row for row in piece if pkey.strip_codes(row).strip()]) < 2:
                continue  # заголовок без описания — переводить нечего
            key = pkey.key_of(piece)
            if not key or key in known or key in made:
                continue
            # Перевод секции: от её заголовка до начала следующего.
            end = len(translated)
            for later, _ in points[order + 1:]:
                if later >= 0:
                    end = later
                    break
            value = translated[at:end].strip()
            if value:
                made[key] = value

    print(f"абзацев в корпусе: {len(paragraphs)}")
    print(f"нарезано НОВЫХ зачарований: {len(made)}")
    if skipped:
        print(f"не разрезалось (заголовок не нашёлся): {skipped}")
    print()
    for key, value in list(made.items())[:8]:
        print(f"  {key[:66]}")
        print(f"    -> {re.sub('§.', '', value)[:66]}")

    if not made:
        return 0
    if args.apply:
        for key, value in made.items():
            paragraphs.append({"text": key, "lines": [], "item": "", "count": 1,
                               "live": True, "ru": value})
        CORPUS.write_text(json.dumps({"paragraphs": paragraphs},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        print()
        print(f"добавлено в корпус: {len(made)} (стало {len(paragraphs)})")
    else:
        print()
        print("это СУХОЙ прогон — чтобы применить, добавь --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
