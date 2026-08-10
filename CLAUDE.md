# lovhistorie

Reconstruct the **point-in-time text of Norwegian statutes** (*gjeldende rett* over
time) — "the law as it read at date *t*" — from public-domain sources, as an
**owned, publishable** corpus.

**Current focus:** **Harvesting the pre-2001 source corpus.** The old "0.39 ceiling /
OCR too lossy" blocker was overturned 2026-08-10 (see `BLOCKER.md`): NB gazette OCR is
clean; the real gap is that LTI (2001+) lacks BOTH pre-2001 enactment bases AND the
pre-2001 amendment stream. Henrik approved (1) a metric fix (`metrics.py` autojunk=False)
and (2) a full harvest of **Norsk Lovtidend Avd. I 1877–2000** from NB (public-domain,
~1,033 items / ~144k pages) — running via `source/scrape/harvest_lovtidend.py` into
`data/lovtidend_text/`. **Next real lift:** the endringslov *structuring* parser
(split harvested gazette into per-act enactment+amendment units → replay). Phase-0 eval
gate (`python -m source.eval.gate`) is DONE and remains the `/goal` condition.

- Success criteria + metrics: `docs/evaluation.md`
- The autonomous goal + the machine-checkable condition: `docs/goal.md`.
  The `/goal` condition compiles to one exit code: `python -m source.eval.gate`
  (exit 0 ⟺ anti-gaming guards pass **and** convergence ≥ threshold). The
  reconstruction entrypoint the loop improves is `source/parse/pipeline.py`.
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
