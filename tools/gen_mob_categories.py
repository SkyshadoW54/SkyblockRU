"""
Категории существ поштучно — чтобы мод возвращал ЦВЕТ каждому слову.

Беда, которую это лечит. Строки вида «✦ Aquatic, ✿ Animal, ○ Elusive» куплены
ЦЕЛИКОМ, сочетание за сочетанием. Перевод на экране есть, а цвет пропадает:
мод красит переведённый кусок, только если знает его пару ПОШТУЧНО
(`Paragraphs.aliases` спрашивает точный словарь). «Animal» там был — зелёный
уцелел; «Aquatic» и «Elusive» лежали лишь внутри целых строк — синий
и фиолетовый пропали.

Замер по живому preview.json: из 30 строк категорий цвет теряли 19.

⚠️ Пары берём ИЗ НАШИХ ЖЕ купленных переводов, а не выдумываем: тогда они
заведомо совпадают с тем, что уже на экране, и разнобоя не будет.

⚠️ Ключ сохраняем СО ЗНАЧКОМ (` Aquatic`): мод сопоставляет кусок строки
целиком, а значок входит в кусок. Без него пара не найдётся.

Запуск:  python tools/gen_mob_categories.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = (ROOT / "src" / "main" / "resources" / "assets" / "skyblockru"
        / "packs" / "ru_ru" / "46-mob-categories.json")
INDEX = (ROOT / "src" / "main" / "resources" / "assets" / "skyblockru"
         / "packs" / "index.json")

sys.path.insert(0, str(Path(__file__).resolve().parent))

SPLIT = re.compile(r"\s*,\s*")

# ⚠️ Признак категории — ЗНАЧОК Hypixel впереди, а не «слово с запятой».
# Без него фильтр нахватал реплик NPC: «friend!», «buddy.», «which» — там
# запятые тоже есть, и число кусков случайно совпадало. Значок из приватной
# зоны Unicode стоит у КАЖДОЙ категории и больше нигде так не встречается.
CATEGORY = re.compile(r"^[-]\s*([A-Z][a-z]+)$")


# ⚠️ Категории, которых автосбор НЕ НАЙДЁТ, — и это не его изъян.
#
# Пары он берёт из купленных строк-сочетаний, а сочетания с этими двумя либо
# не покупались, либо куплены СО СМЕСЬЮ: в 90-from-game.json лежит
# «Skeletal,  Wither and  Undead» -> «Skeletal,  Wither и
#  Undead», где переведён ровно один союз. Такую пару брать нельзя,
# а без неё категория остаётся английской посреди русской фразы — ровно это
# игрок и увидел на книге Smite.
#
# Нашлись сверкой с лором аукциона: Wither встречается 20 раз, Ender 11.
# Значки взяты С СЕРВЕРА, а не подобраны на глаз. В исходнике они невидимы
# (приватная зона Unicode), поэтому проверять их надо не глазами, а прогоном:
# после генерации ключи обязаны совпасть с тем, что лежит в лоре аукциона.
#
# ⚠️ «Wither» переводим ванильным именем из самой игры («Иссушитель»): это моб,
# и игрок видит то же слово в своём клиенте. Форма — как у соседей по словарю
# («Ледяной», «Лесной», «Нежить»), то есть именительный единственного числа.
EXTRA = {
    " Wither": " Иссушитель",
    " Ender": " Эндерский",
}


def collect() -> tuple[dict[str, str], dict[str, set[str]]]:
    import packs

    pairs: dict[str, str] = {}
    conflicts: dict[str, set[str]] = {}
    for pack in packs.load():
        for key, value in (pack.exact or {}).items():
            if "," not in key or not value or "," not in value:
                continue
            left = [part.strip() for part in SPLIT.split(key)]
            right = [part.strip() for part in SPLIT.split(value)]
            if len(left) != len(right) or len(left) < 2:
                continue
            for source, target in zip(left, right):
                # Категория — «значок + ОДНО слово». Всё прочее (фразы,
                # варианты ответа, перечисления предметов) не берём.
                if not CATEGORY.match(source):
                    continue
                if not target or source == target:
                    continue
                if source in pairs and pairs[source] != target:
                    conflicts.setdefault(source, set()).update({pairs[source], target})
                pairs[source] = target
    return pairs, conflicts


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pairs, conflicts = collect()
    if conflicts:
        print("⚠️ РАЗНОБОЙ — сперва решить, как переводим:")
        for source, variants in conflicts.items():
            print(f"  {source.encode('unicode_escape').decode()}: {', '.join(sorted(variants))}")
        return 1
    if not pairs:
        print("пар не нашлось")
        return 1

    # Ручные пары ДОПОЛНЯЮТ собранные, а не перебивают: если сочетание с этой
    # категорией однажды купят чисто, автосбор возьмёт пару из него, и наш
    # список отойдёт в сторону сам.
    added = [name for name in EXTRA if name not in pairs]
    for name in added:
        pairs[name] = EXTRA[name]

    PACK.parent.mkdir(parents=True, exist_ok=True)
    PACK.write_text(json.dumps({
        "id": "mob_categories",
        "priority": 28,
        "_comment": "Категории существ ПОШТУЧНО. Собирается tools/gen_mob_categories.py "
                    "из купленных строк-сочетаний — править надо ИХ, а не этот файл. "
                    "Нужен не ради перевода (сочетания и так куплены целиком), а ради "
                    "ЦВЕТА: мод красит переведённый кусок, только если знает его пару.",
        "only": ["item_lore"],
        "exact": dict(sorted(pairs.items())),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"записано пар: {len(pairs)}")
    for source, target in sorted(pairs.items()):
        print(f"  {source.encode('unicode_escape').decode()} = {target}")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    files = index.setdefault("languages", {}).setdefault("ru_ru", [])
    if PACK.name not in files:
        files.append(PACK.name)
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  вписан в index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
