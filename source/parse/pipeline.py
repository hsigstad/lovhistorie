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


def load_ops(target_law: str):
    """Ordered ops for a law WITH change_type + clean para (richer than
    amendments.load_for). change_type ∈ {change, add, repeal, renumber, move,
    unknown}; renumber/move/unknown are left for replay to flag, not fabricate."""
    ops = []
    with gzip.open(amendments.DATA, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("target_law") != target_law:
                continue
            ops.append({
                "para": _op_para(d),
                "change_type": d.get("change_type"),
                "instruction": d.get("instruction"),
                "new_text": d.get("new_text"),
                "date": d.get("date_in_force_resolved") or d.get("date_in_force"),
                "act": d.get("act_refid"),
            })
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


def reconstruct(target_law: str, as_of: str | None = None):
    """Rebuild {paragraf_id: text} for `target_law` as of `as_of` (or latest).

    Returns (provisions, flags). Inputs are enactment base + amendment ops ONLY.
    """
    base = enactment_base(target_law)
    ops = load_ops(target_law)
    return replay.replay(base, ops, as_of=as_of)
