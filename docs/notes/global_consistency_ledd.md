# Global-consistency ledd application — experiment spec (2026-10-16)

**Status: PROPOSED, not built.** Distilled from the 2026-10-16 design discussion + three measured
dead-ends (applicator, renumber matcher, local content-splice). This is the one principled, untested lever
for the 44% ledd/sub-provision gap.

## The problem, restated
Sub-provision ops ("§X annet ledd skal lyde: …") fail when the engine can't locate the target unit — on
OCR bases with no ledd boundaries, or on heavily-amended provisions where position/ordinal addressing has
drifted. The deterministic engine flags these (correctly, flag-don't-fabricate). The 44% is dominated by
these flags.

## Why the obvious fixes failed (measured)
- **Applicator / local content-splice:** locating by a LOCAL similarity signal (margin to one provision's
  ledds) is too weak. Strict margin gate → abstains ~89% (59/66 on vphl). Unconditional accept → 0% correct,
  **83% clobber** of already-correct provisions (§5-5a 1.0→0.31). No threshold reaches 90% correct at useful
  coverage. (scratchpad/ledd_calibration.py, ledd_experiment.py)
- **Crucial reframe:** these are all MISPLACEMENTS (verbatim text, wrong slot), not fabrications — the
  verbatim-span invariant already makes fabrication ~0. The dial we actually need to move is misplacement.

## The idea: today's text as a GLOBAL CONSISTENCY CONSTRAINT (not a local selector)
The amendments form a dated chain `base → op₁(d₁) → … → opₙ → today`. If every op is applied at its correct
location, forward-replaying ALL ops must reproduce **today's text exactly**. So today's text certifies the
whole op-STRUCTURE at once. Use it to disambiguate each hard op's location: pick the location assignment
whose full forward-replay reproduces today — a far stronger filter than a local margin (it rejects the
§5-5a clobber, because clobbering §5-5a makes the chain miss today).

Past states then come from date-filtering the SAME resolved ops (query at t → replay ops with date ≤ t), so
nothing makes the past look like the present.

## What is searched vs frozen
- FROZEN: the op set (never invent/drop/reorder an op to hit today); each op's `new_text` (verbatim span
  from the amendment act).
- SEARCHED: only the discrete LOCATION (which ledd/nr/punktum) of genuinely-ambiguous ops. A small
  combinatorial search per provision, not free text.

## Guards (acceptance rules — encode these)
1. **Verbatim-span invariant** on every candidate state: every char is a substring of the base or a named
   amendment. Fabrication stays ~0 by construction (except the 7% INSERT-punktum — keep those strict or
   require a substring-verifiable split).
2. **Today is comparator-only, never a source.** No char of current text may enter a provision. (A today-leak
   is systematic past-corruption — looks 100% right today, wrong at every past date — categorically worse
   than random misplacement, and NOT covered by a "90%" budget.)
3. **Held-out PAST test, excluded from fitting.** Fit locations to today (train); report correctness on
   2005-CD / Lovdata-Pro dates (test). Overfitting-to-today is detectable because it breaks the past.
   Cross-validate across dates/laws so "90%" is measured, not asserted.
4. **Calibrated 90% acceptance (HS tolerance).** Accept a disambiguation when its calibrated confidence
   clears the threshold at which measured past-gold correctness ≥ 90%. Tag accepted-but-inferred provisions
   with provenance; the strict/published layer and the anti-gaming gate stay verbatim-certain-only.
5. **Bounded ambiguity budget = a diagnostic.** If today is only reachable by contortion (many ambiguous
   picks forced a particular way), that is a MISSING-OP (coverage) signal → flag, don't spend freedom to
   force the match.
6. **Date causality + idempotency.** op dated d applies only to state from ops ≤ d; flag double-application.
7. **Score on amended provisions / past gold**, never on never-amended provisions (they match today trivially
   and prove nothing).

## Architecture
Fitting is an OFFLINE build step (today as a build-time selector, like the existing LLM caches); resolved
locations are cached as verbatim pointer rows. The RUNTIME reconstruction stays answer-key-free (G1 holds) —
it just replays the resolved, date-ordered, verbatim ops.

## First experiment (measure before building general)
vphl, held-out dates 2009/2014/2018/2021. For provisions with flagged hard ops: enumerate candidate location
assignments, keep the one whose forward-replay best reproduces today AND keeps every span verbatim, accept
only at the past-gold-calibrated ≥90% point, and measure the PAST-gold pit (on vs off) on dates excluded from
calibration. Success = past pit rises with <10% misplacement on the held-out dates. If the global constraint
doesn't uniquely resolve (provisions reach today regardless of the ambiguous pick), that is the honest
negative result → the gap is a genuine ceiling, and coverage (more segmentation / CD discs) is the only lever.
