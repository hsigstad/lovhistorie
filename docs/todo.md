# Todo

## In progress — NB Lovtidend harvest (2026-08-10, ~16h)

- [~] **Full harvest of Norsk Lovtidend Avd. I 1877–2000** running:
  `python -m source.scrape.harvest_lovtidend` → `data/lovtidend_text/`. Resumable; on a
  restart just re-run the same command. Check `data/lovtidend_text/_harvest.log` /
  `_progress.txt`. When done: ~1,033 items / ~144k pages cached.

## Next engine work (the real remaining lift)

- [ ] **Build the endringslov *structuring* parser** — split the harvested gazette into
  per-act enactment + amendment units keyed by ikraft date; feed `replay`. This is the
  substantive project. `source/parse/endringslov.py` already parses a *single* amendment
  block (validated on Lovtidend 1991 Nr. 3) — needs the upstream act-boundary /
  running-header-dedup layer over the raw per-page harvest.
- [ ] Fix `source/scrape/build_enactment.py` regexes: `_HEAD` for `§N-M` chapter-section
  headings, and `_NEXT_LAW` for the two-column reflowed next-law boundary (blocks
  aksjeloven-style laws). Then build the 5 recoverable pre-2001 dev-law bases.
- [ ] Flag holes + kjøpsloven (1988) as known-missing (law/amendment)-years — "flag,
  don't fabricate". Optional fallback source: norgeslover.no scanned PDFs.
- [ ] Re-derive block ops from LTI XMLs to remove the 4000-char `new_text` truncation
  (119 vphl provisions lost).
- [ ] Extend the ledd engine (unnumbered ledd, punktum/bokstav/nr.) — the flagged 55%.

## Follow-up — extend to forskrifter

- [ ] **Extend the pipeline to sentrale forskrifter** (currently lover-only). Sources
  and structure are identical, so most of the reuse is free: the Lovtidend delta
  stream already carries `sf-…` acts alongside `nl-…`; `gjeldende-sentrale-forskrifter.tar.bz2`
  is the current consolidated base; and `sondreskarsten/norwegian-laws` already versions
  ~5,123 forskrifter back to the 2001 floor (Sungho's zip has the `historie/` wordings).
  Work needed: (a) add a few forskrifter to the eval/ground-truth set (they're not scored
  today), (b) flip the recipe filter — `source/parse/nlod_recipe.py` currently *drops*
  res./forskrift instruments as noise, but for forskrift-as-target the amending instrument
  *is* a forskrift/resolusjon. Post-2001 first (nearly free given Sondre's corpus); pre-2001
  forskrifter inherit the same clean-base / OCR issues as pre-2001 laws.

## Henrik — manual (ground truth for the eval)

- [ ] **Download Lovdata Pro historical versions** for the ground-truth eval set.
  Spec: `docs/ground_truth.md`. Save each as **HTML** ("Historiske versjoner" →
  date → save-as-HTML). Drop them in the repo root (I'll file + parse them) or
  directly into `data/ground_truth/<datokode>/<YYYY-MM-DD>.html`.
  - Priority 8: aksjeloven `1997-06-13-44` (started — 2003 done), rettsgebyrloven
    `1982-12-17-86`, avtaleloven `1918-05-31-4`, oreigningslova `1959-10-23-3`,
    kjøpsloven `1988-05-13-27`, verdipapirhandelloven `2007-06-29-75`,
    mesterbrevloven `1986-06-20-35`, tjenesteloven `2009-06-19-103` (negative control).
  - Then: tinglysingsloven `1935-06-07-2`, utleveringsloven `1975-06-13-39`,
    Statens pensjonskasse `1949-07-28-26`, bioteknologiloven `2003-12-05-100`,
    utlendingsloven `2008-05-15-35`, Oppgaveregisteret `1997-06-06-35`.
  - ~3–5 dates per law, spread across its life, bracketing major amendments.
  - This unblocks the point-in-time metric → autonomous work via the `goal` skill.
