"""
Не отдаём ли мы соседним модам СВОЙ перевод вместо текста Hypixel.

Беда, которую это сторожит. Наши точки перехвата ванильные, поэтому подмена
результата достаётся ВСЕМ, кто спрашивает игру, — не только экрану. 17.08 так
сломался SkyHanni: перевод таба стоял на `PlayerInfo.getTabListDisplayName`,
а он читает таб именно оттуда и ищет там английские заголовки виджетов
(«Info», «Island», «Area:», «Commissions:»). Получая русский текст, он не
находил ничего и ругался игроку: «Extra Information from Tab list not found».
Из 23 его маркеров наш перевод ломал 13.

⚠️ НАЙТИ ЭТО МОЖНО БЫЛО ТОЛЬКО ЧТЕНИЕМ ЧУЖОГО JAR. Ни один наш сторож такого
не ловил: у нас всё работало, потому что SkyHanni у нас не стоял. Этот и
написан, чтобы вопрос задавался сам.

Семья повторялась ПЯТЬ раз: таб (строки, потом поля), имя предмета
(`getHoverName`, 03.09), заголовок окна (`Screen.title`, 05.09), боковая
панель (`ownerName`/`getPlayerPrefix`, 16.09), надпись над сущностью
(`Entity.getCustomName`, 17.09). Развязка всегда одна — подменять ВЫЗОВ
внутри отрисовки, а не метод чтения.

Проверяет ДВЕ вещи, и обе без запуска игры:

  1. ЗАПРЕЩЁННЫЕ ЦЕЛИ — наши миксины не смеют перехватывать методы, которые
     соседи зовут САМИ. Перехват чтения достаётся всем; подменять можно
     только вызов ВНУТРИ отрисовки.
  2. ПОДМЕНА ПОЛЯ БЕЗ ВОЗВРАТА — если мы пишем в чужое поле, к выходу из
     метода оно обязано вернуться к оригиналу. Иначе сосед, прочитавший
     поле позже, получит наш перевод. Так и было с шапкой и подвалом таба:
     у SkyHanni в `TabListData` стоят `field_2153`/`field_2154` — ровно они.
  3. СВОИ ОКНА — МИМО ЧУЖИХ ПЕРЕХВАТОВ (11.10). Справку сбоку (`WikiPanel`)
     нельзя рисовать ванильным `tooltip(...)`: в него встают соседи.
     SkyBlock Enhancements подменяет расстановщик позиции у ЛЮБОЙ подсказки
     (наш столбец вставал у курсора, на подсказку предмета) и сбрасывает
     прокрутку, когда меняется первая строка; Stfu зажимает подсказку по
     краям и переносит над курсор. И рисовать её можно только ПОСЛЕ
     отложенной подсказки предмета (`extractDeferredElements`, TAIL): та
     ложится новым слоем поверх всего, что нарисовано раньше.

Запуск:
  python tools/check_neighbours.py            проверить
  python tools/check_neighbours.py --jars     заодно поискать в jar соседей,
                                              что они читают из таба
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIXINS = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "mixin"
CORE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core"

# ⚠️ Наши СОБСТВЕННЫЕ окна. Через ванильный конвейер подсказок их не рисуем:
# туда встают соседи и решают за нас, где окну стоять (замер 11.10 по jar
# сборки SkyBlock Enhanced — см. javadoc `WikiPanel`).
OWN_WINDOWS = [CORE / "WikiPanel.java"]
TOOLTIP_PIPELINE = re.compile(
    r"\.(?:tooltip|renderTooltip|setTooltipForNextFrame|setComponentTooltipForNextFrame)\(")
INSTANCES = Path("C:/MultiMC/instances")

# ⚠️ Методы, которые соседи зовут САМИ. Перехватывать их нельзя: подмена
# достанется им вместо текста Hypixel. Список именной, а не по форме, —
# каждый пункт подтверждён чтением чужого байткода.
FORBIDDEN = {
    "getTabListDisplayName":
        "SkyHanni читает таб через неё (TabListData -> getNameForDisplay -> сюда) "
        "и ищет английские заголовки виджетов",
    "getNameForDisplay":
        "её зовёт TabListData у SkyHanni (method_1918 в его байткоде)",
    "getHoverName":
        "имя предмета читают 115 классов SkyHanni и 72 Skyblocker (замер 03.09 "
        "по их jar). У SkyHanni из-за подмены гасла подсветка нажатых карточек "
        "в Superpairs: SuperPairsItemVisibility ищет в имени английские «?» и "
        "«Click any button!». Переводить имя надо в ПОДСКАЗКЕ (core/ItemName)",
    # ⚠️ 16.09: боковая панель. Замер по сборке SkyBlock Enhanced 5.2.11 —
    # панель читают 22 jar, и все ЭТИМИ методами (scan по байткоду):
    # skyblock-api (McClient.getScoreboard: ownerName + getPlayerPrefix/Suffix;
    # вложена в Custom Scoreboard, SkyOcean, SkyBlockPv, Catharsis, Stella),
    # Skyblocker Utils, SkyHanni ScoreboardCompatKt, btrbz, modernwarpmenu,
    # MarketGuard ProfileResolver (ownerName), Feesh/SBO (formatNameForTeam ->
    # getFormattedName). У skyblock-api CurrencyAPI ищет `^(Purse|Piggy): `,
    # получал «Кошелёк: …» — и счётчик монет Custom Scoreboard замирал.
    # Переводить панель надо в ОТРИСОВКЕ: лямбда displayScoreboardSidebar
    # (HudMixin/GuiMixin -> OverlayHooks.sidebarLine).
    "ownerName":
        "строку панели читают skyblock-api (McClient.getScoreboard) и MarketGuard "
        "(ProfileResolver); переводить надо в лямбде displayScoreboardSidebar",
    "getFormattedName":
        "её зовёт formatNameForTeam, а ту — Feesh, SBO и skyblock-api при разборе "
        "панели; переводить надо в лямбде displayScoreboardSidebar",
    "getPlayerPrefix":
        "префикс строки панели читают skyblock-api, Skyblocker Utils, SkyHanni "
        "ScoreboardCompatKt, btrbz, modernwarpmenu",
    "getPlayerSuffix":
        "суффикс строки панели читают те же, что и getPlayerPrefix, плюс SkyOcean "
        "ProfileInChat",
    "getDisplayName":
        "заголовок панели (Objective.getDisplayName) читают SkyHanni HypixelData/"
        "ScoreboardData, Skyblocker, skyblock-api — по нему они узнают режим; "
        "у сущности её же читают SkyHanni (7 классов) и Skyblocker GuardianHealth",
    # ⚠️ 17.09: надпись над сущностью. Замер по сборке SkyBlock Enhanced 5.2.11
    # (константный пул каждого jar, вложенные тоже): имя сущности читают
    # Skyblocker (HealthBars, DungeonManager, FishingHelper, CompactDamage —
    # 10 классов через getCustomName, 23 через getName, 10 через hasCustomName),
    # SkyHanni (MinionFeatures, DataWatcherApi; 33 класса через getName),
    # Feesh (8: таймеры по именам стендов), SBO (DianaMobDetect), Odin (12),
    # skyblock-api (EntityMixin, SkyBlockEntityKt — вложена в Custom Scoreboard,
    # SkyOcean, SkyBlockPv, Catharsis, Stella). HealthBars ищет в имени стойки
    # английские «Blaze», «The Professor», «Guardian» — а получал «Ифрит».
    # Переводить надпись надо на ВЫЗОВЕ getNameTag внутри extractNameTags
    # (EntityRendererMixin) — между вызовом и записью в EntityRenderState.nameTag.
    "getCustomName":
        "имя сущности читают Skyblocker (HealthBars, DungeonManager, FishingHelper), "
        "SkyHanni (MinionFeatures), Feesh, SBO, skyblock-api; переводить надо "
        "на вызове getNameTag внутри extractNameTags (EntityRendererMixin)",
    "getName":
        "имя сущности читают SkyHanni (33 класса), Skyblocker (23), Odin (12), "
        "Feesh, SBO; имя полосы босса (LerpingBossEvent.getName) — SkyHanni "
        "BossbarData, Skyblocker BossHealthOverlayMixin, Odin BloodCamp. "
        "Переводить надо на вызове: getNameTag внутри extractNameTags "
        "(EntityRendererMixin), getName внутри BossHealthOverlay.extractRenderState "
        "(BossHealthOverlayMixin)",
    "getNameTag":
        "её результат меняет Skyblocker (EntityRendererMixin, @ModifyReturnValue) "
        "и зовёт owo-lib (EntityRendererAccessor); встав на САМ метод, мы бы "
        "переводили до чужих правок — перехватывать надо вызов внутри extractNameTags",
}

# Поля чужих классов, которые соседи читают напрямую. Записав туда перевод,
# обязаны вернуть оригинал к выходу из метода.
WATCHED_FIELDS = {
    "header": "PlayerTabOverlay.header — SkyHanni читает его (field_2153)",
    "footer": "PlayerTabOverlay.footer — SkyHanni читает его (field_2154)",
    # ⚠️ 05.09: Modern Warp Menu опознаёт меню быстрого перемещения по
    # `ContainerScreen.getTitle()` — сверяет строку с «Fast Travel»
    # (WarpMenuListener -> GameCheckUtils.determineOpenMenu, проверено
    # по байткоду). Наш перевод в поле навсегда ломал ему карту островов:
    # игрок видел ванильный сундук с головами.
    "title": "Screen.title — его читает getTitle(), а по нему соседи опознают "
             "меню (Modern Warp Menu сверяет с «Fast Travel»)",
}

# ⚠️ ЗАПИСЬ В `title` ЗАКОННА У НЕ-КОНТЕЙНЕРНЫХ ЭКРАНОВ: настройки и паузу
# соседи не разбирают, а точки отрисовки вроде `extractLabels` у них нет.
# Признак законности — отказ для контейнеров прямо в файле.
FIELD_EXEMPT = {
    "title": re.compile(r"instanceof\s+AbstractContainerScreen"),
}

TARGET = re.compile(r'target\s*=\s*"[^"]*?;([A-Za-z0-9_$]+)\(')
# ⚠️ Имя метода бывает С ДЕСКРИПТОРОМ: `method = "extractNameTags(L...;FDD)V"`.
# Берём всё до скобки или кавычки — иначе такая цель не читалась бы вовсе.
METHOD = re.compile(r'method\s*=\s*"([A-Za-z0-9_$<>]+)[("]')
# Строка, разбитая конкатенацией на несколько строк файла:
#   target = "Lnet/.../EntityRenderer;"
#           + "getNameTag(...)"
# Склеиваем ДО разбора, иначе имя в хвосте цели не видно ни одной регулярке.
SPLIT_STRING = re.compile(r'"\s*\+\s*"')
WRITE = re.compile(r"this\.(\w+)\s*=")


def check_targets() -> list[str]:
    """Перехватываем ли мы то, что соседи зовут сами."""
    bad = []
    for path in sorted(MIXINS.glob("*.java")):
        text = SPLIT_STRING.sub("", path.read_text(encoding="utf-8"))
        # ⚠️ Смотрим ТОЛЬКО аннотации: те же имена стоят в комментариях,
        # где мы как раз объясняем, почему их трогать нельзя.
        for line in text.splitlines():
            if "//" in line:
                line = line[: line.index("//")]
            for name in METHOD.findall(line) + TARGET.findall(line):
                if name not in FORBIDDEN:
                    continue
                # цель ВНУТРИ отрисовки законна: значение уходит на экран,
                # а спросивший игру сам получит оригинал
                if "target =" in line and "ModifyExpressionValue" in text:
                    continue
                bad.append("%s: перехвачена %s — %s"
                           % (path.name, name, FORBIDDEN[name]))
    return bad


def check_fields() -> list[str]:
    """Возвращаем ли чужие поля к оригиналу после отрисовки."""
    bad = []
    for path in sorted(MIXINS.glob("*.java")):
        text = path.read_text(encoding="utf-8")
        for field, why in WATCHED_FIELDS.items():
            if not re.search(r"this\.%s\s*=" % field, text):
                continue
            # ⚠️ Есть законные записи: экран, который соседи не читают.
            # Признак — файл сам отказывается от опасного случая.
            exempt = FIELD_EXEMPT.get(field)
            if exempt and exempt.search(text):
                continue
            # ищем восстановление: запись в @At("RETURN")
            tail = text.split('@At("RETURN")')
            restored = any(re.search(r"this\.%s\s*=" % field, part)
                           for part in tail[1:])
            if not restored:
                bad.append("%s: пишем в %s и НЕ возвращаем к оригиналу — %s"
                           % (path.name, field, why))
    return bad


def code_only(text: str) -> str:
    """Текст Java без комментариев: в них мы как раз объясняем, чего НЕ делать."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(line.split("//")[0] for line in text.splitlines())


