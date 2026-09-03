# -*- coding: utf-8 -*-
"""
ИМЯ БЕЗ ИМПОРТА — сторож падает НЕ ПРИ ЗАПУСКЕ, а когда до него дойдут.

Беда, ради которой написано (24.08). В `check_sections.py` соседние функции
устроены так:

    def dictionaries():
        import status            # ленивый: status сам импортирует нас
        return status.Dictionaries()

    def vanilla_lang():
        return status.vanilla_lang()   # <- А ЗДЕСЬ ИМПОРТА НЕТ

Файл компилируется, импортируется, `--help` работает. Падает только в тот
миг, когда функцию позовут: `NameError: name 'status' is not defined`.
Вместе с ней падал `check_vanilla_names`, который её вызывает, — то есть
сторож не работал НЕИЗВЕСТНО СКОЛЬКО, а выглядел живым.

⚠️ `py_compile` такое не ловит по построению: имя разрешается в рантайме.
Внешний линтер (pyflakes/ruff) поймал бы, но тянуть зависимость в проект,
который держится на stdlib, ради одной проверки — дорого.

Признак УЗКИЙ намеренно: ищем только обращения вида `имя.что_то`, где `имя`
не импортировано ни на уровне модуля, ни внутри самой функции, и не является
ни параметром, ни присвоенной переменной, ни встроенным. Так проверка
отвечает ровно на тот вопрос, из-за которого писалась, и не шумит на
динамике, которой в этих скриптах хватает.

Запуск:  python tools/check_imports.py
"""
from __future__ import annotations

import ast
import builtins
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
BUILTIN = set(dir(builtins))

# Имена модулей самого проекта: только их и проверяем.
OURS = {path.stem for path in TOOLS.glob("*.py")}


def bound_names_of(node: ast.AST) -> set[str]:
    """Имена, связанные ОДНИМ узлом (без захода вглубь функций)."""
    out: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            out.add(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            out.add(alias.asname or alias.name)
    elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        out.add(node.id)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        out.add(node.name)
    elif isinstance(node, ast.ExceptHandler) and node.name:
        out.add(node.name)
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        out.update(node.names)
    return out


def bound_names(node: ast.AST) -> set[str]:
    """Всё, что这 узел связывает: импорты, присваивания, параметры, циклы."""
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                out.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(child, ast.ImportFrom):
            for alias in child.names:
                out.add(alias.asname or alias.name)
        elif isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            out.add(child.id)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(child.name)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            out.add(child.name)
        elif isinstance(child, ast.Global) or isinstance(child, ast.Nonlocal):
            out.update(child.names)
    return out


def params_of(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    a = fn.args
    got = {p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)}
    if a.vararg:
        got.add(a.vararg.arg)
    if a.kwarg:
        got.add(a.kwarg.arg)
    return got


def check(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError, UnicodeDecodeError):
        return []
    # Имена уровня модуля: импорты, глобальные переменные, функции, классы.
    module_level: set[str] = set()
    for node in tree.body:
        module_level |= bound_names(node) if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else {node.name}

    bad: list[tuple[int, str]] = []
    NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

    def shallow(node: ast.AST):
        """
        Узлы тела, БЕЗ захода во вложенные функции и лямбды.

        ⚠️ Без этого сторож давал полсотни ложных: `ast.walk` заходил внутрь
        `def one(match)` и `lambda m: m.group(1)`, где имя — ПАРАМЕТР,
        а знала о нём только сама вложенная функция.
        """
        for child in ast.iter_child_nodes(node):
            if isinstance(child, NESTED):
                continue
            yield child
            yield from shallow(child)

    def lambda_params(fn: ast.Lambda) -> set[str]:
        a = fn.args
        got = {p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)}
        if a.vararg:
            got.add(a.vararg.arg)
        if a.kwarg:
            got.add(a.kwarg.arg)
        return got

    def visit(fn, outer: set[str]) -> None:
        """Область видимости НАКАПЛИВАЕТСЯ: вложенная видит имена родителя."""
        if isinstance(fn, ast.Lambda):
            known = outer | lambda_params(fn)
        else:
            known = outer | params_of(fn) | {n for node in shallow(fn)
                                             for n in bound_names_of(node)}
        body = [fn.body] if isinstance(fn, ast.Lambda) else fn.body
        for stmt in body:
            for node in [stmt, *shallow(stmt)]:
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    name = node.value.id
                    # ⚠️ Смотрим ТОЛЬКО на имена наших модулей. Первая версия
                    # брала любое имя и дала полсотни ложных: `match.group`,
                    # `out.append`, `text.strip` — это переменные, и уследить
                    # за всеми способами их связать (walrus, comprehension,
                    # распаковка, `with as`) значит переписать pyflakes.
                    # А беда была про МОДУЛЬ: `status.vanilla_lang()` без
                    # `import status`. Признак и отвечает ровно на это.
                    if name in OURS and name not in known:
                        bad.append((node.lineno, f"{name}.{node.attr}"))
        # Вложенные — со знанием того, что видит родитель.
        for stmt in body:
            for node in ast.walk(stmt):
                if isinstance(node, NESTED):
                    visit(node, known)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parent_is_fn = any(node in ast.walk(other) and other is not node
                               for other in ast.walk(tree)
                               if isinstance(other, NESTED))
            if not parent_is_fn:
                visit(node, module_level | BUILTIN)
    return bad


