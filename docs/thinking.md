# Thinking

Speculative directions and working hypotheses. Nothing here is decided; when a
direction is adopted it moves to `docs/decisions.md`, worked results to
`docs/done.md`, open work to `docs/todo.md`.

---

## Current open questions

- **Does the boundaries-only LLM segmenter hold on the pre-2001 OCR tail?** Calibrated on
  the aksjeloven-2001 booklet (69→253 provisions, 100% substring-verified, matched the
  hand-tuned regex); the decisive test is a genuinely messy pre-2001 OCR law with the
  held-out point-in-time deliverable as the guardrail (no per-version regression).
- **Is amendment *capture* the real remaining lever?** `loss_breakdown` attributes 184 of
  381 dev-set misses (48%) to provisions with *zero op* in our stream — the amending act
  wasn't resolved from the gazette. Solving capture (omnibus multi-target + `ny §` adds) is
  deterministic and flag-safe; how far does it move convergence in practice?
- **Can the ledd engine be made idempotent enough to flip `whole_only=False`?** The deferred
  +3 is blocked on double-application, not in-force; the similarity-skip prototype works on
  vphl §3-1 but hasn't been productionised into `ledd.apply`.
- **Is the point-in-time deliverable proven for clean-base laws?** It is validated on only 10
  held-out (law × date) versions across three laws (aksjeloven OCR + vphl/tjenesteloven
  clean). We need a couple of clean-base Lovdata-Pro HIST versions to show the deliverable is
  *strong* where the base is clean (expect point-in-time ≈ the higher convergence).
- **Which redrafted law anchors the downstream validation?** The arveloven case is waved off
  (post-reform window too short — see Miscellaneous); the validation needs a different
  substantially-redrafted statute.

## Possible directions

The two live technical bets are written up in detail below:

- **LLM structural segmentation, boundaries-only** — locate structure (kapittel/paragraf/
  ledd + noise), never generate text; deterministic slicing preserves the substring
  guarantee. Highest value on the pre-2001 OCR tail and for scaling past the dev set.
- **Ledd reconstruction = LLM boundaries + similarity alignment** — the 35% `engine-gap:ledd`
  bucket; similarity targets the version-correct ledd, gives idempotency for free, and
  verifies the applied result by end-state alignment.

Beyond those: **extend the pipeline to sentrale forskrifter** (sources and structure are
identical; the Lovtidend delta stream already carries `sf-…` acts — see `docs/todo.md`), and
**scale the segmenter toward all ~756 statutes**, where the pre-2001 long tail is exactly
where deterministic parsing is weakest.

## Connections to literature

This pipeline is the *data primitive* for downstream legal-economics work, so the literature
connection is on the consumption side:

- **Legal-complexity / ambiguity measures.** Point-in-time law versions enable the
  legal-complexity and linguistic-ambiguity measures emerging in recent legal-economics work,
  and a point-in-time citation knowledge graph (cases ↔ laws ↔ provisions ↔ regs ↔ forarbeider).
  Our contribution is that these can be computed on *owned, public-domain* text back to 1877,
  not a licensed corpus. (Specific references belong in the downstream research project, which
  carries the bibliography — this pipeline has none.)
- **Existing open reconstructions.** `sondreskarsten/norwegian-laws` and `norgeslover.no` seed
  history with *today's* text as a 2001 baseline, so they are silently wrong for provisions
  unamended by 2001. Building from the public-domain gazette instead is the methodological
  point of difference (see `README.md`).

## Methodological sketches

- **Zero-fabrication by construction.** Every corpus character traces to a source character:
  the LLM emits only coordinates/labels, so content fabrication collapses into (bounded, often
  self-detecting) localization error. Enforced by an always-on *substring assertion* plus
  deterministic invariants (monotonic, non-overlapping, covering, heading-matches-number).
- **Calibrate on clean laws before the OCR tail.** Compare LLM boundaries to the known-true LTI
  structure on vphl/tjenesteloven; only trust the messy tail once it matches there. Every
  eval-touching change carries the held-out point-in-time no-regression guard.
