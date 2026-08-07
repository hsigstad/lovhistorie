# Goal (for autonomous execution)

## The goal, precisely

Reconstruct the **point-in-time text of Norwegian in-force statutes** ("the law as
it read at date *t*") **from enactment + Norsk Lovtidend amendments only**, such
that — on a **held-out set of laws × dates** — per-provision character similarity
to the **Lovdata Pro** historical version is ≥ **0.98** for ≥ **95%** of provisions,
with coverage ≥ **90%** of laws and **every failure flagged**.

(Targets are provisional until the held-out set is assembled; the *shape* is fixed.)

## Hard rules — these make the goal un-gameable. Do not relax them.

1. **Target = historical, held out. Not current.** Success is measured against
   *past-date* Lovdata Pro versions the pipeline has never seen. Reproducing the
   *current* text is **not** success — a `return current text` solution passes
   convergence but fails point-in-time, and is the exact flaw we are avoiding.
2. **Inputs = enactment + amendments only.** `reconstruct(datokode, as_of)` is given
   the enacting act (gazette) + the Lovtidend amendments. It is **never** given the
   current consolidated text, the historical versions, or any answer key — those
   live only in the eval harness. No network lookup of law text at eval time.
3. **Deterministic; no LLM at pipeline runtime.** Reconstruction is pure
   rules/regex — reproducible and auditable. **No LLM** in the reconstruction path
   (an LLM could fabricate plausible text that passes similarity, or "recall" the
   answer). If OCR post-correction is ever proposed, it needs separate sign-off and
   must itself be deterministic.
4. **Flag, don't fabricate.** An op or provision the pipeline cannot handle is
   **flagged with a reason** and left unreconstructed — **never** filled with
   invented or guessed text. Fabrication that happens to score is a failure, not a
   pass.
5. **Held out means held out.** Never tune, inspect-to-fix, or select on the eval
   set (laws *or* dates). Develop on a separate dev set.

## Convergence is the dev proxy, not the success bar

Convergence-to-current (reproduce today's text from enactment + amendments) needs
no ground truth and drives the engine build. But it is **necessary, not
sufficient** (two errors can cancel; and with the answer key withheld it is a real
test, but still not the deliverable). **Success requires the point-in-time
held-out metric**, not convergence alone.

## Definition of done

- Point-in-time held-out metric ≥ targets; convergence ≥ targets corpus-wide.
- Full corpus run with per-law scorecards + a flagged-failure queue.
- Outputs: point-in-time query + a versioned corpus artifact, public-domain / NLOD.

## Non-goals

- Not a byte-perfect typography/footnote facsimile — statutory *text content*.
- Not pre-1877 (outside NB Lovtidend).
- Not Lovdata Pro as a data source (validation oracle only; its files never enter
  the published corpus).

## For the `goal` skill

Optimize the pipeline against the harness (`source/eval/`) under the hard rules
above. The eval harness is the reward; the held-out set is the guard against
gaming. Prerequisites (roadmap Phase 0): the eval harness runs and the held-out
Lovdata-Pro set exists. Until then, iterate on **convergence with inputs
restricted** — but do not report success without the point-in-time metric.
