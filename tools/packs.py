"""
Чтение словарей мода — ОДНО на весь проект.

⚠️ Зачем. Словари читали 12 инструментов, каждый по-своему, и каждый мог
забыть одно из трёх:
  * ВЫКЛЮЧЕННЫЕ пакеты («default»: false) — их перевод игрок отключил, но он
    есть; считать такой словарь «отсутствующим» значит перевести строку второй
    раз в обход решения игрока. Так на дрели появилась «Огранка V»;
  * секцию `regex` — там живут зачарования и подписи характеристик, и фильтр,
    читавший только `exact`, их не видел;
  * секцию `glossary` целиком — из неё брали лишь «@»-записи.

Каждая забытая мелочь стоила отдельного разбирательства, а чинилась в разных
местах по очереди. Здесь это один раз и для всех.

Пользоваться так:
    from packs import load, terms, disabled_terms
    for pack in load():                     # все пакеты с пометкой enabled
        ...
    known = terms()                         # что переводится ПРЯМО СЕЙЧАС
    off = disabled_terms()                  # что выключено игроком
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"

# Термин из шаблона: «^Held Item:(\s*)$» -> «Held Item»
GROUP = re.compile(r"\((?:\?[:=!][^)]*|[^)]*)\)")
ESCAPED = re.compile(r"\\(.)")


@dataclass
class Pack:
    """Один словарь мода со всеми секциями и признаком «включён ли»."""

    path: Path
    ident: str
    enabled: bool
    priority: int = 0
    exact: dict = field(default_factory=dict)
    glossary: dict = field(default_factory=dict)
    paragraphs: dict = field(default_factory=dict)
    regex: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name


def load(include_disabled: bool = True) -> list[Pack]:
    """Все словари. ⚠️ Ищем РЕКУРСИВНО: они разложены по папкам языков."""
    out: list[Pack] = []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        enabled = raw.get("default") is not False
        if not enabled and not include_disabled:
            continue
        out.append(Pack(
            path=path,
            ident=str(raw.get("id") or path.stem),
            enabled=enabled,
            priority=int(raw.get("priority") or 0),
            exact=raw.get("exact") or {},
            glossary=raw.get("glossary") or {},
            paragraphs=raw.get("paragraphs") or {},
            regex=raw.get("regex") or [],
        ))
    return out


def term_of_rule(pattern: str) -> str | None:
    """
    Термин из шаблона правила: «^Fishing Wisdom:(\\s*)$» -> «Fishing Wisdom».

    Без этого половина характеристик считалась именами собственными: подписи
    и зачарования живут ИМЕННО в regex, а читали только exact и glossary.
    """
    text = pattern[1:] if pattern.startswith("^") else pattern
    text = GROUP.sub("", text)
    text = text.rstrip("$").strip()
    text = ESCAPED.sub(r"\1", text)
    text = text.strip(" :,.")
    return text if text and re.fullmatch(r"[A-Za-z][A-Za-z' \-]*", text) else None


def terms(enabled_only: bool = True) -> set[str]:
    """
    Всё, что словари переводят: exact, paragraphs, glossary И шаблоны.

    ⚠️ По умолчанию только ВКЛЮЧЁННЫЕ: «выключено» — это решение не переводить,
    и путать его с «перевода нет» дорого в обе стороны.
    """
    out: set[str] = set()
    for pack in load():
        if enabled_only and not pack.enabled:
            continue
        out |= set(pack.exact) | set(pack.paragraphs) | set(pack.glossary)
        for rule in pack.regex:
            term = term_of_rule(str(rule.get("p", "")))
            if term:
                out.add(term)
    return out


def disabled_terms() -> set[str]:
    """Термины из ВЫКЛЮЧЕННЫХ словарей: игрок решил их не переводить."""
    out: set[str] = set()
    for pack in load():
        if pack.enabled:
            continue
        out |= set(pack.exact) | set(pack.glossary)
        for rule in pack.regex:
            term = term_of_rule(str(rule.get("p", "")))
            if term:
                out.add(term)
    return out


def disabled_rules() -> list:
    """Скомпилированные шаблоны выключенных словарей — чем закрыта строка."""
    out = []
    for pack in load():
        if pack.enabled:
            continue
        for rule in pack.regex:
            try:
                out.append(re.compile(str(rule.get("p", ""))))
            except re.error:
                continue
    return out


def main() -> int:
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    packs = load()
    on = [p for p in packs if p.enabled]
    off = [p for p in packs if not p.enabled]
    print(f"словарей: {len(packs)}  включено: {len(on)}  выключено: {len(off)}")
    for pack in off:
        print(f"  ВЫКЛЮЧЕН {pack.name} (id {pack.ident}): "
              f"exact {len(pack.exact)}, glossary {len(pack.glossary)}, "
              f"regex {len(pack.regex)}")
    print(f"терминов переводится сейчас: {len(terms())}")
    print(f"терминов выключено игроком:  {len(disabled_terms())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