- **Similarity over ordinal for sub-provision targeting.** Ledd ordinals are version-dependent;
  `argmax metrics.similarity(new_text, ledd)` finds the right target robustly and yields
  idempotency (best ≈ 1 ⇒ already applied ⇒ skip). Detailed below.
- **Per-source τ.** The OCR-calibrated τ (0.90) is *derived* from the never-amended OCR-fidelity
  distribution, not chosen to flatter the number; clean-base laws keep the strict 0.98.

## Ideas to explore later

- **Ledd-level LLM boundaries** (phase 2) — the same segmenter one level down; harder than
  provision-level, needed for the ledd engine on OCR bases.
- **Amendment-side LLM op-extractor** across the pre-2001 gazette harvest — parse each amending
  act into source-verified ops (validated in isolation: 27/27 omnibus targets, payloads
  substring-verified).
- **Targeted pre-2001 re-harvest / layout-aware OCR** for the residual base-drops (footnote-zone
  detection lost in flattened ALTO).
- **Downstream products** — the ambiguity/complexity measures and the case↔law citation graph
  the point-in-time corpus unlocks.

## Miscellaneous notes

- **Validation-case pivot (arveloven → other laws).** The inheritance-law validation Sungho
  scoped is unlikely to work — only ~40 appellate cites, the DA dump ends 2017 (all pre-reform),
  and the new arveloven took force 2021, so the post-reform window is too short. Pivot the
  validation toward the redrafting of *other* substantially-rewritten laws.
- **Adjacent tooling.** Sungho has a *separate* Norwegian-laws parser (759 Lovdata-accessible
  laws) with preliminary linguistic-trait extraction — distinct from the court-decision parser,
  and a useful parallel corpus for the ambiguity measure.
- **The gate threshold is provisional.** The 0.97 bar is not reachable on this dev set (real
  ceiling ~0.90–0.94, `loss_breakdown`); the *real* bar is the held-out point-in-time metric.
  Do **not** lower `gate.THRESHOLD` without Henrik sign-off — that is the anti-gaming "loosen
  the bar" move.

---

## LLM-assisted structural segmentation — boundaries only, never content (2026-08-14)

### The reframe

Almost every reconstruction failure we have diagnosed is **segmentation, not
content**. The signature trap of this project (see `docs/notes/lessons_and_pitfalls.md`)
is that a "hard OCR wall" turns out to be a heading- or boundary-parse bug:

- the booklet `_HEAD` regex matched only 71 of 279 headings (aksjeloven-2001), fixed by a
  heading-tolerant repair to 250/265;
- tjenesteloven §29 over-captured the whole "Endringer i andre lover" tail because the last
  provision's block was unbounded;
- pre-2001 OCR bases collapse unnumbered ledd because `parse_provisions` flattens whitespace;
- garbled `§N-M` headings ("§ 1 —3") need a bespoke `_GARBLED_SECT` repair;
- `_HEAD` / `_repair_headings` / `provisions_ordered` are a growing regex stack that is
  fragile precisely where the OCR is messy.

The OCR **characters** are largely fine (NB gazette OCR is ~0.99 where a provision is
untouched). What is hard is deciding **where each unit starts and ends** in noisy text.
That is a structure problem, and it is the biggest remaining deterministic drag (the
pre-2001 OCR tail) and the breadth gap for scaling past the dev set toward all statutes.

### The idea

Have an LLM read the raw source text and return, for each structural unit (kapittel,
paragraf, ledd, and the footnote/running-header/amendment-instruction noise), its
**location and label** — NOT its text. Deterministic code then slices the source at those
locations to produce `{paragraf_id: text}`. The unit text is always `source[start:end]`,
a verbatim slice of the public-domain source.

This is the strongest form of the governing principle for any LLM use here:

> The LLM may locate structure and choose among source-grounded candidates. It may never
> generate statutory text. Every output character of the corpus traces to a source
> character; the LLM sees only public-domain sources, never the consolidated/oracle text
> (preserves gate guard G1).

### Why it is safe: zero content fabrication by construction

Because the LLM emits only coordinates and labels, content fabrication is not merely
unlikely — it is **structurally impossible**. We can assert mechanically that every
provision string is a contiguous slice of the source (the *substring guarantee*), and
report: *0% of corpus content is model-generated; the model only located boundaries.*

