"""
Режим ПОЛНОГО перевода: можно ли его вообще включить.

Беда, ради которой написано (22.08). Режим — это не один словарь, а группа:
названия предметов, имена NPC и локаций, зачарования, характеристики. Каждый
из них выключен по умолчанию (`"default": false`) и помечен `"group": "full"`,
а команда `/skyblockru full on` ставит выбор сразу всем.

Сломаться тут может тихо, и всеми четырьмя способами сразу:

  * словарь НЕ ВПИСАН в packs/index.json — значит в jar его нет вовсе,
    и включать нечего. Ровно так режим и был отложен 03.08: файлы лежали
    в репозитории, команда существовала, а действия не было;
  * словарь вписан, но `"default"` не false — тогда он применяется У ВСЕХ
    сразу, без всякой команды. Это обратная беда, и она хуже: игрок,
    который ищет вещи на аукционе по английским названиям, получает русские
    и не понимает, что случилось;
  * у словаря забыт `"group"` — он есть, включается поштучно, но команда
    режима про него не знает и включает режим НАПОЛОВИНУ;
  * имя группы в словаре разошлось с константой в Java — тогда группа пуста,
    и команда честно отвечает «недоступно» при полном комплекте файлов.

⚠️ Имя группы читается ИЗ `Translator.java`, а не пишется здесь копией:
копия признака в этом проекте расходилась молча уже трижды.

⚠️ Проверяется И НА УМЕНИЕ НАХОДИТЬ: те же правила прогоняются по нарочно
испорченным данным, и сторож обязан покраснеть на каждой из четырёх бед.
Без этого «молчит» и «работает» неотличимы.

Запуск:
  python tools/check_full_mode.py
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

# ⚠️ Консоль Windows — cp1251, и `print` со значком «⚠️» роняет скрипт
# на первой же находке. Записанная грабля проекта: инструмент, падающий
# на печати, ВРЁТ О СВОЕЙ РАБОТЕ — вывод оборван, а выглядит как поломка
# того, что он проверял. У сторожа это хуже вдвое: он молчит, пока всё
# хорошо, и ломается ровно тогда, когда нашёл беду.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"
LANG = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "lang"
TRANSLATOR = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core" / "Translator.java"
COMMAND = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "command" / "RuCommand.java"
TEXT_TRANSLATOR = (ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core"
                   / "TextTranslator.java")
VERSIONS = ROOT / "versions"

# Что мод пишет в чат про режим. Без этих ключей команда ответит именем ключа —
# то есть возможность есть, а объяснить её нечем.
LANG_KEYS = (
    "skyblockru.full.on",
    "skyblockru.full.off",
    "skyblockru.full.warn",
    "skyblockru.full.howto",
    "skyblockru.full.none",
    "skyblockru.stats.full",
)


def java_group() -> str:
    """Имя группы из Translator.java. Своей копии не заводим."""
    if not TRANSLATOR.exists():
        return ""
    found = re.search(r'FULL_GROUP\s*=\s*"([^"]+)"', TRANSLATOR.read_text(encoding="utf-8"))
    return found.group(1) if found else ""


def read_packs() -> list[dict]:
    """Все встроенные словари: имя файла, id, группа, умолчание."""
    out = []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "file": path.name,
            "id": data.get("id", path.name),
            "group": data.get("group", ""),
            "default": data.get("default", True),
            "only": list(data.get("only") or []),
        })
    return out


def real_areas() -> set[str]:
    """
    Настоящие имена областей — читаем ИЗ Java, копии не держим.

    ⚠️ Область задаётся полем "only", и мод сверяет её со строкой ИСТОЧНИКА
    (`Entry.allows`). Имя, которого нет среди `TextTranslator.SRC_*`, не совпадёт
    НИКОГДА — то есть пакет молча выключается для этой области. Беда тихая:
    словарь грузится, ошибок нет, на экране английский.

    Записанная грабля проекта: `gen_stat_bar` писал «sidebar», а боковая панель
    у мода зовётся `scoreboard`, и правило было мертво по построению. Та же
    опечатка вернулась в `78-sb-stats` и прожила до 23.08.
    """
    if not TEXT_TRANSLATOR.exists():
        return set()
    text = TEXT_TRANSLATOR.read_text(encoding="utf-8")
    return set(re.findall(r'String\s+SRC_[A-Z_]+\s*=\s*"([a-z_]+)"', text))


def declared_names() -> set[str]:
    """Что перечислено в index.json — только это едет в jar."""
    index = PACKS / "index.json"
    if not index.exists():
        return set()
    data = json.loads(index.read_text(encoding="utf-8"))
    names = set(data.get("common", []))
    for files in data.get("languages", {}).values():
        names.update(files)
    return names


def jar_names() -> set[str] | None:
    """Словари внутри свежесобранного jar. None — сборки нет, проверять нечего."""
    jars = [
        jar
        for jar in VERSIONS.glob("*/build/libs/skyblockru-*.jar")
        if "sources" not in jar.name
    ]
    if not jars:
        return None
    jar = max(jars, key=lambda f: f.stat().st_mtime)
    with zipfile.ZipFile(jar) as zf:
        return {
            name.rsplit("/", 1)[1]
            for name in zf.namelist()
            if "/packs/" in name and name.endswith(".json")
        }


def lang_missing() -> list[str]:
    """Каких ключей режима не хватает в переводах интерфейса мода."""
    missing = []
    for lang in ("en_us.json", "ru_ru.json"):
        path = LANG / lang
        if not path.exists():
            missing.append(f"нет файла lang/{lang}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in LANG_KEYS:
            if key not in data:
                missing.append(f"lang/{lang}: нет ключа {key}")
    return missing


def command_present() -> bool:
    """Есть ли ветка команды. Возможность без команды — невидимая."""
    if not COMMAND.exists():
        return False
    return 'literal("full")' in COMMAND.read_text(encoding="utf-8")


def check(packs: list[dict], declared: set[str], in_jar: set[str] | None,
          group: str, areas: set[str] | None = None) -> list[str]:
    """Чистая проверка: на входе данные, на выходе список бед."""
    problems: list[str] = []
    if not group:
        problems.append("в Translator.java не нашлось FULL_GROUP — имя группы неизвестно")
        return problems

    # ⚠️ ВЫКЛЮЧЕННЫЙ СЛОВАРЬ БЕЗ ГРУППЫ — включить его может только поимённая
    # команда, а режим про него не знает вовсе. Замер 23.08: так `sb_enchants`
    # (417 записей) не входил в полный перевод, и названия зачарований
    # оставались английскими при включённом режиме. Игрок про это не узнает:
    # команда честно скажет «режим включён», потому что спрашивает СВОЮ группу.
    for pack in packs:
        if pack["default"] is False and not pack["group"]:
            problems.append(
                f"{pack['file']}: выключен (\"default\": false), но не в группе — "
                f"команда режима его не включит, включать придётся поимённо")

    # ⚠️ ОБЛАСТЬ, КОТОРОЙ НЕ СУЩЕСТВУЕТ, молча выключает пакет для неё.
    # Список настоящих имён берём из Java, а не пишем здесь копией.
    known = areas or set()
    if known:
        for pack in packs:
            for area in pack["only"]:
                if area not in known:
                    problems.append(
                        f"{pack['file']}: область {area!r} не существует — "
                        f"мод такой источник не помечает, пакет там не сработает")

    members = [pack for pack in packs if pack["group"]]
    if not members:
        problems.append("ни один словарь не помечен полем \"group\" — включать нечего")
    # ⚠️ ПУСТОЙ index.json — это САМА беда, а не повод пропустить проверку.
    # Первая версия сторожа писала «if declared and ...», то есть при пустом
    # списке молчала, — и подсадка тут же это поймала: словарь, не вписанный
    # никуда, проходил как здоровый. Та же семья, что записанная грабля про
    # скрипт удаления, который при пустом списке исключений снёс бы всё.
    if members and not declared:
        problems.append("index.json пуст или не прочитан — словари режима в jar не поедут")

    for pack in members:
        name = pack["file"]
        if pack["group"] != group:
            problems.append(
                f"{name}: группа {pack['group']!r} не совпадает с Translator.FULL_GROUP "
                f"({group!r}) — команда этот словарь не увидит")
        # ⚠️ Главная из обратных бед: словарь режима, включённый по умолчанию,
        # применяется у ВСЕХ и без команды.
        if pack["default"] is not False:
            problems.append(
                f"{name}: в группе, но \"default\" не false — режим включён у всех молча")
        if name not in declared:
            problems.append(
                f"{name}: не вписан в index.json — в jar не поедет, включать будет нечего")
        if in_jar is not None and name not in in_jar:
            problems.append(f"{name}: нет в собранном jar")

    return problems


PACK_SRC = (ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core"
            / "TranslationPack.java")

# Что решает `enabledBy`: (выбор игрока, состояние группы, умолчание, ждём, зачем)
SWITCH_CASES = [
    ("none", "true", "false", True,
     "СЛОВАРЬ ДОБАВЛЕН В РЕЖИМ ПОЗЖЕ: записи о нём нет, но группа включена"),
    ("none", "false", "false", False,
     "группа выключена — выключен и словарь"),
    ("none", "none", "false", False,
     "ни выбора, ни группы — работает умолчание"),
    ("none", "none", "true", True,
     "умолчание «включён»"),
    ("false", "true", "false", False,
     "выключил руками — поштучный выбор СИЛЬНЕЕ группы"),
    ("true", "false", "false", True,
     "включил руками при выключенной группе — тоже сильнее"),
]

SWITCH_PROBE = """package ru.skyblockru.core;

