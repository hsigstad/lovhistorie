"""Scoring primitives for the reconstruction eval (see docs/evaluation.md).

INTENT: fixed, documented normalization + similarity + provision splitting so the
    eval score is reproducible and can't be inflated by quietly loosening the
    comparison.
REASONING: OCR text is never byte-identical to clean text, so compare on a
    normalized form with a char-similarity ratio; split provisions in the given
    order so in-text cross-references (`jf. § 3`) and running-header noise don't
    corrupt the units being scored.
ASSUMES: `order` (the authoritative provision list) is supplied by the caller,
    normally from the current NLOD text.
"""
from __future__ import annotations

import difflib
import re

_MON = r"(?:jan|feb|mars|apr|mai|juni|juli|aug|sep|sept|okt|nov|des)"


def strip_running_headers(text):
    """Drop OCR page numbers / running headers interleaved into the body."""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if re.fullmatch(r"\d{1,4}", s):
            continue
        if re.fullmatch(rf"{_MON}\.?\s+(?:Lov\s+)?[Nn]r\.?\s*\d+", s):
            continue
        if re.fullmatch(rf"\d+\s+{_MON}\.?\s+[Nn]r\.?\s*\d+", s):
            continue
        out.append(ln)
    return "\n".join(out)


def strip_annotation(t):
    """Drop the trailing amendment annotation the current NLOD text appends
    ("Endret/Tilfoyd/Opphevet/Endres ved lov ...") and end-of-law tails, so a
    provision is scored on its TEXT, not its provenance note."""
    t = re.split(r"\b(?:Endret|Tilf[oø]yd|Opphevet|Endres)\s+ved\b", t)[0]
    t = re.split(r"Denne lov trer i kraft|\bLov nr\.\s*\d+\b", t)[0]
    return t


def normalize(s):
    """Canonical form for similarity: annotation-stripped, lowercase, Norwegian
    alphanumerics only, whitespace collapsed. (Fixed — do not loosen.)"""
    s = strip_annotation(s).lower().replace("§", " ")
    return " ".join(re.sub(r"[^a-z0-9æøå]+", " ", s).split())


def similarity(a, b):
    """Character-level similarity in [0, 1] of two provision texts (normalized).

    autojunk=False is REQUIRED, not a loosening: difflib's default autojunk=True is
    a speed heuristic that treats any character occurring >1% of the time in a string
    over 200 chars as "junk" and skips it — for provision-length Norwegian prose that
    silently collapses the ratio toward 0 for any non-byte-identical text (a genuinely
    ~98%-identical §1-1 scored 0.011 with autojunk vs 0.768 without). It corrupts the
    measurement rather than tightening it; short (<200 char) provisions are unaffected
    either way. Sign-off: Henrik, 2026-08-10. Normalization above is still fixed."""
    a, b = normalize(a), normalize(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _heading_pat(num):
    core = num.lstrip("§")
    if core[-1:].isalpha():
        return r"§\s*" + core[:-1] + r"\s*" + core[-1] + r"\b"
    return r"§\s*" + core + r"(?![0-9a-z])"


def provisions_ordered(text, order):
    """{paragraf_id: text} by finding each heading in `order` sequentially, so a
    cross-reference to an earlier § inside a body is not mistaken for a heading.
    `order` is the authoritative provision list (e.g. from the current text)."""
    out, pos = {}, 0
    for i, num in enumerate(order):
        m = re.search(_heading_pat(num), text[pos:])
        if not m:
            out[num] = ""
            continue
        start = pos + m.end()
        end = len(text)
        if i + 1 < len(order):
            m2 = re.search(_heading_pat(order[i + 1]), text[start:])
            if m2:
                end = start + m2.start()
        out[num] = strip_annotation(text[start:end])
        pos = start
    return out
