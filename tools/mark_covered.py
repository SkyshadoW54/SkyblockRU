"""
Помечает «переводить нечего» абзацы, все строки которых закрыты ПРАВИЛАМИ.

Зачем. Есть абзацы-комбинации: «Categories: - Liquid: Water - Island: Bayou».
Сочетаний жидкости, острова и особых требований — десятки, и каждый заход
в справочник существ приносит новые. Целиком такой абзац переводить не надо:
каждая его строка закрыта построчным правилом («- Island: (.+)» -> «- Остров:
$1»), и на экране всё по-русски. А очередь этого не знает и просит деньги
за каждое новое сочетание.

⚠️ Фильтр СПРАШИВАЕТ правила, а не верит на слово. В проекте уже была беда,
когда фильтр отбрасывал строки «потому что их закроет X», не проверяя X:
72 строки не переводились вовсе, и никто об этом не узнал.

⚠️ Сверять надо через `covered_by_rule`: в корпусе строка лежит ОБОБЩЁННОЙ
(«Skill {n}.»), а правило писано под живую («Skill ([\\d,]+)»), и прямое
сравнение не совпадает НИ РАЗУ.

Запуск:
    python tools/mark_covered.py            показать, что будет помечено
    python tools/mark_covered.py --yes      пометить
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Пометить абзацы, закрытые правилами")
    parser.add_argument("--yes", action="store_true", help="применить")
    args = parser.parse_args()

    from make_queue import already_translated, covered_by_rule

    known, guarded, covered = already_translated()
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    paragraphs = data["paragraphs"]

    found = []
    for para in paragraphs:
        if para.get("ru") or para.get("nothing"):
            continue
        lines = para.get("lines") or []
        if not lines:
            continue
        # ⚠️ Закрытым считаем абзац, у которого КАЖДАЯ строка либо лежит
        # точной записью, либо ловится правилом. Хватит одной незакрытой —
        # и на экране выйдет смесь языков, а она хуже английского целиком.
        if all(line.strip() in known or covered_by_rule(line.strip(), covered)
               for line in lines if line.strip()):
            found.append(para)

    print(f"абзацев без перевода: "
          f"{sum(1 for p in paragraphs if not p.get('ru') and not p.get('nothing'))}")
    print(f"закрыты построчными правилами: {len(found)}\n")
    for para in found[:12]:
        print(f"  [{para.get('count', 0)}x] {para['text'][:90]}")
    if len(found) > 12:
        print(f"  ... ещё {len(found) - 12}")

    if not found:
        return 0
    if not args.yes:
        print("\nэто СУХОЙ ПРОГОН. Пометить: --yes")
        return 0

    for para in found:
        para["nothing"] = True
        para["why"] = "закрыто построчными правилами"
    CORPUS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nпомечено: {len(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
