# RESOLVED 2026-08-10 — decisions made, harvest running (kept for the record)

The original blocker (below the line) claimed the 0.97 gate was unreachable because the
dev set is 61% pre-2001 with "no clean base" and NB OCR is "too lossy" (ceiling ~0.39).
**Investigation on 2026-08-10 showed that diagnosis was wrong on mechanism**, and Henrik
made the two decisions. This file is retained as history; the pipeline is NOT blocked on
a human anymore.

## What the investigation found
- **NB gazette OCR is clean** (~0.99 where a provision is untouched; antiqua, not fraktur,
  pre-1900). The low pre-2001 scores were NOT OCR noise.
- **The real gap is the 2001 cliff hitting twice**: LTI (`data/lti/`, 2001+) supplies
  neither pre-2001 enactment bases **nor** the pre-2001 amendment (endringslov) stream.
  Amendments are scattered across every issue, so only a full gazette harvest recovers them.
- **Two engine/metric bugs, not data**: (a) `metrics.similarity` used difflib's default
  `autojunk=True`, silently collapsing long-provision similarity toward 0; (b)
  `build_enactment.py` regexes can't parse `§N-M` chapter-section headings or the
  two-column reflowed next-law boundary.
- **NB coverage is broadly complete 1877–2000** except holes **1891, 1976, 1980, 1982,
  1984, 1987, 1988, 1989** → **kjøpsloven (1988) is unrecoverable from NB**; the other 5
  pre-2001 dev laws are fine (rettsgebyrloven via its 1983 gazette-appearance year).

## Decisions (Henrik, 2026-08-10)
1. **Metric fix** — `source/eval/metrics.py` now uses `autojunk=False` (correctness fix,
   not a loosening; signed off in the docstring).
2. **Full harvest approved** — `python -m source.scrape.harvest_lovtidend` pulls the
   digitised **Norsk Lovtidend Avd. I 1877–2000** (1,033 items / ~144k pages / ~0.3GB,
   public-domain) into `data/lovtidend_text/` (gitignored). Newest-first, page-resumable.

## Remaining work (no human needed for 1–2)
1. Fix the two `build_enactment.py` regexes (`§N-M`, reflowed next-law boundary).
2. **Build the endringslov *structuring* parser** — split harvested gazette into per-act
   enactment + amendment units keyed by date, feed replay. This is the substantive lift.
3. Handle holes + kjøpsloven: flag those (law/amendment)-years as known-missing
   ("flag, don't fabricate"); optionally seek a fallback source (norgeslover.no PDFs).
4. (Henrik, manual) download Lovdata-Pro held-out ground truth for the deliverable
   point-in-time metric — see `docs/ground_truth.md`.

---

# BLOCKER (original, 2026-08-07) — superseded, see above

# BLOCKER — the 0.97 gate is unreachable on this dev set (needs a Henrik decision)

The pre-2001 dev laws had no enactment base in hand and NB OCR was assumed too lossy to
reach τ=0.98. The 2026-08-10 investigation overturned the "too lossy" premise: OCR is
clean; the true limiter was the missing pre-2001 amendment stream (now being harvested)
plus the metric/parser bugs listed above.
