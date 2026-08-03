"""
ЗАГОЛОВКИ построчно — извлекаем из уже купленных абзацев, а не покупаем заново.

Беда, ради которой написано. Hypixel ставит заголовок отдельной строкой:

    ∙ Ghost Ability: Instant Wall          <- заголовок
    Creates a 5x3 wall at the block…       <- описание

а на экране выходило слипшееся «∙ Способность призрака: Instant Wall Создаёт
стену 5x3…». Мод УМЕЕТ резать найденный перевод (`Paragraphs.header`), но
только если вырезанное совпадает с переводом ПЕРВОЙ СТРОКИ. Построчного
перевода у заголовков нет — и резка отменяется.

⚠️ **Покупать эти строки не нужно: они уже оплачены** внутри абзаца. Перевод
заголовка стоит в его начале и помечен своим цветом — значит его можно ВЫРЕЗАТЬ
и положить построчной записью. Тот же приём, каким проект уже разрезает
абзацы зачарований и списки: ключ не меняется, деньги не тратятся.

⚠️ Границу строк берём из корпуса (`lines`), а не угадываем по форме: признак
«Подпись: Имя» ловит и «Seller: [MVP] Player», и «Mining Speed: +5» —
на живом дампе это 851 строка против 309 настоящих.

⚠️ Какой кандидат резки верный, решает СОРАЗМЕРНОСТЬ: первая строка занимает
в оригинале ту же долю, что заголовок в переводе. Проверять совпадением
с переводом первой строки нельзя — его-то мы и создаём.

Запуск:
  python tools/gen_headers.py           сухой прогон, показать что выйдет
  python tools/gen_headers.py --apply   записать в словарь
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "src" / "main" / "java" / "ru" / "skyblockru" / "core"
CORPUS = ROOT / "data" / "work" / "paragraphs.json"
LANG = "ru_ru"
OUT = ROOT / "src/main/resources/assets/skyblockru/packs" / LANG / "41-headers.json"

CODES = re.compile(r"§.")
HOLES = re.compile(r"\{[ns]\}")

# Горячая клавиша в заголовке способности. Список закрытый — Hypixel пишет
# их ЗАГЛАВНЫМИ и в конце строки; девять видов на весь дамп.
KEY_HINT = re.compile(r"\b(?:SNEAK|RIGHT CLICK|LEFT CLICK|ON SHOOT|CLICK|DIG)\b")
# как они выглядят в наших переводах
KEY_RU = re.compile(r"ШИФТ|ПКМ|ЛКМ|ВЫСТРЕЛ|КОПАЙ|НАЖМИ", re.IGNORECASE)
SPACES = re.compile(r"\s+")


def plain(text: str) -> str:
    """Текст без §-кодов и с мягкими пробелами — для сверки заголовков.

    ⚠️ Пробелы сравниваем МЯГКО: Hypixel ставит двойной пробел перед горячей
    клавишей («Acupuncture  ПКМ»), а разметка — один. Строгая сверка знак
    в знак не сходилась ни разу; та же грабля уже была при разметке цветом.
    """
    return SPACES.sub(" ", CODES.sub("", text or "")).strip()
SEP = "\u0001"

RUNNER = """
import java.nio.file.*;
import java.util.*;
import ru.skyblockru.core.ParagraphColors;

