# -*- coding: utf-8 -*-
"""
Снимает перевод у абзацев из СЛУЖЕБНЫХ строк — их склеивать вредно.

Внизу подсказки Hypixel ставит подряд требование, «Co-op Soulbound» и строку
редкости. Пустой строкой они не разделены, поэтому для мода это ОДИН абзац,
и купленный перевод склеивает их в сплошную строку. Беда двойная:

  * служебные метки — не проза, их вёрстка значима сама по себе;
  * мерцающие символы гибнут. Hypixel пишет их как «§k» + буква:
    «§d§l§ka§r §d§lMYTHIC HELMET §d§l§ka» — на экране это бегущий глиф,
    похожий на звёздочку. Дамп §-коды снимает, в корпус попадает голая «a»,
    а плоский перевод абзаца выкладывается БЕЗ §k — и вместо мерцания игрок
    видит буквы: «МИФИЧЕСКИЙ ШЛЕМ а», «Привязан к кооперативу ˟ а».

Снимаем ТОЛЬКО там, где каждая строка абзаца закрыта построчно, — иначе
вместо слипшегося русского получим английский, а это хуже.

    python tools/drop_service_paragraphs.py         показать
    python tools/drop_service_paragraphs.py --yes   применить
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
import status  # noqa: E402

CORPUS = ROOT / "data" / "work" / "paragraphs.json"

# строка редкости целиком: «MYTHIC HELMET», «LEGENDARY DUNGEON BOOTS»,
# по краям может стоять мерцающая «a» (в дампе от §k остаётся только буква)
RARITY_LINE = re.compile(
    r"^a? ?(COMMON|UNCOMMON|RARE|EPIC|LEGENDARY|MYTHIC|DIVINE|SPECIAL|SUPREME"
    r"|ULTIMATE|VERY SPECIAL|ADMIN)[A-Z '-]* ?a?$")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Служебные абзацы — построчно")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--show", type=int, default=10)
    args = parser.parse_args()

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = doc.get("paragraphs") or []
    dictionaries = status.Dictionaries()
    queue, corpus_state = status.load_queue(), status.load_corpus()

    drop, kept = [], 0
    for para in paragraphs:
        # ⚠️ Смотрим И НЕПЕРЕВЕДЁННЫЕ, а не только купленные.
        #
        # Сперва инструмент брал лишь абзацы с `ru` — то есть умел ОТМЕНЯТЬ
        # покупку, но не умел её предотвратить. Замер 02.08: 34 таких абзаца
        # ждали перевода и просились в оплату каждый прогон, хотя решение вести
        # их построчно принято ещё 02.08. Покупка была бы вредна дважды: перевод
        # не применился бы (мод ведёт их построчно), а мерцание §k погибло бы.
        # Признак один и тот же, поэтому и место ему одно.
        if para.get("nothing"):
            continue
        lines = [str(row).strip() for row in (para.get("lines") or [])]
        if not any(RARITY_LINE.match(line) for line in lines):
            continue
        # ⚠️ Снимаем, только если КАЖДАЯ строка переводится сама по себе.
        # Иначе абзац — единственный путь, и снять его значит показать
        # английский текст вместо слипшегося русского.
        ok = True
        for line in lines:
            if not line:
                continue
            # ⚠️ Проверяем и ЯДРО строки: мерцающие «a» по краям — это §k-символы
            # Hypixel, в словаре их нет и быть не должно. Мод переведёт такую
            # строку ПОКУСОЧНО (`walk`), заменив «MYTHIC HELMET» и не тронув «a»
            # вместе с её стилем — то есть мерцание уцелеет, чего абзац как раз
            # и не умеет.
            core = re.sub(r"^a\s+|\s+a$", "", line).strip()
            good = False
            for probe in {line, core}:
                answer = status.verdict(probe, dictionaries, queue, corpus_state)
                if answer["status"] in ("перевод есть", "переводить нечего (помечено)"):
                    good = True
                    break
            if not good:
                ok = False
                break
        if ok:
            drop.append(para)
        else:
            kept += 1

    bought = sum(1 for para in drop if para.get("ru"))
    print(f"абзацев со строкой редкости: {len(drop) + kept}")
    print(f"  все строки закрыты построчно — берём построчно: {len(drop)}")
    print(f"     из них снимаем купленный перевод:            {bought}")
    print(f"     из них НЕ покупаем (перевода и не было):     {len(drop) - bought}")
    print(f"  оставляем (абзац единственный путь):    {kept}")
    print()
    for para in drop[:args.show]:
        print("   ", pkey.key_of(para.get("lines") or [])[:76])
    if len(drop) > args.show:
        print(f"   ... ещё {len(drop) - args.show}")

    if not args.yes:
        print("\nсухой прогон. Применить: --yes")
        return 0

    for para in drop:
        para.pop("ru", None)
        para["nothing"] = True
    CORPUS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nснято переводов: {len(drop)} (строки закрывает построчный путь)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
