"""
Ключ абзаца и обобщение чисел — ОДНА реализация на весь проект.

⚠️ Зачем. Ключ абзаца строят ДВОЕ: мод в игре (`Paragraphs.key`) и скрипты
при сборке корпуса. Разойдутся хоть на пробел — перевод не найдётся НИ РАЗУ,
и беда будет тихой: ошибок нет, подсказки просто английские, будто словарь пуст.

Со стороны скриптов копий накопилось шесть, и одна уже разошлась: в
`measure_color.py` обобщение было `\\d+(?:[.,]\\d+)*%?` — с процентом на конце,
то есть «+20%» превращалось в «{n}», а у всех остальных в «{n}%». Такое
расхождение не ловится ничем, кроме случайного взгляда.

Здесь правила ровно те же, что в моде:
  * ЧИСЛО — цифры с разделителями внутри: «1,234», «2.5», «1,018.6»;
  * процент и значок в число НЕ входят: «+20%» -> «+{n}%»;
  * строки склеиваются ОДНИМ пробелом;
  * кусок короче двух строк абзацем не считается.

Сверяет обе стороны `tools/check_contract.py` — правишь тут, прогони его.
"""
from __future__ import annotations

import re

# ⚠️ Ровно как в моде: цифры и разделители ВНУТРИ числа. Знак процента,
# значок и скобки остаются снаружи — они часть текста, а не значения.
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

# §-коды: в ключ они не входят никогда — один и тот же текст Hypixel красит
# по-разному у разных предметов, и с кодами словарь не совпал бы.
CODE = re.compile("§.")

MIN_LINES = 2


def strip_codes(text: str) -> str:
    """Снять §-коды: ключ строится по чистому тексту."""
    return CODE.sub("", text)


def generalize(text: str) -> str:
    """Числа -> {n}. То же самое делает Translator при поиске."""
    return NUMBER.sub("{n}", text)


def key_of(lines: list[str], generalise: bool = True) -> str:
    """
    Ключ абзаца из его строк: снять коды, склеить пробелом, обобщить числа.

    ⚠️ Склейка ИМЕННО одним пробелом и ИМЕННО после снятия кодов — иначе ключ
    разойдётся с модом. Пустые строки сюда не передают: по ним кусок режется.
    """
    joined = " ".join(strip_codes(str(line)).strip() for line in lines).strip()
    joined = re.sub(r"\s+", " ", joined)
    return generalize(joined) if generalise else joined


def is_paragraph(lines: list[str]) -> bool:
    """Годится ли кусок в абзац: не короче двух непустых строк."""
    return len([l for l in lines if strip_codes(str(l)).strip()]) >= MIN_LINES


def runs(lines: list[str]) -> list[list[str]]:
    """
    Режет строки на абзацы ПО ПУСТЫМ СТРОКАМ — единственный признак, который
    знает и мод. Строку-характеристику он обойти не умеет и вклеит её в абзац,
    поэтому и скрипты режут только так.
    """
    out: list[list[str]] = []
    run: list[str] = []
    for line in list(lines) + [""]:
        if strip_codes(str(line)).strip():
            run.append(str(line))
            continue
        if is_paragraph(run):
            out.append(run.copy())
        run = []
    return out


def main() -> int:
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    samples = [
        (["§7Grants §a+20%§7 chance", "§7to catch §dSea Creatures§7."],
         "Grants +{n}% chance to catch Sea Creatures."),
        (["Health: +293 (+40)"], "Health: +{n} (+{n})"),
        (["You will earn 2% interest", "for your first 2 million coins."],
         "You will earn {n}% interest for your first {n} million coins."),
    ]
    bad = 0
    for lines, expect in samples:
        got = key_of(lines)
        ok = got == expect
        bad += not ok
        print(("  [ok] " if ok else "  [ПРОВАЛ] ") + got)
        if not ok:
            print("     ждали: " + expect)
    print()
    print("замечаний:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
