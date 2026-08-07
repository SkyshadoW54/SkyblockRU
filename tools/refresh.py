"""
Полный круг: дамп -> корпус и очередь -> перевод -> словари -> проверки -> jar.

⚠️ Зачем отдельный скрипт. Мод собирает строки НЕПРЕРЫВНО, а инструменты читают
дамп СНИМКОМ. Игрок открывает меню, которого мод раньше не видел, — и подсказка
попадает в дамп уже после того, как собрана очередь. Отсюда бесконечное «почему
это не переведено»: строка есть в игре, есть в дампе, а в очереди её нет.

Круг из шести команд руками я за один вечер прогнал семь раз, каждый раз рискуя
забыть шаг (например merge_paragraphs, без которого перевод не доедет до мода).
Теперь это одна команда.

Порядок жёсткий, менять нельзя:
  1. корпус абзацев с ЖИВЫМ дампом      (появляются новые абзацы)
  2. очередь строк                       (уже знает про новые абзацы)
  3. перевод абзацев, потом строк        (деньги; --dry покажет объём без трат)
  4. слить оба в словари мода
  5. проверки: шаблоны, контракт, перевод
  6. собрать jar и положить в инстанс

Запуск:
  python tools/refresh.py --dry     посмотреть, сколько нового и почём
  python tools/refresh.py           сделать всё
  python tools/refresh.py --no-api  без перевода: только пересборка и сборка
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "work"
DUMP = Path("C:/MultiMC/instances/26.2/.minecraft/config/skyblockru/dump")
INSTANCE = Path("C:/MultiMC/instances/26.2/.minecraft/mods")
JAR = ROOT / "build" / "libs" / "skyblockru-0.1.0+26.2.jar"


def run(args: list[str], quiet: bool = False) -> tuple[int, str]:
    """Запускает шаг и возвращает (код, вывод). Кириллицу не теряем."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    done = subprocess.run(args, cwd=ROOT, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    out = (done.stdout or "") + (done.stderr or "")
    if not quiet:
        for line in out.splitlines():
            if line.strip():
                print("     " + line)
    return done.returncode, out


def step(number: int | str, title: str) -> None:
    print()
    print(f"[{number}] {title}")


