# lovhistorie

Reconstruct the **point-in-time text of Norwegian statutes** (*gjeldende rett* over
time) — "the law as it read at date *t*" — from public-domain sources, as an
**owned, publishable** corpus.

**Current focus:** **Blocked on 2 decisions — see `BLOCKER.md`.** Phase 0 eval
framework is DONE: the completion gate (`python -m source.eval.gate`, one exit code =
anti-gaming guards + corpus convergence) works, and the method is validated on clean
post-2001 data (tjenesteloven 27/33). But the 9-law dev set is 61% pre-2001 laws with
no clean base, so the 0.97 gate is unreachable (ceiling ~0.39) until Henrik decides
(1) a clean pre-2001 source (Lovdata CD discs recommended) and (2) splitting the gate
into post-2001-clean vs pre-2001 tracks (`gate.py`). Convergence this session:
0.043 → 0.094.

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
