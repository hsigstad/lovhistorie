# lovhistorie

Reconstruct the **point-in-time text of Norwegian statutes** (*gjeldende rett* over
time) — "the law as it read at date *t*" — from public-domain sources, as an
**owned, publishable** corpus.

**Current focus:** **Phase 0** — build the evaluation framework and assemble the
held-out Lovdata-Pro ground-truth set. Autonomous work starts once the eval harness
runs and ground truth exists.

- Success criteria + metrics: `docs/evaluation.md`
- The autonomous goal (for the `goal` skill): `docs/goal.md`
- Phased plan: `docs/roadmap.md`
- Ground-truth download task (Henrik, manual): `docs/ground_truth.md`
- Full technical background (from the vague feasibility work): `docs/notes/statutory_law_versioning.md`

**Approach:** original enactment + every amendment, from **Norsk Lovtidend** (NB,
public domain, 1877→present) + the free **NLOD** current dumps. **Not** Lovdata Pro
— that is a validation oracle only, and its downloads never enter the published
corpus.

**Layout:** `source/` (scrape / parse / eval), `docs/`, `build/`, `data/`. Migrated
from `projects/vague`: `source/scrape/nb_lovtidend.py`,
`source/parse/{endringslov,nlod_recipe}.py`, `source/eval/reconstruction_qa.py`.

**Data policy:** `data/ground_truth/` (Lovdata Pro) is **eval-only, never
redistributed**. Published outputs come solely from public-domain sources.

**Git:** commit straight to `main`, stage files by name. No GitHub remote yet
(will likely be a public repo eventually, like `hsigstad/politica`).
