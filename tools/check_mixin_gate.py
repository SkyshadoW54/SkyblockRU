"""
Привратник миксинов обязан выбрать РОВНО ОДИН перехват надписей.

⚠️ Зачем. 01.08 мод перестал запускаться на 26.2 — не переводил плохо,
а НЕ СТАРТОВАЛ ВООБЩЕ: краш при инициализации игры.

    Mixin [skyblockru.mixins.json:GuiMixin] FAILED during APPLY
    @ModifyVariable could not find any targets matching 'setOverlayMessage'
    in net/minecraft/client/gui/Gui

Причина в признаке, который выглядел железным. `MixinGate` спрашивал
«есть ли класс `Gui`», и это ФАКТ, а не догадка, — только не тот факт:

    javap 26.2:    Gui — класс ЕСТЬ, setOverlayMessage НЕТ
                   Hud — setOverlayMessage, setTitle, setSubtitle
    javap 26.1.2:  Gui — setOverlayMessage ЕСТЬ
                   Hud — класса нет вовсе

В 26.2 существуют ОБА класса, и обёртка для 26.1 применилась туда, где ей
делать нечего. При `defaultRequire: 1` это критический отказ.

⚠️ Компиляция такого не ловит по устройству: цель миксина задана СТРОКОЙ
(`@Mixin(targets = ...)`) именно затем, чтобы сборка не требовала класс.
Значит проверять надо на БАЙТКОДЕ ИГРЫ — что этот сторож и делает, без
запуска игры.

⚠️ Карта «миксин -> класс и метод» читается ИЗ `MixinGate.java`, а не
держится копией: копии признаков в этом проекте расходились трижды,
и всякий раз молча.

Запуск:
  python tools/check_mixin_gate.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "mixin" / "MixinGate.java"
LOOM = Path.home() / ".gradle" / "caches" / "fabric-loom" / "minecraftMaven"

# «ru.skyblockru.mixin.HudMixin», new String[] {"net.minecraft.client.gui.Hud", "setOverlayMessage"}
ENTRY = re.compile(
    r'"(ru\.skyblockru\.mixin\.\w+)"\s*,\s*new\s+String\[\]\s*\{\s*'
    r'"([\w.]+)"\s*,\s*"(\w+)"\s*\}')


def find_java(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for base in (Path("C:/Program Files/Java"), Path("C:/Program Files/Eclipse Adoptium")):
        if base.exists():
            for path in sorted(base.glob(f"jdk*/bin/{name}.exe"), reverse=True):
                return str(path)
    return None


def gate_map() -> list[tuple[str, str, str]]:
    """Что привратник требует от каждого миксина — берём из его исходника."""
    if not GATE.exists():
        return []
    return ENTRY.findall(GATE.read_text(encoding="utf-8"))


def game_jars() -> list[tuple[str, Path]]:
    """
    Версии игры из кэша Loom: (версия, лучший jar).

    ⚠️ На одну версию Loom кладёт НЕСКОЛЬКО jar, и выбрать первый попавшийся —
    значит ослепнуть. Для 1.21.11 их четыре:
      * `minecraft-merged-deobf-1.21.11.jar`      — 45 классов, СЫРОЙ
      * `...-intermediary-...`                    — промежуточные имена, не наши
      * `minecraft-merged-1.21.11-loom.mappings…` — 10342 класса, ВОТ ЭТОТ
    Сторож брал первый по алфавиту, попадал на сырой и молча пропускал версию —
    ровно ту, на которой игра и упала.

    Поэтому берём jar с НАИБОЛЬШИМ числом классов под `net/minecraft/`,
    а intermediary отбрасываем: там имена не те, что в наших миксинах.
    """
    best: dict[str, tuple[int, Path]] = {}
    for jar in sorted(LOOM.rglob("minecraft-merged-*.jar")):
        # ⚠️ Отбрасываем чужие СИСТЕМЫ ИМЁН, а не только сырые jar:
        # intermediary — промежуточные имена, yarn — свои собственные.
        # Наши миксины написаны под официальные Mojang, и сверять надо с ними.
        # Первый заход брал jar с максимумом классов и попадал на yarn (10580
        # против 10342) — там `Gui` называется иначе, и сторож объявлял
        # «не применится ни один» на пустом месте.
        if "intermediary" in jar.name or "yarn" in jar.name:
            continue
        # версия без хвостовой точки от «.jar»: 1.21.11, а не «1.21.11.»
        version = re.match(r"minecraft-merged-(?:deobf-)?(\d+(?:\.\d+)*)", jar.name)
        if not version:
            continue
        try:
            with zipfile.ZipFile(jar) as z:
                named = sum(1 for n in z.namelist() if n.startswith("net/minecraft/"))
        except (zipfile.BadZipFile, OSError):
            continue
        key = version.group(1)
        if named > best.get(key, (0, jar))[0] or key not in best:
            best[key] = (named, jar)
    return sorted((v, jar) for v, (_, jar) in best.items())


def deobfuscated(jar: Path) -> bool:
    """
    Годится ли jar для замера — то есть разобран ли он по именам.

    ⚠️ Loom оставляет в кэше и СЫРОЙ jar: если setup не дошёл до конца (или
    версию просто скачали под другую сборку), внутри лежат классы `aad.class`,
    `aac.class`, а не `net/minecraft/...`. Мерить по такому — получить ровный
    список «класса нет» у ВСЕХ перехватов и объявить бедой то, чего нет.
    Я на это уже попался при замере порта на 1.21: вывод «в 1.21 переименовано
    всё» был бы неверным, спасла только проверка содержимого jar.
    """
    try:
        with zipfile.ZipFile(jar) as z:
            named = sum(1 for n in z.namelist() if n.startswith("net/minecraft/"))
        return named > 200
    except (zipfile.BadZipFile, OSError):
        return False


def has_method(javap: str, jar: Path, cls: str, method: str) -> bool | None:
    """True/False, либо None — если класса в этой версии нет вовсе."""
    done = subprocess.run([javap, "-classpath", str(jar), cls],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.returncode != 0:
        return None
    return bool(re.search(rf"\b{re.escape(method)}\s*\(", done.stdout))


TARGET_CLASS = re.compile(r"@Mixin\s*\(\s*(?:value\s*=\s*)?([A-Za-z_][\w.]*)\.class")
TARGET_STR = re.compile(r'@Mixin\s*\(\s*targets\s*=\s*"([^"]+)"')
METHOD = re.compile(r'method\s*=\s*"([^"]+)"')
IMPORT = re.compile(r"^import\s+([\w.]+);", re.M)
MIXIN_DIR = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "mixin"


def check_all_targets(javap: str, jars: list[tuple[str, Path]]) -> int:
    """
    ВСЕ строковые цели миксинов против байткода игры.

    ⚠️ Зачем отдельно от привратника. Он сторожил ровно два миксина —
    `Hud`/`Gui`, — и этого оказалось мало: на 1.21.11 игра упала на
    `TooltipSideMixin`, потому что метод там зовётся `renderTooltip`,
    а не `extractTooltip`.

    Сборка при этом прошла с НУЛЁМ ошибок, и не могла иначе: имя метода
    в `@Inject(method = "...")` — обычная СТРОКА, компилятор её не читает.
    Ровно та же слепота, что у `@Mixin(targets = "...")`, только шире:
    целей 21, а сторожил я две.
    """
    if not MIXIN_DIR.exists():
        return 0
    targets = []
    for src in sorted(MIXIN_DIR.glob("*Mixin.java")):
        body = src.read_text(encoding="utf-8")
        imports = {i.rsplit(".", 1)[-1]: i for i in IMPORT.findall(body)}
        match = TARGET_STR.search(body)
        cls = match.group(1) if match else None
        if not cls:
            match = TARGET_CLASS.search(body)
            cls = imports.get(match.group(1), match.group(1)) if match else None
        if cls:
            methods = sorted({m.split("(")[0] for m in METHOD.findall(body)})
            targets.append((src.stem, cls, methods))

    # ⚠️ Цели берём ИЗ ИСХОДНИКОВ АКТИВНОЙ версии, а для остальных — из того,
    # что Stonecutter развернул при сборке (`versions/<v>/build/generated`).
    # Сверять активный исходник с чужой версией — гарантированно получить
    # «не найдено» и приучить себя не смотреть на красное.
    active = active_version()
    print(f"\n=== СТРОКОВЫЕ ЦЕЛИ МИКСИНОВ: {len(targets)} миксинов,"
          f" активная версия {active or '?'} ===")
    print("    компиляция их НЕ проверяет — имя метода это строка")
    if not active:
        print("    активную версию не разобрал — пропускаю")
        return 0

    jar = next((j for v, j in jars if v == active and deobfuscated(j)), None)
    if jar is None:
        print(f"    нет разобранного jar для {active} — пропускаю")
        return 0

    missing = []
    for name, cls, methods in targets:
        text = dump(javap, jar, cls)
        if text is None:
            continue          # класса нет — это забота привратника выше
        for method in methods:
            if method == "<init>":
                continue
            if not re.search(rf"\b{re.escape(method)}\s*\(", text):
                missing.append(f"{name}: {cls.split('.')[-1]}#{method}")

    # ⚠️ Цели миксина, отключённого привратником, искать незачем: на 26.2
    # это `GuiMixin`, и его методов там нет ПО ЗАМЫСЛУ.
    gated = {mixin.split(".")[-1] for mixin, _cls, _method in gate_map()}
    missing = [row for row in missing if row.split(":")[0] not in gated]

    if not missing:
        print(f"    все цели на месте")
        return 0
    print(f"    СЛОМАНО: целей не найдено — {len(missing)}")
    for row in missing:
        print(f"      {row}")
    print("    это значит, что игра упадёт при запуске: Mixin не найдёт, куда"
          " встраиваться")
    return 1


GATE_GENERATED = ("build", "generated", "stonecutter", "main", "java",
                  "ru", "skyblockru", "mixin", "MixinGate.java")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
APPLIES = re.compile(r"private static boolean applies\b.*?\n\t\}", re.S)
# ⚠️ Именно ВЫЗОВ `mc("1.21.11", "26.2")`, а не объявление `fun mc(vararg ...)`:
# без требования кавычки первым совпадением идёт объявление, и список выходит пуст.
MC_LIST = re.compile(r'mc\(\s*("[^)]*)\)')


def declared_versions() -> list[tuple[str, bool]]:
    """
    Версии из `settings.gradle.kts`: (версия, обфусцирована ли).

    ⚠️ Список читается ИЗ настроек сборки, а не держится копией: добавят версию —
    сторож увидит её сам. Признак обфускации там же и записан: `>=26.1` собирают
    `build-unobfuscated.gradle.kts`, всё что ниже — обфусцированное.
    """
    settings = ROOT / "settings.gradle.kts"
    if not settings.exists():
        return []
    found = MC_LIST.search(settings.read_text(encoding="utf-8"))
    if not found:
        return []
    out = []
    for raw in re.findall(r'"([^"]+)"', found.group(1)):
        parts = tuple(int(p) for p in re.findall(r"\d+", raw))
        out.append((raw, parts < (26, 1)))
    return out


def gate_asks_runtime(version: str, active: str | None) -> bool | None:
    """
    Спрашивает ли привратник РАНТАЙМ в сборке под эту версию.

    Активную версию Stonecutter оставляет в `src` как есть, остальным пишет
    развёрнутый исходник в `build/generated`. Неактивную ветку он закрывает
    блочным комментарием — по нему и видно, какая живая.

    Возвращает None, если под версию ещё не собирали и смотреть не на что.
    """
    path = (ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "mixin"
            / "MixinGate.java") if version == active \
        else ROOT.joinpath("versions", version, *GATE_GENERATED)
    if not path.exists():
        return None
    body = APPLIES.search(path.read_text(encoding="utf-8"))
    if not body:
        return None
    return "hasMethod(" in BLOCK_COMMENT.sub("", body.group(0))


def targets_from(directory: Path) -> list[tuple[str, str, list[str]]]:
    """Цели миксинов из папки с исходниками: (миксин, класс, методы)."""
    out = []
    for src in sorted(directory.glob("*Mixin.java")):
        body = src.read_text(encoding="utf-8")
        imports = {i.rsplit(".", 1)[-1]: i for i in IMPORT.findall(body)}
        match = TARGET_STR.search(body)
        cls = match.group(1) if match else None
        if not cls:
            match = TARGET_CLASS.search(body)
            cls = imports.get(match.group(1), match.group(1)) if match else None
        if cls:
            methods = sorted({m.split("(")[0] for m in METHOD.findall(body)})
            out.append((src.stem, cls, methods))
    return out


def check_every_version(javap: str, jars: list[tuple[str, Path]], active: str | None) -> int:
    """
    Цели миксинов НА КАЖДОЙ собранной версии.

    ⚠️ Зачем отдельно от проверки активной версии. Порт на 1.21.x развёл
    двенадцать сборок, и у каждой Stonecutter подставляет СВОИ имена целей.
    Компиляция их не читает (это строки), а промах означает не «плохо
    переведено», а падение игры при запуске — так уже было на 1.21.11
    с `extractTooltip`.

    ⚠️ Смотрим РАЗВЁРНУТЫЕ исходники из `versions/<v>/build/generated`:
    именно они попадают в jar. Для активной версии их нет — там `src` as is.
    """
    versions = [v for v, _ in declared_versions()]
    if not versions:
        return 0
    print("\n=== ЦЕЛИ МИКСИНОВ НА КАЖДОЙ ВЕРСИИ ===")
    print("    имя метода в @Inject — строка; компиляция её не проверяет")
    bad = 0
    for version in versions:
        if version == active:
            directory = MIXIN_DIR
        else:
            directory = ROOT.joinpath("versions", version, "build", "generated",
                                      "stonecutter", "main", "java", "ru",
                                      "skyblockru", "mixin")
        if not directory.exists():
            print(f"   {version:9} под неё не собирали — пропускаю")
            continue
        jar = next((j for v, j in jars if v == version and deobfuscated(j)), None)
        if jar is None:
            print(f"   {version:9} нет разобранного jar игры в кэше Loom")
            continue

        gated = {mixin.split(".")[-1] for mixin, _cls, _method in gate_map()}
        missing = []
        for name, cls, methods in targets_from(directory):
            if name in gated:
                continue          # это забота привратника
            text = dump(javap, jar, cls)
            if text is None:
                missing.append(f"{name}: нет класса {cls.split('.')[-1]}")
                continue
            for method in methods:
                if method == "<init>":
                    continue
                if not re.search(rf"\b{re.escape(method)}\s*\(", text):
                    missing.append(f"{name}: {cls.split('.')[-1]}#{method}")
        if missing:
            bad += 1
            print(f"   {version:9} СЛОМАНО: {len(missing)} целей не найдено")
            for row in missing[:4]:
                print(f"      {row}")
        else:
            print(f"   {version:9} все цели на месте")
    return bad


def check_runtime_names(active: str | None) -> int:
    """
    ⚠️ Обфусцированной версии рантайм-проверка по именам Mojang ВРЁТ ВСЕГДА.

    Это и случилось на 1.21.11: привратник спрашивал байткод класса
    `net.minecraft.client.gui.Gui`, а Loom при сборке перевёл цели миксина
    в промежуточные имена — в рантайме класс зовётся `class_329`. Оба перехвата
    получали «нет», и крупные заголовки оставались английскими.

    ⚠️ Проверка выше этого НЕ ЛОВИТ И НЕ МОЖЕТ: она меряет по деобфусцированному
    jar из кэша Loom, то есть отвечает на вопрос «есть ли такой класс в игре»,
    а не «найдёт ли его привратник у ИГРОКА». Оба вопроса законны, но ответ
    на первый ничего не говорит про второй — на 1.21.11 он был бодрое «APPLY»
    при полностью выключенном перехвате.
    """
    versions = declared_versions()
    if not versions:
        print("\n=== ИМЕНА В РАНТАЙМЕ ===")
        print("    не разобрал список версий из settings.gradle.kts — пропускаю")
        return 0

    print("\n=== ИМЕНА В РАНТАЙМЕ: как привратник решает в каждой сборке ===")
    print("    обфусцированной версии спрашивать байткод по именам Mojang нельзя:"
          " в рантайме классы переименованы")
    bad = 0
    for version, obfuscated in versions:
        asks = gate_asks_runtime(version, active)
        kind = "обфусцирована" if obfuscated else "как есть"
        if asks is None:
            print(f"   {version:9} {kind:14} под неё не собирали — проверить нечем")
            continue
        how = "спрашивает рантайм" if asks else "выбор при сборке"
        if obfuscated and asks:
            bad += 1
            print(f"   {version:9} {kind:14} СЛОМАНО: {how}")
            print("      имена классов у игрока другие -> оба перехвата выключатся"
                  " молча, заголовки останутся английскими")
        elif not obfuscated and not asks:
            bad += 1
            print(f"   {version:9} {kind:14} СЛОМАНО: {how}")
            print("      26.1 и 26.2 идут ОДНИМ jar — выбрать можно только"
                  " в рантайме, иначе одна из версий получит чужой перехват")
        else:
            print(f"   {version:9} {kind:14} ок: {how}")
    return bad


def active_version() -> str | None:
    """Активная версия Stonecutter — из строки `stonecutter active "26.2"`."""
    control = ROOT / "stonecutter.gradle.kts"
    if not control.exists():
        return None
    found = re.search(r'stonecutter\s+active\s+"([^"]+)"',
                      control.read_text(encoding="utf-8"))
    return found.group(1) if found else None


def dump(javap: str, jar: Path, cls: str) -> str | None:
    done = subprocess.run([javap, "-classpath", str(jar), cls],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.stdout if done.returncode == 0 else None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    needs = gate_map()
    if not needs:
        print("СЛОМАНО: не разобрал карту NEEDS из MixinGate.java")
        print(f"  файл: {GATE}")
        print("  если формат карты поменялся — поправь ENTRY, а не копируй список")
        return 1
    print(f"привратник требует метод у {len(needs)} миксинов:")
    for mixin, cls, method in needs:
        print(f"   {mixin.split('.')[-1]:10} -> {cls}#{method}")

    javap = find_java("javap")
    if not javap:
        print("\nСЛОМАНО: не нашёл javap — без него проверять нечем")
        return 1

    jars = game_jars()
    if not jars:
        print(f"\nСЛОМАНО: в кэше Loom нет ни одного jar игры ({LOOM})")
        return 1

    bad = 0
    checked = 0
    for version, jar in jars:
        applied = []
        print(f"\n=== Minecraft {version} ===")
        if not deobfuscated(jar):
            print("   пропускаю: jar в кэше СЫРОЙ (обфусцирован) — по нему"
                  " замер не делается")
            continue
        checked += 1
        for mixin, cls, method in needs:
            state = has_method(javap, jar, cls, method)
            if state is None:
                print(f"   {mixin.split('.')[-1]:10} класса {cls} нет  -> skip")
                continue
            print(f"   {mixin.split('.')[-1]:10} {cls} {'ИМЕЕТ' if state else 'без'}"
                  f" {method}  -> {'APPLY' if state else 'skip'}")
            if state:
                applied.append(mixin.split(".")[-1])
        if len(applied) == 1:
            print(f"   ок: применится ровно один — {applied[0]}")
        elif not applied:
            bad += 1
            print("   СЛОМАНО: не применится НИ ОДИН — надписи над хотбаром"
                  " останутся английскими, и молча")
        else:
            bad += 1
            print(f"   СЛОМАНО: применятся СРАЗУ ДВА — {', '.join(applied)}."
                  " При defaultRequire: 1 игра не запустится вовсе")

    bad += check_all_targets(javap, jars)
    bad += check_every_version(javap, jars, active_version())
    bad += check_runtime_names(active_version())

    print()
    if bad:
        print(f"СЛОМАНО: {bad} версий выбирают перехват неверно")
        return 1
    print(f"СЛОМАНО: 0 — на всех {checked} проверенных версиях выбирается"
          f" ровно один перехват (в кэше версий: {len(jars)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