Fabrication therefore collapses into **localization error** — a misplaced boundary. That
is a different, far more benign failure than invented law: it is bounded (a boundary shift
moves a few characters, it cannot conjure a provision), and it is largely self-detecting
(see invariants). This is `flag-don't-fabricate` applied to structure.

### Design: do NOT ask for character offsets

LLMs cannot reliably emit exact integer character positions — tokenization means
"`char_start=4213`" comes back plausible but off by N. Two reshapes keep the model off both
*content* and *arithmetic*:

1. **Line-numbered input → per-line labels (preferred).** Prepend line numbers to the OCR
   and ask the model to label each line: `heading-paragraf` (+ the §-number), `heading-kapittel`,
   `ledd-start`, `body`, `footnote`, `running-header`, `amendment-instruction`. Deterministic
   code splits between labeled lines. Per-line classification is what LLMs are good at and
   char-counting is what they are bad at, so this plays entirely to the strength. It also
   subsumes the footnote / running-header stripping we currently do with regex and
   `metrics.strip_annotation` — those become label classes.
2. **Verbatim anchors → deterministic `find()`.** The model returns, per unit, the exact
   heading string plus the first and last ~6 words verbatim; code `str.find()`s them to get
   offsets. Anchors are short verbatim quotes (reliable); an anchor not found *exactly* in
   the source is itself a fabrication flag.

Either way the model's numeric output is line indices (small, reliable) or nothing.

### Self-checking invariants (deterministic, no ground truth needed)

Because the output is coordinates/labels, hard invariants catch most localization errors
without an oracle — encode them in the extraction schema's validator (llmkit / Pydantic):

- boundaries **monotonic** and **non-overlapping** (`start_i < end_i ≤ start_{i+1}`);
- units **cover** the text — gaps are flagged (dropped content or a missed unit);
- each `§N` slice must **begin with a heading matching N** (label-vs-content cross-check;
  catches a mis-numbered slice);
- provision numbers **sequential** — a jump (`§12 → §14`) flags a missed `§13`.

### Measurement — the fabrication/accuracy harness

1. **Substring assertion** — always-on, mechanical: every provision text is a contiguous
   source slice. This *is* the zero-fabrication proof.
2. **Calibrate on CLEAN laws first.** Run on vphl / tjenesteloven, where we hold both the
   true LTI structure and the Lovdata ground truth. Compare LLM boundaries to the known-true
   ones → boundary precision/recall and resulting per-provision similarity. Only if it
   matches the deterministic LTI parse on clean laws do we trust it on the OCR tail —
   *before* pointing it at ambiguous pre-2001 text.
3. **Held-out point-in-time as guardrail** — must improve the deliverable with zero
   per-version regression, the same discipline used for every eval-touching change this
   session (the per-provision no-regression guard).
4. **Confidence → flag, never fill.** Low-confidence line labels flag exactly as the
   deterministic engine does; the flag-rate is itself a reported quality number.

### Where it earns the most, and how it slots in

Highest value on the **pre-2001 OCR bases and the booklet snapshots** — the biggest
deterministic drag and the breadth gap. It slots in narrowly: it *replaces the
heading-finding step* inside `parse_provisions` (the fragile regex part) while keeping the
deterministic slicing (`provisions_ordered` already slices given an ordered boundary list).
So it is a bounded swap with a small blast radius, opt-in per law exactly like
`parse_provisions(repair_headings=True)` is booklet-only today. Clean LTI bases keep the
deterministic path (they do not need it); the LLM path is reserved for the messy tail.

### Why it could replace a lot

If calibration holds, one structure-only LLM pass could retire the `_HEAD` /
`_repair_headings` / `_GARBLED_SECT` regex stack for the OCR laws, fix unnumbered-ledd
segmentation, bound over-capturing final provisions (§29-type), and classify away footnotes
and running headers — several separate deterministic patches replaced by one measured
component, with a stronger fabrication guarantee than the regex stack ever had (the regex
stack can silently mis-segment; the substring assertion + invariants cannot silently
fabricate). It also generalises: the same segmenter is what scaling to all ~756 statutes
needs, since the pre-2001 long tail is where deterministic parsing is weakest.