def pending() -> tuple[int, int]:
    """Сколько абзацев и строк ждут перевода прямо сейчас."""
    paras = json.loads((WORK / "paragraphs.json").read_text(encoding="utf-8"))
    waiting = sum(1 for p in paras.get("paragraphs") or []
                  if not (p.get("ru") or "") and not p.get("nothing"))
    queue = json.loads((WORK / "from_game.json").read_text(encoding="utf-8"))
    # ⚠️ «_asis» лежит в exact С ПУСТЫМ значением — это помеченные «переводить
    # нечего», а не ждущие. Без вычитания счётчик показывал 708 вместо 38
    # и грозил ценой впятеро больше настоящей.
    asis = queue.get("_asis") or []
    asis = set(asis if isinstance(asis, list) else asis)
    strings = sum(1 for key, value in (queue.get("exact") or {}).items()
                  if not value and key not in asis)
    return waiting, strings


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Полный круг обновления перевода")
    parser.add_argument("--dry", action="store_true",
                        help="только пересобрать и показать объём, без API и сборки")
    parser.add_argument("--no-api", action="store_true",
                        help="без перевода: пересборка, словари, сборка jar")
    args = parser.parse_args()

    tooltips = DUMP / "tooltips.json"
    if not tooltips.exists():
        print("нет дампа подсказок:", tooltips)
        return 1

    step(1, "корпус абзацев по живому дампу")
    code, _ = run([sys.executable, "tools/make_paragraphs.py",
                   "data/work/lore_tooltips.json", "--live", str(tooltips)], quiet=True)
    if code:
        print("     не собрался корпус — дальше идти нельзя")
        return 1
    print("     готово")

    step(2, "очередь строк")
    code, out = run([sys.executable, "tools/make_queue.py"], quiet=True)
    if code:
        return 1
    for line in out.splitlines():
        if any(word in line for word in ("ЖДУТ", "нечего", "ВЫКЛЮЧЕННЫМ")):
            print("     " + line.strip())

    waiting_paras, waiting_lines = pending()
    print()
    print(f"  ждут перевода: абзацев {waiting_paras}, строк {waiting_lines}")
    # цена по факту прошлых прогонов: абзац ~$0.002, строка ~$0.0015
    print(f"  ориентировочно: ${waiting_paras * 0.002 + waiting_lines * 0.0015:.2f}")

    if args.dry:
        print()
        print("сухой прогон: ничего не переведено и не собрано")
        return 0

    if not args.no_api:
        if waiting_paras:
            step(3, f"перевод абзацев ({waiting_paras})")
            run([sys.executable, "tools/translate_tooltips.py", "data/work/paragraphs.json"])
        if waiting_lines:
            step(4, f"перевод строк ({waiting_lines})")
            run([sys.executable, "tools/translate_ai.py", "data/work/from_game.json", "--sync"])

    # ⚠️ РАЗМЕТКА ЦВЕТОМ — БЕСПЛАТНАЯ ЧАСТЬ, и её место именно здесь.
    #
    # Цвета копятся сами: игрок открыл экран — мод записал куски с цветами
    # в dump/paragraph-colors.json. А вот перевод оставался плоским, пока
    # кто-нибудь не вспомнит про color_lore. То есть собранное лежало мёртвым
    # грузом, и мод продолжал УГАДЫВАТЬ цвет там, где точный ответ уже был.
    #
    # Без --apply инструмент денег не тратит: он ставит только механическую
    # разметку (кусок уцелел в переводе дословно — число, процент, английское
    # имя) и говорит, скольким абзацам нужна модель.
    step("4a", "разметка цветом по собранному")
    code, out = run([sys.executable, "tools/color_lore.py"], quiet=True)
    free = next((l for l in out.splitlines() if "БЕЗ модели" in l), "")
    waiting_marks = next((l for l in out.splitlines() if "ждут разметки" in l), "")
    print(f"     {free.strip() or 'ничего не размечено'}")
    if waiting_marks:
        print(f"     {waiting_marks.strip()} — нужна модель: python tools/color_lore.py --apply")

    step(5, "словари мода")
    run([sys.executable, "tools/merge_paragraphs.py"], quiet=True)
    run([sys.executable, "tools/export_pack.py", "from_game", "90-from-game.json"], quiet=True)
    print("     96-paragraphs.json и 90-from-game.json обновлены")

    step(6, "проверки")
    bad = False
    # ⚠️ Снимок ПЕРВЫМ: остальные проверки смотрят на куски логики и честно
    # молчат, когда экран уже сломан. Диф по всему экрану — единственное, что
    # видит результат целиком.
    # ⚠️ И ПОТЕРИ ЦВЕТА внутри подсказок. Инструмент для этого был всё время
    # (`preview.py --broken` сравнивает цвета ДО и ПОСЛЕ в каждой подсказке),
    # но гонял я его руками и от случая к случаю — а значит промахи находил
    # игрок, а не проверка. Теперь это шаг круга, как и всё остальное.
    code, out = run([sys.executable, "tools/preview.py", "--broken", "--plain"], quiet=True)
    lost = [l for l in out.splitlines() if "цвета стало МЕНЬШЕ" in l]
    total = next((l for l in out.splitlines() if "подсказок записано" in l), "")
    print(f"     [{'!!' if lost else 'ok'}] цвета в подсказках — "
          f"потерь: {len(lost)}   ({total.strip()})")
    for line in lost[:4]:
        print("     " + line.strip())

    code, out = run([sys.executable, "tools/snapshot.py", "--show", "4"], quiet=True)
    head = [l for l in out.splitlines() if "изменилось:" in l or "расхождений нет" in l]
    print("     [ok] снимок экрана" + (f" — {head[0].strip()}" if head else ""))
    for line in out.splitlines():
        if line.startswith("    было:") or line.startswith("    стало:") or line.strip().startswith("=="):
            print("     " + line)
    for name, cmd in (("шаблоны", ["tools/check_rules.py"]),
                      ("контракт корпуса", ["tools/check_contract.py"]),
                      ("накопление дампа", ["tools/check_dump_persistence.py"]),
                      # ⚠️ Упор в потолок сбора выглядит как «новых данных
                      # больше нет»: счётчик стоит, ошибок нет, в логе тишина.
                      # Так простоял MAX_TOOLTIPS на 5000, и так же 29.07
                      # обнаружился MAX_PARAGRAPH_COLORS на 10000 — заметил
                      # игрок, а не мод.
                      ("потолки сбора", ["tools/check_limits.py"]),
                      # Резка списков молча ломается «в обе стороны»: перестанет
                      # резать — на экране снова английский при купленном
                      # переводе; съедет граница — пункты разъедутся по чужим
                      # местам. Ни то, ни другое ошибкой не выглядит.
                      ("резка списков", ["tools/check_list_cuts.py"]),
                      # ⚠️ СТОРОЖ ВНЕ КРУГА НЕ СТОРОЖИТ. Эти пятеро гоняют
                      # настоящую Java без игры и стоят меньше секунды каждый,
                      # но запускались, только когда я о них вспомню. Ревизия
                      # 29.07: из 13 сторожей проекта в круге стояли 5.
                      #
                      # Цена промаха видна на живом примере того же дня:
                      # check_colors поймал, что добавление знака «∙» ломает
                      # 13 подсказок классов. Не вспомни я его — правка уехала
                      # бы в jar, и нашёл бы её игрок по скриншоту.
                      #
                      # ⚠️ Остальные трое НЕ включены осознанно: check_terms
                      # шумит на сезонах (12 записей сделаны так намеренно),
                      # check_list_marks сам разошёлся с модом, а
                      # check_dialogues требует аргумент. Включить красного
                      # сторожа — значит приучить себя не смотреть на красное.
                      # ⚠️ Ники ВОЗВРАЩАЮТСЯ сами. Их чистили 03.08, а 04.08
                      # в собранном релизе нашлось 22 штуки — новый дамп принёс
                      # новые, и словари их подхватили. Разовая чистка тут
                      # не работает по природе: пока игрок играет, в дамп
                      # попадают чужие имена. Значит проверка обязана быть
                      # в круге, а не «когда вспомню».
                      ("ники игроков", ["tools/check_nicknames.py"]),
                      ("склейка абзацев", ["tools/check_colors.py"]),
                      ("резка зачарований", ["tools/check_sections.py"]),
                      # ⚠️ Кнопки выбора. Единственная беда проекта, которая
                      # ломала не текст, а ИГРУ: нажимаешь «Не-а», а NPC
                      # продолжает рассказывать. По экрану её не увидеть —
                      # текст переведён, кнопки на месте, цвет верный, — и нашёл
                      # её игрок поведением. Ни один прежний сторож такого
                      # не ловил: все смотрят текст и цвет.
                      ("кнопки выбора", ["tools/check_click_events.py"]),
                      ("раскраска абзацев", ["tools/check_paragraph_colors.py"]),
                      ("ванильные названия", ["tools/check_vanilla_names.py"]),
                      ("раскладка справки", ["tools/check_wiki_layout.py"]),
                      # ⚠️ Какой файл справки мод возьмёт С ДИСКА вместо
                      # встроенного. `Wiki.open` получал путь запрошенного
                      # файла, а искал по ЯЗЫКУ — и на любой запрос отдавал один
                      # и тот же `wiki/ru_ru.json`. Беда ждала своего дня молча:
                      # пока справку не выкладывали в облако, подменяться было
                      # нечему. 05.08 туда уехала правка справки ТЕРМИНОВ — и
                      # встала на место справки ЗАЧАРОВАНИЙ у всех разом, без
                      # нового jar. Панель по Alt перестала находить что-либо.
                      ("подмена справки", ["tools/check_wiki_override.py"]),
                      # ⚠️ Не отстала ли справка от списка защищённых имён.
                      # «Fear» внутри NPC «Fear Mongerer» термином не является,
                      # и справка про характеристику там ни при чём — игрок
                      # прислал это скриншотом. Список берётся из данных
                      # (10 пар на 1049 имён), а не угадывается по форме
                      # текста: правило «слово с Заглавной справа» тут
                      # бессильно, имя разрезано переносом.
                      ("имена в справке", ["tools/gen_wiki_names.py"]),
                      # Ограда вокруг наших перехватов: наше исключение не смеет
                      # ронять подсказку — ни у нас, ни у соседних модов (список
                      # строк Fabric отдаёт БЕЗ копирования, проверено javap).
                      # Проверяется настоящей Java и на УМЕНИЕ НАХОДИТЬ: подсадка
                      # «ловит, но не считает» роняет проверку — то есть ограду
                      # нельзя незаметно превратить в глушилку.
                      ("ограда перехватов", ["tools/check_guard.py"]),
                      # Разнобой разметки внутри ОДНОГО предмета: часть абзацев
                      # цветная, часть плоская — на экране это соседние строки,
                      # выглядящие по-разному, и глаз цепляется именно за это.
                      # ⚠️ Ругается только на РОСТ: долг в 487 абзацев сборку
                      # не валит, иначе она не собралась бы никогда.
                      ("разнобой разметки", ["tools/check_markup_gaps.py"]),
                      # Починка искажённых маркеров {c1}/{i1}: у русского
                      # перевода кириллическая «с» неотличима от латинской «c».
                      # Проверяются ОБА края — чинится искажённое и не трогается
                      # чужое ({n}, {s}, «стена {n}x{n}», сноска «(c)»).
                      ("маркеры разметки", ["tools/check_marks.py"]),
                      # Сканер экрана обязан ЛОВИТЬ и не шуметь. Проверяется
                      # подсадкой каждой беды, которую игрок присылал скриншотом:
                      # ослепший сканер молчит так же, как исправный.
                      # ⚠️ САМАЯ ДОРОГАЯ ИЗ ВОЗМОЖНЫХ ПОЛОМОК: игра не
                      # запускается вовсе. 01.08 обёртка для 26.1 применилась
                      # на 26.2 — там существуют ОБА класса, а привратник
                      # спрашивал про класс, а не про метод. Краш при старте,
                      # и ни один сторож этого не видел: цель миксина задана
                      # СТРОКОЙ, поэтому компиляция проходит по построению.
                      # Проверяется по БАЙТКОДУ игры, без запуска.
                      ("выбор миксина", ["tools/check_mixin_gate.py"]),
                      ("сканер экрана", ["tools/check_scan.py"]),
                      # ⚠️ Отчёт — то же самое, и цена вранья в нём выше: он
                      # открывает КАЖДУЮ сессию. Ложная находка наверху списка
                      # приучает не смотреть в список вовсе, а пропущенная
                      # настоящая уезжает к игроку и возвращается скриншотом.
                      #
                      # Поводом стал отсев ников, который «работал» СЛУЧАЙНО:
                      # «boml9's Profile» пропадало из отчёта не потому, что
                      # признак его узнавал, а потому, что цифра ломала \b
                      # в регулярке и слово не находилось вообще. Настоящая
                      # смесь со словом «Tier9» прошла бы так же молча.
                      ("отчёт", ["tools/check_report.py"]),
                      # ⚠️ Что уходит на сервер перевода. Единственная проверка
                      # в этом круге, где цена промаха не «кривой перевод»,
                      # а чужая переписка на чужом диске: кривой перевод
                      # правится следующим прогоном, а отправленное не вернёшь.
                      # Гоняет `core/TelemetryFilter.java` настоящей Java —
                      # заведомые случаи ОБОИХ краёв плюс живой дамп.
                      ("отправка строк", ["tools/check_telemetry.py"]),
                      # ⚠️ Имя САМОГО игрока в собранной строке. Та же семья,
                      # что выше: Hypixel обращается к человеку по нику прямо
                      # в тексте («[NPC] Terry: Ahoy, Player_1!»), и такая
                      # строка уезжала на сервер вместе с именем — замер 07.08
                      # по хешам отправленного: 23 строки, все 23 уже ушли.
                      # Признак железный (клиент знает своё имя), поэтому
                      # проверять надо не его, а то, что он не задевает лишнего:
                      # чужой ник и имя внутри чужого слова.
                      ("своё имя в строке", ["tools/check_self_name.py"]),
                      # ⚠️ `check_headers` в круг НЕ включён — он ещё сырой.
                      # Признак «у заголовка нет построчного перевода» слишком
                      # строгий: резка состоится и без него, если заголовок
                      # остался в переводе ДОСЛОВНО («Pursuit», «Ridable» —
                      # имена способностей, их не переводят). Пока не научится
                      # смотреть перевод АБЗАЦА, он даёт 5 ложных находок,
                      # а красный сторож в круге приучает не смотреть
                      # на красное. Запускать руками.
                      # ⚠️ Термины справки: склейка строк пробелом съедала
                      # границу, и слово из имени предмета гасило термин лора.
                      # Баг пережил ДВЕ починки, потому что проверить логику
                      # было нечем — она сидела в Wiki, завязанном на Minecraft.
                      ("термины справки", ["tools/check_wiki_terms.py"]),
                      ("перевод", ["tools/check_translation.py", "data/work/paragraphs.json"])):
        code, out = run([sys.executable, *cmd], quiet=True)
        broken = [l for l in out.splitlines() if "СЛОМАНО" in l and ": 0" not in l]
        # ⚠️ КОД ВОЗВРАТА — ТОЖЕ ПРОВАЛ, и это половина сторожей.
        #
        # Раньше провал определялся ТОЛЬКО по слову «СЛОМАНО» в выводе, а его
        # печатают лишь двое из четырёх: check_translation и
        # check_dump_persistence. check_rules (битый шаблон, который Java
        # не примет) и check_contract (разошлись ключи мода и скриптов —
        # «перевод не найдётся НИ РАЗУ») сообщают о беде кодом возврата,
        # и refresh их молча пропускал, собирая jar как ни в чём не бывало.
        failed = bool(broken) or code != 0
        mark = "!!" if failed else "ok"
        why = broken[0].strip() if broken else (f"код возврата {code}" if code else "")
        print(f"     [{mark}] {name}" + (f" — {why}" if why else ""))
        if failed and not broken:
            # у такого сторожа вся суть в выводе — покажем хвост, иначе
            # игроку придётся запускать его руками, чтобы узнать причину
            for line in out.strip().splitlines()[-6:]:
                print("        " + line)
        bad |= failed
    if bad:
        print()
        print("  ⚠️ проверка не прошла — jar не собираю")
        return 1

    step(7, "сборка jar")
    gradlew = "gradlew.bat" if os.name == "nt" else "./gradlew"
    code, out = run([str(ROOT / gradlew), "build", "-q"], quiet=True)
    if code or not JAR.exists():
        print("     сборка не прошла:")
        print(out[-1500:])
        return 1
    shutil.copy(JAR, INSTANCE / JAR.name)
    print(f"     jar собран и положен в инстанс: {JAR.name}")
    print()
    print("Готово. Перезапусти игру полностью — jar держится в памяти.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
