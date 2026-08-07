# -*- coding: utf-8 -*-
"""Раздача мода: ОДИН zip на версию игры, внутри два jar и инструкция.

⚠️ РЕШЕНИЕ ИГРОКА 03.08: никаких сборок под конкретные лаунчеры.
Было три формата (`.mrpack`, MultiMC-zip, ручной zip) - и это ошибка
в другую сторону: раздавать девять файлов вместо трёх, а человеку ещё
и выбирать, какой ему. Стало проще: zip + два мода + текст, где расписано,
куда их класть В ЛЮБОМ лаунчере. Суть везде одна - поставить Fabric Loader
и положить jar в папку mods; различается только, где эта папка лежит.

⚠️ Fabric API берётся С MODRINTH (свежий, с проверкой sha1) и кладётся
в кэш `data/fabric-api/`. Иначе версия зависела бы от того, что случайно
лежит в инстансе на этой машине.

  python tools/pack.py --dry       показать состав
  python tools/pack.py             собрать в release/packs/
  python tools/pack.py --offline   не ходить в сеть, взять локальный API
"""
import hashlib
import io
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
OUT = RELEASE / "packs"
CACHE = ROOT / "data" / "fabric-api"
PROPS = ROOT / "gradle.properties"
UA = "SkyblockRU/dev (russian translation mod for Hypixel SkyBlock)"

# запасной источник, когда сети нет: заведомо рабочие jar с этой машины
LOCAL_DIRS = [CACHE, pathlib.Path(r"C:\MultiMC\instances")]

# ⚠️ ВСЕ ВЕРСИИ ИГРЫ, НА КОТОРЫХ МОД РАБОТАЕТ. Это НЕ то же самое, что
# версии в settings.gradle.kts: там СБОРКИ (их две), а тут версии ИГРЫ (пять).
# Ниже 1.21.11 не добавлять: туда не пускает САМ Hypixel.
GAMES = ["1.21.11", "26.1", "26.1.1", "26.1.2", "26.2"]

# ⚠️ ПОД ЧТО СОБИРАЕМ. Архивов МЕНЬШЕ, чем версий игры, потому что Fabric API
# делится по ВЕТКАМ, а не по каждой версии:
#     26.1, 26.1.1, 26.1.2  ->  fabric-api ...+26.1.2   (depends `~26.1-`)
#     26.2                  ->  fabric-api ...+26.2     (depends `~26.2-`)
# Один архив закрывает всю ветку. Какие именно версии - считает `covers`
# и пишет в инструкцию, чтобы человек не гадал.
TARGETS = ["1.21.11", "26.1.2", "26.2"]


# ---------------------------------------------------------------- общее

