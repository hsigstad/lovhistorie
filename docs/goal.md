# Goal (for autonomous execution)

## The goal, precisely

Build a pipeline that reconstructs the **point-in-time text of Norwegian in-force
statutes** ("the law as it read at date *t*") from **public-domain sources only**
(Norsk Lovtidend via Nasjonalbiblioteket + the NLOD current dumps), such that, on
the **held-out Lovdata-Pro eval set** ([evaluation.md](evaluation.md)):

1. per-provision character similarity ≥ **0.98** for ≥ **95%** of sampled
   `(law, date, provision)` points (point-in-time accuracy); **and**
2. corpus-wide convergence-to-current ≥ **0.98** for ≥ **95%** of provisions; **and**
3. coverage ≥ **90%** of in-force laws fully processed;
4. with **every failure flagged** — no silent errors.

(Targets are provisional until the ground-truth set is assembled; the *shape* of
the goal is fixed.)

## Why this goal is meaningful and checkable

- **Meaningful** — it is exactly the object the research needs (law-in-force at a
  date), **owned and publishable** (public-domain + NLOD), not encumbered.
- **Checkable** — metrics are defined against ground truth; the **held-out eval
  set** makes success unambiguous and un-gameable.
- **Bounded** — a clear pass bar; *done* when the metrics hit target.

## Definition of done

- Eval harness **green** (all metrics ≥ targets) on the held-out set.
- A full corpus run produced, with per-law scorecards and a flagged-failure queue.
- Outputs: a **point-in-time query** (law as of date) + a **versioned corpus
  artifact**, released under public-domain / NLOD terms.

## Non-goals (scope discipline)

- **Not** a byte-perfect facsimile of typography / footnotes — statutory *text
  content* is the target.
- **Not** pre-1877 (outside NB Lovtidend coverage) — handled separately only if a
  concrete need arises.
- **Not** Lovdata Pro as a *data source* — it is the validation oracle only, and
  its downloaded versions never enter the published corpus.

## For the `goal` skill

This is the target for autonomous iteration: **run the pipeline → measure against
`evaluation.md` → improve the weakest metric → repeat** until the pass bar is met.
The eval harness is the reward signal; the held-out set is the guard against
gaming. Prerequisites before autonomy starts (see [roadmap.md](roadmap.md) Phase 0):
the eval harness runs, and the ground-truth set exists.
