"""Global-consistency ledd fitter — the ONE untested lever for the 44% sub-provision gap.

INTENT: disambiguate WHERE a flagged sub-provision op places its verbatim new_text by the GLOBAL
    constraint "forward-replay of ALL dated ops must reproduce TODAY's text" — not the LOCAL content
    margin that measured 0% correct / 83% clobber (docs/notes/global_consistency_ledd.md, done.md
    2026-10-16). For a provision with flagged pure-ledd ops, enumerate candidate ledd-slot
    assignments, replay the whole law to today, and keep the assignment whose reconstruction best
    reproduces today. FIT uses today as a COMPARATOR ONLY (score the final state); the shipped
    resolver is answer-key-free (it replays the cached slot decisions, never reads today/gold).
REASONING: today certifies the whole op-STRUCTURE at once, so it rejects the clobbers the local
    signal accepted (clobbering §5-5a makes the chain miss today -> that assignment loses). Past
    states come from date-filtering the SAME resolved ops, so nothing makes the past look present.
GUARDS (encoded here; full list in the spec):
    - Verbatim-span: place() only ever writes the op's verbatim new_text or deletes a ledd. ~0 fab.
    - Today comparator-only: current text scores the final state; never copied into a provision.
    - NEVER accept a placement that scores WORSE against today than abstaining (the clobber floor —
      this single rule would have rejected every LOCAL-experiment clobber, e.g. §5-5a 1.0->0.31).
    - Accept at a gate (strict-unique OR clearly-better-by-margin on the GLOBAL today signal);
      MEASURE correctness on held-out PAST gold excluded from fitting (source/eval/ledd_consistency_probe).
    - Bounded search: provisions whose candidate space explodes -> flag (missing-op / coverage signal).
SCOPE (v1 — measure before building general): pure-ledd replace/insert/repeal on non-blob provisions.
    bokstav/nr/punktum sub-list ops and OCR-blob provisions abstain (recorded as diagnostics), since
    their location search is a different (harder) combinatorial problem.
ASSUMES: source.parse.pipeline importable; gate.current_provisions(DK) = today (public NLOD dump,
    NOT the Lovdata-Pro oracle). Keyed by ledd_apply.op_key(law, instruction, new_text).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from source.parse import pipeline, ledd, ledd_apply, replay
from source.eval import gate, metrics

_SUBLIST = re.compile(r"\b(?:punktum|bokstav|nr\.?)\b")   # out of v1 scope (not pure-ledd)
_MAX_LEAVES = 4000                                        # ambiguity-budget cap per provision
_MAX_NODES = 30000                                        # DFS node cap (per provision)


# ---------------------------------------------------------------------------
# placement — the ONLY text mutation; mirrors ledd.apply's pure-ledd edits exactly
# (so an accepted slot behaves identically whether applied here or by the ledd engine).
# ---------------------------------------------------------------------------
def _candidates(provision: str, action: str):
    """Candidate ledd slots for `action` in the running provision, or [] if out of scope."""
    _, ledds, mode = ledd._parse(provision)
    if mode == "blob" or not ledds:
        return []
    if action == "insert":
        return list(range(len(ledds) + 1))      # insert BEFORE position i
    if action in ("replace", "repeal"):
        return list(range(len(ledds)))
    return []


def place(provision: str, new_text: str, action: str, slot: int) -> str | None:
    """Place the op's verbatim new_text at ledd `slot` (or delete it). None if slot invalid."""
    title, ledds, mode = ledd._parse(provision)
    ledds = list(ledds)
    nt = " ".join((new_text or "").split())
    if action == "replace":
        if not (0 <= slot < len(ledds)) or not nt:
            return None
        old = ledds[slot]
        pm = ledd._NUM_MARK.match(old)
        keep = pm.group(0) if (pm and not ledd._NUM_MARK.match(nt)) else ""
        ledds[slot] = keep + nt
        return ledd._serialize(title, ledds, mode)
    if action == "insert":
        if not (0 <= slot <= len(ledds)) or not nt:
            return None
        ledds.insert(slot, nt)
        return ledd._serialize(title, ledd._renumber(ledds), mode)
    if action == "repeal":
        if not (0 <= slot < len(ledds)):
            return None
        del ledds[slot]
        return ledd._serialize(title, ledd._renumber(ledds), mode)
    return None


def _action_of(instr: str) -> str | None:
    """Pure-ledd action, or None if out of v1 scope (sub-list / unparseable)."""
    if _SUBLIST.search(instr or ""):
        return None
    return ledd._action(instr or "")


# ---------------------------------------------------------------------------
# per-provision replay: a sub-provision op only ever touches its OWN provision's text,
# so we replay JUST a para's op sub-chain through the REAL routing (replay._apply_change_type
# on a 1-key doc) — identical behaviour to the full reconstruct, ~1000x faster (a handful of
# ops, not the law's ~900). This is what makes the combinatorial slot search tractable.
# ---------------------------------------------------------------------------
def _replay_para(base_text: str, para_ops: list, fb) -> str:
    para = para_ops[0].get("para")
    doc = {para: base_text} if base_text else {}
    flags = []
    for op in para_ops:
        replay._apply_change_type(doc, op, flags, fb)
    return doc.get(para, "")