### Open questions / risks

- **Long laws exceed context / output degrades.** Chunk by page or chapter with overlap;
  stitch deterministically; handle provisions split across chunk edges.
- **Ledd granularity.** Provision-level boundaries are the easy, high-value win; ledd-level
  boundaries (needed for the ledd engine) are harder and should be a second phase, still
  boundaries-only.
- **Consistency across runs.** Cache (llmkit) so the corpus is reproducible; treat the LLM
  output as a cached, audited build input, like the OCR itself — not a gate-time call.
- **The metric stays deterministic.** This is reconstruction-side only. No LLM-as-judge for
  scoring (that would loosen the bar); the char-identity metric is unchanged.

## Ledd reconstruction = LLM boundaries + similarity alignment (2026-08-14)

The biggest loss bucket is `engine-gap:ledd` (35% of misses) — sub-provision ops the engine
can't safely apply. Parsing them is easy; safe APPLICATION is the hard part, and it has three
sub-problems that LLM + similarity together solve:

1. **Ledd segmentation** — splitting a provision into its ledds. OCR bases collapse whitespace
   so ledd boundaries are lost. → the SAME boundaries-only LLM segmenter, one level down: locate
   ledd starts (line/anchor), slice deterministically. Each ledd is a verbatim source slice.
2. **Which ledd does the op target?** The instruction addresses by ORDINAL ("tredje ledd" = 3rd),
   but the ordinal is VERSION-DEPENDENT: if an earlier amendment inserted/removed a ledd, "3rd"
   at the op's date is not the 3rd in the base. → target by **text similarity**, not ordinal: for
   a REPLACE, the op's new text is a *modified* version of the ledd it replaces, so `argmax
   metrics.similarity(new_text, ledd)` finds it robustly. **Prototype (vphl §3-1, done.md
   2026-08-14): similarity picks the right ledd (0.89 vs 0.1–0.37 for the others); under a
   simulated earlier-insert the ORDINAL picks the WRONG ledd (0.37) while similarity still picks
   the RIGHT one (0.89).** Content-match is version-robust where the ordinal is not — the same
   lever as provision-renumber-by-text, one level down.
3. **Idempotency (the blocker for the deferred +3).** The double-application bug: a whole-provision
   rebuild + an in-force sub-op both touch a §, applying the ledd twice. → before applying a
   REPLACE, check `similarity(target_ledd, new_text)`; if ≈1 the op is ALREADY applied → SKIP.
   **Prototype: after applying, sim = 1.000 → re-application detects it and skips.** Idempotency
   falls straight out of similarity.

**Application rules (deterministic, fabrication-safe — content is always a source slice):**
- REPLACE: target = argmax-similarity ledd above threshold; if best ≈1 skip (idempotent);
  overwrite with the source-slice payload.
- INSERT ("nytt tredje ledd"): the new ledd has no existing counterpart, so place by ordinal,
  then VERIFY by end-state alignment (below); renumber following ledds deterministically.
- REPEAL: target = the ledd matching the repealed ordinal/content; remove; verify absence.
- **Verify (similarity):** after applying, align the reconstructed provision's ledds to the
  endpoint (current text / GT) 1-1 by similarity; a clean alignment accepts, a mismatch FLAGS
  (flag-don't-fabricate). The application is validated by alignment, never trusted blindly.

Net: the LLM locates ledd boundaries + parses the op (source-slice payload); similarity targets
the correct ledd (version-robust), gives idempotency for free, and verifies the result. No ledd
text is ever generated. This is how the 35% ledd bucket becomes safe to turn on.

### First experiment (calibration before commitment)

1. Prototype the line-label segmenter on **one clean law** (vphl or tjenesteloven): measure
   boundary precision/recall vs the known LTI structure and confirm the substring guarantee
   holds (fabrication rate provably ~0).
2. Then run it on **one pre-2001 OCR law** (foreldelsesloven or avtaleloven) and check the
   held-out point-in-time deliverable moves with no per-version regression.
3. Only then consider making the LLM path the default for OCR-base laws.
