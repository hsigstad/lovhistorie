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

from source.parse import amendments, replay


def enactment_base(target_law: str) -> dict:
    """{paragraf_id: text} of the law AS ORIGINALLY ENACTED, from the gazette.

    HARD RULE: this must be built from Norsk Lovtidend (the enactment issue) — the
    public-domain source — NEVER from the current consolidated text. Reading the
    current text here is the cheat the gate exists to catch; do not do it.

    TODO (main lever): parse the enactment issue via source.scrape.nb_lovtidend into
    per-provision text. Until then this returns {} and provisions that were never
    amended cannot be reconstructed (they score 0 against the current text) — which
    is the honest state, and exactly what convergence should expose.
    """
    return {}


def reconstruct(target_law: str, as_of: str | None = None):
    """Rebuild {paragraf_id: text} for `target_law` as of `as_of` (or latest).

    Returns (provisions, flags). Inputs are enactment base + amendment ops ONLY.
    """
    base = enactment_base(target_law)
    ops = amendments.load_for(target_law)
    return replay.replay(base, ops, as_of=as_of)
