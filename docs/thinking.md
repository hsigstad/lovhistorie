# Thinking

Speculative directions and working hypotheses. Nothing here is decided; when a
direction is adopted it moves to `docs/decisions.md`, worked results to
`docs/done.md`, open work to `docs/todo.md`.

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

### First experiment (calibration before commitment)

1. Prototype the line-label segmenter on **one clean law** (vphl or tjenesteloven): measure
   boundary precision/recall vs the known LTI structure and confirm the substring guarantee
   holds (fabrication rate provably ~0).
2. Then run it on **one pre-2001 OCR law** (foreldelsesloven or avtaleloven) and check the
   held-out point-in-time deliverable moves with no per-version regression.
3. Only then consider making the LLM path the default for OCR-base laws.
