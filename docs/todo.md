# Todo

## Next engine work (the real remaining lift)

- [ ] **Amendment coverage — THE pre-2001 lever (confirmed by OCR experiments 2026-08-12).**
  Correcting OCR (deterministic OR LLM) barely helps; the residual gap on "never-amended"
  provisions is REAL missing amendments (e.g. skifteretten→tingretten 2002 court reform,
  wording changes) whose amending acts our gazette parser didn't resolve. Three sub-levers:
  (a) **name→datokode map** — resolve "endr. i aksjeloven" style name citations;
  (b) **omnibus acts** — "endr. i X, Y og enkelte andre lover" amend MANY laws but
  `gazette.py` extracts only the first/none target — parse ALL targets per act;
  (c) **blanket terminology reforms** — sweeping renames (skifteretten→tingretten) applied
  across all laws; may need special handling. FIRST STEP: quantify how much of the
  pre-2001 gap each sub-lever accounts for before building.
- [ ] ~~OCR/LLM correction, multimodal re-OCR~~ — TESTED + DEPRIORITISED (2026-08-12,
  see done.md): safe but low ceiling; OCR is a minor contributor.
- [ ] **Evaluate `martgra/lovdata-pipeline` §/ledd/chapter parser** (external, 2026-08-12)
  for the omnibus-act / `§N-M`-heading structuring lift — deterministic parts only, no RAG/LLM.
  See `docs/notes/external_source_repos.md`.
- [ ] **Missing/renumbered provisions — the large structural lever (measured 2026-08-12).** The
  biggest failing bucket is current provisions ABSENT from recon: added post-base via add-ops we
  don't apply, or shifted by `nåværende § X blir § Y` renumbering (kjøpsloven 125 missing; vphl
  ~45 "cascade-empty" where every later ledd edit then flags too). Resolve add/renumber ops so the
  provisions exist. Higher yield + lower risk than the ledd engine.
- [ ] ~~**ledd engine — finish insert/nr/punktum ops.**~~ MEASURED + DEPRIORITISED 2026-08-12
  (see done.md): true convergence ceiling is only ~56 provisions and they are the *riskiest*
  (INSERT `nytt … punktum` needs legal-sentence segmentation → fabrication risk). Not worth it vs
  the missing-provision lever. Keep flag-don't-fabricate.
- [ ] **DECISION (Henrik): adopt a per-source τ?** evaluation.md/lessons #6 prescribe OCR-calibrated
  τ (~0.90) for pre-2001 OCR laws + report the distribution. Measured lift: split-τ (clean@0.98,
  OCR@0.90) = 0.485 vs 0.431 flat. Legitimate (documented), but moves the headline number, so it's
  a metric-policy call, not engine work.
- [ ] **Preserve nr/bokstav markers in whole-provision replacement bodies.** `endringslov`/
  `gazette` strip `1. 2.` / `a) b)` markers from `§X skal lyde` / `Kapittel N skal lyde`
  bodies, so a later `nr. 4 skal lyde` finds no list and flags (~77 flagged nr ops). The
  ledd *engine* already handles these when markers are present — this is upstream.
- [ ] **Unnumbered-ledd on OCR bases** — `parse_provisions` collapses whitespace, so
  pre-2001 laws (unnumbered ledd) lose ledd boundaries and the engine can't split them.
  Preserve line breaks in the OCR base to enable ledd editing there (LTI already does this).
- [x] ~~**Fallback base source for hole-year laws** — kjøpsloven (1988) and rettsgebyrloven
  (1982) enactments fell in NB digitisation holes.~~ DONE 2026-08-12: recovered from PD NB
  *booklets* (særtrykk) as SNAPSHOT bases with `base_as_of` (see done.md). Not enactment —
  they bake in early amendments and reconstruct dates ≥ their ajourført boundary; earlier
  dates flagged. Remaining gap is post-snapshot add-ops/ledd edits (amendment coverage), not base.
- [ ] **PD booklets as a public-domain point-in-time VALIDATION set** (follow-up from the base
  recovery). Each NB law særtrykk is a dated snapshot ("Ajourført senest …") = the same thing
  Lovdata-Pro historical versions give us, but free and redistributable. Could supplement/replace
  the encumbered oracle for check-2. Needs: (a) a catalog sweep of available booklets per law×year,
  (b) held-out partitioning (a booklet used as a base for law L must NOT also validate L),
  (c) OCR-calibrated τ (booklet-OCR vs recon-OCR is OCR-vs-OCR). Opportunistic coverage only.
- [ ] Resolve true **ikrafttredelse dates** (bodies say "trer i kraft <date>"); `--build`
  currently uses the act date as `date_in_force_resolved` (first approximation).

## Follow-up — extend to forskrifter

- [ ] **Extend the pipeline to sentrale forskrifter** (currently lover-only). Sources
  and structure are identical, so most of the reuse is free: the Lovtidend delta
  stream already carries `sf-…` acts alongside `nl-…`; `gjeldende-sentrale-forskrifter.tar.bz2`
  is the current consolidated base; and `sondreskarsten/norwegian-laws` already versions
  ~5,123 forskrifter back to the 2001 floor (the source zip has the `historie/` wordings).
  Work needed: (a) add a few forskrifter to the eval/ground-truth set (they're not scored
  today), (b) flip the recipe filter — `source/parse/nlod_recipe.py` currently *drops*
  res./forskrift instruments as noise, but for forskrift-as-target the amending instrument
  *is* a forskrift/resolusjon. Post-2001 first (nearly free given Sondre's corpus); pre-2001
  forskrifter inherit the same clean-base / OCR issues as pre-2001 laws.

## Manual (ground truth for the eval)

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
