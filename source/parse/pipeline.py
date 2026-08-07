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

import json
from pathlib import Path

from source.parse import amendments, replay

_ENACTMENT = Path(__file__).resolve().parents[2] / "data" / "enactment"


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
    ops = amendments.load_for(target_law)
    return replay.replay(base, ops, as_of=as_of)
