# -*- coding: ascii -*-
"""How much colour can be returned MECHANICALLY, without paying for anything.

Idea being measured: when a translated paragraph is laid back into the tooltip,
look for pieces of the ORIGINAL that survived verbatim in the translation
(numbers, placeholders, English names) and paint them with their former colour.
TextTranslator.carryLegacyCodes already does exactly this for single lines:
it takes a coloured run of the original and looks for it in the translation
with indexOf().

This script measures the CEILING: how much of a paragraph could be painted
that way. It does not know the real colours (the dump strips them), so it
answers "how much text is findable", not "how much text is coloured".

Usage:  python tools/measure_color.py [data/work/paragraphs.json]
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "work" / "paragraphs.json"

# Minimal piece length for a latin run, as asked. The mod uses 2
# (TextTranslator.MIN_RUN_LENGTH); both are reported.
MIN_PIECE = 3

# NOTE: this file had its OWN number pattern with a trailing '%?', so
# '+20%' became '{n}' here but '{n}%' everywhere else. A diverged copy
# of the paragraph key is invisible until something silently stops
# matching, so the shared one from pkey is used instead.
from pkey import NUMBER as NUM  # noqa: E402
HOLE = re.compile(r"\{[ns]\}")
# Maximal run of latin words, apostrophes and hyphens inside.
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'\-]*(?:[ ]+[A-Za-z][A-Za-z'\-]*)*")
CAP = re.compile(r"[A-Z][A-Za-z'\-]+")


def multiset(items):
    out = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def covered(need, have):
    """All of `need` present in `have`, counting repeats."""
    a, b = multiset(need), multiset(have)
    return all(b.get(k, 0) >= v for k, v in a.items())


def sentence_initial(text, start):
    """True if the word at `start` opens a sentence (so its capital means
    nothing) -- 'Grants' is not a name, 'Kuudra' is."""
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    if i < 0:
        return True
    return text[i] in ".!?:\n"


def free(claimed, at, end):
    return all(not claimed[i] for i in range(at, end))


def claim(claimed, at, end):
    for i in range(at, end):
        claimed[i] = True


def find_free(ru, claimed, piece, frm=0):
    """First occurrence of `piece` in `ru` that overlaps nothing already
    painted. Mirrors result.indexOf() plus the 'don't paint twice' rule."""
    at = ru.find(piece, frm)
    while at >= 0:
        if free(claimed, at, at + len(piece)):
            return at
        at = ru.find(piece, at + 1)
    return -1