# ---------------------------------------------------------------------------
# per-provision joint search: lazy-frontier DFS over candidate slot assignments
# ---------------------------------------------------------------------------
@dataclass
class ProvFit:
    para: str
    off_sim: float
    leaves: list = field(default_factory=list)   # [(assign:{opkey:(action,slot)}, today_sim)]
    decision: str = ""                            # accept-strict | accept-margin | flag-*
    accepted: dict = field(default_factory=dict)  # opkey -> (action, slot)  (only if accepted)


def _search_provision(law, para, base_text, para_ops, today_text) -> ProvFit:
    """All full slot-assignments for `para`'s flagged pure-ledd ops, scored by today-reproduction."""
    leaves = []
    aborted = [False]
    nodes = [0]

    def dfs(assign: dict):
        if aborted[0] or len(leaves) > _MAX_LEAVES or nodes[0] > _MAX_NODES:
            aborted[0] = True
            return
        nodes[0] += 1
        frontier = {}   # opkey -> (action, [candidate slots]); first unassigned op this run

        def fb(provision, instruction, new_text, op_type):
            k = ledd_apply.op_key(law, instruction or "", new_text or "")
            if k in assign:
                action, slot = assign[k]
                return place(provision, new_text, action, slot)
            action = _action_of(instruction or "")            # unassigned op
            if action is None:
                return None                                   # out of v1 scope -> abstain
            if not frontier:                                  # capture the FIRST unassigned op only
                cands = _candidates(provision, action)
                if cands:
                    frontier[k] = (action, cands)
            return None                                       # abstain (resolved in a deeper branch)

        final = _replay_para(base_text, para_ops, fb)
        if not frontier:                                      # leaf: all flagged ops assigned
            leaves.append((dict(assign), metrics.similarity(final, today_text)))
            return
        k, (action, cands) = next(iter(frontier.items()))
        for slot in cands:
            dfs({**assign, k: (action, slot)})

    dfs({})
    off = metrics.similarity(_replay_para(base_text, para_ops, lambda *a, **k: None), today_text)
    pf = ProvFit(para=para, off_sim=round(off, 4),
                 leaves=sorted(leaves, key=lambda x: -x[1]))
    if aborted[0]:
        pf.decision = "flag-too-ambiguous"
    return pf


# ---------------------------------------------------------------------------
# gate — strict-unique OR clearly-better-by-margin, under a mandatory clobber floor
# ---------------------------------------------------------------------------
def _gate(pf: ProvFit, tau: float, mode: str, delta: float, floor_eps: float = 1e-4):
    if pf.decision.startswith("flag") or not pf.leaves:
        pf.decision = pf.decision or "flag-no-candidate"
        return
    best_assign, best = pf.leaves[0]
    second = pf.leaves[1][1] if len(pf.leaves) > 1 else None
    # MANDATORY floor: never accept a placement worse than (or equal to) abstaining.
    if best <= pf.off_sim + floor_eps:
        pf.decision = "flag-no-gain-over-abstain"
        return
    if mode == "strict":
        ok = best >= tau and (second is None or second < tau)
        pf.decision = "accept-strict" if ok else "flag-not-unique-at-tau"
    else:  # 'margin' — clearly better than the runner-up on the GLOBAL today signal
        ok = second is None or (best - second) >= delta
        pf.decision = "accept-margin" if ok else "flag-ambiguous-margin"
    if pf.decision.startswith("accept"):
        pf.accepted = dict(best_assign)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def fit(law: str, dk: str, mode: str = "strict", delta: float = 0.05):
    """Fit slot decisions for `law` against today. Returns (accepted:{opkey:(action,slot)}, fits:[ProvFit])."""
    today = gate.current_provisions(dk)
    tau = gate.TAU_OCR if pipeline.is_ocr_base(law) else gate.TAU
    base = pipeline.enactment_base(law)

    groups = {}
    for op in pipeline.load_ops(law):
        groups.setdefault(op.get("para"), []).append(op)

    fits, accepted = [], {}
    for para in sorted(p for p in groups if p):
        para_ops = groups[para]
        base_text = base.get(para, "")
        # discovery: does this provision have >=1 in-scope flagged pure-ledd op?
        flagged = [False]

        def disc(provision, instruction, new_text, op_type, _f=flagged):
            a = _action_of(instruction or "")
            if a and _candidates(provision, a):
                _f[0] = True
            return None

        _replay_para(base_text, para_ops, disc)
        if not flagged[0]:
            continue
        pf = _search_provision(law, para, base_text, para_ops, today.get(para, ""))
        _gate(pf, tau, mode, delta)
        fits.append(pf)
        accepted.update(pf.accepted)
    return accepted, fits


def make_global_resolver(law: str, dk: str, mode: str = "strict", delta: float = 0.05):
    """Answer-key-free resolver for the probe: replays the fitted slot decisions (no today/gold read)."""
    accepted, _fits = fit(law, dk, mode=mode, delta=delta)

    def resolve_global(provision, instruction, new_text, op_type):
        k = ledd_apply.op_key(law, instruction or "", new_text or "")
        dec = accepted.get(k)
        if not dec:
            return None
        action, slot = dec
        return place(provision, new_text or "", action, slot)

    resolve_global.accepted = accepted          # exposed for diagnostics
    return resolve_global
