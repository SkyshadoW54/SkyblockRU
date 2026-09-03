"""ВЫКЛЮЧЕННЫЙ словарь не смеет вытеснять записи из ВКЛЮЧЁННОГО.

⚠️ БЕДА ТИХАЯ И ДОРОГАЯ. Генераторы не кладут запись, если ключ уже лежит
точной записью в ДРУГОМ словаре: две записи на одну строку — это спор,
который решается номером файла, а не качеством. Правило верное, но
«другой словарь» бывает ВЫКЛЮЧЕННЫМ — а он не работает у игрока без режима,
и перевод пропадает.

Замер 28.08: после того как в режимный 86-full-paragraphs добавили секцию
`exact`, из обычного 96-paragraphs молча выпали 1242 записи — все короче
порога, то есть нужные тем, у кого абзац приходит одной строкой.

⚠️ НИ ОДИН ПРЕЖНИЙ СТОРОЖ ЭТОГО НЕ ЛОВИЛ, и у каждого своя причина:
  check_shrink     эталон — последний jar, а его пересобрали уже с бедой;
  check_corpus_lag сверяет корпус со словарём, там всё сходилось;
  check_mode_wins  смотрит, ЧЕЙ перевод победил, а запись отсутствовала.
Нашла её разовая сверка с облаком перед выкладкой.

    python tools/check_disabled_wins.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PACKS = ROOT / "src" / "main" / "resources" / "assets" / "skyblockru" / "packs"


def load() -> list[tuple[Path, dict]]:
    out = []
    for path in sorted(PACKS.rglob("*.json")):
        if path.name == "index.json":
            continue
        try:
            out.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def disabled(pack: dict) -> bool:
    """Словарь выключен по умолчанию — значит у игрока без режима его НЕТ."""
    return bool(pack.get("group")) or pack.get("default") is False


def main() -> int:
    packs = load()
    on = [(p, d) for p, d in packs if not disabled(d)]
    off = [(p, d) for p, d in packs if disabled(d)]
    print(f"включённых словарей: {len(on)}, выключенных: {len(off)}")

    # ключи выключенных
    off_keys: dict[str, str] = {}
    for path, d in off:
        for k, v in (d.get("exact") or {}).items():
            if v:
                off_keys.setdefault(k, path.name)

    # ⚠️ СПРАШИВАЕМ ДВИЖОК, а не форму данных. Первый вариант признака дал
    # 8 находок, и ВСЕ ОКАЗАЛИСЬ ЛОЖНЫМИ: ключ уступлен выключенному, но без
    # режима закрыт либо картой абзацев, либо точной записью ДРУГОГО
    # включённого словаря. Отчёт, показывающий наши решения бедой, приучает
    # в него не смотреть — записанное правило проекта.
    import status
    plain = status.Dictionaries()          # как у игрока БЕЗ режима
    problems = 0
    for path, d in on:
        pars = d.get("paragraphs") or {}
        ex = d.get("exact") or {}
        if not pars:
            continue
        lost = []
        for k in pars:
            if k not in off_keys or k in ex or len(k) > 96:
                continue
            # ⚠️ «ЗАКРЫТ АБЗАЦЕМ» НЕ ОПРАВДАНИЕ, и первая версия признака
            # на этом ослепла: подсадка трёх пропаж прошла как здоровая.
            # Дубль в `exact` нужен ровно для случая, когда абзац НЕ собрался —
            # у игрока шире окно, и строка пришла ЦЕЛИКОМ. Карта абзацев тут
            # не спасает по построению.
            got = status.lookup(k, plain, origin="item_lore")
            if got and got[0]:
                continue                    # закрыт другим ВКЛЮЧЁННЫМ словарём
            lost.append(k)
        if lost:
            problems += len(lost)
            print(f"\n{path.name}: {len(lost)} записей вытеснены выключенным словарём")
            for k in lost[:5]:
                print(f"   ключ: {k[:66]}")
                print(f"     уступлено -> {off_keys[k]}")

    print()
    if problems:
        print(f"СЛОМАНО: {problems} — выключенный словарь вытеснил записи "
              f"из включённого; у игрока без режима перевод ПРОПАДЁТ")
        return 1
    print("СЛОМАНО: 0 — выключенные словари ничего не вытесняют")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
