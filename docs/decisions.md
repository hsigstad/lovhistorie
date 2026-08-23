# Decisions

Committed design choices.

## 2026-08-23 — KEEP endringslov's regex parser (it is OFF the convergence path; retiring it is a guard-redesign task, not a mechanical delete)

**Decision.** `source/parse/endringslov.py` (the legacy pre-2001 amendment-body regex parser) and
`gazette.build_amendment_ops` STAY. This is a deliberate keep, not a pending "to-kill".

**Why keeping it costs nothing on convergence.** The reconstruction path (`pipeline.load_ops` →
`replay`) does NOT read endringslov's output (`pre2001_amendments.jsonl.gz`). Pre-2001 amendments that
DRIVE convergence come from `gazette_recovered` — the LLM localize-then-verify stream. endringslov's
output is consumed only by `amendments.load_for()` → the **G3 base-integrity guard** and legacy eval.
So its regex is already retired from reconstruction; its own (non-)robustness on pre-2001 OCR is now
irrelevant to convergence. It only has to supply G3 a coarse *set* of amended provisions, which does
not need perfect parsing. Convergence will therefore NOT require endless tuning of this regex — it is
frozen and off-path.

**Why we don't just delete it.** Deleting it forces G3 to source its "provisions that should differ"
set elsewhere. The intended swap (G3 `amendments.load_for` → `load_ops`) BREAKS G3: it introduces
false-positive contamination flags on provisions unchanged since enactment (foreldelsesloven §2/§20:
base==current, they converge, yet a harmless recovery op marks them "amended"). G3 tests text alone
and cannot distinguish "never substantively changed" from "base copied from the answer"; the external
amended-set happened to be the right should-differ proxy precisely because it excludes unchanged
provisions, and `load_ops` (carrying recovery ops on those provisions) pollutes it. Retiring
endringslov thus requires REDESIGNING G3's contamination test (e.g. gate on the op's own new_text
differing from base, or curate an explicit should-differ set) — a correctness task, not a cleanup.
Until that is designed + validated, endringslov stays. See `docs/done.md` 2026-08-23.

## 2026-08-16 — Prefer LLM over regex for any fragile STRUCTURAL judgment; keep two deterministic firewalls (HS)

**Decision (HS).** Do NOT optimize for LLM cost — the corpus is a bounded, one-time, cached pass, so
where an LLM makes life easier or more robust it wins. Concretely: any regex that makes a *structural
judgment* that can be wrong — heading detection, block/section attribution, payload boundaries, op
parsing — should move to the LLM (boundaries-only). The trigger to migrate a given regex is its
*reliability*, not its cost: a simple regex that provably never mis-decides (e.g. `gazette.datokode`,
the `I lov <cite>` section split IF verified) may stay because it is the reliable *mechanical* half;
a complex one that mis-decides (e.g. `_BLOCK_HEADER`, which mis-attributed finansforetaksloven §21-15
to vphl) goes to the LLM.

**Two firewalls stay deterministic — NOT for cost, for correctness guarantees:**
1. **Text slicing.** The LLM LOCATES (line/anchor); deterministic code SLICES the source. This is why
   we can assert *"0% of corpus content is model-generated; every provision is a verbatim source
   slice"* — the publishability guarantee. The LLM must never emit the statutory text itself.
2. **The eval metric** (`metrics.similarity`, the gate). An LLM judge there is loosening the
   anti-gaming bar. Scoring stays deterministic + fixed.

So the shape is "LLM locates/parses, deterministic code executes (slice) and scores." Migrate fragile
regexes freely; never move the two firewalls.

## 2026-08-14 — The only fundamental barriers to ~100% are OCR errors and source genuinely absent from public-domain archives (no new excuses)

**Principle (HS).** For POINT-IN-TIME reconstruction, only two things are fundamental limits on
reaching ~100% fidelity:
1. **OCR character errors** in the public-domain source text (Norsk Lovtidend / booklet OCR). We
   slice the source verbatim and deliberately do NOT LLM-correct characters (that reintroduces
   fabrication), so the reconstruction is only as clean as the OCR. This is a FLOOR, not a wall —
   reducible by better/multimodal OCR or by anchoring never-amended provisions to a clean later
   text — and it is ZERO for clean-base (born-digital LTI/NLOD, post-2001) laws (vphl enactment
   scores 0.997).
2. **Source documents genuinely absent** from the public-domain archives — the handful of NB
   digitisation hole years (1891, 1976, 1980, 1982, 1984, 1987–1989). Even these often have a
   fallback (booklets/særtrykk already rescue kjøpsloven/rettsgebyr), so the truly-unrecoverable
   residual is tiny.

**Everything else is a solvable engineering or data problem — a bug to fix, not an excuse.** Per
`loss_breakdown`, the non-OCR misses are: name/omnibus/blanket citation resolution and harvest
coverage of *available* issues (the LLM amendment extractor + more harvesting), ledd/sub-provision
application (LLM boundaries + similarity alignment — validated 2026-08-14), and renumber/move
id-remap (similarity matching). None is fundamental. We commit to treating each as fixable and NOT
inventing a new "it's inherently hard" excuse. The project's signature trap is exactly that —
mistaking a measurement/segmentation/coverage bug for a hard wall (`docs/notes/lessons_and_pitfalls.md`).