def check_own_windows(windows: list[Path] | None = None,
                      mixins: Path | None = None) -> list[str]:
    """Свои окна рисуем сами и после подсказки предмета, а не ванильной подсказкой."""
    bad = []
    for path in windows or OWN_WINDOWS:
        if not path.exists():
            bad.append("%s: файла нет — сторож своих окон смотрит не туда" % path.name)
            continue
        for number, line in enumerate(code_only(path.read_text(encoding="utf-8")).splitlines(), 1):
            if TOOLTIP_PIPELINE.search(line):
                bad.append("%s:%d: своё окно рисуется ванильной подсказкой — соседи "
                           "(SkyBlock Enhancements, Stfu) переставят его на подсказку "
                           "предмета: %s" % (path.name, number, line.strip()))
    # Рисовать — только на выходе из отложенной отрисовки: раньше подсказка
    # предмета ляжет сверху новым слоем и закроет справку.
    drawers = []
    for path in sorted((mixins or MIXINS).glob("*.java")):
        code = code_only(path.read_text(encoding="utf-8"))
        if "WikiPanel.afterDeferred(" not in code:
            continue
        drawers.append(path.name)
        if not re.search(r'method\s*=\s*"extractDeferredElements"\s*,\s*at\s*=\s*@At\("TAIL"\)', code):
            bad.append("%s: справка рисуется не на выходе из extractDeferredElements — "
                       "подсказка предмета ляжет поверх неё" % path.name)
    if not drawers:
        bad.append("никто не зовёт WikiPanel.afterDeferred — справка не рисуется вовсе")
    return bad