def mod_meta_bytes(raw: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return json.loads(zf.read("fabric.mod.json").decode("utf-8"))


def mod_meta(jar: pathlib.Path) -> dict:
    return mod_meta_bytes(jar.read_bytes())


def game_of(version: str) -> str:
    """Версия игры из версии мода: `0.155.2+26.2` -> `26.2`.

    ⚠️ Читаем поле version ИЗНУТРИ jar, а не имя файла: имя врёт
    (`fabric-api-0.141.6-1.21.11.jar` через дефис, внутри `+1.21.11`).
    """
    return version.split("+", 1)[1] if "+" in version else ""


def loader_version() -> str:
    found = re.search(r"^\s*loader_version\s*=\s*(\S+)",
                      PROPS.read_text(encoding="utf-8"), re.M)
    if not found:
        raise SystemExit("в gradle.properties нет loader_version")
    return found.group(1)


def as_tuple(version: str) -> tuple:
    """`1.21.11-` -> (1, 21, 11). Хвосты после цифр отбрасываем.

    ⚠️ Fabric пишет границы с висящим дефисом (`>=1.21.11- <1.21.12-`) -
    это метка предрелиза, а не часть номера. Наивный `isdigit()` давал
    на «11-» ноль, и сравнение молча врало.
    """
    out = []
    for part in version.split("."):
        digits = re.match(r"\d+", part)
        out.append(int(digits.group()) if digits else 0)
    return tuple(out)


def in_range(game: str, spec: str) -> bool:
    """Подходит ли версия игры под диапазон из fabric.mod.json.

    ⚠️ Спрашиваем ОБЪЯВЛЕННЫЙ диапазон, а не суффикс имени. Наш jar зовётся
    `skyblockru-0.2.0+26.2.jar`, но объявляет `>=26.1 <26.3` и законно
    работает на 26.1, 26.1.1, 26.1.2 и 26.2. Сверка по суффиксу объявила бы
    его негодным для 26.1.2 - сторож ответил бы на свой вопрос, а не на наш.
    """
    want = as_tuple(game)
    ok = True
    for part in spec.split():
        part = part.strip()
        if part.startswith(">="):
            ok = ok and want >= as_tuple(part[2:])
        elif part.startswith("<="):
            ok = ok and want <= as_tuple(part[2:])
        elif part.startswith("<"):
            ok = ok and want < as_tuple(part[1:])
        elif part.startswith(">"):
            ok = ok and want > as_tuple(part[1:])
        elif part.startswith("~"):
            # ~26.1 = вся ветка 26.1.x: >=26.1 и <26.2
            low = as_tuple(part[1:])
            high = low[:-1] + (low[-1] + 1,) if len(low) > 1 else (low[0] + 1,)
            ok = ok and low <= want < high
        else:
            ok = ok and want == as_tuple(part.lstrip("=^"))
    return ok


def covers(our: pathlib.Path, api_spec: str) -> list:
    """Версии игры, на которых заработает ЭТА пара «мод + Fabric API»."""
    our_spec = str(mod_meta(our).get("depends", {}).get("minecraft", ""))
    return [g for g in GAMES
            if in_range(g, our_spec) and (not api_spec or in_range(g, api_spec))]


def jar_for(game: str, jars: list) -> pathlib.Path | None:
    """Наш jar, который ОБЪЯВЛЯЕТ поддержку этой версии игры."""
    for jar in jars:
        spec = str(mod_meta(jar).get("depends", {}).get("minecraft", ""))
        if spec and in_range(game, spec):
            return jar
    return None


# ------------------------------------------------------- поиск Fabric API

def from_modrinth(game: str) -> dict | None:
    query = urllib.parse.urlencode({
        "game_versions": json.dumps([game]),
        "loaders": json.dumps(["fabric"]),
    })
    url = "https://api.modrinth.com/v2/project/fabric-api/version?" + query
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            versions = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print("     (Modrinth недоступен: %s)" % type(exc).__name__)
        return None
    for version in versions:
        for file in version.get("files", []):
            if file.get("primary", True) and file["filename"].endswith(".jar"):
                return {"filename": file["filename"], "url": file["url"],
                        "sha1": file["hashes"]["sha1"], "size": file["size"]}
    return None


def fetch(entry: dict) -> pathlib.Path:
    """Скачать в кэш и СВЕРИТЬ sha1. Уже лежит - не качаем."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / entry["filename"]
    if path.exists() and hashlib.sha1(path.read_bytes()).hexdigest() == entry["sha1"]:
        return path
    request = urllib.request.Request(entry["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
    got = hashlib.sha1(raw).hexdigest()
    if got != entry["sha1"]:
        raise SystemExit("sha1 не сошёлся у %s" % entry["filename"])
    path.write_bytes(raw)
    return path


def java_link(version: str) -> tuple:
    """Свежий установщик Java нужной версии: (описание, ссылка).

    ⚠️ Спрашиваем Adoptium, а не вшиваем ссылку: вшитая устареет молча —
    ровно как версия в имени файла, на чём проект уже попадался. Сети нет
    или версии не нашлось — отдаём страницу выбора, она рабочая всегда.
    """
    page = "https://adoptium.net/temurin/releases/?version=" + version
    url = ("https://api.adoptium.net/v3/assets/latest/%s/hotspot"
           "?architecture=x64&image_type=jre&os=windows&vendor=eclipse" % version)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            builds = json.loads(response.read().decode("utf-8"))
        installer = builds[0]["binary"]["installer"]["link"]
        return "Java %s (%s)" % (version, builds[0]["release_name"]), installer
    except Exception:
        return "Java %s" % version, page


def local_api(game: str) -> pathlib.Path | None:
    seen: dict[str, pathlib.Path] = {}
    for base in LOCAL_DIRS:
        if not base.is_dir():
            continue
        for jar in base.rglob("fabric-api-*.jar"):
            try:
                meta = mod_meta(jar)
            except Exception:
                continue
            if meta.get("id") == "fabric-api" and game_of(meta.get("version", "")) == game:
                seen.setdefault(meta["version"], jar)
    return seen[sorted(seen)[-1]] if seen else None


def api_for(game: str, offline: bool):
    entry = None if offline else from_modrinth(game)
    if entry:
        try:
            return fetch(entry), True
        except Exception as exc:
            print("     (скачать не вышло: %s)" % exc)
    jar = local_api(game)
    return (jar, False) if jar else (None, False)


# ------------------------------------------------------------- инструкция

GUIDE = """\
SkyblockRU - русский перевод Hypixel SkyBlock
==============================================

  !!! МОД В БЕТА-ТЕСТЕ. ПЕРЕВОД НЕПОЛНЫЙ И ПОЛНЫМ НЕ БУДЕТ !!!

  Вы ОБЯЗАТЕЛЬНО встретите непереведённые описания, диалоги и надписи.
  Это не поломка: текстов в SkyBlock десятки тысяч, Hypixel добавляет
  и переписывает их постоянно, а часть оставлена английской нарочно -
  названия предметов, имена NPC и локаций (по ним ищут на аукционе
  и о них говорят в гайдах).

  Перевод пополняется сам: он приходит по сети, переустанавливать мод
  для этого не нужно. Сообщать о непереведённом не надо - мод собирает
  такие строки самостоятельно.

Подходит для версий Minecraft: {games}

В папке mods рядом с этим файлом лежат ДВА мода. Нужны оба:
  {our}
     - сам перевод
  {api}
     - Fabric API, без него мод не запустится


НУЖНА JAVA {java} ИЛИ НОВЕЕ
---------------------{underline}
Проверить, какая стоит: нажмите Win+R, введите cmd, в чёрном окне
наберите   java -version
Если версия меньше {java} или команды нет вовсе - поставьте:

  {java_name}
  {java_link}

Если ссылка не открывается, возьмите с сайта:
  https://adoptium.net/temurin/releases/?version={java}
  (выберите Windows, x64, JRE и скачайте .msi)

Ставится обычным установщиком, галочки менять не нужно.
MultiMC и Prism Launcher умеют скачивать Java сами:
Settings -> Java -> Download Java.


ЧТО НУЖНО СДЕЛАТЬ (одно и то же в любом лаунчере)
--------------------------------------------------
  1) поставить Fabric Loader под свою версию игры;
  2) положить ОБА файла из папки mods в папку mods своей сборки.