def paint(text, ru, min_piece=MIN_PIECE):
    """Greedily mark every char of `ru` that can be painted from `text`.

    Returns (painted_chars, list_of_pieces).
    Order matters: longest pieces first, so 'Chocolate Factory' wins over
    'Chocolate' -- the same reason the engine keeps long terms ahead of short.
    """
    cands = []
    for m in HOLE.finditer(text):
        cands.append(m.group(0))
    for m in NUM.finditer(text):
        cands.append(m.group(0))
    for m in LATIN_RUN.finditer(text):
        words = m.group(0).split(" ")
        # every contiguous group of words, longest first
        for size in range(len(words), 0, -1):
            for i in range(0, len(words) - size + 1):
                piece = " ".join(words[i:i + size])
                if len(piece) >= min_piece:
                    cands.append(piece)

    cands.sort(key=len, reverse=True)
    claimed = [False] * len(ru)
    used = []
    seen_at = {}
    from_hole = 0
    for piece in cands:
        if len(piece) < min_piece and not NUM.fullmatch(piece) and not HOLE.fullmatch(piece):
            continue
        frm = seen_at.get(piece, 0)
        at = find_free(ru, claimed, piece, frm)
        if at < 0:
            continue
        claim(claimed, at, at + len(piece))
        seen_at[piece] = at + len(piece)
        used.append(piece)
        if HOLE.fullmatch(piece) or NUM.fullmatch(piece):
            from_hole += len(piece)
    return sum(1 for c in claimed if c), used, from_hole


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else CORPUS
    data = json.loads(path.read_text(encoding="utf-8"))["paragraphs"]
    done = [p for p in data if p.get("ru") and not p.get("nothing")]

    print("corpus: %s" % path)
    print("paragraphs: %d total, %d translated" % (len(data), len(done)))
    print("")

    # ---- 1. numbers -------------------------------------------------------
    lit_has = lit_all = 0
    hole_has = hole_all = 0
    both_has = both_all = 0
    lit_has_w = lit_all_w = 0
    for p in done:
        t, ru, w = p["text"], p["ru"], p.get("count", 1)
        tn, rn = NUM.findall(t), NUM.findall(ru)
        th, rh = HOLE.findall(t), HOLE.findall(ru)
        if tn:
            lit_has += 1
            lit_has_w += w
            if covered(tn, rn):
                lit_all += 1
                lit_all_w += w
        if th:
            hole_has += 1
            if covered(th, rh):
                hole_all += 1
        if tn or th:
            both_has += 1
            if covered(tn, rn) and covered(th, rh):
                both_all += 1

    def pct(a, b):
        return 100.0 * a / b if b else 0.0

    print("1) NUMBERS")
    print("   literal digits (\\d+%%?) in original : %d paragraphs (%.1f%% of translated)"
          % (lit_has, pct(lit_has, len(done))))
    print("   ... all of them verbatim in ru      : %d (%.1f%% of those)"
          % (lit_all, pct(lit_all, lit_has)))
    print("   ... same, weighted by screen count  : %.1f%%" % pct(lit_all_w, lit_has_w))
    print("   placeholders {n}/{s} in original    : %d paragraphs (%.1f%%)"
          % (hole_has, pct(hole_has, len(done))))
    print("   ... all of them verbatim in ru      : %d (%.1f%% of those)"
          % (hole_all, pct(hole_all, hole_has)))
    print("   any number channel (digits or hole) : %d paragraphs (%.1f%%)"
          % (both_has, pct(both_has, len(done))))
    print("   ... fully preserved                 : %d (%.1f%%)"
          % (both_all, pct(both_all, both_has)))
    print("")

    # ---- 2. english capitalised words ------------------------------------
    cap_has = cap_all = cap_any = 0
    name_has = name_all = name_any = 0
    tok_total = tok_kept = 0
    for p in done:
        t, ru = p["text"], p["ru"]
        caps, names = [], []
        for m in CAP.finditer(t):
            caps.append(m.group(0))
            if not sentence_initial(t, m.start()):
                names.append(m.group(0))
        if caps:
            cap_has += 1
            kept = [c for c in caps if c in ru]
            tok_total += len(caps)
            tok_kept += len(kept)
            if covered(caps, [m.group(0) for m in CAP.finditer(ru)]):
                cap_all += 1
            if kept:
                cap_any += 1
        if names:
            name_has += 1
            kept = [c for c in names if c in ru]
            if len(kept) == len(names):
                name_all += 1
            if kept:
                name_any += 1

    print("2) ENGLISH CAPITALISED WORDS")
    print("   any capitalised word                : %d paragraphs (%.1f%%)"
          % (cap_has, pct(cap_has, len(done))))
    print("   ... all of them survive verbatim    : %d (%.1f%%)" % (cap_all, pct(cap_all, cap_has)))
    print("   ... at least one survives           : %d (%.1f%%)" % (cap_any, pct(cap_any, cap_has)))
    print("   tokens: %d seen, %d survive (%.1f%%)" % (tok_total, tok_kept, pct(tok_kept, tok_total)))
    print("   NOT sentence-initial (real names)   : %d paragraphs (%.1f%%)"
          % (name_has, pct(name_has, len(done))))
    print("   ... all survive verbatim            : %d (%.1f%%)" % (name_all, pct(name_all, name_has)))
    print("   ... at least one survives           : %d (%.1f%%)" % (name_any, pct(name_any, name_has)))
    print("")

    # ---- 2b. holes keep their ORDER, not just their count ----------------
    # For colour it is not enough that {n} survived: fillNumbers puts real
    # numbers into holes BY ORDER, so hole #2 of the original must still be
    # hole #2 of the translation, or the number gets a stranger's colour.
    same_order = 0
    for p in done:
        th, rh = HOLE.findall(p["text"]), HOLE.findall(p["ru"])
        if th and th == rh:
            same_order += 1
    print("1b) hole ORDER identical (colour goes to the right number): %d of %d (%.1f%%)"
          % (same_order, hole_has, pct(same_order, hole_has)))
    print("")

    # ---- 3. share of characters paintable --------------------------------
    for min_piece in (3, 2):
        ratios = []
        tot_paint = tot_ru = tot_text = tot_hole = 0
        wsum = wpaint = 0
        zero = 0
        full = 0
        for p in done:
            painted, used, from_hole = paint(p["text"], p["ru"], min_piece)
            ru_len = len(p["ru"])
            if not ru_len:
                continue
            ratios.append(painted / ru_len)
            tot_paint += painted
            tot_ru += ru_len
            tot_text += len(p["text"])
            tot_hole += from_hole
            w = p.get("count", 1)
            wsum += ru_len * w
            wpaint += painted * w
            if painted == 0:
                zero += 1
            if painted >= ru_len:
                full += 1
        print("3) PAINTABLE CHARS (pieces >= %d chars)" % min_piece)
        print("   mean per-paragraph share            : %.1f%%"
              % (100.0 * sum(ratios) / len(ratios)))
        print("   overall chars painted / chars in ru : %d / %d = %.1f%%"
              % (tot_paint, tot_ru, pct(tot_paint, tot_ru)))
        print("   same against the ORIGINAL length    : %d / %d = %.1f%%"
              % (tot_paint, tot_text, pct(tot_paint, tot_text)))
        print("   same, weighted by screen count      : %.1f%%" % pct(wpaint, wsum))
        print("   of the painted chars: %.1f%% are holes {n}/{s}, %.1f%% english text"
              % (pct(tot_hole, tot_paint), pct(tot_paint - tot_hole, tot_paint)))
        print("   paragraphs with NOTHING paintable   : %d (%.1f%%)" % (zero, pct(zero, len(ratios))))
        print("   paragraphs fully paintable          : %d (%.1f%%)" % (full, pct(full, len(ratios))))
        print("")

    # ---- 3b. what kind of piece carries the colour ------------------------
    import statistics
    shares = []
    eng = only_hole = none = pieces = 0
    buckets = {"0%": 0, "0-10%": 0, "10-25%": 0, "25-50%": 0, "50%+": 0}
    for p in done:
        painted, used, _fh = paint(p["text"], p["ru"])
        share = painted / max(1, len(p["ru"]))
        shares.append(share)
        pieces += len(used)
        has_eng = any(not HOLE.fullmatch(u) for u in used)
        if has_eng:
            eng += 1
        elif used:
            only_hole += 1
        else:
            none += 1
        x = 100 * share
        key = ("0%" if x == 0 else "0-10%" if x < 10 else "10-25%" if x < 25
               else "25-50%" if x < 50 else "50%+")
        buckets[key] += 1
    print("3b) WHAT CARRIES THE COLOUR")
    print("   pieces found: %d total, %.2f per paragraph" % (pieces, pieces / len(done)))
    print("   at least one ENGLISH piece survives : %d (%.1f%%)" % (eng, pct(eng, len(done))))
    print("   only holes {n}/{s} paintable        : %d (%.1f%%)" % (only_hole, pct(only_hole, len(done))))
    print("   nothing paintable at all            : %d (%.1f%%)" % (none, pct(none, len(done))))
    print("   median share                        : %.1f%%" % (100 * statistics.median(shares)))
    print("   buckets: %s" % buckets)
    print("")

    # ---- 4. examples ------------------------------------------------------
    picked = []
    for p in done:
        painted, used, _hole = paint(p["text"], p["ru"])
        if not used:
            continue
        picked.append((p.get("count", 1), painted / max(1, len(p["ru"])), p, used))
    picked.sort(key=lambda x: -x[0])
    out = []
    for cnt, share, p, used in picked[:10]:
        out.append({
            "count": cnt,
            "share": round(100 * share, 1),
            "text": p["text"],
            "ru": p["ru"],
            "pieces": used,
        })
    dst = ROOT / "data" / "work" / "color_examples.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("4) 10 examples (by screen frequency) written to %s" % dst)


if __name__ == "__main__":
    main()
