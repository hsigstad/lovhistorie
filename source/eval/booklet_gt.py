"""Booklet-derived point-in-time ground truth — a PUBLIC-DOMAIN alternative to the
encumbered Lovdata-Pro oracle (ground_truth.py).

INTENT: a standalone-law booklet (særtrykk) at NB is a dated snapshot ("Ajourført med
    endringer, senest …"). OCR + parse it into {paragraf_id: text} — exactly the shape
    the harness scores a Lovdata-Pro version in — so `reconstruct(datokode, date)` can be
    validated point-in-time against it. Unlike Lovdata-Pro, this source is public-domain
    and may be redistributed, so it can become a publishable validation set.
REASONING: reuse the enactment OCR path (build_enactment._resilient_pages +
    parse_provisions with the booklet heading repair) so booklet text is parsed the same
    way the bases are; cache the parsed result so the harness runs offline after the first
    OCR pass.
HELD-OUT DISCIPLINE: a booklet used as a BASE for a law (build_enactment.BOOKLETS) must
    NOT also validate that law — do not register the same (law, booklet) in both roles.
    aksjeloven's base is the 1997 gazette, so its 2001 booklet is a legitimate held-out
    validator; kjøpsloven/rettsgebyr booklets ARE their bases and so are omitted here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _is_failed_extraction(text: str) -> bool:
    """True when a booklet provision parsed to garbage rather than its text — the dense
    særtrykk layout interleaves 'Jfr. §…' footnotes with inline headings, so a provision
    occasionally aligns to a footnote fragment ("," or a bare cross-reference list) instead
    of its body. We DROP those (flag-don't-fabricate: a GT entry we couldn't extract is
    absent, never a false answer) rather than let them score as spurious 0.0 mismatches.
    Conservative — only unambiguous garbage: <8 real characters, or a reference-dominated
    fragment (opens with punctuation/§/digit, carries 'Jfr'/multiple §-refs, little prose).
    Verified on aksjeloven-2001: catches 8/11 true failures with ZERO real provisions lost."""
    s = text.strip()
    if len(re.sub(r"[\s,.;:§)\d()-]", "", s)) < 8:
        return True
    head, prose = s[:45], re.findall(r"[a-zæøå]{4,}", s.lower())
    return bool(re.match(r"^[,.;:)]|^§|^\d", s)) and ("Jfr" in head or head.count("§") >= 2) \
        and len(prose) < 6

GT_ROOT = Path(__file__).resolve().parents[2] / "data" / "booklet_gt"

# datokode -> [snapshot spec]. `date` is the booklet's ajourført version boundary (the
# point-in-time this snapshot represents). URN/page/span/title_needle locate the law body
# in the digitised booklet (same fields as build_enactment.BOOKLETS).
BOOKLETS = {
    "1997-06-13-44": [  # aksjeloven — Cappelen 2001 særtrykk, ajourført 21.12.2000 → 2001-01-01
        {"date": "2001-01-01", "urn": "URN:NBN:no-nb_digibok_2023030748042",
         "page": 13, "span": 100, "title_needle": "Lov om aksjeselskape"},
    ],
}


def _ocr_parse(spec: dict) -> dict:
    """OCR the booklet body and parse it into {para: text} (booklet heading repair on)."""
    from source.scrape import build_enactment as be

    txt = be._resilient_pages(spec["urn"], spec["page"], spec["span"])
    m = re.search(re.escape(spec["title_needle"]), txt)
    body = txt[m.start():] if m else txt
    provs = be.parse_provisions(body, repair_headings=True)
    return {p: t for p, t in provs.items() if not _is_failed_extraction(t)}


def load_version(datokode: str, date: str, root: Path = GT_ROOT, refresh: bool = False):
    """{paragraf_id: text} for one booklet snapshot, or None if unregistered. Cached to
    data/booklet_gt/<datokode>/<date>.json after the first OCR pass (refresh=True re-OCRs)."""
    spec = next((s for s in BOOKLETS.get(datokode, []) if s["date"] == date), None)
    if spec is None:
        return None
    cache = root / datokode / f"{date}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    provs = _ocr_parse(spec)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(provs, ensure_ascii=False, indent=1), encoding="utf-8")
    return provs


def versions_for(datokode: str, root: Path = GT_ROOT):
    """[(date, {para: text})] for a law's registered booklet snapshots."""
    out = []
    for spec in BOOKLETS.get(datokode, []):
        provs = load_version(datokode, spec["date"], root)
        if provs:
            out.append((spec["date"], provs))
    return sorted(out)
