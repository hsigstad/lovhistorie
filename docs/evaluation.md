# Evaluation — how we measure success

**This is task #1.** The pipeline can only run autonomously if success is
*measurable* and hard to game. This doc defines the metrics, the ground truth, and
the pass bar. Everything else (the pipeline build) is downstream of this — the
[goal](goal.md) is defined against these metrics.

## The three checks (cheapest/broadest first)

### 1. Convergence to current — free, exhaustive, internal consistency
For each law: replay `original enactment + all amendments (in ikrafttredelse
order)` → a reconstructed "current" text. Compare to the authoritative **current
NLOD** text, provision by provision (normalized character similarity).

- **Metric — convergence rate**: fraction of provisions with similarity ≥ τ.
  Reported per-law and corpus-wide.
- **Why**: if we can't reproduce *today's* text from enactment + amendments, the
  pipeline has an error (OCR, parse, or a missing / mis-applied amendment). Free,
  and covers the whole corpus.
- **Also yields OCR fidelity** on provisions that never changed (see check 3).
- **Limitation**: convergence is *necessary but not sufficient* — a pipeline could
  converge while getting *intermediate* versions wrong (two errors cancelling). So
  it is the broad screen, not the verdict. Hence check 2.

### 2. Point-in-time accuracy vs Lovdata Pro — gold standard, held-out
**The decisive test.** For a held-out set of `(law, date)` pairs, compare our
reconstruction *as of that date* to the manually-downloaded **Lovdata Pro**
historical version (see [ground_truth.md](ground_truth.md)).

- **Metric — point-in-time accuracy**: per-provision character similarity,
  aggregated (mean + the full distribution, not just the mean).
- **Held out**: the pipeline is *never tuned* on this set — this prevents
  overfitting and gaming.
- This directly answers "is our *historical* text correct?", which convergence
  cannot.

### 3. OCR fidelity — free, per provision
Provisions unchanged over a law's life: our extracted gazette text vs the current
NLOD text → the OCR error distribution. Isolates OCR quality from replay quality.
(Seed implementation: `source/eval/reconstruction_qa.py`.)

## Ground truth

| Source | Role | Cost | Used by |
|---|---|---|---|
| **Current NLOD text** | authoritative endpoint | free, whole corpus | checks 1, 3 |
| **Lovdata Pro historical versions** | gold standard for past dates | manual, held-out sample | check 2 |
| Sondre repo per-commit diffs | correct post-first-amendment; per-op dev cross-check only | free | dev, *not* a headline metric |

## Pass criteria (the bar)

Proposed targets — finalize once the ground-truth set exists:

- **Point-in-time accuracy** ≥ 0.98 mean similarity on the held-out eval set, with
  ≥ 95% of provisions ≥ 0.98.
- **Convergence rate** ≥ 0.98 for ≥ 95% of provisions corpus-wide.
- **Coverage** ≥ 90% of in-force laws fully processed (located + extracted +
  replayed); the remainder **flagged**, never silently wrong.
- **Zero silent failures**: every non-converging provision is flagged with a reason
  (OCR / parse / missing-amendment / locate-fail).

## Reporting (the eval harness produces these each run)

- **Per-law scorecard**: convergence rate, n provisions, per-provision flags.
- **Corpus dashboard**: convergence distribution, coverage, point-in-time accuracy
  on the eval set, fidelity curve by era.

## Anti-gaming (the hard rules — see [goal.md](goal.md))

The optimizer will exploit anything unspecified. These close the shortcut doors:

- **Target is historical, not current.** The success metric is point-in-time
  (check 2) against **held-out** past-date versions. "Reproduce current" is
  gameable by `return current text` — so convergence (check 1) is a **dev proxy
  only**, never the success bar.
- **Input restriction (the reconstruct contract).** The pipeline function
  `reconstruct(datokode, as_of) -> {para: text}` receives **only** the enacting act
  (gazette) + the Lovtidend amendments. The current text and the historical
  versions are held by the **harness alone** as answer keys — never passed to the
  pipeline, and no network lookup of law text at eval time. This defeats
  "return the answer" even for convergence.
- **Deterministic, no LLM, flag-don't-fabricate.** Reconstruction is pure
  rules/regex (reproducible/auditable); no LLM in the path (it could fabricate
  passing text); an op/provision the pipeline cannot handle is **flagged**, never
  filled with guessed text.
- **Held out means held out** — never tune or select on the eval set (laws *or*
  dates). Develop on a separate dev set.
- **Fixed normalization** — documented in `source/eval/metrics.py`; "similarity"
  can't be inflated by quietly loosening it.
- **Report the raw distribution**, not just the mean — a good mean can hide a bad
  tail, and the tail is where wrong law text lives.
