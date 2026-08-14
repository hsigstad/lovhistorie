# Todo

## Next engine work (the real remaining lift)

> **Ceiling reality (2026-08-13, from `loss_breakdown`).** The 0.97 gate is **not reachable
> on this dev set**: hitting it needs +355 of the 381 misses (~93% of *everything*), but 8%
> is char-OCR noise with a proven low ceiling (lesson 4) and 29% is the risky ledd/renumber
> tail. Best case, stacking every safe + risky lever, tops out ~**0.90–0.94**. This is
> expected — `goal.md` calls the 0.97 target "provisional until the held-out set is
> assembled", and the *real* deliverable bar is the held-out point-in-time metric (blocked on
> the manual Lovdata-Pro download below), not convergence. **Do not lower `gate.THRESHOLD`
> without Henrik sign-off** (that is the anti-gaming "loosen the bar" move). Keep working the
> safe capture lever; when it is exhausted, the honest stop is a `BLOCKER.md`, not chasing OCR.

- [ ] **Amendment coverage — THE lever, now QUANTIFIED (2026-08-13, `source.eval.loss_breakdown`).**
  Correcting OCR (deterministic OR LLM) barely helps; the residual gap on "never-amended"
  provisions is REAL missing amendments (e.g. skifteretten→tingretten 2002 court reform,
  wording changes) whose amending acts our gazette parser didn't resolve. Three sub-levers:
  (a) ~~**name→datokode map**~~ — MEASURED ~ZERO 2026-08-13 (see done.md): across all 1033 harvested
  issues, TOC-title name-citation of the dev laws is 0 (avtale/foreld/rettsg/mester/kjøp), so a name
  map recovers nothing on the dev set. The pre-2001 residual is harvest COVERAGE + blanket reforms;
  (b) ~~**omnibus acts**~~ — MEASURED SMALL 2026-08-13 (see done.md): LTI stream already well-targeted
  (1/304 header rows mis-file a dev law); pre-2001 `I lov <dev-cite>` secondary headers only 3/6/1 for
  avtale/foreld/kjøp. Not worth a full-stream rebuild; the pre-2001 gap is (a)/(c), not omnibus;
  (c) **blanket terminology reforms** — sweeping renames (skifteretten→tingretten) applied
  across all laws; may need special handling.
  **Quantified (loss_breakdown, 381 misses):** the single biggest, SAFEST lever is amendment
  *capture* — **184 of 381 misses (48%) have ZERO op** in our stream targeting that provision
  (`uncaptured-amdt` 100 + most of `base-missing` 84, whose examples §9a/§38a-c/§5a/§15a are
  uncaptured `ny §` adds). Solving capture is deterministic + flag-safe and would move
  convergence ~0.56 → ~0.75–0.80. NEXT: start with omnibus multi-target in `gazette.py` +
  applying `ny §` adds. Run `python -m source.eval.loss_breakdown` for the current attribution.
- [ ] ~~OCR/LLM correction, multimodal re-OCR~~ — TESTED + DEPRIORITISED (2026-08-12,
  see done.md): safe but low ceiling; OCR is a minor contributor.
- [ ] **Evaluate `martgra/lovdata-pipeline` §/ledd/chapter parser** (external, 2026-08-12)
  for the omnibus-act / `§N-M`-heading structuring lift — deterministic parts only, no RAG/LLM.
  See `docs/notes/external_source_repos.md`.
- [x] ~~**Missing/renumbered provisions — the large structural lever.**~~ MEASURED 2026-08-12: it
  was mostly a DENOMINATOR artifact — 138/1008 "missing" were treaty annexes (CISG/limitation
  convention) incorporated by reference, un-reconstructable from Lovtidend. Fixed by scoping the
  convergence denominator to statutory provisions (see done.md). Real remaining tail is small:
  a few OCR base-drops (kjøpsloven §1/§50/§71, foreldelsesloven §15a) + ~35 renumber-targets.
