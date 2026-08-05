# -*- coding: utf-8 -*-
"""
Выложить словари и справку в облако — то, что мод скачает игрокам.

    python tools/publish.py --dry     показать, что изменилось, ничего не слать
    python tools/publish.py           залить изменившееся и обновить манифест

⚠️ ЛЬЁМ ТОЛЬКО ИЗМЕНИВШЕЕСЯ. Сравниваем sha256 локального файла с тем, что
записан в выложенном манифесте: словари меняются по одному, а гонять все
шесть мегабайт каждый раз незачем.

⚠️ ПРОВЕРКИ МОДА ПОВТОРЯЕМ ЗДЕСЬ ЖЕ. `UpdateService` молча отбрасывает файл,
если имя не подходит, размер больше предела или в json нет знакомой секции.
Узнать об этом из игры нельзя — ошибка уходит в лог, а игрок видит бодрое
«переводы обновлены». Поэтому не пускаем такой файл в облако вовсе.

⚠️ Ключи берутся из окружения (`YC_S3_KEY_ID`, `YC_S3_SECRET`) и никогда
не печатаются.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import s3  # noqa: E402

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
WIKI = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "wiki"
GRADLE = ROOT / "gradle.properties"

MANIFEST_KEY = "manifest.json"
SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}\.json")

# ⚠️ Держим в согласии с UpdateService: там же предел и там же список секций.
# Разойдутся — облако примет файл, который игра отбросит, и это будет тихо.
MAX_BYTES = 16 * 1024 * 1024
PACK_SECTIONS = ("exact", "regex", "glossary", "paragraphs", "byItem")

# ⚠️⚠️ ЭТИ ФАЙЛЫ НЕ РАЗДАЁМ, ПОКА У ЛЮДЕЙ jar 0.2.4 И СТАРШЕ.
#
# До 0.2.5 `Wiki.open` искал файл на диске ПО ЯЗЫКУ, а не по имени
# запрошенного: на любой запрос отдавался один и тот же `wiki/ru_ru.json`.
# Стоило выложить справку ТЕРМИНОВ — и она вставала на место справки
# ЗАЧАРОВАНИЙ у всех разом, за минуту, без нового jar: панель по Alt
# переставала находить что-либо, приглашение исчезало.
#
# Файл на диске переживает обновление jar, поэтому само это не чинится.
# Убрав его из манифеста, мы делаем его СИРОТОЙ — мод удалит его сам
# (`UpdateService.orphansOf`) и вернётся к встроенному. Тот побайтово
# такой же (sha256 сверены), так что справка терминов не теряет ничего.
#
# ⚠️ СНЯТЬ ЭТОТ ЗАПРЕТ, когда люди перейдут на 0.2.5+: там `open` берёт
# файл по имени, и раздавать справку снова безопасно. Без записи здесь
# следующая выкладка молча вернула бы беду.
HOLD_BACK = {"ru_ru.json"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mod_version() -> str:
    """Версия мода — из gradle.properties, копии не держим."""
    if not GRADLE.exists():
        return ""
    found = re.search(r"^mod_version\s*=\s*(.+)$", GRADLE.read_text(encoding="utf-8"), re.M)
    return found.group(1).strip() if found else ""


def declared() -> set[str]:
    """Словари, ОБЪЯВЛЕННЫЕ в index.json, — ровно то, что грузит мод.

    ⚠️ Раньше выкладывалось всё, что лежит в папке (`PACKS.rglob`), и это
    открыло дыру: 03.08 три словаря расширенного перевода убрали из
    index.json и из jar — а облако продолжило их раздавать. Мод исправно
    скачал их игроку в `config/skyblockru/packs`, и возможность включения
    вернулась в обход решения.

    **Облако обязано раздавать ровно то же, что лежит в jar.** Файл остался
    в репозитории для будущей работы — это не повод везти его игрокам.
    """
    index = PACKS / "index.json"
    if not index.is_file():
        return set()
    data = json.loads(index.read_text(encoding="utf-8"))
    names = set(data.get("common") or [])
    for files in (data.get("languages") or {}).values():
        names.update(files)
    return names


def collect() -> tuple[list[dict], list[str]]:
    """Файлы к выкладке и список отказов с причиной."""
    out, refused = [], []
    allowed = declared()

    def take(path: Path, kind: str, remote_dir: str) -> None:
        data = path.read_bytes()
        text = data.decode("utf-8")
        if not SAFE_NAME.fullmatch(path.name):
            refused.append(f"{path.name}: имя не подходит под правило мода")
            return
        if len(text) > MAX_BYTES:
            refused.append(f"{path.name}: больше {MAX_BYTES // 1024 // 1024} МБ — мод отбросит")
            return
        try:
            json_data = json.loads(text)
        except json.JSONDecodeError as error:
            refused.append(f"{path.name}: не разбирается как json ({error})")
            return
        if kind == "pack":
            if path.name == "index.json":
                # ⚠️ index.json НЕ выкладываем: он перечисляет ВСТРОЕННЫЕ словари
                # и к пользовательской папке отношения не имеет — мод читает
                # оттуда все файлы подряд.
                return
            # ⚠️ Не объявлен в index.json — значит его нет и в jar. Раздавать
            # такое нельзя: игрок получил бы через обновление то, чего мы
            # намеренно не кладём в мод. См. declared().
            if allowed and path.name not in allowed:
                refused.append(f"{path.name}: нет в index.json — в jar не едет, "
                               f"в облако тоже не поедет")
                return
            if not any(section in json_data for section in PACK_SECTIONS):
                refused.append(f"{path.name}: нет секций {PACK_SECTIONS} — мод отбросит")
                return
        elif not (isinstance(json_data.get("terms"), dict)):
            refused.append(f"{path.name}: нет секции terms — мод отбросит справку")
            return
        elif path.name in HOLD_BACK:
            # ⚠️ Не поломка файла, а осознанная задержка раздачи: см. HOLD_BACK.
            refused.append(f"{path.name}: придержан — на jar до 0.2.5 он "
                           f"подменяет собой справку зачарований")
            return
        out.append({
            "kind": kind,
            "path": path,
            "file": path.name,
            "key": f"{remote_dir}/{path.name}",
            "sha256": sha256(data),
            "size": len(data),
        })

    for path in sorted(PACKS.rglob("*.json")):
        take(path, "pack", "packs")
    if WIKI.exists():
        for path in sorted(WIKI.rglob("*.json")):
            take(path, "wiki", "wiki")
    return out, refused


def remote_manifest() -> dict:
    """Что сейчас выложено. Пустой словарь, если манифеста ещё нет."""
    import requests
    try:
        answer = requests.get(s3.public_url(MANIFEST_KEY), timeout=30)
    except requests.RequestException:
        return {}
    if answer.status_code != 200:
        return {}
    try:
        return answer.json()
    except ValueError:
        return {}


def published_hashes(manifest: dict) -> dict[str, str]:
    out = {}
    for section in ("packs", "wiki"):
        for entry in manifest.get(section) or []:
            if entry.get("file") and entry.get("sha256"):
                out[entry["file"]] = entry["sha256"]
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Выложить словари в облако")
    parser.add_argument("--dry", action="store_true", help="показать, ничего не слать")
    parser.add_argument("--all", action="store_true", help="залить всё заново")
    parser.add_argument("--note", default="", help="строка, которую мод покажет игроку")
    args = parser.parse_args()

    files, refused = collect()
    if refused:
        print("=== НЕ ВЫКЛАДЫВАЮ (мод бы их отбросил) ===")
        for line in refused:
            print("   ", line)
        print()

    was = published_hashes(remote_manifest())
    fresh = [f for f in files if args.all or was.get(f["file"]) != f["sha256"]]

    total = sum(f["size"] for f in files)
    print(f"словарей и справки: {len(files)}, всего {total / 1024 / 1024:.1f} МБ")
    print(f"изменилось с прошлой выкладки: {len(fresh)}")
    for entry in fresh[:20]:
        print(f"   {entry['file']:28} {entry['size'] / 1024:6.0f} КБ")
    if len(fresh) > 20:
        print(f"   ... ещё {len(fresh) - 20}")

    # ⚠️ УДАЛЕНИЕ — ТОЖЕ ИЗМЕНЕНИЕ, и на этом мы попались 03.08. Убрали
    # словарь из index.json, запустили выкладку — «изменилось: 0, манифест
    # не трогаю», и он остался в манифесте вместе с записью о файле.
    # То есть ОТОЗВАТЬ выложенный словарь было нельзя: новых байтов нет,
    # значит и манифест не переписывался. Сравнивать надо СОСТАВ.
    gone = sorted(set(was) - {entry["file"] for entry in files})
    if gone:
        print(f"больше не выкладываем ({len(gone)}):")
        for name in gone:
            print(f"   {name}")
        print("   файлы в облаке останутся — роль не умеет удалять,")
        print("   но без записи в манифесте мод их не скачает")
        # ⚠️ Здесь стояло «у тех, кто уже скачал, они останутся и будут
        # применяться». Это было верно до 03.08, а потом завели отзыв
        # (UpdateService.orphansOf): свой файл, пропавший из манифеста,
        # мод УДАЛЯЕТ при следующем обновлении. Устаревшее предупреждение
        # опаснее пустого — оно выглядит фактом и отговаривает от починки,
        # которая работает.
        print("   ⚠️ у скачавших мод удалит их сам (orphansOf) — но только")
        print("      если мод не старше 0.2.2, где завели отзыв")

    if args.dry:
        print("\nсухой прогон: ничего не отправлено")
        return 0
    if not fresh and not gone:
        print("\nвсё уже выложено — манифест не трогаю")
        return 0

    for entry in fresh:
        s3.put(entry["key"], entry["path"].read_bytes())
        print(f"   залито: {entry['file']}")

    manifest = {
        "packs": [
            {"file": e["file"], "url": s3.public_url(e["key"]), "sha256": e["sha256"]}
            for e in files if e["kind"] == "pack"
        ],
        "wiki": [
            {"file": e["file"], "url": s3.public_url(e["key"]), "sha256": e["sha256"]}
            for e in files if e["kind"] == "wiki"
        ],
    }
    version = mod_version()
    if version:
        # Про новую версию мода мод только СООБЩАЕТ — jar по сети не качается.
        manifest["mod"] = {"version": version}
    if args.note:
        manifest["note"] = args.note

    body = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
    s3.put(MANIFEST_KEY, body)
    print(f"\nманифест обновлён: {s3.public_url(MANIFEST_KEY)}")
    print(f"  словарей в нём: {len(manifest['packs'])}, справки: {len(manifest['wiki'])}")
    print("\nэтот адрес и нужно прописать в RuConfig.DEFAULT_UPDATE_URL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
