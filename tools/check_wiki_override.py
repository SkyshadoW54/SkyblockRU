"""
Какой файл справки мод возьмёт С ДИСКА вместо встроенного.

Беда, ради которой написано (05.08). `Wiki.open` получал путь ЗАПРОШЕННОГО
файла, а на диске искал по ЯЗЫКУ:

    read(".../wiki/ru_ru.json",          TERMS)    -> с диска wiki/ru_ru.json
    read(".../wiki/enchants_ru_ru.json", ENCHANTS) -> с диска wiki/ru_ru.json  <- ТОТ ЖЕ

То есть на любой запрос отдавался один и тот же файл. Пока справку не
выкладывали в облако, на диске её не было и подмениться было нечему. Как
только туда уехала правка справки ТЕРМИНОВ, она встала на место справки
ЗАЧАРОВАНИЙ у всех разом, без нового jar: в ENCHANTS легли 73 термина вместо
173 зачарований. А у термина римского уровня не бывает никогда, поэтому
панель по Alt не находила НИЧЕГО и приглашение не показывалось вовсе.

⚠️ Признак железный и от наполнения справки не зависит: РАЗНЫМ встроенным
файлам обязаны отвечать РАЗНЫЕ файлы на диске, и имя должно совпадать
с именем встроенного. Иначе облако молча подменяет одну справку другой.

⚠️ Логика берётся из НАСТОЯЩЕЙ Java (`Wiki.userFileName`), а не переписывается
на Python: копия признака в этом проекте расходилась молча уже трижды.

⚠️ Проверяется И НА УМЕНИЕ НАХОДИТЬ: тем же кодом прогоняется старое
поведение («всегда <язык>.json»), и сторож обязан на нём покраснеть. Без этого
«молчит» и «работает» неотличимы.

Запуск:
  python tools/check_wiki_override.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

WIKI_DIR = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "wiki"
LANG = "ru_ru"

RUNNER = """
import ru.skyblockru.core.Wiki;

public class WikiOverrideRun {
    public static void main(String[] args) {
        for (String builtin : args) {
            System.out.println(builtin + "\\u0001" + Wiki.userFileName(builtin));
        }
    }
}
"""

# ⚠️ Подсадка старой поломки: ровно то, что стояло в Wiki.open до 05.08.
# Живёт в проверке, а не в моде, — иначе это была бы копия признака.
BROKEN = """
public class WikiBrokenRun {
    public static void main(String[] args) {
        for (String builtin : args) {
            System.out.println(builtin + "\\u0001" + "ru_ru.json");
        }
    }
}
"""


def builtin_paths() -> list[str]:
    """Пути встроенных файлов справки — ровно так, как их строит Wiki.load."""
    return [
        f"/assets/skyblockru/wiki/{LANG}.json",
        f"/assets/skyblockru/wiki/enchants_{LANG}.json",
    ]


def run(java: str, cp: list[str], work: Path, source: str, cls: str,
        paths: list[str]) -> dict[str, str]:
    src = work / (cls + ".java")
    src.write_text(source, encoding="utf-8")
    javac = java.replace("java.exe", "javac.exe")
    build = subprocess.run(
        [javac, "-encoding", "UTF-8", "-cp", ";".join(cp), "-d", str(work), str(src)],
        capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stderr.strip()[:2000])
        raise SystemExit("не скомпилировалось")
    out = subprocess.run(
        [java, "-Dstdout.encoding=UTF-8", "-cp", ";".join(cp + [str(work)]), cls, *paths],
        capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        print(out.stderr.strip()[:2000])
        raise SystemExit("не запустилось")
    got: dict[str, str] = {}
    for row in out.stdout.splitlines():
        if "" in row:
            builtin, name = row.split("", 1)
            got[builtin] = name
    return got


def check(got: dict[str, str]) -> list[str]:
    """Что не так с раскладкой «встроенный -> файл на диске»."""
    bad: list[str] = []
    seen: dict[str, str] = {}
    for builtin, name in got.items():
        want = builtin.rsplit("/", 1)[-1]
        if name != want:
            bad.append(f"{builtin} -> с диска возьмёт «{name}», а надо «{want}»")
        if name in seen:
            bad.append(f"«{name}» отвечает СРАЗУ ДВУМ: {seen[name]} и {builtin}")
        seen[name] = builtin
    return bad


def main() -> int:
    from check_click_events import classpath, find_java

    java = find_java("java")
    if java is None:
        print("не нашёл java — пропускаю")
        return 0
    cp = classpath()
    if cp is None:
        return 0

    paths = builtin_paths()
    missing = [p for p in paths if not (WIKI_DIR / p.rsplit("/", 1)[-1]).is_file()]
    if missing:
        print("нет файлов справки: " + ", ".join(missing))
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        got = run(java, cp, work, RUNNER, "WikiOverrideRun", paths)
        bad = check(got)

        # проверка НА УМЕНИЕ НАХОДИТЬ
        broken = run(java, cp, work, BROKEN, "WikiBrokenRun", paths)
        caught = check(broken)

    print("=== ФАЙЛ СПРАВКИ С ДИСКА ===")
    for builtin in paths:
        print(f"  {builtin}")
        print(f"     -> wiki/{got.get(builtin, '?')}")

    if not caught:
        print("\nСЛОМАНО: проверка не поймала подсаженную поломку — она слепа")
        return 1
    print(f"\nподсадка старого поведения поймана: {len(caught)} замечаний")

    if bad:
        print("\nСЛОМАНО:")
        for row in bad:
            print("  " + row)
        return 1
    print("раскладка верна: каждому встроенному файлу отвечает свой файл на диске")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
