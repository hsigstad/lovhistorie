"""Deterministic replay engine: apply amendment ops to a base to reconstruct
point-in-time statutory text.

INTENT: implement the `reconstruct` side of the pipeline (docs/reference/goal.md) — apply the
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


def replay(base: dict, ops: list, as_of: str | None = None, ledd_fallback=None):
    """Apply ops (up to as_of) to base. Returns (provisions, flags).

    Ops carry `change_type` (from load_ops) or the legacy `kind` (amendments.load_for).
    flags: ops we could not apply (renumber/move/unknown/sub-provision the ledd engine
    can't do) — their provisions are left as-is, never filled with invented text.

    `ledd_fallback(provision, instruction, new_text, op_type) -> str | None`: OPTIONAL applicator
    tried when the deterministic ledd engine returns None on a sub-provision op (the LLM applicator
    source.llm.apply_op). OFFLINE ONLY — runtime reconstruction passes None and stays deterministic
    (rule 3); an offline pre-apply pass passes apply_op to bake the result into a derived stream.
    """
    doc = dict(base)
    flags = []
    for op in ops:
        if as_of and op.get("date") and op["date"] > as_of:
            continue
        if "change_type" in op:
            _apply_change_type(doc, op, flags, ledd_fallback)
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
# A CLEAN provision id: §9a, §38, §38b, §1-1, §2-11a — NOT §kapittel4 / §avsnittII / mashed
# structural ids. Gate for the direct whole-provision set below so a malformed structural op
# (chapter/heading) can never create a garbage provision (the class that corrupted aksjeloven).
_CLEAN_PARA = re.compile(r"§\d+[a-zæøå]?(?:-\d+[a-zæøå]?)?$")


def _apply_change_type(doc, op, flags, ledd_fallback=None):
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
            if result is None and ledd_fallback:         # offline LLM applicator (apply_op)
                result = ledd_fallback(doc.get(para, ""), instr, new, "repeal")
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
        if result is None and ledd_fallback and _SUBUNIT.search(instr):  # offline LLM applicator
            result = ledd_fallback(doc.get(para, ""), instr, new, ct)
        if result is not None:
            doc[para] = result
            return
        # Whole-provision "§ N skal lyde:" whose new_text lacks the '§ N.' heading (so the
        # startswith('§') branch above missed it) and which has no sub-unit for ledd to address:
        # set the provision body directly — INSERT-ONLY (para absent), e.g. a § ADDED by amendment
        # (avtaleloven §9a). We do NOT overwrite an existing provision from a bare-body op: tried it
        # (even recovery-only, gap-fill-gated) and it netted NEGATIVE — it converts §36 (whose 1983
        # text is complete) but corrupts foreld provisions that converge from the enactment base yet
        # are register-"amended", where the recovered OCR text is worse (−9 foreld). A "substantially
        # different" difflib gate to separate the good §36 overwrite from the bad foreld ones was
        # tried (2026-08-23) and ALSO netted −7: foreld's bad ops are substantially-different WRONG
        # text (mis-capture), not re-OCR, so text-difference can't tell them apart. The honest lever
        # is SOURCE-ONLY overwrite confidence (does our localize-then-verify pipeline corroborate the
        # op's attribution?), NOT the answer key: an oracle/current-text/register check here would be a
        # BUILD input (circular — if we had the snapshot we'd just publish it — and it voids
        # convergence as an honest proxy; oracles are validation-only). Until a source-only confidence
        # signal separates them, bare-body overwrite stays off. (A whole-provision REWRITE that carries
        # its '§ N.' heading still overwrites via the startswith('§') branch above — high-confidence.)
        if not _SUBUNIT.search(instr) and _CLEAN_PARA.match(para or "") and para not in doc:
            doc[para] = _strip_heading(new)
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