**One honest measurement caveat (not an excuse).** Convergence is scored vs the current NLOD text and
point-in-time vs the Lovdata oracle, both of which carry editorial apparatus (footnotes, "– – –"
redactions, convention annexes). We strip/scope these symmetrically (annexes out of scope; footnote
tables dropped; provenance stripped) so "100%" means clean STATUTORY content, not the oracle's
editorial layer. Reaching ~100% requires the target to be clean too — which is a measurement-hygiene
task we own, not a reconstruction limit.

## 2026-08-14 — Adopt LLM boundaries-only segmentation for OCR-base laws (base first, amendments phase-2)

**Question (HS):** the deterministic convergence levers are exhausted (~0.62–0.67 ceiling) and the
biggest remaining drag is the pre-2001 OCR tail. Almost every failure we diagnose is *segmentation*
(where a provision/ledd/amendment starts and ends), not OCR characters and not content. Can an LLM
help without risking fabrication in a corpus whose whole value is being an owned, faithful,
publishable reconstruction?

**Decision — yes, under a strict boundaries-only discipline.** The LLM locates STRUCTURE (provision
heading line numbers, or — for line-break-poor sources — verbatim head/tail anchors) and labels units;
deterministic code slices the source. The model emits only coordinates and labels, **never statutory
text**, so every provision/payload string is a verbatim source slice.

- **Content fabrication is structurally impossible** — asserted at build time (the substring guarantee);
  the residual failure is a *mislocated boundary*, which is bounded and self-detecting.
- **Deterministic invariants** (monotonic, non-overlapping, coverage, heading-matches-id) repair or FLAG
  bad boundaries — `flag-don't-fabricate` applied to structure.
- **G1 preserved** — the model sees only public-domain OCR, never the current/oracle text.
- **Reproducible** — extraction is cached + Pydantic-validated + audited via llmkit
  (`source/llm/`); the segmented base is a frozen build input, not a gate-time call.

**Evidence (docs/done.md 2026-08-14):** base segmenter beats the hand-tuned regex on the hardest
documented case (aksjeloven-2001 booklet **192 vs 153** @≥0.90, 100% source-faithful) and end-to-end in
the real pipeline (avtaleloven convergence **30 → 33/45**, gate **0.6695 → 0.6731**, all guards PASS).
Amendment structure validated in isolation (**27/27** target laws vs the regex parser's 6; ops exact;
payloads source-verified via line-labels 80% or anchors 96%). Similarity-matching recovers renumbers
deterministically as a complementary tool.

**Alternatives rejected:**
- *More regex tuning* — diminishing returns; a fragile per-law stack that generalises poorly.
- *LLM generating statutory text* — reintroduces fabrication; defeats the corpus's purpose.
- *LLM-as-judge for scoring* — that is loosening the anti-gaming bar; the char-identity metric stays
  deterministic. The LLM is reconstruction-side only.

**Scope + sequencing.** (1) Base segmenter is PRODUCTIONISED and wired opt-in per law via
`build_enactment.LLM_BASE_LAWS` (avtaleloven live; extend to the other weak OCR laws one at a time, each
gated). (2) Anchor mode for line-break-poor sources. (3) Phase-2: amendment-side op-extraction for
pre-2001 gazette endringslov. (4) `source/parse/align.py` for similarity-based renumber/ledd matching.

## 2026-08-14 — Retire the regex heading stack ONLY after full OCR-law migration (not yet)

**Question (HS):** now that the LLM base wins, is the old regex heading code (`parse_provisions`
heading-finding, `_HEAD`, `_repair_headings`, `_GARBLED_SECT`) dead — delete it?

**Decision — not yet; it is still load-bearing.** As of 2026-08-14 only avtaleloven uses the LLM base.
The regex stack remains the path for **8 of 9 base builds** — the 4 other gazette laws (oreigningslova,
aksjeloven, foreldelsesloven, mesterbrevloven) via `build()`, the 2 booklets (rettsgebyr, kjøpsloven)
via `build_booklet(repair_headings=True)` — plus `source/eval/booklet_gt.py`. Deleting now would break
the pipeline. (Note: `gazette.py`'s amendment-stream regex is a *separate* concern, addressed by
phase-2, not by this decision.)

**Retirement condition (tracked, not forgotten).** Migrate laws into `LLM_BASE_LAWS` one at a time,
each confirmed by the gate (convergence up, guards green, base 100% substring-verified). When
`LLM_BASE_LAWS` covers every OCR-base law AND the booklet path is migrated (or its GT re-derived), the
heading-finding regex (`_HEAD`/`_repair_headings`/`_GARBLED_SECT` and the heading branch of
`parse_provisions`) becomes dead and is deleted then — git history preserves it, and this entry records
what it was and why it went. Until then it stays.
