"""
Ванильные зачарования в корпусе — теми ли словами, что в клиенте игрока.

⚠️ Зачем. Ванильное зачарование мод отдаёт САМОЙ игре: в словаре лежит
«@enchantment.minecraft.depth_strider», и клиент подставляет «Подводная
ходьба». Но в корпусе абзацев те же зачарования переведены СВОИМИ словами,
как их когда-то написала модель: «Покоритель глубин III», «Огнестойкость V».

Получается разнобой внутри одной подсказки: в списке зачарований вверху
предмет назван по-клиентски, а в описании ниже — по-нашему. Игрок видит
два разных названия одного зачарования и не может связать их между собой.

Побочный вред виден в `check_sections.py`: заголовок секции ищется по
переводу из словаря, а в корпусе лежит другое слово — и абзац объявляется
неразрезаемым, хотя в игре он режется.

⚠️ Правим ТОЛЬКО ЗАГОЛОВОК секции — «Имя УРОВЕНЬ» в начале абзаца. В прозе
замена опасна: у русских названий разный род и падеж («Покоритель глубин»
мужской, «Подводная ходьба» женский), и слепая замена дала бы «с Подводная
ходьба». Это та же грабля, что записана про `rename_term.py`.

Запуск:
  python tools/check_vanilla_names.py           показать расхождения
  python tools/check_vanilla_names.py --fix     починить заголовки
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_sections import vanilla_lang  # noqa: E402

CORPUS = ROOT / "data" / "work" / "paragraphs.json"
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

CODE = re.compile("§.")
ROMAN = r"[IVXLC]{1,6}"


def vanilla_names() -> dict[str, str]:
    """
    Английское имя ванильного зачарования -> русское ИЗ КЛИЕНТА.

    Источник соответствия — наши же словари: там ванильное отличается от
    кастомного тем, что перевод начинается с «@». Придумывать список заново
    нельзя: он разойдётся с тем, что мод реально отдаёт игре.
    """
    lang = vanilla_lang()
    out: dict[str, str] = {}
    for path in PACKS.rglob("*.json"):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for name, value in (pack.get("glossary") or {}).items():
            # ⚠️ Только ЗАЧАРОВАНИЯ. По «@» отбирать нельзя: тем же способом
            # записаны 2581 ванильное НАЗВАНИЕ ПРЕДМЕТА, и с ними список
            # раздувался до 2602 — вместо трёх десятков настоящих.
            if isinstance(value, str) and value.startswith("@enchantment."):
                russian = lang.get(value[1:])
                if russian:
                    out[name] = russian
    return out


def head_of(text: str) -> tuple[str, str] | None:
    """Заголовок «Имя УРОВЕНЬ» в начале строки -> (имя, уровень)."""
    match = re.match(rf"^([A-Z][A-Za-z' -]*?)\s({ROMAN})(?=\s|$)", text)
    return (match.group(1), match.group(2)) if match else None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Ванильные названия против клиента")
    parser.add_argument("--fix", action="store_true", help="починить заголовки")
    args = parser.parse_args()

    names = vanilla_names()
    if not names:
        print("не нашёл русскую локализацию игры — проверять нечем")
        return 1
    print(f"ванильных зачарований известно: {len(names)}")

    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = data.get("paragraphs") or []
    bad: list[tuple[dict, str, str, str]] = []
    for para in paragraphs:
        translated = para.get("ru") or ""
        if not translated:
            continue
        head = head_of(CODE.sub("", para.get("text") or ""))
        if not head:
            continue
        name, level = head
        client = names.get(name)
        if not client:
            continue
        plain = CODE.sub("", translated).strip()
        # Как должно начинаться: «Подводная ходьба III». Английское имя
        # тоже годится — значит зачарование оставлено как есть, и это
        # не наша забота.
        if plain.startswith(f"{client} {level}") or plain.startswith(f"{name} {level}"):
            continue
        got = plain.split(".")[0][:60]
        bad.append((para, name, client, got))

    print(f"абзацев с заголовком ванильного зачарования и переводом: "
          f"{sum(1 for p in paragraphs if p.get('ru') and head_of(CODE.sub('', p.get('text') or '')) and names.get(head_of(CODE.sub('', p.get('text') or ''))[0]))}")
    print(f"названо НЕ ТАК, КАК В КЛИЕНТЕ: {len(bad)}")
    print()
    seen: dict[str, int] = {}
    for _, name, client, got in bad:
        seen[f"{name} -> клиент «{client}», у нас «{got}»"] = \
            seen.get(f"{name} -> клиент «{client}», у нас «{got}»", 0) + 1
    for line, count in sorted(seen.items(), key=lambda x: -x[1]):
        print(f"  {count:3}x  {line}")

    if not args.fix:
        print()
        print("это сухой прогон, --fix починит заголовки")
        return 0

    fixed = 0
    for para, name, client, _ in bad:
        translated = para["ru"]
        head = head_of(CODE.sub("", para.get("text") or ""))
        level = head[1]
        plain = CODE.sub("", translated).strip()
        # ⚠️ Заголовок кончается там, где стоит римский уровень. Меняем
        # ровно его, остальной текст не трогаем: в прозе то же слово
        # может стоять в другом падеже, и замена сломала бы согласование.
        cut = re.match(rf"^(.*?\s{level})(?=\s|$)", plain)
        if not cut:
            continue
        old_head = cut.group(1)
        if old_head.count(" ") > 4:
            continue                      # это не заголовок, а фраза
        # правку делаем в РАЗМЕЧЕННОЙ строке: ищем текст заголовка по кускам
        new = replace_head(translated, old_head, f"{client} {level}")
        if new and new != translated:
            para["ru"] = new
            fixed += 1

    if fixed:
        CORPUS.write_text(json.dumps({"paragraphs": paragraphs},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(f"починено заголовков: {fixed}")
    print(f"записано: {CORPUS.relative_to(ROOT)}" if fixed else "файл не менялся")
    return 0


def replace_head(marked: str, old_head: str, new_head: str) -> str | None:
    """
    Заменить заголовок в РАЗМЕЧЕННОМ переводе, сохранив §-коды.

    ⚠️ Текст заголовка в размеченной строке разорван кодами («§9Огне§7…»
    не бывает, но «§7§9Growth V§7» — сплошь и рядом), поэтому ищем по
    строке БЕЗ кодов, а режем по позициям в исходной.
    """
    plain_pos = []
    plain = []
    i = 0
    while i < len(marked):
        if marked[i] == "§" and i + 1 < len(marked):
            i += 2
            continue
        plain.append(marked[i])
        plain_pos.append(i)
        i += 1
    text = "".join(plain)
    at = text.find(old_head)
    if at < 0:
        return None
    start = plain_pos[at]
    end = plain_pos[at + len(old_head) - 1] + 1
    return marked[:start] + new_head + marked[end:]


if __name__ == "__main__":
    raise SystemExit(main())
