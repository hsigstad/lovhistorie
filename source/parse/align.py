"""Text-similarity alignment for identity-over-time — deterministic, fabrication-free.

INTENT: track a unit (provision or ledd) by its TEXT, not its version-dependent id/ordinal,
    so renumbers and ledd-position shifts are recovered from content. Two uses: (a) renumber
    recovery — align reconstructed provisions to a target version and read off the id-remap;
    (b) ledd targeting — find which ledd an amendment op replaces, robust to earlier inserts,
    with idempotency for free.
REASONING: this is pure ALIGNMENT over `metrics.similarity` — it LINKS existing units, never
    generates content, so it cannot fabricate. A match is asserted only above a threshold
    (mutual-best for the bipartite case); everything else is left unmatched and FLAGGED
    (flag-don't-fabricate). Validated 2026-08-14: recovered vphl §16→§20 renumbers and, on
    §3-1, correctly targeted the amended ledd where the ordinal failed under a shift.
ASSUMES: inputs are normalised-comparable statutory text ({id: text} or [text]); callers
    supply a threshold (default 0.90, matching the OCR-base convergence bar).
"""
from __future__ import annotations

from source.eval import metrics

THRESHOLD = 0.90
IDEMPOTENT = 0.999   # a REPLACE whose target already equals the new text is already applied


def best_match(text: str, candidates: list[str]):
    """(index, score) of the candidate most similar to `text`, or (None, 0.0) if none."""
    best_i, best_s = None, 0.0
    for i, c in enumerate(candidates):
        s = metrics.similarity(text, c)
        if s > best_s:
            best_i, best_s = i, s
    return best_i, best_s


MARGIN = 0.25   # a REPLACE modifies its ledd, so the target is identified by a clear GAP over
#                 the next-best ledd, not by absolute similarity (which is <1 by construction).


def target_ledd(ledds: list[str], new_text: str, *, ordinal: int | None = None,
                margin: float = MARGIN):
    """Which ledd a REPLACE op targets, by CONTENT not ordinal. Returns a dict:
    {index, score, second, already_applied, ordinal_agrees, matched}. `index` is the
    argmax-similarity ledd; `already_applied` (score ≥ IDEMPOTENT) means the op is a no-op →
    SKIP (idempotency). `matched` requires the best to clearly beat the second-best by `margin`
    — because a REPLACE gives a *modified* version of its ledd, so absolute similarity is <1 by
    construction; what identifies the target is the GAP. An ambiguous best (no gap) → matched
    False → flag, don't guess. The version-dependent ordinal is only a cross-check."""
    scores = sorted(((metrics.similarity(new_text, l), i) for i, l in enumerate(ledds)),
                    reverse=True)
    if not scores:
        return {"index": None, "score": 0.0, "second": 0.0, "matched": False,
                "already_applied": False, "ordinal_agrees": False}
    (s, i), second = scores[0], (scores[1][0] if len(scores) > 1 else 0.0)
    return {
        "index": i,
        "score": round(s, 4),
        "second": round(second, 4),
        "matched": (s - second) >= margin,
        "already_applied": s >= IDEMPOTENT,
        "ordinal_agrees": (ordinal is not None and i == ordinal - 1),
    }


def mutual_best(a_units: dict, b_units: dict, *, threshold: float = THRESHOLD):
    """Bipartite mutual-best matching between two {id: text} versions above `threshold`.
    Returns [(a_id, b_id, score)] where a_id is each side's best for the other — a 1-1
    content alignment. Unmatched ids on either side are the caller's inserted/repealed/gap
    set (not returned; read them off the input keys minus the matched ones)."""
    a_keys, b_keys = list(a_units), list(b_units)
    b_texts = [b_units[k] for k in b_keys]
    best_of_a = {}                                   # a_id -> (b_idx, score)
    for ak in a_keys:
        bi, bs = best_match(a_units[ak], b_texts)
        if bi is not None and bs >= threshold:
            best_of_a[ak] = (bi, bs)
    a_texts = [a_units[k] for k in a_keys]
    matches = []
    for ak, (bi, bs) in best_of_a.items():
        # mutual: b_keys[bi]'s best back among a must be ak
        aj, aj_s = best_match(b_texts[bi], a_texts)
        if aj is not None and a_keys[aj] == ak:
            matches.append((ak, b_keys[bi], round(bs, 4)))
    return matches


def find_renumbers(source: dict, target: dict, *, threshold: float = THRESHOLD):
    """{target_id: source_id} for target provisions whose text matches a source provision
    under a DIFFERENT id — i.e. renumbers the id-based path misses. Content-based, so it
    recovers `nåværende §X blir §Y` moves without parsing the instruction; a target with no
    strong match anywhere is left out (genuinely missing, flagged by absence)."""
    remap = {}
    for sid, tid, _ in mutual_best(source, target, threshold=threshold):
        if sid != tid:
            remap[tid] = sid
    return remap
