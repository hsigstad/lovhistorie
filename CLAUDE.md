# lovhistorie

Reconstruct the **point-in-time text of Norwegian statutes** (*gjeldende rett* over
time) — "the law as it read at date *t*" — from public-domain sources, as an
**owned, publishable** corpus.

> **READ `docs/notes/lessons_and_pitfalls.md` FIRST.** Nearly every "hard wall" or
> "obvious cause" in this project turned out to be a *measurement* bug, not a
> reconstruction limit. That doc lists the misunderstandings we already made and
> corrected — don't repeat them.

**Current focus (as of 2026-08-12):** the full **Norsk Lovtidend Avd. I 1877–2000**
harvest is DONE (`source/scrape/harvest_lovtidend.py` → `data/lovtidend_text/`); the
gazette structuring parser (`source/parse/gazette.py`), pre-2001 amendment stream, ledd
engine, and the post-2001 + 5 pre-2001 OCR bases are all built. **Convergence 0.043 →
0.344** (`python -m source.eval.gate`), guards green. The **point-in-time deliverable
metric is unblocked and validated** (aksjeloven 2024 ≈ convergence) — see
`docs/ground_truth.md` + the lessons doc for the Lovdata-Pro acquisition flow. **Next
lift:** amendment coverage for the pre-2001 half (name→datokode + omnibus + blanket
terminology) — a set of small deterministic fixes; OCR/LLM correction was TESTED and
DEPRIORITISED (see lessons doc). Newest work log: `docs/done.md`; open items: `docs/todo.md`.

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