Различается только то, где эта папка лежит. Найдите ниже свой лаунчер.


--- ОБЫЧНЫЙ ЛАУНЧЕР MINECRAFT (от Mojang) ---

  1. Скачайте установщик Fabric: https://fabricmc.net/use/installer/
     Запустите его, выберите версию игры из списка выше, нажмите Install.
  2. Нажмите Win+R, вставьте  %appdata%\\.minecraft  и нажмите Enter.
     Если папки mods внутри нет - создайте её.
  3. Скопируйте туда оба файла из папки mods.
  4. В лаунчере выберите профиль с надписью fabric и запустите игру.


--- MULTIMC / PRISM LAUNCHER ---

  1. Add Instance -> выберите версию игры -> вкладка Mod Loader -> Fabric.
  2. Правой кнопкой по сборке -> Edit -> Mods -> Add,
     либо кнопка "Open Folder" (Folder -> .minecraft) и папка mods.
  3. Положите туда оба файла и запустите сборку.


--- MODRINTH APP / ATLAUNCHER / GDLAUNCHER ---

  1. Создайте новый профиль (Instance): версия игры из списка выше,
     загрузчик - Fabric.
  2. Откройте папку профиля: в Modrinth App это кнопка "..." -> Open folder,
     в ATLauncher - Edit Instance -> Open Folder. Внутри найдите mods.
  3. Положите туда оба файла и запустите профиль.

  Примечание: сайт modrinth.com в России заблокирован, поэтому скачать
  сам лаунчер оттуда может не получиться. Само приложение при этом
  работает. Если сайт не открывается - берите любой другой лаунчер
  из списков выше, для мода разницы нет.


--- CURSEFORGE APP ---

  1. Create Custom Profile -> версия игры из списка выше -> Fabric.
  2. У профиля нажмите "..." -> Open Folder, откройте папку mods.
  3. Положите туда оба файла и запустите профиль.


ПРОВЕРКА
--------
Зайдите в игру и напишите в чат:  /skyblockru
Мод ответит своей версией и датой сборки. Если ответа нет - мод не
загрузился: проверьте, что в профиле выбран Fabric и что в папке mods
лежат ОБА файла.


