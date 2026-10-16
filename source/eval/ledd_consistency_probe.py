"""Experiment harness for the global-consistency ledd lever (see docs/notes/global_consistency_ledd.md).

INTENT: give a focused follow-up session a running start on the ONE untested ledd lever — using today's
    text as a GLOBAL consistency constraint to disambiguate where flagged sub-provision ops apply, scored
    on HELD-OUT PAST gold. This file already wires the two non-obvious pieces: (a) the replay ledd_fallback
    seam (monkeypatch `ledd_apply.make_fallback`) so you can swap in any location-resolution strategy, and
    (b) past-gold scoring per held-out date. It ships with the LOCAL baseline (align.target_ledd) that we
    MEASURED as insufficient (0% correct / 83% clobber, unconditional; ~0 coverage, strict) — the job is to
    replace `resolve_local` with `resolve_global` (forward-replay-must-reproduce-today search) and show the
    PAST-gold pit rises at <10% misplacement on dates excluded from calibration.
REASONING: measure before building general (three local shortcuts already returned ~0). The acceptance
    gates are pre-committed in the spec; this harness just makes them runnable on vphl (clean base, 5
    held-out Lovdata-Pro dates) before generalising.
ASSUMES: data/ground_truth/<dk>/ gold on disk; the dev pipeline importable. Verbatim invariant: a resolver
    may only place an op's verbatim new_text; today's text is a COMPARATOR, never copied into a provision.
"""
from __future__ import annotations
import statistics
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.parse import pipeline, ledd, ledd_apply, align   # noqa: E402
from source.eval import gate, metrics, ground_truth           # noqa: E402

LAW = "lov/2007-06-29-75"   # vphl: clean base, rich 2007-2021 history, 5 held-out Lovdata-Pro dates
DK = "2007-06-29-75"


def resolve_local(provision, instruction, new_text, op_type):
    """BASELINE (measured insufficient): place verbatim new_text at the best LOCAL content match.
    Replace this with a global-consistency resolver. Returns rebuilt provision text or None (abstain)."""
    nt = (new_text or "").strip()
    if not nt:
        return None
    title, ledds, mode = ledd._parse(provision)
    if not ledds:
        return None
    t = align.target_ledd(ledds, nt, ordinal=ledd._ordinal(instruction))
    if t.get("already_applied"):
        return provision
    if t["index"] is None or not t.get("matched"):   # strict margin gate; set matched check aside to go loose
        return None
    ledds[t["index"]] = nt
    return ledd._serialize(title, ledds, mode)


def reconstruct_with(resolver, as_of):
    """reconstruct(LAW, as_of) with `resolver` spliced in as the ledd_fallback (None resolver = off)."""
    _orig = ledd_apply.make_fallback
    ledd_apply.make_fallback = (lambda tl: resolver) if resolver else (lambda tl: (lambda *a, **k: None))
    try:
        return pipeline.reconstruct(LAW, as_of)[0]
    finally:
        ledd_apply.make_fallback = _orig


def score(resolver=None, dates=None):
    """Point-in-time fidelity on held-out gold, resolver on vs off. Returns per-date + aggregate."""
    gts = dict(ground_truth.versions_for(DK))
    cur = gate.current_provisions(DK)
    order = [p for p in cur if not metrics.is_convention_annex(p)]
    tau = gate.TAU_OCR if pipeline.is_ocr_base(LAW) else gate.TAU
    out = {}
    agg = []
    for date in sorted(dates or gts):
        gold = gts[date]
        recon = reconstruct_with(resolver, date)
        sims = [metrics.similarity(recon.get(p, ""), gold.get(p, "")) for p in order if p in gold]
        agg += sims
        out[date] = (round(statistics.mean(sims), 4), round(sum(s >= tau for s in sims) / len(sims), 4), len(sims))
    out["_AGG"] = (round(statistics.mean(agg), 4), round(sum(s >= tau for s in agg) / len(agg), 4), len(agg))
    return out


if __name__ == "__main__":
    print("OFF :", score(None))
    print("LOCAL:", score(resolve_local))
