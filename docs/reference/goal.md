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

## The machine-checkable condition (`/goal`)

The whole goal is compiled into one exit code:

```
python -m source.eval.gate     # exit 0 ⟺ done
```

`source/eval/gate.py` returns **0 only if** all three anti-gaming guards pass **and**
corpus convergence ≥ `THRESHOLD`:

- **G1 no-answer-key-import** — the reconstruction path (`source/parse/pipeline.py`
  and everything it imports) must not import the harness (`source.eval`) or hardcode
  the current dump. AST-enforced. This is hard rule 2 in code.
- **G2 runs-isolated** — with the answer-key dir physically removed, the current
  loader returns nothing yet `reconstruct()` still produces provisions → it provably
  doesn't consume the answer key.
- **G3 base-integrity** — an *amended* provision whose enactment base is identical to
  the current text means the base was seeded from the answer → fail (hard rule 1/2).
- **convergence** — `matched / ALL current provisions` (denominator is every
  provision, so "reconstruct fewer, easier provisions" can't inflate the score).

Exit codes: `0` PASS · `1` guards clean but convergence below threshold (keep
working) · `3` a guard tripped (a hard stop — something is gaming the metric, fix the
approach, don't chase the number). All three guards are verified to fire when cheated.

**This gate uses convergence, which is a strong-but-not-final signal (see below).**
The un-gameable *deliverable* bar is still the point-in-time held-out metric. So the
`/goal` condition for an autonomous run is:

> `python -m source.eval.gate` exits 0, **or** `BLOCKER.md` exists at the repo root
> describing a specific obstacle needing human input.

The `BLOCKER.md` disjunction is the honest stop: if the real ceiling sits below the
threshold, the run writes the blocker instead of grinding or fabricating.

## For the `goal` skill

Optimize the pipeline (`source/parse/pipeline.py`, chiefly `enactment_base` and the
`ledd` engine) against the gate under the hard rules above. The gate is the reward
and the guard in one. Prerequisites (roadmap Phase 0): the eval harness runs (done —
the gate) and the held-out Lovdata-Pro set exists (for the final point-in-time
metric). Iterate on **convergence with inputs restricted**; do not report the
*deliverable* done without the point-in-time metric, even when the gate exits 0.

## Working method — how we pursue the goal (added 2026-08-21)

**Aim, precisely:** iteratively improve the reconstruction metric on the **dev set**
using **general fixes only**, and continue until there is a **very good, specific
reason** a law cannot be improved further.

- The metric is dev-set convergence (and point-in-time), measured across **all 9 dev
  laws together** — never a single provision. One provision (e.g. avtaleloven §36) is
  a **diagnostic**, never the target: a fix that only helps one provision/law is the
  same trap as the brittle regexes we are removing.
- Every fix must be a **mechanism that generalizes**, validated on the dev set as a
  whole with an **A/B** showing it doesn't regress other laws — not a per-case patch.
- **"Very good reason we cannot improve"** = a documented external/structural limit,
  e.g. a NB digitisation hole (1984 is undigitised), a bundled-treaty annex
  incorporated by reference (un-reconstructable by construction), a genuine
  OCR-fidelity floor, or a harvest gap with no public source. **"The LLM missed it"
  is NOT such a reason** — that is a general-quality lever (better prompt, model,
  anchoring) to improve.
- **Loop:** run → per-law delta → diagnose the *general* cause of the largest
  residual → general fix → re-run. Stop only when the residual is all documented
  structural limits (then `BLOCKER.md`).

**Reconciling with Hard rule 3 (no LLM at runtime).** The LLM lives ONLY in the
**offline build** that produces the amendment/base streams (the same status as
OCR/harvest data prep), is **cached** (reproducible run-to-run), and is
**verbatim-anchored + flag-don't-fabricate** (it emits located source slices, never
generated text). The **runtime reconstruction** (`pipeline.reconstruct` → `load_ops`
→ `replay` → `ledd`) stays **deterministic**: it reads pre-built public-domain
`jsonl.gz`, uses no LLM and no answer key (G1/G2 enforce this). So rule 3's intent —
no LLM can fabricate or "recall" the answer at eval time — holds; the LLM only helps
*extract* public amendments offline, which a fully-deterministic (but brittle) parser
could also do. This interpretation is load-bearing for the current direction and was
CONFIRMED by HS (2026-08-21).
