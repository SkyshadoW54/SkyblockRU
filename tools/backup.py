# -*- coding: utf-8 -*-
"""Собрать в один архив то, что НЕЛЬЗЯ восстановить.

Зачем. Почти всё в проекте воспроизводится: код лежит в репозитории, лор
аукциона и вики качаются скриптами, сборки пересобираются. А вот ПЕРЕВОДЫ
восстановить нечем — только перевести заново за деньги. Они живут в двух
местах, и оба стоит унести:

  переводы (data/work)  — черновики: ключи, пометки «переводить нечего»,
                          архив очереди. Их нет ни в репозитории, ни в jar;
  словари (packs, wiki) — готовый перевод, тот же, что уезжает игрокам.
                          Он есть в репозитории, но копия лишней не бывает.

Что НЕ берём: дампы из игры (рабочие данные, завтра там окажется чужой ник),
скачанное из чужих источников (одна команда — и оно снова тут), сборки.

  python tools/backup.py            собрать в release/backup/
  python tools/backup.py --list     показать состав, не собирая
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "release" / "backup"
ASSETS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru"

# ⚠️ Список ИМЕНОВАННЫЙ, а не «всё из data/work»: там 138 МБ, и 130 из них —
# скачанное. Файл с переводами добавляется сюда руками, когда появляется:
# лучше забыть один, чем возить гигабайты и перестать делать копии вовсе.
TRANSLATIONS = [
    "paragraphs.json",       # корпус абзацев: перевод + пометки «нечего»
    "from_game.json",        # очередь строк: чат, меню, панель
    "queue_archive.json",    # архив очереди — переводы, выпавшие из состава
    "lore_blocks.json",
    "enchants.json",
    "election_perks.json",
    "enchant_articles.json",
]


def collect() -> list[tuple[Path, str]]:
    """Пары «файл на диске -> путь внутри архива»."""
    out: list[tuple[Path, str]] = []
    work = ROOT / "data" / "work"
    for name in TRANSLATIONS:
        path = work / name
        if path.is_file():
            out.append((path, "переводы/" + name))
    for folder in ("packs", "wiki"):
        base = ASSETS / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.json")):
            out.append((path, "словари/" + path.relative_to(base).as_posix()))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    items = collect()
    if not items:
        print("нечего собирать — проверь пути")
        return 1

    groups: dict[str, list[int]] = {}
    for path, inner in items:
        groups.setdefault(inner.split("/")[0], []).append(path.stat().st_size)
    for name, sizes in groups.items():
        print("  %-10s %3d файлов  %6.1f МБ"
              % (name, len(sizes), sum(sizes) / 1024 / 1024))

    if "--list" in sys.argv:
        print("\nтолько показ — архив не собран")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    # ⚠️ Имя БЕЗ даты: иначе в папке копится десяток архивов, и непонятно,
    # какой свежий. Нужна история — её ведёт то облако, куда вы его кладёте.
    archive = OUT / "SkyblockRU-переводы.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ЧТО ЭТО.txt", (
            "Резервная копия перевода SkyblockRU.\r\n"
            "\r\n"
            "переводы/  — черновики: корпус абзацев, очередь строк, архив.\r\n"
            "             Восстановить их можно только повторным переводом,\r\n"
            "             то есть за деньги. Класть обратно в data/work/.\r\n"
            "\r\n"
            "словари/   — готовый перевод, который видит игрок.\r\n"
            "             Класть в src/main/resources/assets/skyblockru/.\r\n"
            "\r\n"
            "Всё остальное в проекте восстанавливается само: код лежит\r\n"
            "в репозитории, лор и вики качаются скриптами, сборки\r\n"
            "пересобираются одной командой.\r\n"
        ).encode("utf-8"))
        for path, inner in items:
            zf.write(path, inner)

    print("\n-> %s  (%.1f МБ)" % (archive, archive.stat().st_size / 1024 / 1024))
    print("   положить в любое облако; историю версий ведёт само облако")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
