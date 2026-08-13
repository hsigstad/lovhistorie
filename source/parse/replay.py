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

import re

from source.parse import ledd

# Leading provision heading '§ N. …' so the stored body excludes the heading, matching the
# gate's heading-free provision bodies. A spaced suffix letter ('§ 5-8 a.') is stripped ONLY
# when a period follows it (first alternative) — otherwise '§ 27 første' would lose the 'f'
# of 'første'; the bare form (second alternative) keeps the original behaviour.
_HEADING = re.compile(r"^\s*§\s*(?:\d+(?:-\d+)?\s*[a-z]\.|\d+(?:-\d+)?[a-z]?\.?)\s*")


def _strip_heading(new_text: str) -> str:
    """Whole-provision new_text starts '§ N. …'; drop the heading so it matches the
    gate's provision bodies (which exclude headings). Collapse whitespace."""
    return " ".join(_HEADING.sub("", new_text).split())


def replay(base: dict, ops: list, as_of: str | None = None):
    """Apply ops (up to as_of) to base. Returns (provisions, flags).

    Ops carry `change_type` (from load_ops) or the legacy `kind` (amendments.load_for).
    flags: ops we could not apply (renumber/move/unknown/sub-provision the ledd engine
    can't do) — their provisions are left as-is, never filled with invented text.
    """
    doc = dict(base)
    flags = []
    for op in ops:
        if as_of and op.get("date") and op["date"] > as_of:
            continue
        if "change_type" in op:
            _apply_change_type(doc, op, flags)
        else:
            _apply_kind(doc, op, flags)   # legacy path (run_convergence)
    return doc, flags


def _flag(flags, op, why):
    flags.append({"para": op.get("para"), "why": why, "date": op.get("date"),
                  "instruction": op.get("instruction")})


# A repeal that names a SUB-UNIT ("§ X femte ledd oppheves", "nr. 3 oppheves") must remove
# only that ledd/punktum/nr/bokstav — NOT the whole provision. The gazette/LTI stream labels
# these change_type="repeal" with the provision as `para`, so a naive doc.pop(para) deletes
# the entire §. (ledd.py's own docstring flags this exact hazard: "§4 pkt.b oppheves wrongly
# deletes all of §4".)
_SUBUNIT = re.compile(r"\b(?:ledd|punktum|bokstav|nr\.?)\b")


def _apply_change_type(doc, op, flags):
    para = op.get("para")
    ct = op.get("change_type")
    new = op.get("new_text")
    instr = op.get("instruction") or ""
    if ct == "repeal" and para:
        if _SUBUNIT.search(instr):
            # sub-unit repeal — route to the ledd engine; if it can't resolve the address
            # cleanly, FLAG and LEAVE THE PROVISION INTACT (never delete the whole § on a
            # sub-unit repeal — flag-don't-fabricate, and keeping it is far closer to current
            # than an empty provision).
            result = ledd.apply(doc.get(para, ""), instr, new)
            if result is not None:
                doc[para] = result
            else:
                _flag(flags, op, "repeal-subunit")
            return
        doc.pop(para, None)          # whole-provision repeal
        return
    if "overskrift" not in instr and para and new and new.lstrip().startswith("§"):
        # A whole-provision body ('§ N. …') IS the provision's new enacted text,
        # whatever the instruction's change_type parsed to. Chapter/part block
        # replacements ('Kapittel N skal lyde', 'Etter kapittel M skal del … lyde')
        # are split into per-§ pieces upstream (pipeline._split_block) but every piece
        # inherits the block's change_type — often 'unknown' — so the add/change gate
        # below would flag them. Apply by the §-heading body instead. Faithful (the
        # act's own enacted text, never fabricated); move/renumber/repeal never carry
        # a §-body (verified), so this cannot mis-fire on a structural op.
        doc[para] = _strip_heading(new)
        return
    if ct in ("add", "change") and para and new:
        if "overskrift" in instr:          # heading-only change: provision body unchanged
            return
        result = ledd.apply(doc.get(para, ""), instr, new)   # sub-provision -> ledd engine
        if result is not None:
            doc[para] = result
            return
    _flag(flags, op, ct)                    # renumber / move / unknown / unhandled


def _apply_kind(doc, op, flags):
    para, kind, new = op.get("para"), op.get("kind"), op.get("new_text")
    if kind in ("replace", "add") and new:
        doc[para] = new
    elif kind == "repeal":
        doc.pop(para, None)
    elif kind == "subprovision":
        result = ledd.apply(doc.get(para, ""), op.get("instruction"), new)
        if result is not None:
            doc[para] = result
        else:
            _flag(flags, op, kind)
    else:
        _flag(flags, op, kind)


def reconstructable(ops):
    """Paragraf ids the current engine can fully reconstruct from ops alone
    (their last op is a whole-provision replace/add) — the honest reach today."""
    last = {}
    for op in sorted(ops, key=lambda o: (o["date"] or "", o["act"] or "")):
        if op["para"]:
            last[op["para"]] = op["kind"]
    return {p for p, k in last.items() if k in ("replace", "add")}
