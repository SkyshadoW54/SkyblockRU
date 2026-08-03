"""
Готовит папку для публикации: словари + манифест.

Мод при заходе на сервер читает манифест, сверяет хеши и докачивает только
изменившиеся файлы. Игроку нажимать ничего не надо.

Что получается в dist/:
  dist/manifest.json      - что и откуда качать
  dist/packs/*.json       - сами словари

Дальше эту папку надо просто выложить так, чтобы файлы отдавались по прямой
ссылке (GitHub, свой сайт — что угодно, лишь бы https). Адрес манифеста
прописывается игрокам в config/skyblockru/config.json -> updateUrl,
либо зашивается в мод значением по умолчанию.

Запуск:
  python tools/make_manifest.py --base https://raw.githubusercontent.com/USER/REPO/main/packs
  python tools/make_manifest.py --base ... --note "добавил перевод меню аукциона"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
DIST = ROOT / "dist"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mod_version() -> str:
    for line in (ROOT / "gradle.properties").read_text(encoding="utf-8").splitlines():
        if line.startswith("mod_version"):
            return line.split("=", 1)[1].strip()
    return "0.0.0"


def main() -> int:
    parser = argparse.ArgumentParser(description="Собрать манифест обновлений переводов")
    parser.add_argument("--base", required=True,
                        help="адрес папки, куда лягут словари (https)")
    parser.add_argument("--note", default="", help="что нового — покажется игроку в чате")
    parser.add_argument("--mod-url", default="", help="ссылка на скачивание нового jar")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    if not base.lower().startswith("https://"):
        print("Адрес должен начинаться с https:// — мод другие не принимает")
        return 1

    out_packs = DIST / "packs"
    if DIST.exists():
        shutil.rmtree(DIST)
    out_packs.mkdir(parents=True)

    entries = []
    for path in sorted(PACKS.rglob("*.json")):
        # index.json нужен только внутри jar — он перечисляет встроенные словари
        if path.name == "index.json":
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exception:
            print(f"! {path.name} — битый JSON, пропускаю: {exception}")
            continue

        shutil.copy2(path, out_packs / path.name)
        entries.append({
            "file": path.name,
            "url": f"{base}/{path.name}",
            "sha256": sha256(path),
        })
        print(f"  {path.name}")

    manifest = {
        "version": mod_version(),
        "note": args.note,
        "packs": entries,
    }
    if args.mod_url:
        manifest["mod"] = {"version": mod_version(), "url": args.mod_url}

    (DIST / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    print()
    print(f"готово: {len(entries)} словарей в {DIST.relative_to(ROOT)}")
    print()
    print("Дальше:")
    print("  1. выложить содержимое dist/ так, чтобы файлы отдавались по https")
    print(f"  2. манифест окажется по адресу {base.rsplit('/', 1)[0]}/manifest.json")
    print("  3. этот адрес прописать в updateUrl (в config.json игрока или")
    print("     значением по умолчанию в RuConfig.java перед сборкой)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