public class HeadRun {
    public static void main(String[] args) throws Exception {
        List<String> rows = Files.readAllLines(Paths.get(args[0]));
        StringBuilder out = new StringBuilder();
        for (String row : rows) {
            List<Integer> ends = ParagraphColors.markedHeadEnds(row);
            for (int i = 0; i < ends.size(); i++) {
                if (i > 0) { out.append(','); }
                out.append(ends.get(i));
            }
            out.append('\\n');
        }
        System.out.print(out);
    }
}
"""


def find_java(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for base in (Path("C:/Program Files/Java"), Path("C:/Program Files/Eclipse Adoptium")):
        if not base.exists():
            continue
        for path in sorted(base.glob(f"*/bin/{name}.exe"), reverse=True):
            return str(path)
    return None


def cut_points(translations: list[str]) -> list[list[int]] | None:
    """Кандидаты на конец заголовка — настоящей Java, а не копией на Python."""
    javac, java = find_java("javac"), find_java("java")
    if not javac or not java:
        print("не нашёл javac/java — а без них резку проверять нечем")
        return None
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "HeadRun.java").write_text(RUNNER, encoding="utf-8")
        build = subprocess.run(
            [javac, "-encoding", "UTF-8", "-d", str(work),
             str(CORE / "ParagraphColors.java"), str(CORE / "ColorLayout.java"),
             str(work / "HeadRun.java")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if build.returncode != 0:
            print("Java не собрала ParagraphColors:")
            print(build.stderr[:1200])
            return None
        data = work / "rows.txt"
        data.write_text("\n".join(t.replace("\n", " ") for t in translations),
                        encoding="utf-8")
        got = subprocess.run([java, "-cp", str(work), "HeadRun", str(data)],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if got.returncode != 0:
            print("Java упала:", got.stderr[:800])
            return None
        out = []
        for line in got.stdout.splitlines():
            out.append([int(x) for x in line.split(",") if x.strip()])
        return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Заголовки абзацев — построчно")
    parser.add_argument("--apply", action="store_true", help="записать словарь")
    parser.add_argument("--show", type=int, default=12)
    args = parser.parse_args()

    corpus = json.loads(CORPUS.read_text(encoding="utf-8")).get("paragraphs") or []
    # Берём только те, где ЕСТЬ разметка и ЕСТЬ первая строка отдельно:
    # без разметки границу заголовка взять неоткуда.
    cases = [p for p in corpus
             if p.get("ru") and "§" in p["ru"] and len(p.get("lines") or []) >= 2]
    print(f"абзацев с разметкой и строками: {len(cases)}")

    points = cut_points([p["ru"] for p in cases])
    if points is None:
        return 1

    # ⚠️ ПОДПИСЬ СО ЗНАЧЕНИЕМ заголовком не бывает, даже если в одном абзаце
    # она стоит отдельной строкой. «Progress to Level {n}:» — законный заголовок
    # у абзаца «Progress to Level {n}: / {n}/{n} XP», но У ДРУГОГО абзаца та же
    # подпись идёт со значением: «Progress to Level {n}: {n}%». Запись одна
    # на обоих, и там она режет строку ПОСЕРЕДИНЕ — подпись остаётся наверху,
    # а «17.1%» уезжает вниз, к полосе прогресса. Игрок прислал это на питомцах.
    #
    # Различить абзацы движок не может: он сверяет вырезанное с записью словаря,
    # а она для него верна. Значит отсеивать надо ЗДЕСЬ, по всему корпусу сразу:
    # если подпись где-то встречается с продолжением, заголовком её не зовём.
    risky: set[str] = set()
    for para in corpus:
        rows = para.get("lines") or []
        if not rows:
            continue
        first = str(rows[0]).strip()
        head, sep, tail = first.partition(":")
        if sep and tail.strip():
            risky.add((head + sep).strip())

    # ⚠️ ЗАГОЛОВОК НЕ ДОЛЖЕН БЫТЬ ОБРЕЗКОМ УЖЕ ИЗВЕСТНОГО ПЕРЕВОДА.
    #
    # У строки «Mob Types: ⚓ Aquatic, ☮ Animal» построчный перевод есть
    # («Типы мобов: ⚓ Водный, ☮ Животное»), а вырезалось из абзаца
    # «Типы мобов: ⚓ водный» — то есть НАЧАЛО того же перевода, оборванное
    # на первой категории. Соразмерность такое пропускает: обрезок и правда
    # занимает похожую долю строки.
    #
    # Признак железный: вырезанное является ПРЕФИКСОМ известного перевода
    # и короче него. Настоящий заголовок так не выглядит — он либо совпадает
    # с переводом целиком, либо отличается словами, а не длиной.
    # ⚠️ Импорт ленивый и ЗДЕСЬ: ниже он уже есть, но нужен раньше — питон
    # считает `status` локальной переменной на всю функцию, и обращение
    # до импорта падает с UnboundLocalError.
    import status  # noqa: PLC0415
    known = status.Dictionaries(without={OUT.name})
    CODES = re.compile("§.")

    def is_cut_off(source: str, made: str) -> bool:
        whole = status.lookup(source, known)
        if not whole:
            return False
        # ⚠️ lookup отдаёт ПАРУ «перевод + файл», а не строку. Первый заход
        # сравнивал с кортежем целиком, признак не срабатывал ни разу
        # и молча показывал 0 находок.
        if isinstance(whole, tuple):
            whole = whole[0]
        a = CODES.sub("", str(whole)).strip().lower()
        b = CODES.sub("", made).strip().lower()
        return len(b) < len(a) and a.startswith(b)

    pairs: dict[str, str] = {}
    skipped = 0
    dropped_risky = 0
    dropped_cut = 0
    for para, ends in zip(cases, points):
        if not ends:
            continue
        head_src = str(para["lines"][0]).strip()
        if not head_src:
            continue
        whole = CODES.sub("", para["ru"])
        # доля, которую первая строка занимает в оригинале
        want = len(head_src) / max(1, len(para["text"]))
        # ⚠️ ГОРЯЧАЯ КЛАВИША — часть заголовка, а не описания. Hypixel пишет
        # её в той же строке («Ability: To the Moon!  SNEAK»), причём ДРУГИМ
        # цветом, поэтому кандидатов на рез получается два: до имени и после
        # клавиши. По одной соразмерности выигрывал первый, клавиша оставалась
        # снаружи — и на экране «ШИФТ» уезжал вниз, слипаясь с описанием
        # («Способность: To the Moon!» / «ШИФТ Заряжай прыжок, приседая»).
        # Игрок прислал это скриншотом на Spring Boots.
        needs_key = KEY_HINT.search(head_src) is not None
        best, score = None, None
        for end in ends:
            cut = CODES.sub("", para["ru"][:end]).strip()
            if not cut:
                continue
            # клавиша есть в оригинале — кандидат обязан её захватить
            if needs_key and not KEY_RU.search(cut):
                continue
            got = len(cut) / max(1, len(whole))
            diff = abs(got - want)
            if score is None or diff < score:
                best, score = cut, diff
        # ⚠️ Соразмерность обязана быть близкой. Иначе это не заголовок,
        # а покрашенная первая ФРАЗА прозы — резать её нельзя, на этом
        # проект уже обжигался (точка уезжала в начало следующей строки).
        if best is None or score > 0.25:
            skipped += 1
            continue
        # ⚠️ ЧИСЛО ДЫРОК ОБЯЗАНО СОВПАСТЬ. Первый прогон дал «Progress to Level
        # {n}: {n}%» -> «Прогресс до уровня {n}:» — вторая дырка потерялась,
        # и `fillNumbers` подставил бы числа не туда. Это не заголовок,
        # а обрезок: резка пришлась не на границу.
        if len(HOLES.findall(head_src)) != len(HOLES.findall(best)):
            skipped += 1
            continue
        # ⚠️ ЗАГОЛОВОК КОРОТКИЙ. Без этого под признак попадала проза,
        # разрезанная переносом: «Pet Items can boost pets in many» ->
        # «Предметы питомцев» — соразмерность совпала, а смысл потерян.
        # Настоящий заголовок либо с двоеточием («Held Item: X»), либо
        # в несколько слов («Gold's Power»).
        if ":" not in head_src and len(head_src.split()) > 4:
            skipped += 1
            continue
        # ⚠️ Подпись, которая где-то в корпусе идёт СО ЗНАЧЕНИЕМ (см. `risky`
        # выше): заголовком не берём, иначе у того абзаца значение оторвётся.
        if head_src in risky:
            dropped_risky += 1
            continue
        # обрезок известного перевода — не заголовок (см. выше про Mob Types)
        if is_cut_off(head_src, best):
            dropped_cut += 1
            continue
        # ⚠️ ПОТЕРЯННАЯ ЗАПЯТАЯ — верный признак обрезка, и он не требует,
        # чтобы перевод строки был известен. У «Mob Types: ⚓ Aquatic, ☮ Animal»
        # вырезалось «Типы мобов: ⚓ водный» — перечисление оборвано на первом
        # элементе. Таких записей набралось СЕМЬ, вплоть до пустой «Типы мобов:»,
        # и предыдущий фильтр ловил лишь две: у остальных построчного перевода
        # нет вовсе. Заголовок с запятой внутри бывает, но потерять её при резке
        # он не может — значит потеря и есть признак.
        if "," in head_src and "," not in best:
            dropped_cut += 1
            continue
        if head_src in pairs and pairs[head_src] != best:
            continue  # разные переводы одной строки — не выдумываем, пропускаем
        pairs[head_src] = best

    print(f"извлечено заголовков: {len(pairs)}")
    print(f"  пропущено (не соразмерны — проза): {skipped}")
    print(f"  пропущено (подпись со значением): {dropped_risky}")
    print(f"  пропущено (обрезок известного перевода): {dropped_cut}")

    # Уже закрытые построчно не дублируем: словарь должен закрывать ТО, ЧЕГО НЕТ.
    # ⚠️ СЕБЯ из опроса исключаем. Иначе на ВТОРОМ прогоне генератор находит
    # в 41-headers.json свои же прошлые записи, объявляет «новых нет» и пишет
    # пустой словарь: 1385 -> 0, без единой жалобы. Так и случилось 31.07,
    # спас файл из собранного jar. Та же грабля была у split_sb_stats.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import status
    dic = status.Dictionaries(without={OUT.name})

    # ⚠️ БЕРЁМ И ТО, ЧТО ПЕРЕВЕДЕНО ИНАЧЕ, а не только новое.
    #
    # `Paragraphs.header` режет абзац, только если вырезанный заголовок
    # СОВПАДАЕТ с построчным переводом первой строки. Разошлись на одно
    # слово — резка отменяется, и заголовок слипается с описанием:
    #     построчно: «Бонус комплекта: Witherborn ({n}/{n})»
    #     в абзаце:  «Бонус полного комплекта: Witherborn ({n}/{n})»
    # Замер по корпусу: таких расхождений 514, и каждое — слипшийся
    # заголовок на экране. Пока условием было «перевода нет», генератор
    # их не трогал: перевод-то есть, просто другой.
    #
    # Побеждает наша запись: priority 24 сильнее, чем у ручных словарей
    # (20-ui = 30, 40-lore = 25), потому что у `exact` выигрывает пакет
    # с МЕНЬШИМ priority. Против корпуса (21) и очереди (10) не пойдём —
    # там перевод куплен, и спорить с ним незачем.
    fresh, fixed = {}, 0
    for src, ru in pairs.items():
        got = status.lookup(src, dic)
        if got is None:
            fresh[src] = ru
            continue
        known = got[0] if isinstance(got, tuple) else got
        if plain(known) != plain(ru):
            fresh[src] = ru
            fixed += 1
    print(f"  из них НОВЫХ (перевода не было): {len(fresh) - fixed}")
    print(f"  переведено ИНАЧЕ, чем в абзаце:  {fixed}  (из-за них резка не срабатывала)")
    print()
    for src, ru in list(fresh.items())[:args.show]:
        print(f"   {src[:52]}")
        print(f"      -> {ru[:52]}")
    if len(fresh) > args.show:
        print(f"   ... ещё {len(fresh) - args.show}")

    if not args.apply:
        print()
        print("СУХОЙ ПРОГОН. Записать: --apply")
        return 0

    pack = {
        "id": "headers",
        "priority": 24,
        # ⚠️ Тождественные записи здесь ОСОЗНАННЫ, и без этого поля мод честно
        # ругался на 1229 штук сразу. Имена зачарований мы не переводим —
        # значит «перевод» заголовка равен оригиналу. Запись всё равно нужна:
        # `Paragraphs.header` режет абзац, только если lookup первой строки
        # вернул непустое. Нет записи — нет резки, заголовок слипается.
        "allowIdentity": True,
        "_comment": "Заголовки абзацев ПОСТРОЧНО. Собран tools/gen_headers.py —"
                    " правь СКРИПТ, а не этот файл. Нужен не ради перевода"
                    " (он уже куплен внутри абзаца), а чтобы мод отрезал"
                    " заголовок своей строкой: Paragraphs.header сверяет"
                    " вырезанное с переводом ПЕРВОЙ СТРОКИ, и без такой записи"
                    " резка отменяется, а заголовок слипается с описанием.",
        "exact": dict(sorted(fresh.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(f"записано: {OUT.relative_to(ROOT)}  ({len(fresh)} записей)")
    index = json.loads((OUT.parent.parent / "index.json").read_text(encoding="utf-8"))
    if OUT.name not in (index.get("languages") or {}).get(LANG, []):
        print(f"⚠️ впиши {OUT.name} в index.json -> languages.{LANG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
