"""
Названия зачарований в переводах — вернуть на место ЗАМЕНОЙ, а не покупкой.

Беда видна на любом предмете с зачарованиями. В корпусе лежит:

    «Bank V Сохраняет 50% твоих монет… Родство с водой I Увеличивает скорость
     добычи под водой. Рост V Даёт +75 к здоровью.»

Здесь сразу два разных нарушения, и оба тихие:

  * **Aqua Affinity** — ВАНИЛЬНОЕ зачарование, его перевод берётся у клиента
    игрока (@enchantment.minecraft.aqua_affinity → «Подводник»). А в переводе
    стоит «Родство с водой» — выдумка, которой нет ни в игре, ни в наших
    словарях. У игрока в инвентаре одно слово, в описании другое.
  * **Growth** — зачарование SkyBlock, оно живёт в переключаемом `sb_enchants`
    и по умолчанию ВЫКЛЮЧЕНО (по английским названиям ищут на аукционе).
    А в абзаце оно переведено «Рост» — то есть выключатель обойдён, ровно как
    это уже было с «Огранка V» (записано в граблях).

Побочный вред третий: пока название переведено НЕ так, как его знает словарь,
мод не может разрезать абзац на секции (`ParagraphColors.sections` ищет
заголовок по словарю) — и все зачарования слипаются в кашу.

⚠️ Чинится ЗАМЕНОЙ, а не повторным переводом. Это записанное правило проекта:
русское на английское меняется механически, стоит ноль и сохраняет разметку
цветом, тогда как повторный перевод её стирает и портит вычитанные формулировки.

Запуск:
  python tools/fix_enchant_names.py           показать, что не так (сухой прогон)
  python tools/fix_enchant_names.py --apply   починить
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
QUEUE = ROOT / "data" / "work" / "from_game.json"

LEVEL = r"(?:[IVXLC]+)"

# ⚠️ Разделитель между словом и уровнем — не просто пробел: разметка вставляет
# между ними §-коды («§bРодство с водой§7 I»). Та же грабля, что уже записана
# про «§bМагического§7 §bпоиска§7»: шаблон с обычным \s+ не совпадал, и запись
# переживала три захода замены подряд.
GAP = r"(?:§.|\s)+"


def rule_name(pattern: str) -> str | None:
    """Имя зачарования из шаблона правила: «^Growth ([IVXLC]+)$» -> «Growth»."""
    body = pattern
    if not body.startswith("^"):
        return None
    body = body[1:]
    body = re.split(r"[(\[]", body)[0]
    body = body.replace("\\", "").strip()
    return body or None


def vanilla_pairs() -> dict[str, str]:
    """Ванильное зачарование -> как его называет клиент игрока."""
    from check_sections import vanilla_lang

    lang = vanilla_lang()
    pairs: dict[str, str] = {}
    for path in PACKS.rglob("*.json"):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for rule in pack.get("regex") or []:
            key = re.search(r"@([a-z0-9_]+(?:\.[a-z0-9_]+)+)", rule.get("r", ""))
            if not key:
                continue
            name = rule_name(rule.get("p", ""))
            translated = lang.get(key.group(1))
            if name and translated:
                pairs[name] = translated
    return pairs


def toggle_pairs() -> dict[str, str]:
    """Зачарование SkyBlock -> его русский перевод из ВЫКЛЮЧЕННОГО словаря."""
    pairs: dict[str, str] = {}
    for path in PACKS.rglob("*.json"):
        if path.name == "index.json":
            continue
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if pack.get("default") is not False:
            continue
        for rule in pack.get("regex") or []:
            name = rule_name(rule.get("p", ""))
            russian = re.sub(r"\$\d|§.", "", rule.get("r", "")).strip()
            # Только настоящие имена: замена должна быть русским словом,
            # а не той же латиницей и не пустой строкой.
            if name and russian and re.search(r"[А-Яа-яЁё]", russian):
                pairs.setdefault(name, russian)
    return pairs


def build_fixes() -> list[tuple[re.Pattern, str, str, str]]:
    """
    Что на что менять: (шаблон, замена, английское имя-сторож, пояснение).

    Ванильное — на клиентское название, чтобы совпадало с инвентарём игрока.
    SkyBlock — обратно на АНГЛИЙСКОЕ, потому что словарь с ними выключен.

    ⚠️ Имя-сторож обязательно. Русское слово НЕ определяет зачарование
    однозначно: «Удача» — это и `Luck` (SkyBlock, выключено), и ванильная
    `Fortune`, которую клиент зовёт точно так же. Замена вслепую превратила бы
    правильную «Удача III» у Fortune в «Luck III». Поэтому меняем только там,
    где в ОРИГИНАЛЕ строки стоит именно это английское имя.
    """
    fixes: list[tuple[re.Pattern, str, str, str]] = []

    for name, client in vanilla_pairs().items():
        for wrong in wrong_forms(name, client):
            fixes.append((
                re.compile(re.escape(wrong) + r"(?=" + GAP + LEVEL + r"\b)"),
                client, name,
                f"ванильное: «{wrong}» -> «{client}» (так его зовёт клиент)"))

    for name, russian in toggle_pairs().items():
        fixes.append((
            re.compile(re.escape(russian) + r"(?=" + GAP + LEVEL + r"\b)"),
            name, name,
            f"SkyBlock: «{russian}» -> «{name}» (словарь выключен)"))

    # ⚠️ И ОБРАТНО: ванильное зачарование, оставшееся в переводе английским.
    # Решение игрока — переводить их, потому что клиент Minecraft и так зовёт
    # их по-русски, и в инвентаре игрок видит «Подводник», а не «Aqua Affinity».
    # Длинные имена вперёд: «Fire Protection» должен победить «Protection».
    for name in sorted(vanilla_pairs(), key=len, reverse=True):
        client = vanilla_pairs()[name]
        fixes.append((
            re.compile(r"(?<![A-Za-z])" + re.escape(name) + r"(?=" + GAP + LEVEL + r"\b)"),
            client, name,
            f"на русский: «{name}» -> «{client}» (ванильное, так зовёт клиент)"))
    return fixes


def leading_capital(text: str, at: int) -> bool:
    """
    Стоит ли ПЕРЕД этим местом ещё одно слово с заглавной буквы.

    ⚠️ Без этой проверки замена лезет внутрь составного имени: «Mining Fortune»
    превратилось бы в «Mining Удача», потому что «Fortune» — известное ванильное
    зачарование. А «Mining Fortune» — характеристика-жаргон, её трогать нельзя
    вовсе. Два заглавных слова подряд — это имя целиком.

    Приём взят у `merge_paragraphs.keep_enchants_consistent`, где он появился
    после «Trophy Охотник V».
    """
    before = text[:at].rstrip()
    previous = re.search(r"([A-Za-z]+)$", before)
    return bool(previous and previous.group(1)[0].isupper())


SEEN: dict[str, set[str]] = {}


def wrong_forms(name: str, client: str) -> list[str]:
    """Чужие переводы ванильного зачарования, найденные ПО ПОРЯДКУ заголовков."""
    return sorted(SEEN.get(name, set()) - {client})


def scan_wrong(vanilla: dict[str, str]) -> None:
    """
    Собирает, какими русскими словами названы ванильные зачарования.

    ⚠️ Сопоставляем ПО ПОРЯДКУ, а не по совпадению уровня. Первая версия искала
    в переводе русское слово с тем же римским уровнем — и разъезжалась на любом
    предмете, где уровни повторяются: у «Protection V … Respiration III …
    Thorns III» она сватала «Подводное дыхание» к Thorns и предлагала заменить
    его на «Шипы». Сухой прогон показал 53 такие «починки», все ложные.

    Правильно так: заголовки оригинала идут слева направо, и в переводе они
    стоят в ТОМ ЖЕ порядке. Значит каждый следующий ищем ПРАВЕЕ предыдущего —
    ровно как это делает ParagraphColors.sections, только в обратную сторону.
    """
    data = json.loads(CORPUS.read_text(encoding="utf-8")).get("paragraphs") or []
    head = re.compile(r"^[A-Z][A-Za-z' -]*\s(" + LEVEL + r")$")
    for para in data:
        translated = para.get("ru") or ""
        rows = [str(row).strip() for row in (para.get("lines") or []) if str(row).strip()]
        heads = [row for row in rows if head.match(row)]
        if not translated or len(heads) < 2:
            continue
        edge = 0
        for row in heads:
            name, _, level = row.rpartition(" ")
            # Кандидат: русское слово(а) прямо перед этим уровнем, правее
            # предыдущего заголовка. Латиницу пропускаем — там имя уже целое.
            found = re.compile(r"([А-ЯЁ][А-Яа-яЁё]+(?:\s+[а-яё]+){0,2})" + GAP
                               + re.escape(level) + r"\b").search(translated, edge)
            if not found:
                # Заголовок остался английским — так и должно быть, идём дальше
                plain = re.compile(re.escape(name) + GAP + re.escape(level))
                spot = plain.search(translated, edge)
                if spot:
                    edge = spot.end()
                continue
            edge = found.end()
            if name in vanilla:
                SEEN.setdefault(name, set()).add(found.group(1).strip())


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Названия зачарований в переводах")
    parser.add_argument("--apply", action="store_true", help="применить (по умолчанию сухой прогон)")
    args = parser.parse_args()

    vanilla = vanilla_pairs()
    print(f"ванильных зачарований знаем: {len(vanilla)}")
    scan_wrong(vanilla)
    fixes = build_fixes()
    print(f"правил замены: {len(fixes)}")

    total = 0
    touched: dict[str, int] = {}
    for path, section in ((CORPUS, "paragraphs"), (QUEUE, "exact")):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("paragraphs") if section == "paragraphs" else None

        def repair(value: str, source: str) -> str:
            nonlocal total
            out = value
            for pattern, replacement, guard, why in fixes:
                # ⚠️ Сторож: меняем только если в ОРИГИНАЛЕ есть это имя.
                # Иначе «Удача» у ванильной Fortune стала бы «Luck».
                if not re.search(r"\b" + re.escape(guard) + r"\s+" + LEVEL + r"\b", source):
                    continue

                def swap(match: re.Match, target: str = replacement) -> str:
                    # ⚠️ «Mining Fortune» не трогаем: перед именем стоит ещё одно
                    # слово с заглавной, значит это составное имя целиком.
                    if leading_capital(match.string, match.start()):
                        return match.group(0)
                    return target

                new = pattern.sub(swap, out)
                if new != out:
                    touched[why] = touched.get(why, 0) + 1
                    total += 1
                    out = new
            return out

        if rows is not None:
            for para in rows:
                if para.get("ru"):
                    para["ru"] = repair(para["ru"], para["text"])
        else:
            for key, value in list((data.get("exact") or {}).items()):
                if value:
                    data["exact"][key] = repair(value, key)
        if args.apply:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print()
    if not touched:
        print("нечего чинить: названия зачарований на месте")
        return 0
    for why, count in sorted(touched.items(), key=lambda item: -item[1]):
        print(f"  {count:>4}x  {why}")
    print()
    print(f"всего замен: {total}")
    if args.apply:
        print("применено")
    else:
        print("это СУХОЙ прогон — чтобы применить, добавь --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
