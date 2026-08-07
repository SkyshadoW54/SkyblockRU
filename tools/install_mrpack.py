# -*- coding: utf-8 -*-
"""
Сборка модов `.mrpack` -> инстанс MultiMC, вместе с нашим модом.

Зачем. Формат Modrinth умеют Prism Launcher и Modrinth App, а у нас MultiMC,
и импорта там нет. Ставить руками — 36 скачиваний по ссылкам из манифеста,
и делать это приходится каждый раз, когда игрок присылает новую версию
сборки (у него уже вторая: файл называется «... (2).mrpack»).

⚠️ Хеш проверяем У КАЖДОГО файла. Ссылки ведут на cdn.modrinth.com, но
скачивание — это место, где тихо портятся байты: оборванная закачка даёт
jar, который Fabric отвергнет уже при старте игры, и виноватым будет
выглядеть последний поставленный мод (то есть наш).

⚠️ `JavaPath` в instance.cfg НЕ пишем: путь к JDK свой на каждой машине,
и записанный чужой ломает запуск молча. MultiMC подставит свой.

⚠️ Наш мод кладём ПОСЛЕДНИМ и отдельно: в сборке игрока его нет, а проверять
совместимость надо именно в его окружении. Версию берём из release/ — ту,
что раздаётся людям, а не случайную из versions/.

  python tools/install_mrpack.py "путь/к/сборке.mrpack"
  python tools/install_mrpack.py "..." --name 1.21.11-play   имя инстанса
  python tools/install_mrpack.py "..." --dry                 показать состав
  python tools/install_mrpack.py "..." --no-mod              без нашего мода
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
INSTANCES = Path("C:/MultiMC/instances")

UA = {"User-Agent": "SkyblockRU-installer (github.com/SkyshadoW54/SkyblockRU)"}


def read_pack(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read("modrinth.index.json"))


def digest(data: bytes, kind: str) -> str:
    return hashlib.new(kind, data).hexdigest()


def fetch(url: str, hashes: dict) -> bytes:
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=120) as answer:
        data = answer.read()
    # ⚠️ Сверяем тем алгоритмом, который назвал САМ манифест. Modrinth кладёт
    # и sha1, и sha512; полагаться на один — значит однажды не найти его вовсе.
    for kind in ("sha512", "sha1"):
        want = (hashes or {}).get(kind)
        if want:
            got = digest(data, kind)
            if got != want:
                raise ValueError("хеш не сошёлся (%s): ждали %s, вышло %s"
                                 % (kind, want[:16], got[:16]))
            return data
    return data


def our_jar(game: str) -> Path | None:
    """Наш мод под нужную версию игры — из папки раздачи."""
    if not RELEASE.exists():
        return None
    # «1.21.11» -> суффикс «+1.21.11»; ветка 26.x собирается как «+26.2».
    branch = "26.2" if game.startswith("26.") else game
    found = sorted(RELEASE.glob(f"skyblockru-*+{branch}.jar"))
    return found[-1] if found else None


def write_instance(folder: Path, game: str, loader: str, title: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    pack = {
        "formatVersion": 1,
        "components": [
            {"uid": "net.minecraft", "version": game,
             "cachedName": "Minecraft", "important": True},
            {"uid": "net.fabricmc.intermediary", "version": game,
             "cachedName": "Intermediary Mappings", "dependencyOnly": True,
             "cachedVolatile": True,
             "cachedRequires": [{"uid": "net.minecraft", "equals": game}]},
            {"uid": "net.fabricmc.fabric-loader", "version": loader,
             "cachedName": "Fabric Loader",
             "cachedRequires": [{"uid": "net.fabricmc.intermediary"}]},
        ],
    }
    (folder / "mmc-pack.json").write_text(
        json.dumps(pack, indent=4, ensure_ascii=False), encoding="utf-8")
    cfg = folder / "instance.cfg"
    if not cfg.exists():
        cfg.write_text(
            "InstanceType=OneSix\n"
            "iconKey=bee\n"
            f"name={title}\n"
            "OverrideJavaLocation=false\n",
            encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", help="файл .mrpack")
    parser.add_argument("--name", help="имя инстанса MultiMC")
    parser.add_argument("--dry", action="store_true", help="только показать")
    parser.add_argument("--no-mod", action="store_true", help="без нашего мода")
    args = parser.parse_args()

    source = Path(args.pack)
    if not source.exists():
        print("нет файла:", source)
        return 1

    index = read_pack(source)
    deps = index.get("dependencies") or {}
    game = deps.get("minecraft")
    loader = deps.get("fabric-loader")
    files = index.get("files") or []
    if not game or not loader:
        print("СЛОМАНО: в манифесте нет версии игры или загрузчика:", deps)
        return 1

    name = args.name or f"{game}-{(index.get('name') or 'pack').split()[0]}"
    folder = INSTANCES / name

    print("=== СБОРКА ===")
    print("  имя       :", index.get("name"))
    print("  версия    :", index.get("versionId"))
    print("  Minecraft :", game)
    print("  Fabric    :", loader)
    print("  модов     :", len(files))
    mod = None if args.no_mod else our_jar(game)
    print("  наш мод   :", mod.name if mod else "НЕТ (собери release.py)")
    print("  инстанс   :", folder)

    if args.dry:
        print("\nсухой прогон: ничего не скачано")
        return 0

    write_instance(folder, game, loader, name)
    root = folder / ".minecraft"
    mods = root / "mods"
    # ⚠️ Папку модов чистим: сборка обновляется, и старые версии тех же модов
    # остались бы рядом с новыми. Fabric на два jar одного мода ругается —
    # записанная грабля проекта про два наших jar в одной папке.
    if mods.exists():
        shutil.rmtree(mods)
    mods.mkdir(parents=True, exist_ok=True)

    print("\n=== СКАЧИВАЮ ===")
    bad = 0
    for number, item in enumerate(files, 1):
        target = root / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        links = item.get("downloads") or []
        if not links:
            print("  %2d/%d  НЕТ ССЫЛКИ  %s" % (number, len(files), item["path"]))
            bad += 1
            continue
        try:
            data = fetch(links[0], item.get("hashes"))
        except Exception as trouble:
            print("  %2d/%d  СЛОМАНО     %s  (%s)"
                  % (number, len(files), Path(item["path"]).name, trouble))
            bad += 1
            continue
        target.write_bytes(data)
        print("  %2d/%d  ок %6.1f МБ  %s"
              % (number, len(files), len(data) / 1048576, Path(item["path"]).name))

    # overrides — то, что автор пака кладёт как есть (конфиги, отключённые моды)
    with zipfile.ZipFile(source) as zf:
        extra = [n for n in zf.namelist()
                 if n.startswith("overrides/") and not n.endswith("/")]
        for name_in_zip in extra:
            target = root / name_in_zip[len("overrides/"):]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name_in_zip))
        if extra:
            print("  overrides: %d файлов" % len(extra))

    if mod:
        shutil.copy2(mod, mods / mod.name)
        print("  наш мод:", mod.name)

    print()
    if bad:
        print("СЛОМАНО: %d файлов не скачалось — инстанс НЕПОЛНЫЙ" % bad)
        return 1
    print("готово: %d модов в %s" % (len(files) + (1 if mod else 0), folder))
    print("В MultiMC инстанс появится сам — он читает папку instances при запуске.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