def unprintable_prints() -> list[tuple[str, str]]:
    """Инструменты, которые УПАДУТ на собственной печати.

    ⚠️ Консоль Windows — cp1251, и `print` со значком «⚠️», стрелкой или
    иконкой Hypixel роняет скрипт с UnicodeEncodeError. Беда тихая и злая:
    вывод обрывается на середине, и это читается как поломка того, что
    инструмент проверял, а не его самого. За 26.08 так соврали ЧЕТЫРЕ
    инструмента подряд (`try_rule`, `export_pack`, `gen_full_paragraphs`,
    `gen_item_names`), причём `export_pack` падал ДО записи файла — словарь
    оставался несобранным, а команда выглядела отработавшей.

    ⚠️ У СТОРОЖА это хуже вдвое: строка со значком печатается только при
    НАХОДКЕ, значит он молчит, пока всё хорошо, и ломается ровно тогда,
    когда нужен. Так стоял `check_full_mode` — в круге сборки.

    Защита — одна строка (`sys.stdout.reconfigure` либо `io.TextIOWrapper`),
    и признак проверяет именно её наличие, а не привычку помнить.
    """
    guard = re.compile(r"sys\.stdout\s*=\s*io\.TextIOWrapper"
                       r"|sys\.stdout\.reconfigure\s*\(")
    found = []
    for path in sorted(TOOLS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if guard.search(text):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        risky = set()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"):
                continue
            # ⚠️ РАЗБИРАЕМ КОД, А НЕ ТЕКСТ. Значок пишут и прямо («⚠️»),
            # и escape-последовательностью («\\u26a0»): регулярка по
            # тексту второе не видит, а падает оно одинаково.
            for inner in ast.walk(node):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    for char in inner.value:
                        try:
                            char.encode("cp1251")
                        except UnicodeEncodeError:
                            risky.add(char)
        if risky:
            found.append((path.name, "".join(sorted(risky))))
    return found


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    found: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(TOOLS.glob("*.py")):
        hits = check(path)
        if hits:
            found[path.name] = hits
    total = sum(len(v) for v in found.values())
    print(f"проверено файлов: {len(list(TOOLS.glob('*.py')))}")

    crashers = unprintable_prints()
    if crashers:
        print(f"\n=== ПАДАЮТ НА СОБСТВЕННОЙ ПЕЧАТИ: {len(crashers)} ===")
        print("  Консоль Windows это cp1251: такой print роняет скрипт,")
        print("  вывод обрывается, и это читается как поломка ЧУЖОЙ работы.")
        print("  Лечится одной строкой:")
        print('      sys.stdout.reconfigure(encoding="utf-8", errors="replace")')
        for name, chars in crashers:
            print(f"      {name:32} {chars[:20]}")

    if not found and not crashers:
        print("СЛОМАНО: 0 — импорты на месте, печать не роняет инструменты")
        return 0
    if not found:
        return 1
    print(f"\n=== ⚠️ ИМЯ БЕЗ ИМПОРТА: {total} ===")
    print("  Такой код компилируется и падает NameError, когда до него дойдут.")
    for name, hits in found.items():
        print(f"  {name}")
        for line, what in hits[:6]:
            print(f"      строка {line}: {what}")
        if len(hits) > 6:
            print(f"      ... ещё {len(hits) - 6}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
