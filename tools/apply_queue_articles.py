"""
Вписывает переводы из `queue_articles.py` в очередь строк.

⚠️ Сопоставление идёт по тексту БЕЗ значков: они непечатаемы, и в исходнике
скрипта их не набрать. Значки возвращаются из оригинала на метки {i1}, {i2}.

⚠️ Уже заполненное НЕ трогаем: перевод мог прийти другим путём и быть лучше.

Запуск:
  python tools/apply_queue_articles.py           показать, что впишется
  python tools/apply_queue_articles.py --apply   вписать
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from queue_articles import LABELS, WHOLE  # noqa: E402

QUEUE = ROOT / "data" / "work" / "from_game.json"

ICON = re.compile(r"[-☀-➿⬀-⯿]")
# «Blocks Mined: {n}», «✓ Loadout Slots: {n}», « Mythological Tiers: {n}%»
LABEL_LINE = re.compile(r"^(\W*)(.+?): ([+\-]?\{n\}%?)$")


def без_значков(text: str) -> str:
    return re.sub(r"\s+", " ", ICON.sub(" ", text)).strip()


def put_icons(russian: str, original: str) -> str:
    icons = ICON.findall(original)
    out = russian
    for number, icon in enumerate(icons, start=1):
        out = out.replace("{i%d}" % number, icon)
    return re.sub(r"\s*\{i\d}", "", out)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Переводы подписей в очередь")
    parser.add_argument("--apply", action="store_true", help="вписать в очередь")
    args = parser.parse_args()

    data = json.loads(QUEUE.read_text(encoding="utf-8"))
    exact = data.get("exact") or {}
    asis = set(data.get("_asis") or [])

    whole_clean = {без_значков(k): v for k, v in WHOLE.items()}
    made: dict[str, str] = {}
    for key, value in exact.items():
        if value or key in asis:
            continue
        clean = без_значков(key)
        # 1) строка целиком
        if clean in whole_clean:
            made[key] = put_icons(whole_clean[clean], key)
            continue
        # 2) подпись «Имя: {n}» — сохраняем ведущие значки и хвост значения
        hit = LABEL_LINE.match(key)
        if not hit:
            continue
        head, name, tail = hit.groups()
        russian = LABELS.get(без_значков(name))
        if russian:
            made[key] = f"{head}{russian}: {tail}"

    print(f"ждали перевода: {sum(1 for k, v in exact.items() if not v and k not in asis)}")
    print(f"впишется: {len(made)}")
    print()
    for key, value in list(made.items())[:12]:
        print(f"  {без_значков(key)[:44]:<44} -> {без_значков(value)[:40]}")

    if not made:
        return 0
    if not args.apply:
        print()
        print("это СУХОЙ прогон — чтобы вписать, добавь --apply")
        return 0

    exact.update(made)
    QUEUE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    left = sum(1 for k, v in exact.items() if not v and k not in asis)
    print()
    print(f"вписано: {len(made)}, осталось ждать: {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