def scan_jars() -> None:
    """Что соседи читают из таба — справочно, по их jar в инстансах."""
    seen = set()
    for jar in INSTANCES.glob("*/.minecraft/mods/*.jar"):
        if "skyblockru" in jar.name.lower() or jar.name in seen:
            continue
        seen.add(jar.name)
        try:
            zf = zipfile.ZipFile(jar)
        except (zipfile.BadZipFile, OSError):
            continue
        hits = []
        for entry in zf.namelist():
            if not entry.endswith(".class"):
                continue
            try:
                data = zf.read(entry)
            except (KeyError, OSError):
                continue
            if b"PlayerTabOverlay" not in data and b"class_640" not in data:
                continue
            marks = [probe.decode() for probe in
                     (b"header", b"footer", b"method_1918",
                      b"getNameForDisplay", b"getTabListDisplayName")
                     if probe in data]
            if marks:
                hits.append((entry.split("/")[-1], marks))
        if hits:
            print("   %s" % jar.name)
            for name, marks in hits[:4]:
                print("      %-46s %s" % (name, ", ".join(marks)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jars", action="store_true",
                        help="показать, что соседи читают из таба")
    args = parser.parse_args()

    bad = check_targets() + check_fields() + check_own_windows()
    if args.jars:
        print("=== ЧТО СОСЕДИ ЧИТАЮТ ИЗ ТАБА ===")
        scan_jars()
        print()

    if bad:
        print("=== СЛОМАНО: %d ===" % len(bad))
        for row in bad:
            print("   " + row)
        print("\n   Перехватывать надо ВЫЗОВ ВНУТРИ ОТРИСОВКИ, а не сам метод:")
        print("   тогда перевод уходит на экран, а сосед получает текст Hypixel.")
        return 1

    print("чисто: соседям отдаём оригинал")
    print("   проверено целей: %d, полей: %d, своих окон: %d"
          % (len(FORBIDDEN), len(WATCHED_FIELDS), len(OWN_WINDOWS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