public final class SwitchProbe {
    public static void main(String[] args) {
        for (int i = 0; i + 2 < args.length; i += 3) {
            Boolean own = args[i].equals("none") ? null : Boolean.valueOf(args[i]);
            Boolean group = args[i + 1].equals("none") ? null : Boolean.valueOf(args[i + 1]);
            System.out.println(TranslationPack.enabledBy(own, group,
                    Boolean.parseBoolean(args[i + 2])));
        }
    }
}
"""


CYRILLIC = re.compile("[а-яёА-ЯЁ]")
CODES = re.compile("§.")


def plain(text: str) -> str:
    return CODES.sub("", str(text)).strip()


def is_translation(value: str | None) -> bool:
    """Русский текст либо @ключ клиента. Латиница переводом не считается."""
    if not value:
        return False
    text = plain(value)
    return bool(CYRILLIC.search(text)) or text.startswith("@")


def mutes(key: str, winner: str | None, without: str | None) -> bool:
    """Гасит ли ТОЖДЕСТВЕННАЯ запись готовый перевод.

    Чистая функция ради подсадки: на входе ровно то, что ответил движок.
    `winner` — что он отдаёт СЕЙЧАС, `without` — что отдал бы без этого
    словаря. Беда, если сейчас приходит сама строка, а без словаря пришёл бы
    русский перевод: значит запись не дополняет словарь, а перебивает его.
    """
    if not winner or plain(winner) != plain(key):
        return False
    return is_translation(without) and plain(without) != plain(key)


def muting_entries() -> list[str]:
    """⚠️ ТОЖДЕСТВЕННАЯ ЗАПИСЬ ПОВЕРХ ГОТОВОГО ПЕРЕВОДА — беда, возвращавшаяся ДВАЖДЫ.

    25.08 таких записей было 606: 584 гасили режим (зачарования SkyBlock),
    22 — обычный перевод, включая ванильные, которые клиент знает сам.
    Починили генератор, а 27.08 замер нашёл ещё 33 — словарь просто
    не пересобрали, и старые записи дожили до раздачи.

    `check_shrink` этого не ловит и не может: он стережёт УСУШКУ словаря,
    а тут ПРИРОСТ мусора. Признак спрашивает ДВИЖОК, а не рассуждает
    о приоритетах: у `exact` побеждает меньший priority, и держать эту
    арифметику копией здесь значило бы разойтись с ним при первой правке.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import status  # noqa: PLC0415

    candidates: dict[str, list[str]] = {}
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        same = [key for key, value in (data.get("exact") or {}).items()
                if isinstance(value, str) and plain(key) == plain(value)]
        if same:
            candidates[path.name] = same
    if not candidates:
        return []

    # ⚠️ ОБА РЕЖИМА. В обычном гаснут ванильные зачарования, в полном —
    # словари группы. Спросив один, увидишь половину.
    problems: list[str] = []
    for mode, groups in (("обычный", None), ("режим full", {"full"})):
        whole = status.Dictionaries(groups=groups) if groups else status.Dictionaries()
        # ⚠️⚠️ ДЕШЁВЫЙ ОТСЕВ ПЕРЕД ДОРОГИМ ОПРОСОМ.
        #
        # `status.lookup` при промахе перебирает 4570 правил — 51 мс на вопрос.
        # Первый вариант этого раздела спрашивал движок про КАЖДУЮ из 778
        # тождественных записей в обоих режимах и стоил 133 с: сторож стал
        # самым дорогим в круге сборки, то есть я починил одну дороговизну
        # и завёл другую.
        #
        # Отсев надёжен как НИЖНЯЯ ГРАНИЦА, а не как копия движка: если ключ
        # не встречается в `exact` другого словаря и с ним не совпадает
        # НИ ОДНО правило, перевода не может быть ни при каком порядке
        # и приоритете. Точный ответ по-прежнему даёт движок — просто его
        # спрашивают о десятках строк, а не о тысяче.
        #
        # Тот же приём, каким `protected.check_block` ускорен в 74 раза.
        may_translate = set()
        for key, value in whole.exact.items():
            text = value[0] if isinstance(value, tuple) else value
            if plain(text) != plain(key):
                may_translate.add(key)
        for name, keys in candidates.items():
            # ⚠️⚠️ ПРИМЕРЯТЬ НАДО ВСЕ ВИДЫ СТРОКИ, а не сырой ключ.
            #
            # В словаре ключ ОБОБЩЁН («Enchanting {n}: {n}%»), а правила писаны
            # под ЖИВУЮ строку («([\d,]+)»): движок применяет их ДО обобщения.
            # Первый вариант отсева сравнивал сырой ключ — и ОСЛЕП ровно на том
            # случае, ради которого раздел писался: подсадка настоящей записи
            # прошла как здоровая. Поймала это только проверка НА БОЕВЫХ ДАННЫХ;
            # чистая подсадка `mutes` такого не покрывает по построению.
            #
            # Виды строки берём у `status.probes` — та же функция, что у отчёта.
            # Записанная грабля проекта, всплывшая в третий раз.
            suspects = [key for key in keys
                        if key in may_translate
                        or any(rule.pattern.fullmatch(view)
                               for view in status.probes(key)
                               for rule in whole.rules)]
            if not suspects:
                continue
            winners = {}
            for key in suspects:
                got = status.lookup(key, whole)
                value = got[0] if isinstance(got, tuple) else got
                if value is not None and plain(value) == plain(key):
                    winners[key] = value
            if not winners:
                continue
            # Словарь без этого файла строим ЛЕНИВО: он стоит секунду,
            # а файлов с тождественными записями бывает восемь из тридцати.
            rest = (status.Dictionaries(without={name}, groups=groups) if groups
                    else status.Dictionaries(without={name}))
            for key, value in winners.items():
                got = status.lookup(key, rest)
                other = got[0] if isinstance(got, tuple) else got
                src = got[1] if isinstance(got, tuple) and len(got) > 1 else "?"
                if mutes(key, value, other):
                    problems.append(
                        f"{name}: {mode} — тождественная запись {key[:40]!r} гасит "
                        f"готовый перевод {plain(other)[:34]!r} из {src}")
    return problems


