# -*- coding: utf-8 -*-
"""
Поднять в облаке ТОЛЬКО номер версии мода — ничего больше.

    python tools/publish_version.py            сухой прогон
    python tools/publish_version.py --apply    выложить

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ ИНСТРУМЕНТ. По `mod.version` мод решает, звать ли игрока
за новым jar. Когда правка в КОДЕ, словари не меняются вовсе — а сказать
людям надо: облаком код не доедет никогда.

⚠️ ШТАТНЫЙ `publish.py` ТУТ НЕ ГОДИТСЯ, и это записанная грабля: он
пересобирает манифест ЦЕЛИКОМ, а придержанные словари из него выпадают —
у скачавших мод удалит их как сирот. `publish_one.py` не годится с другой
стороны: он намеренно не трогает `mod.version`.

⚠️ Берём ОБЛАЧНЫЙ манифест и правим в нём одно поле. Список файлов и все
хеши остаются ровно теми, что лежат в облаке сейчас.
"""
import argparse
import json
import pathlib
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import s3  # noqa: E402


def local_version() -> str:
    """Версия из gradle.properties — источник правды для сборки."""
    for line in (ROOT / "gradle.properties").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("mod_version"):
            return line.split("=", 1)[1].strip()
    raise SystemExit("mod_version не найден в gradle.properties")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="выложить (по умолчанию сухой прогон)")
    args = ap.parse_args()

    want = local_version()
    raw = urllib.request.urlopen(s3.public_url("manifest.json"), timeout=30).read()
    manifest = json.loads(raw.decode("utf-8"))
    have = (manifest.get("mod") or {}).get("version")

    print(f"в облаке: {have}")
    print(f"локально: {want}")
    print(f"манифест: packs {len(manifest.get('packs') or [])}, "
          f"wiki {len(manifest.get('wiki') or [])}")
    print()
    if have == want:
        print("уже совпадает, делать нечего")
        return 0

    # ⚠️ ВНИЗ НЕ ОПУСКАЕМ. Номер меньше прежнего значил бы, что мод зовёт
    # игроков ОТКАТИТЬСЯ; сравнение версий у мода числовое (Versions.newer),
    # и такой манифест он воспримет всерьёз.
    def parts(v: str) -> list[int]:
        return [int(x) for x in v.split("+")[0].split(".") if x.isdigit()]

    if have and parts(want) < parts(have):
        print(f"⚠️ локальная версия СТАРШЕ облачной — выкладывать нельзя")
        return 1

    print("ИЗМЕНИТСЯ РОВНО ЭТО:")
    print(f"  manifest.json -> mod.version: {have} -> {want}")
    print(f"  все {len(manifest.get('packs') or [])} записей о словарях и справке НЕ ТРОГАЕМ")
    print()
    if not args.apply:
        print("СУХОЙ ПРОГОН. Выложить: --apply")
        return 0

    manifest.setdefault("mod", {})["version"] = want
    s3.put("manifest.json",
           json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))
    print("выложено:", s3.public_url("manifest.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