- [ ] **Renumber-target provisions (~35, the hard residual).** `nåværende § X blir § Y` structural
  ops move a provision to a new id; we flag them, so the target id is absent from recon. Handling
  needs tracking id remaps over time (a provision's id is version-dependent). Fiddly; modest yield.
- [ ] **OCR base-drops (small, safe).** A handful of real statutory provisions are dropped by base
  OCR extraction — kjøpsloven §1/§50 (l/1 confusion: "§ l."), §71; foreldelsesloven §15a. Fix the
  `_HEAD` regex / booklet page span. ~4 provisions, low risk.
- [ ] ~~**ledd engine — finish insert/nr/punktum ops.**~~ MEASURED + DEPRIORITISED 2026-08-12
  (see done.md): true convergence ceiling is only ~56 provisions and they are the *riskiest*
  (INSERT `nytt … punktum` needs legal-sentence segmentation → fabrication risk). Not worth it vs
  the missing-provision lever. Keep flag-don't-fabricate.
- [x] ~~**DECISION (Henrik): adopt a per-source τ?**~~ DONE 2026-08-12: τ_OCR=0.90 DERIVED from the
  never-amended OCR-fidelity distribution (4:1 rescue-ratio floor), applied per-source, dual-reported
  (OCR-calib + strict) in the gate. Convergence 0.499→0.562 (statutory). See done.md.
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
- [ ] **PD booklets as a public-domain point-in-time VALIDATION set — VIABLE; needs a
  heading-tolerant parser (NOT an OCR problem).** Corrected 2026-08-13 (I first mis-blamed OCR —
  the project's signature trap). Catalog sweep found unused PD snapshots: aksjeloven 2001
  (`digibok_2023030748042`), foreldelsesloven 1992/1993, kjøpsloven 1991, rettsgebyr 1993. The
  aksjeloven-2001 cross-check (ajourført exactly 2001-01-01, vs the Lovdata-Pro 2001 GT we hold)
  looked bad at first (26% coverage, mean 0.60) — but that was **`parse_provisions` failing to
  segment garbled `§ 1 —3` headings, not OCR**: the OCR carries 279 of 293 headings; the strict
  `_HEAD` regex matched only 71. **Repairing the heading token (same OCR) → 94% coverage (250/265),
  median 0.991, mean 0.846, 63% ≥0.98 / 73% ≥0.90.** So the booklet DOES reproduce the oracle.
  DONE 2026-08-13: heading-tolerant parser built (`_repair_headings`, line-anchored, opt-in via
  `parse_provisions(repair_headings=True)`, booklet-only — the clean gazette bases don't benefit and
  a global repair regressed aksjeloven, so it's off by default; regression-clean). aksjeloven-2001
  booklet now parses 95% coverage / median 0.994 vs the 2001 oracle. NEXT:
  - (a) ~~**bank booklets as a PD validation set** — a loader yielding `{para: text}`.~~ DONE
    2026-08-13: `source/eval/booklet_gt.py` (registry + cache), aksjeloven-2001 scored vs the oracle
    end-to-end — content faithful (booklet↔oracle median 0.994) but a ~9pp same-verdict gap
    (see done.md). Two residual items before it's a drop-in numeric oracle substitute:
    - ~~11 segmentation fails~~ PARTLY DONE 2026-08-13: `_is_failed_extraction` flags/drops 8/11
      unambiguous garbage (zero collateral); gap 9.1→7.3pp. Recovering the rest needs layout-aware
      OCR (footnote-zone detection lost in flattened ALTO) — five deterministic re-extraction
      attempts all regressed, so not worth more heuristics; 3 fragments remain flagged-absent.
    - **OCR-vs-OCR τ** (now the DOMINANT residual) — scoring an OCR reconstruction against a scanned
      booklet double-counts OCR; needs a lower τ than the clean-oracle 0.90, or a born-digital edition.
  - (b) **held-out partition** — a booklet used as a base for law L must NOT also validate L
    (encoded: `booklet_gt.BOOKLETS` omits kjøpsloven/rettsgebyr, whose booklets ARE their bases).
  - (c) re-test **aksjeloven-2001 as a cleaner BASE** now the parser lands (median 0.994 vs 2001 GT
    beats the noisy gazette base's 149/293 — build it with base_as_of=2001-01-01 and compare).
  - (Booklet-as-cleaner-BASE for foreldelse still unproven: 1993 base-only 14/33 @0.9 vs gazette 18/33.)
- [x] ~~**Block-header leak + sub-unit repeals**~~ DONE 2026-08-13: `_BLOCK_HEADER` missed the "Lov [av] <cite>"
  header form, leaking allmennaksjeloven ops into aksjeloven; fixed + enabled sub-unit repeals (safe subset).
  Convergence 0.655 → 0.662 (+6, kjøpsloven), zero τ-regression, guards PASS (see done.md).
- [ ] **Sub-provision REPLACE/ADD (ledd `… skal lyde`) — the deferred +3, blocked on ledd-engine idempotency,
  NOT in-force.** Enabling `whole_only=False` now nets +3 but with 3 replacement regressions (§21-15/§5-27/§16-9)
  that are DOUBLE-APPLICATION (a whole-provision rebuild + an in-force sub-op on one §; the ledd engine isn't
  idempotent). PROVEN not-in-force: all three acts are triggered/in force per the in-force index. Needs an
  idempotent `ledd.apply` (detect the change is already present, skip) before `whole_only=False` is clean.
- [x] ~~**In-force resolver (built the index; wire for point-in-time).**~~ DONE 2026-08-14 (see done.md):
  `source/parse/inforce.py` resolves TRUE ikrafttredelse dates (act's own `dateInForce`, else the triggering
  `sf-` "(Delt) ikraftsetting av lov …" resolution) — 2,322/2,882 acts resolved, 1,179 later than passage;
  wired into `lti_amendments` (`date_in_force_resolved`), convergence unchanged 0.662 / guards PASS / zero
  regression, point-in-time correctness demonstrated (kjøpsloven §7 repeal withheld until its true 2002-07-01).
  REMAINING (the follow-ups below).
  - [ ] **Per-provision partial scope for "delt ikraftsetting"** — act-level resolution assigns the earliest
    trigger date to ALL of a split act's ops, so a provision in a LATER (or never-triggered) batch is
    over-applied (e.g. aksjeloven `2019-03-15-6` §4-13 → resolved 2020-01-01 but that § came later). Parse the
    "§§ X trer i kraft …, resten senere" scope from each resolution body for full fidelity. Refines the
    point-in-time tail; not a convergence lever.
  - [ ] **Extend the resolver to the EXTERNAL amendment stream** (`amendments.jsonl.gz`), not just the LTI
    re-parse stream — resolve `date_in_force_resolved` by `act_refid` at load in `pipeline.load_ops` (or a
    one-off patch pass), so the whole point-in-time deliverable benefits, not only the omnibus-recovery rows.

## Measurement side (point-in-time fairness)

- [ ] **`lovdata_html.py` GT-parse length inflation — clean laws are scored PESSIMISTICALLY.**
  Found 2026-08-14 tracing tjenesteloven: recon matches the CURRENT NLOD text at convergence 0.955,
  but the Lovdata-Pro GT provisions parse ~10-20% LONGER (e.g. §2 recon≈327 ≈ current, GT=402), so the
  point-in-time "near misses" (0.90-0.98) are an oracle-parse difference, not reconstruction error.
  Likely `lovdata_html.py` includes inline notes / cross-ref nodes the NLOD dump omits. Investigate
  whether the GT parser should drop the same editorial nodes (symmetric with the current-text reader)
  — would lift clean-law point-in-time toward its true fidelity. Measurement-side; tread carefully (it
  moves the deliverable number, so treat like a metric change — sign-off + no-regression guard).
- [x] ~~**strip_annotation completeness (nynorsk + in-force footnotes)**~~ DONE 2026-08-14 (see done.md):
  +6 convergence, point-in-time μ 0.855→0.857, tjenesteloven §28 → 1.0, zero regression, signed off.
- [ ] **tjenesteloven §29 "Endringer i andre lover" — editorial redaction, FLAGGED not chased.** Lovdata
  consolidates the consequential-amendment list to "– – –"; our base carries the enacted enumeration.
  Reproducing "– – –" would overfit the oracle's editorial convention. If ever worth it, handle like a
  convention annex (scope out "Endringer i andre lover"-type provisions), not by trimming the base.

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
  - **Prediction — PARTLY CONFIRMED 2026-08-13.** aksjeloven (OCR base) point-in-time at held-out
    2001/2003 = rate 0.52-0.54 / mean ~0.80, ≈ its convergence 0.556 → the engine reconstructs past
    states as well as the current one (no date-specific failure); point-in-time is now wired into
    `status` (see done.md). STILL TO DO: 1-2 HIST versions for a CLEAN-base law (vphl `2007-06-29-75`
    conv 0.66 / tjenesteloven `2009-06-19-103` conv 0.90) — the decisive test that the deliverable is
    STRONG for clean laws (expect point-in-time ≈ their higher convergence) and OCR bases are the drag.