def check_switch() -> list[str]:
    """Гоняет решение «включён ли словарь» настоящей Java.

    ⚠️ Раздел заведён после того, как игрок нашёл беду НА ЭКРАНЕ: два словаря,
    добавленные в режим позже, у него не включились, и понять это можно было
    только переключив команду туда-обратно. Выбор хранился поимённо, а записи
    о новых словарях в конфиге не было — значит работало умолчание «выкл».
    """
    import subprocess
    import tempfile
    try:
        import check_click_events as helper
    except Exception:
        return []
    java = helper.find_java("java")
    javac = helper.find_java("javac")
    if not java or not javac:
        return []
    cp = helper.classpath()
    if cp is None:
        return []

    args = []
    for own, group, default, _want, _why in SWITCH_CASES:
        args += [own, group, default]

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        probe = work / "SwitchProbe.java"
        probe.write_text(SWITCH_PROBE, encoding="utf-8")
        out = work / "classes"
        out.mkdir()
        build = subprocess.run(
            [javac, "-encoding", "UTF-8", "-nowarn", "-cp", ";".join(cp),
             "-d", str(out), str(PACK_SRC), str(probe)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            return ["TranslationPack.java не компилируется: "
                    + build.stderr.strip().splitlines()[0][:120]]
        run = subprocess.run(
            [java, "-Dstdout.encoding=UTF-8", "-cp", ";".join([str(out)] + cp),
             "ru.skyblockru.core.SwitchProbe", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if run.returncode != 0:
        return ["проверка выключателя не запустилась"]
    got = [line.strip() == "true" for line in run.stdout.split() if line.strip()]
    if len(got) != len(SWITCH_CASES):
        return [f"ждали {len(SWITCH_CASES)} ответов о выключателе, получили {len(got)}"]
    out_problems = []
    for (own, group, default, want, why), have in zip(SWITCH_CASES, got):
        if have != want:
            out_problems.append(
                f"выключатель: выбор={own} группа={group} умолчание={default} — "
                f"ждали {'вкл' if want else 'выкл'}, вышло {'вкл' if have else 'выкл'} ({why})")
    return out_problems


def main() -> int:
    group = java_group()
    packs = read_packs()
    declared = declared_names()
    in_jar = jar_names()

    print(f"имя группы из Translator.java: {group!r}")
    members = [pack for pack in packs if pack["group"] == group]
    print(f"словарей в группе: {len(members)}")
    for pack in members:
        print(f"   {pack['file']:26} id={pack['id']:14} default={pack['default']}")
    if in_jar is None:
        print("собранного jar нет — состав jar не проверяется")

    areas = real_areas()
    if areas:
        print(f"настоящих областей в TextTranslator.java: {len(areas)}")
    else:
        print("TextTranslator.java не прочитан — области не проверяются")
    problems = check(packs, declared, in_jar, group, areas)
    if not command_present():
        problems.append("в RuCommand.java нет ветки literal(\"full\") — команды не существует")
    problems.extend(lang_missing())
    switch = check_switch()
    problems.extend(switch)
    muting = muting_entries()
    problems.extend(muting)
    if not muting:
        print("тождественных записей поверх готового перевода: 0")
    if not switch:
        print(f"выключатель: {len(SWITCH_CASES)} случаев обоих краёв — все верны")
    # ⚠️ Команда обязана писать состояние ГРУППЫ. Вернётся поимённая запись —
    # и добавленный завтра словарь снова не включится у тех, кто режим включил.
    command = (ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "command"
               / "RuCommand.java").read_text(encoding="utf-8")
    if "Translator.setGroup(" not in command:
        problems.append("RuCommand: команда не пишет состояние группы (setGroup) — "
                        "выбор снова стал поимённым")

    # ⚠️ ПРОВЕРКА НА УМЕНИЕ НАХОДИТЬ. Те же правила по нарочно испорченным
    # данным: сторож обязан покраснеть на каждой беде. Файлы при этом
    # не трогаются — портим копию в памяти.
    healthy = [{"file": "x.json", "id": "x", "group": group, "default": False,
                "only": ["item_lore"]}]
    probes = {
        "словарь не вписан в index.json": (healthy, set(), None),
        "словарь включён по умолчанию":
            ([{**healthy[0], "default": True}], {"x.json"}, None),
        "имя группы разошлось с Java":
            ([{**healthy[0], "group": "other"}], {"x.json"}, None),
        "словаря нет в jar": (healthy, {"x.json"}, set()),
        # ⚠️ Две беды, прожившие в проекте до 23.08 (см. real_areas и check).
        "выключен, но не в группе":
            ([{**healthy[0], "group": ""}], {"x.json"}, None),
        "область, которой не существует":
            ([{**healthy[0], "only": ["sidebar"]}], {"x.json"}, None),
    }
    # ⚠️ Подсадка для тождественных записей — на чистой функции, а не на файлах:
    # портить боевой словарь ради проверки нельзя, а признак от этого не зависит.
    mute_probes = {
        "тождественная запись гасит русский перевод":
            ("Duplex I", "Duplex I", "Дуплет I"),
        "тождественная запись гасит @ключ клиента":
            ("Sharpness IV", "Sharpness IV", "@enchantment.minecraft.sharpness IV"),
    }
    mute_healthy = {
        "перевода нет вовсе — запись законна": ("Gold's Power", "Gold's Power", None),
        "везде тождественно — гасить нечего": ("Bank V", "Bank V", "Bank V"),
        "перевод есть и побеждает — беды нет": ("Growth V", "Рост V", "Рост V"),
        "соседи дают латиницу — это не перевод": ("Elite I", "Elite I", "Elite I "),
    }
    blind_mute = [name for name, args in mute_probes.items() if not mutes(*args)]
    blind_mute += [f"здоровый случай объявлен бедой: {name}"
                   for name, args in mute_healthy.items() if mutes(*args)]

    probe_areas = {"item_lore", "chat", "scoreboard"}
    blind = [name for name, (p, d, j) in probes.items()
             if not check(p, d, j, group, probe_areas)]
    if check(healthy, {"x.json"}, {"x.json"}, group, probe_areas):
        blind.append("здоровый случай объявлен бедой")
    blind.extend(blind_mute)

    print()
    if blind:
        print("⚠️ СТОРОЖ СЛЕП:")
        for name in blind:
            print(f"   не поймал: {name}")
    else:
        print(f"подсадка: {len(probes) + len(mute_probes)} бед из "
              f"{len(probes) + len(mute_probes)} поймано, "
              f"{len(mute_healthy) + 1} здоровых случаев прошли")

    print()
    if problems:
        print(f"СЛОМАНО: {len(problems)}")
        for line in problems:
            print(f"   {line}")
    else:
        print("итого замечаний: 0 — режим включается")
    return 1 if problems or blind else 0


if __name__ == "__main__":
    sys.exit(main())
