"""The reconstruction entrypoint — the ONLY thing the autonomous loop improves.

INTENT: expose one function, `reconstruct(target_law, as_of)`, that rebuilds a law's
    provisions from PUBLIC-DOMAIN inputs only — the enactment base (gazette) + the
    ordered Lovtidend amendment ops — and never from the current/final consolidated
    text. The eval gate (source/eval/gate.py) drives this toward convergence.
REASONING: keeping the whole reconstruction behind one import boundary lets the gate
    prove input-isolation mechanically: this module (and everything it imports) must
    NOT import the harness package `source.eval`, which is where the answer key lives.
    Break that and the gate's static guard fails — the anti-gaming contract in code.
ASSUMES: amendments.load_for gives ordered ops; replay applies them; enactment_base
    supplies the starting text. enactment_base is the current frontier of the work
    (see its docstring) — today it returns {} so convergence measures amendments
    alone; wiring the gazette base is the main lever to raise it.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

from source.parse import amendments, replay

_ENACTMENT = Path(__file__).resolve().parents[2] / "data" / "enactment"
_PARA = re.compile(r"§\s*(\d+(?:-\d+)?[a-z]?)")


def _clean_para(s: str | None):
    """First '§ N' anywhere in `s` -> '§N'. For target fields that NAME the provision
    ('§ 1-9', '§ 6 n'). NOT for new_text bodies — their first § is often a cross-ref."""
    if not s:
        return None
    m = _PARA.search(s)
    return "§" + m.group(1) if m else None


def _leading_para(new_text: str | None):
    """'§ N' ONLY if new_text opens with its own heading ('§ 4.Vedtak…' -> '§4').
    Start-anchored so a body cross-reference ('Vedtak etter §§ 2, 3…') never matches."""
    if not new_text:
        return None
    m = _PARA.match(new_text.lstrip())
    return "§" + m.group(1) if m else None


def _op_para(d: dict):
    """Clean paragraf id: the fields that NAME the target first; new_text's own
    leading heading only as a last resort (never a mid-body §-reference)."""
    return (_clean_para(d.get("paragraph"))
            or _clean_para(d.get("target"))
            or _clean_para(d.get("instruction"))
            or _leading_para(d.get("new_text")))


_BLOCK = re.compile(r"(?m)(?=^\s*§\s*\d+(?:-\d+)?[a-z]?\.)")


def _split_block(new_text: str):
    """A '§ X skal lyde' / 'Kapittel N skal lyde' new_text can carry SEVERAL
    provisions ('§ 1-1.…\\n§ 1-2.…'). Split on line-start '§ N.' headings into
    [(para, piece_with_heading)] so each provision is set from its own slice, not all
    dumped onto the first. Body cross-references ('… jf. § 2-2') are mid-line and
    never split. Returns [] if there is no leading heading."""
    pieces = []
    for part in _BLOCK.split(new_text):
        m = _PARA.match(part.lstrip())
        if m:
            pieces.append(("§" + m.group(1), part.strip()))
    return pieces


def load_ops(target_law: str):
    """Ordered ops for a law WITH change_type + clean para (richer than
    amendments.load_for). change_type ∈ {change, add, repeal, renumber, move,
    unknown}; renumber/move/unknown are left for replay to flag, not fabricate.
    Multi-provision new_text blocks are expanded to one op per provision."""
    ops = []
    with gzip.open(amendments.DATA, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("target_law") != target_law:
                continue
            base = {
                "change_type": d.get("change_type"),
                "instruction": d.get("instruction"),
                "date": d.get("date_in_force_resolved") or d.get("date_in_force"),
                "act": d.get("act_refid"),
            }
            new = d.get("new_text")
            pieces = _split_block(new) if new and new.lstrip().startswith("§") else []
            if pieces:                        # whole-provision block: one op per §
                for para, piece in pieces:
                    ops.append({**base, "para": para, "new_text": piece})
            else:                             # sub-provision / repeal / structural
                ops.append({**base, "para": _op_para(d), "new_text": new})
    ops.sort(key=lambda o: (o["date"] or "", o["act"] or ""))
    return ops


def enactment_base(target_law: str) -> dict:
    """{paragraf_id: text} of the law AS ORIGINALLY ENACTED, from the gazette.

    Reads the cached, public-domain enactment built OFFLINE by
    source.scrape.build_enactment (data/enactment/<datokode>.json). No network, no
    OCR, no current text at runtime — deterministic (hard rule 3).

    HARD RULE: the cache must come from Norsk Lovtidend, NEVER from the current
    consolidated text (the gate's base-integrity guard enforces this). Laws not yet
    built return {} — their never-amended provisions can't be reconstructed and
    score 0 against the current text, which is the honest state convergence exposes.
    """
    dk = target_law.split("/")[-1]
    f = _ENACTMENT / f"{dk}.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("provisions", {})


def is_ocr_base(target_law: str) -> bool:
    """True if the enactment base was OCR'd from a gazette/booklet (its `source` has no
    clean-LTI-XML `lti` key). OCR bases carry irreducible character noise, so the eval
    applies an OCR-calibrated τ to them (gate.TAU_OCR); clean LTI bases keep the strict
    τ. Objective + structural (the source provenance recorded at build time), so it can't
    be used to hand-pick which provisions get the looser bar."""
    dk = target_law.split("/")[-1]
    f = _ENACTMENT / f"{dk}.json"
    if not f.exists():
        return False
    src = json.loads(f.read_text(encoding="utf-8")).get("source", {})
    return "lti" not in src


def base_as_of(target_law: str) -> str | None:
    """The version boundary a SNAPSHOT base was captured at (booklet 'ajourført' date),
    or None for a pure enactment base. When set, the base already incorporates every
    amendment dated <= this, so reconstruction must replay ONLY later amendments."""
    dk = target_law.split("/")[-1]
    f = _ENACTMENT / f"{dk}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8")).get("base_as_of")


def reconstruct(target_law: str, as_of: str | None = None):
    """Rebuild {paragraf_id: text} for `target_law` as of `as_of` (or latest).

    Returns (provisions, flags). Inputs are enactment base + amendment ops ONLY.
    For a snapshot base (base_as_of set), amendments already baked into the snapshot
    (date <= base_as_of) are skipped so they are not double-applied; dates before the
    snapshot are not reconstructable from it and are the honest floor of its reach.
    """
    base = enactment_base(target_law)
    ops = load_ops(target_law)
    since = base_as_of(target_law)
    if since:
        ops = [o for o in ops if not o.get("date") or o["date"] >= since]
    return replay.replay(base, ops, as_of=as_of)