ЧАСТЫЕ ОШИБКИ
-------------
* "Your version of Minecraft cannot be used to play on Hypixel"
  - это ответ СЕРВЕРА, а не мода. Hypixel пускает в SkyBlock только
    с версии 1.21.11 и новее.
* Игра вылетает при запуске - скорее всего Fabric API от другой версии.
  Берите тот, что лежит здесь: он подобран под версии из списка выше.
* Мод не отвечает на /skyblockru - выбран профиль без Fabric.


Обновление перевода приходит само, переустанавливать мод для этого
не нужно. Настройки: команда /skyblockru в игре.
"""


def pack_name(our: pathlib.Path, games: list) -> str:
    """Имя нашего jar ВНУТРИ архива — по ветке, а не по сборке.

    ⚠️ Беда, из-за которой это написано: в архиве `SkyblockRU-26.1.x.zip`
    лежал `skyblockru-0.2.8+26.2.jar`, и человек справедливо спрашивал —
    «я скачал для 26.1.x, а тут 26.2, оно вообще заработает?».

    Заработает: суффикс значит «СОБРАНО в ветке 26.2», а не «работает только
    на 26.2» — внутри jar объявлено `minecraft: >=26.1 <26.3`. Это уже
    записанная грабля проекта: на ней однажды ошибся и наш собственный сторож.

    Но объяснять это каждому скачавшему — плохой способ. Имя должно
    отвечать на вопрос само, поэтому внутри архива файл называется по ветке:
    `skyblockru-0.2.9+26.1.x.jar`.

    ⚠️ Переименование безопасно: Fabric читает `fabric.mod.json`, а не имя
    файла, и наши инструменты — тоже (записанное правило «версию берём
    ИЗ jar, имя врёт»). Инструкция получает то же имя, иначе человек не
    найдёт, что класть, — за этим следит `verify`.
    """
    if len(games) < 2:
        return our.name
    branch = name_for(games)          # «26.1.x» — то же, что в имени архива
    version = our.name.split("+", 1)[0]   # «skyblockru-0.2.9»
    return f"{version}+{branch}.jar"


def write_zip(dst: pathlib.Path, our: pathlib.Path, api: pathlib.Path,
              java: str, games: list, java_name: str, link: str) -> None:
    inside = pack_name(our, games)
    text = GUIDE.format(games=", ".join(games), java=java,
                        our=inside, api=api.name,
                        java_name=java_name, java_link=link,
                        underline="-" * len(java))
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        # ⚠️ BOM НАРОЧНО: без него Блокнот на части машин открывает
        # кириллицу кракозябрами, и инструкция становится бесполезной.
        zf.writestr("КАК-УСТАНОВИТЬ.txt",
                    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
        zf.write(our, "mods/" + inside)
        zf.write(api, "mods/" + api.name)


# ------------------------------------------------------------- проверка

def verify(zip_path: pathlib.Path, games: list) -> bool:
    """Проверить СОБРАННЫЙ архив, а не намерение его собрать.

    ⚠️ Беды тут тихие: Fabric API от чужой ветки, потерянный мод, пустая
    инструкция. Всплыли бы у чужого человека при первом запуске - там,
    где мы уже ничего не увидим.
    """
    bad = []
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        jars = [n for n in names if n.endswith(".jar")]
        if len(jars) != 2:
            bad.append("jar %d, а должно 2: %s" % (len(jars), jars))
        if not any("skyblockru" in n for n in jars):
            bad.append("нет нашего мода")
        if not any("fabric-api" in n for n in jars):
            bad.append("нет Fabric API")

        guide = [n for n in names if n.endswith(".txt")]
        if not guide:
            bad.append("нет инструкции — без неё архив бесполезен")
        else:
            text = zf.read(guide[0]).decode("utf-8-sig")
            for jar in jars:
                if jar.split("/")[-1] not in text:
                    bad.append("в инструкции не назван %s" % jar.split("/")[-1])
            for game in games:
                if game not in text:
                    bad.append("в инструкции нет версии %s" % game)
            # ⚠️ Без нужной Java игра не стартует вовсе, а сообщение об этом
            # человек не свяжет с модом. Ссылка обязана быть.
            if "adoptium" not in text:
                bad.append("в инструкции нет ссылки на Java")

        # ⚠️ Сверяем ОБЪЯВЛЕННЫЙ диапазон, а не суффикс имени: `+26.2`
        # значит «собрано в ветке 26.2», а не «работает только на 26.2».
        for name in jars:
            spec = str(mod_meta_bytes(zf.read(name))
                       .get("depends", {}).get("minecraft", ""))
            if not spec:
                continue
            miss = [g for g in games if not in_range(g, spec)]
            if miss:
                bad.append("%s объявляет %s — не подходит для %s"
                           % (name.split("/")[-1], spec, ", ".join(miss)))

        for name in jars:
            if "skyblockru" in name:
                bad.extend(junk_in_jar(zf.read(name), name.split("/")[-1]))

    for line in bad:
        print("       !! %s" % line)
    return not bad


# то, чему в нашем jar место есть; всё прочее — посторонний груз
ALLOWED = ("assets/", "ru/", "META-INF/")
ALLOWED_FILES = ("fabric.mod.json", "skyblockru.mixins.json",
                 "skyblockru-refmap.json")


def junk_in_jar(raw: bytes, label: str) -> list:
    """Посторонние файлы внутри нашего jar.

    ⚠️ Такой проверки не было, и однажды к игрокам уехали 470 КБ копий:
    `11-stat-forms.json.bak-trophy`, `40-lore.json.bak-gain` и родня. Запрет
    по имени `*.bak` их не поймал — после `.bak` шёл суффикс, каждый раз
    новый. Нашёл это не сторож, а вопрос игрока «что в моде лишнего».
    Поэтому проверяем не список запретов, а СПИСОК РАЗРЕШЁННОГО: чего
    в перечне нет — то и есть посторонний груз, как бы оно ни называлось.
    """
    out = []
    with zipfile.ZipFile(io.BytesIO(raw)) as jar:
        for name in jar.namelist():
            if name.endswith("/"):
                continue
            if name.startswith(ALLOWED) or name in ALLOWED_FILES:
                continue
            out.append("%s: посторонний файл %s" % (label, name))
        # копии рядом со словарями: имя каждый раз новое, ловим по признаку
        for name in jar.namelist():
            low = name.lower()
            if any(mark in low for mark in (".bak", ".orig", ".rej", ".tmp",
                                            ".old", ".save", "~")):
                out.append("%s: копия перед правкой уехала в jar — %s"
                           % (label, name))
    return out[:10]


# ------------------------------------------------------------------ ход

def name_for(games: list) -> str:
    """Имя архива по ПОКРЫТИЮ, а не по одной версии.

    Одна версия - её номер; вся ветка - `26.1.x`, чтобы человек сразу
    видел, что архив годится не только для последней в ветке.
    """
    if len(games) == 1:
        return games[0]
    head = games[0].rsplit(".", 1)[0] if games[0].count(".") > 1 else games[0]
    return head + ".x"


def build(game: str, jars: list, dry: bool, offline: bool) -> bool:
    our = jar_for(game, jars)
    print("=== %s ===" % game)
    if our is None:
        print("     !! НЕТ нашей сборки под %s — проверь settings.gradle.kts" % game)
        return False
    java = str(mod_meta(our).get("depends", {}).get("java", "")).lstrip(">=") or "21"

    api, fresh = api_for(game, offline)
    if api is None:
        print("     !! НЕТ Fabric API под %s — ни в сети, ни на диске" % game)
        return False
    api_spec = str(mod_meta(api).get("depends", {}).get("minecraft", ""))
    games = covers(our, api_spec)

    print("     мод         %s" % our.name)
    print("     fabric-api  %s%s"
          % (api.name, "  (с Modrinth)" if fresh else "  (локальный)"))
    java_name, link = ("Java %s" % java, "") if offline else java_link(java)
    print("     loader      %s     java >=%s" % (loader_version(), java))
    print("     java        %s" % (link or "ссылка не получена — будет страница"))
    print("     годится для %s" % ", ".join(games))
    if dry:
        print()
        return True
    if not link:
        java_name, link = java_link(java)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / ("SkyblockRU-%s.zip" % name_for(games))
    write_zip(path, our, api, java, games, java_name, link)
    good = verify(path, games)
    print("     -> %-26s %5.0f КБ  %s"
          % (path.name, path.stat().st_size / 1024,
             "любой лаунчер" if good else "СЛОМАН"))
    print()
    return good


def main() -> int:
    dry = "--dry" in sys.argv
    offline = "--offline" in sys.argv
    jars = sorted(RELEASE.glob("skyblockru-*.jar")) if RELEASE.is_dir() else []
    if not jars:
        print("в release/ нет наших jar — сперва: python tools/release.py")
        return 1

    # ⚠️ Чистим папку раздачи, как это делает release.py: файл от прошлой
    # сборки выглядит настоящим и уезжает игроку вместе со свежими.
    if not dry and OUT.is_dir():
        for old in sorted(OUT.iterdir()):
            if old.is_file():
                old.unlink()

    ok = True
    for game in TARGETS:
        ok = build(game, jars, dry, offline) and ok
    if ok and not dry:
        bundle()
    if dry:
        print("сухой прогон: ничего не записано")
    elif ok:
        print("папка: %s" % OUT)
    else:
        print("СЛОМАНО — смотри пометки выше")
    return 0 if ok else 1


def bundle() -> None:
    """ОДИН архив со всеми версиями — для облачных дисков.

    <b>Зачем.</b> На Google Drive и Яндекс.Диске удобна ОДНА ссылка, а три
    файла рядом заставляют человека гадать, какой его. Класть zip внутрь zip
    тоже нельзя: тогда он распаковывает дважды и всё равно выбирает.

    ⚠️ Поэтому внутри лежат ПАПКИ ПО ВЕРСИЯМ, а не архивы: скачал, распаковал,
    открыл папку со своей версией, положил оба файла в mods. Выбор очевиден
    по названию папки — это то же правило, ради которого мы отказались от трёх
    форматов раздачи: «инструкция дешевле выбора».

    ⚠️ Цена решения честная: человек качает ~12 МБ вместо 4. Ужать нельзя —
    Fabric API у каждой ветки СВОЙ, это не дубликат одного файла.
    """
    packs = sorted(OUT.glob("SkyblockRU-*.zip"))
    packs = [p for p in packs if not p.name.startswith("SkyblockRU-все")]
    if not packs:
        return
    target = OUT / "SkyblockRU-все-версии.zip"
    readme = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for pack in packs:
            # «SkyblockRU-26.1.x.zip» -> папка «26.1.x»
            folder = pack.stem.replace("SkyblockRU-", "")
            readme.append(folder)
            with zipfile.ZipFile(pack) as src:
                for item in src.namelist():
                    if item.endswith("/"):
                        continue
                    data = src.read(item)
                    # инструкцию кладём одну, общую — она у веток одинакова
                    # по смыслу и различается лишь списком версий
                    if item.lower().endswith(".txt"):
                        out.writestr("%s/%s" % (folder, item), data)
                        continue
                    out.writestr("%s/%s" % (folder, item), data)
        out.writestr("ЧИТАТЬ ПЕРВЫМ.txt", pick_text(readme))
    print("     -> %-26s %5.0f КБ  одна ссылка на все версии"
          % (target.name, target.stat().st_size / 1024))


def pick_text(folders: list) -> bytes:
    """Записка «выбери свою папку» — первое, что видит скачавший."""
    rows = [
        "SkyblockRU - русский перевод Hypixel SkyBlock",
        "=" * 46,
        "",
        "  !!! МОД В БЕТА-ТЕСТЕ. ПЕРЕВОД НЕПОЛНЫЙ И ПОЛНЫМ НЕ БУДЕТ !!!",
        "",
        "В этом архиве СРАЗУ ВСЕ версии. Возьмите ОДНУ папку - свою:",
        "",
    ]
    # ⚠️ «26.1.x» разворачиваем в перечень: человек ищет СВОЮ версию глазами,
    # а «для Minecraft 26.1.x» не отвечает на вопрос «а моя 26.1.1 подойдёт?».
    spell = {"26.1.x": "26.1, 26.1.1, 26.1.2"}
    for folder in folders:
        rows.append("  %-12s - для Minecraft %s" % (folder, spell.get(folder, folder)))
    rows += [
        "",
        "Внутри вашей папки лежит подробная инструкция КАК-УСТАНОВИТЬ.txt",
        "и папка mods с ДВУМЯ файлами - нужны оба.",
        "",
        "Коротко: поставить Fabric Loader под свою версию игры",
        "и положить оба файла из mods в папку модов своей сборки.",
        "",
        "Ниже 1.21.11 SkyBlock не пускает - это ограничение Hypixel,",
        "а не мода.",
        "",
    ]
    return "\r\n".join(rows).encode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
