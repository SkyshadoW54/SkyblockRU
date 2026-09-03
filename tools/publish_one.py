# -*- coding: utf-8 -*-
"""Выложить в облако ОДИН словарь, не трогая остальные.

    python tools/publish_one.py 41-headers.json           покажет
    python tools/publish_one.py 41-headers.json --apply   выложит

⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ ИНСТРУМЕНТ, если есть publish.py. Тот пересобирает манифест
из ЛОКАЛЬНЫХ хешей ВСЕХ не-придержанных словарей. Значит выложить один файл
им нельзя двумя способами сразу:

  * залить только его — у остальных в манифесте окажутся свежие хеши при
    старом содержимом в облаке, и мод не сойдётся по sha256;
  * придержать остальные через HOLD_BACK — они выпадут из манифеста, а это
    не «не обновлять», а ОТЗЫВ: мод удалит скачанные копии у игроков как
    сирот (orphansOf) и откатит их к словарям из своего jar.

Поэтому берём ОБЛАЧНЫЙ манифест и подменяем в нём ровно одну запись.

⚠️ `mod.version` НЕ ТРОГАЕМ. По ней мод решает, звать ли игрока за новым jar,
и поднимать её надо вместе с релизом, а не с правкой словаря.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import s3  # noqa: E402

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
SECTIONS = ("exact", "regex", "glossary", "paragraphs")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="имя словаря, например 41-headers.json")
    ap.add_argument("--apply", action="store_true", help="выложить (по умолчанию сухой прогон)")
    args = ap.parse_args()

    hits = [p for p in PACKS.rglob(args.name) if p.is_file()]
    if len(hits) != 1:
        print(f"словарь {args.name}: найдено файлов {len(hits)}")
        return 1
    local = hits[0]
    data = local.read_bytes()
    new_sha = hashlib.sha256(data).hexdigest()

    # ⚠️ Повторяем проверку мода: словарь без единой знакомой секции он молча
    # отбросит, и выкладка окажется пустой работой.
    body = json.loads(data.decode("utf-8"))
    if not any(k in body for k in SECTIONS):
        print(f"{args.name}: мод не признает это словарём (нет ни одной секции {SECTIONS})")
        return 1

    raw = urllib.request.urlopen(s3.public_url("manifest.json"), timeout=30).read()
    manifest = json.loads(raw.decode("utf-8"))
    entries = [e for e in manifest.get("packs") or [] if e.get("file") == args.name]
    if len(entries) != 1:
        print(f"в манифесте записей {args.name}: {len(entries)} — точечная правка не годится")
        return 1
    old_sha = entries[0]["sha256"]

    print(f"файл:     {args.name}  ({len(data)} байт)")
    print(f"в облаке: sha256 {old_sha[:16]}")
    print(f"локально: sha256 {new_sha[:16]}")
    print(f"манифест: packs {len(manifest['packs'])}, "
          f"wiki {len(manifest.get('wiki') or [])}, mod {manifest.get('mod', {}).get('version')}")
    print()
    if old_sha == new_sha:
        print("уже выложен, делать нечего")
        return 0

    print("ИЗМЕНИТСЯ РОВНО ЭТО:")
    print(f"  1. packs/{args.name} — залит заново")
    print(f"  2. manifest.json — sha256 у {args.name}: {old_sha[:12]} -> {new_sha[:12]}")
    print(f"  остальные {len(manifest['packs']) - 1} записей и mod.version НЕ ТРОГАЕМ")
    print()
    if not args.apply:
        print("СУХОЙ ПРОГОН. Выложить: --apply")
        return 0

    entries[0]["sha256"] = new_sha
    s3.put(f"packs/{args.name}", data)
    s3.put("manifest.json",
           json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))
    print("выложено:", s3.public_url(f"packs/{args.name}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
