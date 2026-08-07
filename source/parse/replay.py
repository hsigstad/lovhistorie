"""Deterministic replay engine: apply amendment ops to a base to reconstruct
point-in-time statutory text.

INTENT: implement the `reconstruct` side of the pipeline (docs/goal.md) — apply the
    ordered ops to the enactment base, honouring `as_of`, using rules/regex only
    (no LLM), and FLAGGING any op it cannot apply rather than fabricating text.
REASONING: full-provision ops (`§ X skal lyde`), `ny § X`, and `oppheves` are clean
    whole-provision operations. Sub-provision ops (ledd/punktum/bokstav — 55% of the
    corpus) need a ledd engine (not yet built) and are FLAGGED, not guessed: a
    flagged provision is left at its last-known text, so convergence exposes exactly
    what the ledd engine must fix. This is the flag-don't-fabricate rule.
ASSUMES: base is {paragraf_id: text}; ops come from amendments.load_for (ordered by
    resolved in-force date). The current/historical text is NEVER an input here —
    only the base (enactment) + ops. See the reconstruct contract in evaluation.md.
"""
from __future__ import annotations


def replay(base: dict, ops: list, as_of: str | None = None):
    """Apply ops (up to as_of) to base. Returns (provisions, flags).

    flags: [{para, kind, date, instruction}] — ops we could not apply (need the
    ledd engine or are malformed); their provisions are left unreconstructed for
    that change, never filled with invented text.
    """
    doc = dict(base)
    flags = []
    for op in ops:
        if as_of and op["date"] and op["date"] > as_of:
            continue
        para, kind, new = op["para"], op["kind"], op.get("new_text")
        if kind == "replace" and new:
            doc[para] = new
        elif kind == "add" and new:
            doc[para] = new
        elif kind == "repeal":
            doc.pop(para, None)
        else:  # subprovision / other / malformed -> FLAG, do not fabricate
            flags.append({"para": para, "kind": kind, "date": op.get("date"),
                          "instruction": op.get("instruction")})
    return doc, flags


def reconstructable(ops):
    """Paragraf ids the current engine can fully reconstruct from ops alone
    (their last op is a whole-provision replace/add) — the honest reach today."""
    last = {}
    for op in sorted(ops, key=lambda o: (o["date"] or "", o["act"] or "")):
        if op["para"]:
            last[op["para"]] = op["kind"]
    return {p for p, k in last.items() if k in ("replace", "add")}
