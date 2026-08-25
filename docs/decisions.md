# Decisions

Committed design choices.

## 2026-08-24 — Capture-precision solved via CONTENT-AWARE application (+12 answer-free); the residual is RENUMBERING, not application

**Phase 0/1 (done).** The answer-free pointer regressions are MIS-ATTRIBUTED ops (content from another
law: oreign §11 skjønn, foreld §2/§20 forvaltningsloven), not no-ops. A standalone lexical/
corroboration precision filter FAILED (precision 0.03 — dev laws share generic legal vocabulary). The
fix is to move the precision judgment INTO application: `pointer_apply` is now CONTENT-AWARE (skips an
amendment whose NEW text is about a clearly different subject than the provision, judged from the
enactment). No separate filter, no extra cost. With answer-free scope (OCR-base laws only; ledd-dropped
candidates; op-coverage gate) this gives **587 -> 599/829 (72.3%), guards PASS** — a legit ~4x over
the prior +1..5, vs the gamed +41. Gains: oreign +4, rettsg +6, mester +3, kjøp +2, foreld +1.

**Phase 2 (reasoning escalation) REFUTED.** o3 == gpt-4.1 on aksje low-scorers (both 0.26, 1-2 ops) —
the residual is NOT mis-reasoning.

**Renumbering lever investigated and REJECTED as the big one.** Decomposed aksje's ~99 statutory misses:
only **3 are renumbering** (enactment content at a different current id, e.g. §11-10 lån -> current
§11-14); §11-10 was a misleading single example. The real breakdown: ~41 provisions with NO captured
ops (missing "ny §" inserts + provisions absent from our OCR base, e.g. §2-11), ~45 with partial/wrong
captures, ~16 in-base-same-id (OCR/terminology), ~11 captured-but-not-applied, 3 renumbered. §1-6 (added
by lov 2017-06-16-71) has 0 captured ops — a CAPTURE gap, not an application bug (0 aksje new-provisions
are captured-but-unapplied). So aksje is a HETEROGENEOUS CAPTURE-COMPLETENESS tail (missing amendment
ops + enactment-base gaps), NOT a single structural lever. Renumbering handling would recover ~3.

**Consequence.** Capture precision is DONE (content-aware application, +12 -> 599/829, 72.3% answer-free,
guards PASS). There is NO single clean "next lever": the remaining ~28% is a long heterogeneous tail
(missing amendment ops, enactment-base gaps, OCR, a few renumbers), each worth a handful of provisions —
capture/harvest/parse-quality grinding, which the "general fixes only" mandate rules out and which has
diminishing returns. The reconstruction MACHINERY is mature (application + precision solved). Recommend
consolidating the +12 (bake pointer_ops, refresh status/site) rather than chasing the tail.
`pointer_apply` content-aware + `build_pointer` committed; pointer_ops local (gitignored).

## 2026-08-23 — LLM holistic/pointer apply reconstructs mangled provisions, but ANSWER-FREE deployment is capture-precision-limited (piloted end-to-end)

**What works.** The deterministic ledd engine mangles sub-provision ops on unmarked OCR bases
(rettsgebyr §14: 24 captured amendments -> 0.09, a garbled splice). An LLM given base + ALL ordered
amendments reconstructs it: §14 -> 0.72 (gpt-4.1), 0.82 (o3). The cost problem (HS: no >$1000 corpus)
is solved by POINTER output (source.llm.pointer_apply): the model emits only references
({"amendment":N} / base anchors), deterministic code assembles VERBATIM source. That makes the "0%
fabricated" guarantee AUTOMATIC, collapses verification to a substring check, and cuts output ~30-100x
so mini/gpt-4.1 suffice — dev ~$0.5, extrapolated corpus ~$100 (vs ~$1000+ for free-text generation).

**The wall is SELECTION, and it is fundamental to answer-free operation.** Deploying this to raise
convergence requires deciding, PER PROVISION, whether to replace the deterministic result with the
pointer result. WITH the current text (select provisions that miss): +41 -> 628/829 (75.75%), zero
regression — but this READS THE ANSWER to choose WHERE, so a published corpus (no answer) cannot
reproduce it. It is gaming, not a deployable number. Every ANSWER-FREE selector tried nets only +1..+5
WITH regressions (vphl -4..-13, oreign/foreld -1): flags (ledd dropped an op), unmarked-base gate,
op-coverage comparison, and coverage(det)==0 all fail the same way. Root cause: a provision whose
deterministic recon incorporated NONE of its ops is EITHER "real amendments were dropped -> applying
helps" OR "base is already correct; the amendments were no-ops / mis-captured -> applying corrupts",
and these are INDISTINGUISHABLE without the answer. Overriding the second class regresses converged
provisions, offsetting the gains. The only thing the miss-based selector does that answer-free can't
is AVOID touching already-correct provisions — and "is it already correct?" IS the answer (convergence).

**Consequence.** 71% is NOT a fundamental INFORMATION limit (provisions reconstruct in isolation), but
it is near the answer-free DEPLOYMENT ceiling GIVEN CURRENT CAPTURE PRECISION. The binding blocker is
CAPTURE PRECISION — mis-attributed / no-op amendments that, when applied, corrupt already-correct
provisions — plus the arbitration problem, NOT the application method (which is solved) and NOT OCR
(refuted earlier). The real lever now is rigorous corroboration-filtered capture (remove
mis-attributions so applying-all-captured-ops is safe), which would let pointer_apply run answer-free
without regressions. `pointer_apply` / `holistic_apply` / `build_pointer` are committed as validated
infrastructure (pointer_ops NOT baked into the stream — answer-free net gain is not yet clean).

## 2026-08-23 — Re-OCR is NOT a convergence lever; the misses are AMENDMENT-bound, not OCR-bound (piloted)

**Finding.** A hypothesis that ~130 of the 242 dev misses were "enactment-base OCR-quality limited"
(word-splits, dropped letters, header-bleed) was PILOTED and REFUTED. Re-OCR'd all of oreigningslova
(1959-10-23-3) from the public page images with a vision LLM (source-only — it read only the images,
never the answer; G1-safe). Character quality improved exactly as predicted ("yt tola"→"lyt tola",
running-header garbage removed) — but **convergence did not move: 17/31 → 17/31, zero provisions
crossed threshold.**

**Why.** The misses are dominated by missing AMENDMENT CONTENT, not OCR:
- §4 (0.47): current has two ledd the enactment lacks (forvaltningslova §15 ref + tvangsfullbyrdelses-
  loven clause, added 1969 & 2015) + a terminology reform. Clean OCR moves it ~0.47→~0.48.
- §2 (0.70): the expropriation-purpose list grew 42→~54 items across 12 amendments.
- near-misses §22/§23 (0.86/0.88): re-OCR left them flat/slightly worse — small spelling/terminology
  gaps, not OCR noise.
- §11: its enactment base already scores 1.000 vs current — its miss was a BAD OP APPLICATION.

**Correction.** The earlier "~130 OCR-limited" estimate over-attributed to OCR from surface errors
(e.g. "yt tola") without checking that the DOMINANT difference in those provisions was amendment
content. Lesson: measure the dominant delta, don't infer a cause from a visible-but-minor defect.

**Consequence — priority order (OCR de-prioritised).** The binding levers are, in order: (1) amendment
CAPTURE completeness (missing added-ledd / list-expansion content — the tail-anchor extractor fix is
part of this); (2) amendment APPLICATION (sub-op ledd application; bad ops that corrupt a good base,
e.g. §11); (3) blanket TERMINOLOGY reforms (fan out across many provisions). Do NOT build the OCR
re-processing infrastructure — it was empirically shown not to move the metric. (A law that is
OCR-heavy AND lightly-amended could differ, but the most OCR-damaged dev law showed no gain, so the
burden of proof is on any future OCR claim: pilot one law end-to-end first.)

## 2026-08-23 — Pre-2001 gazette capture: UNBLOCKED + completable, but net-negative convergence (piloted end-to-end)

**Finding.** The pre-2001 amendment-capture lever (the one the OCR/terminology pilots pointed to) was
unblocked and run to completion on oreigningslova. Fixed the real capture bugs — date-only citation
resolution (7ad2cc4), name-based issue/act selection (segment_issue leaves date=None so datokode
matching failed), segment/localize model split (mini misses old-act mentions), and hang-hardening
(HTTP client timeout + per-issue SIGALRM + resume) so the sweep COMPLETES instead of hanging. Capture
yield rose ~7x (1 op/700 issues → the full oreign sweep captured 7 ops incl. real §2 list-additions).

**But convergence went 17/31 → 16/31 (−1).** The recovered pre-2001 ops are partial/fragmentary
sub-provision ops (list-item / ledd changes) that, gap-filled onto unmarked OCR bases, CORRUPT
provisions rather than converge them: §30 0.31, §1 emptied by an op with blank new_text. And the
heavily-amended provisions need ALL their amendments to converge (§2's list grew 42→54 across ~12
acts; a few captured fragments make it worse, not better). Residual capture failures also remain:
14 cite-unresolved (name-only / ambiguous-date cites) + 11 body-capped (huge omnibus acts truncated).

**Consequence.** Pre-2001 gazette capture is NOT a viable general convergence lever as-is — the ops
are too fragmentary and their partial application is net-negative. Three levers are now piloted and
rejected on the dev set (re-OCR, terminology reforms, pre-2001 capture); the dev set is at its
practical general-fix ceiling (consistent with the ~0.90-0.94 real-ceiling estimate). The capture
hardening is committed as reusable infrastructure (it correctly completes now), but the gazette ops
are NOT baked into the stream (they regress). Reviving this lever needs op-QUALITY work (whole-
provision capture, precise sub-op application, all-amendments-or-none gating), not more capture volume.

## 2026-08-23 — Blanket terminology reforms are LOW-payoff on the dev set (piloted)

**Finding.** Hypothesis: uncaptured blanket terminology reforms ("ordet «X» endrast til «Y»", e.g. the
2005 tvistelov "kjæremål»→«anke") fan out across many provisions and are a cheap high-yield lever
(the blanket stream holds only 1 op). PILOTED by scanning dev misses for recon carrying a superseded
term the current text dropped, then applying the swaps and re-scoring: only **5 candidate miss
provisions** (all rettsgebyrloven), and applying the swaps converts exactly **1** (§27a 0.89→0.94).
The rest (§5a 0.64, §23a 0.65, §27 0.81, §10 0.74) have larger amendment gaps a term swap can't close.

**Consequence.** Do not build a general blanket-reform capture/apply system for the dev set — the
payoff is ~1 provision. (Terminology changes here mostly arrive INSIDE full-provision rewrites, not as
standalone blanket-reform acts.) Together with the re-OCR pilot above, both "surface" levers are
ruled out; the binding constraint is amendment CAPTURE completeness + sub-provision APPLICATION.

## 2026-08-23 — Oracles are VALIDATION-ONLY, never a build input (current text, register, AND point-in-time HIST snapshots) (HS)

**Decision (HS).** No oracle may drive a RECONSTRUCTION decision. This covers the current/answer text
(G1 already), the amendment register (prior ruling), AND point-in-time Lovdata HIST snapshots. An
oracle may only MEASURE the deliverable (score convergence, score a held-out past state, audit
coverage) — never decide what the pipeline outputs (e.g. whether a bare-body op should overwrite a
provision).

**Why.** Two independent reasons:
1. **Circular / self-defeating.** If we had the point-in-time snapshot to validate an overwrite, we'd
   already possess the answer for that provision — nothing to reconstruct. We'd just publish the
   snapshot. The deliverable exists precisely because the snapshots aren't ours to redistribute.
2. **Voids the metric.** Convergence is an honest proxy ONLY while the build is source-only. The moment
   a reconstruction decision reads the answer, convergence measures "we peeked," not "the pipeline
   reconstructs."

**Consequence.** When a reconstruction step needs a judgment (e.g. §36's overwrite: is this a genuine
rewrite or a mis-capture?), the ONLY admissible signals are SOURCE-ONLY — the public enactment +
amendments and our own localize-then-verify confidence (corroboration across streams, verbatim
anchoring, dated amending act). If no source-only signal can make the call safely, the provision stays
an honest structural limit — reaching for the oracle is not an option. See replay.py's insert-only
comment (§36/foreld overwrite) and [[project_lovhistorie]] register ruling.

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

## 2026-08-24 — The residual tail is NOT idiosyncratic — but every general fix hits ONE wall: answer-free overwrite-safety

**Question (HS):** "let's not conclude a general-fix does not exist yet. I find it hard to believe the
remaining 28% are so idiosyncratic they can only be solved case by case."

**HS was right that it is not idiosyncratic — and that reframes the ceiling.** Decomposing the misses
surfaced a clean STRUCTURAL pattern, not a scatter of one-offs: **block amendments.** An amendment that
inserts/replaces a whole subsection ("Nytt avsnitt II skal lyde: II. <heading> § 11-10. … § 11-11. …")
is captured as ONE op keyed to a single paragraf, BURYING the other provisions inside its `new_text`.
`_CHAP_HEAD` split only "Kapittel"/"§"-opening blocks, never "avsnitt"/roman-heading blocks. A diagnostic
(`scratchpad/buried.py`) found **27 dev provisions** whose current text literally appears inside a
captured-but-unsplit block op (vphl 14, aksje 9, rettsg 2, kjøp 2). Real, general, quantified.

**The general fix was built and A/B-gated — and it revealed the actual wall.** Extending the splitter to
block amendments (instruction names `avsnitt|kapittel|del` AND ≥2 strictly-ascending `§ N.` headings, so
cross-references don't false-split):
- **Overwrite variant** (split pieces carry their heading → replay overwrites via the heading path):
  aksje **+3**, but vphl **−6** → **net −3**. Splitting introduces the block's (often stale) version and
  OVERWRITES provisions that had already converged via other ops.
- **Insert-only variant** (pieces stripped to bare bodies → replay's INSERT-ONLY path, adds new
  provisions but never overwrites): **net 0** (587, no regression, no gain). The aksje +3 came entirely
  from the overwrite cases (replacing an existing §); the genuinely-new inserted provisions don't cross
  τ (superseded/heading-mismatched). Reverted (net-0 code, not worth the surface).

**Why this matters — the single general wall.** Every lever explored this arc (content-aware pointer,
block-split, gazette capture) recovers some provisions ONLY by OVERWRITING an existing reconstruction,
and regresses others the same way. Deciding *which* overwrites help requires knowing whether the current
reconstruction is already right — **which is the answer.** So the tail is not a pile of idiosyncratic
cases; it is one general phenomenon — **answer-free overwrite-safety** — that is fundamentally
answer-limited. The content-aware pointer (+12) is the best answer-free *approximation* of that decision
we found (content-mismatch self-skip + op-coverage gate + OCR-base scope), which is exactly why it is the
only lever that netted positive. **Conclusion: ~72% (599/829) is the honest answer-free ceiling on this
dev set, and the barrier is a single well-characterised wall, not irreducible idiosyncrasy.**

## 2026-08-25 — Why ~72% is the ceiling: the miss decomposition, what's ruled out, and the ONE live lever

Session spent characterising the 230 misses (below per-source τ) rather than chasing the number, plus
probing whether any honest lever remains. Diagnostics in `scratchpad/{why,drill,quant,break,exploit,
cover,probe,probe2}.py`. Findings, so we don't re-litigate them:

**1. The 230 misses split three ways (`quant.py`):**
- **Assembly — 142 (62%):** we captured the pieces but deterministic replay can't reassemble them.
  Flagship: `rettsgebyr §14`, 23 correct captured amendments → 0.09, because the ledd engine can't
  locate "første ledd tredje punktum" in an unmarked OCR base. This is the *answer-free overwrite-safety*
  bucket (above).
- **Capture — 82 (36%):** the needed amendment isn't in our parsed ops (e.g. `aksje §1-6`, 0 ops).
- **Oracle — 6+ (3%):** the *target* isn't reconstructable. `oreigningslova §36`: enactment lists ~40
  repealed laws; current NLOD collapses the whole list to "– – –" (108 chars vs our faithful 13,636).
  No amendment produces that — it's a Lovdata editorial convention. We're *more* faithful than the answer
  key and score ~0. Closed by definition (fixing = importing the oracle = gaming).

**2. The overwrite wall, demonstrated on ONE provision (`break.py`).** `vphl §13-1` reconstructs
**perfectly (1.000)** deterministically. Running the LLM pointer on it gives **0.284** — it rebuilds the
provision as *"sentral motpart"* (the 2014 restatement) when today's §13-1 is *"børs"* (a 2018 block
restatement phrased as "Etter kapittel 10 skal del 4 til 6 lyde", change_type `unknown`). Blind
date-ordering gets it right *because* it doesn't reason; the LLM's content judgment — the very feature
that earns +12 on OCR bases — mis-resolves supersession here. Both outputs are verbatim, well-formed
statute; **answer-free nothing distinguishes them.** Ungated, this is the vphl −22. The gate is what
converts a net-negative tool into +12 and is simultaneously the ceiling.

**3. Public point-in-time snapshots investigated and REJECTED as oracle (this session):**
- *Wayback of lovdata.no* — the free site is a JS app; archived pages carry the index + chapter-1 only
  (~20 KB of ~200 KB). Unusable.
- *`sondreskarsten/norwegian-laws` `law-history`* — full consolidated text per law, backdated commits,
  public/NLOD. BUT its 2001 grunnlinje is **byte-identical to current** (verified) and it's forward-only,
  so any provision without a ≤D restatement shows *today's* text at date D. Its default-to-current is the
  exact failure mode we're validating against → actively misleading as an oracle (false-penalises correct
  reconstructions, false-rewards our characteristic bug). Fine only as an amendment-*stream* cross-check.
- The only independent public oracle left is the **Lovdata CD editions (~1995/2000/2005)**, now out of
  15-yr DB protection (2005 content is in NB's NCC but fragmented; native structured discs held by NB).
  Acquisition deferred by HS for now.

**4. "Relax G1 — use the final text to SELECT among verbatim-only assemblies" (HS) — analysed, rejected.**
The verbatim rule guards *fabrication*, but the binding risk is *selection/overfitting-to-today*. Two
reasons it fails: (a) it turns convergence from a blind measurement into a fit, moving all honesty onto
the point-in-time oracle we lack; (b) selecting by the *current* endpoint recreates the Skarsten bug —
`vphl §13-1` again: matching current picks 2018 "børs" even for a 2015 query where "sentral motpart" is
right → today's text at all past dates. The current text can only certify *today* (which NLOD gives free);
it cannot certify past states, which are the product. Salvageable *only* as a global consistency
constraint to recover generalisable op-structure, validated on held-out past snapshots — i.e. still needs
the CD oracle. (`exploit.py`/`cover.py`: only ~15% of provisions are ≥95% verbatim-present in the inputs,
so the guard does bound pure lookup — but that doesn't rescue the overfit-to-today problem.)

**5. A hypothesised "LTI parser drops harvested restatements" lever — INVESTIGATED AND REFUTED.**
An initial loose probe (`probe2.py`: "provision id near 'skal lyde' in any act whose text mentions the
law's datokode") suggested ~17/26 absent aksje provisions had restatements in the raw LTI that the parser
dropped — e.g. `aksje §2-10` seemingly restated by `nl-20150410-017 "Ny § 2-10 skal lyde:"`. **That was a
cross-law FALSE POSITIVE.** `nl-20150410-017` is *finansforetaksloven* (a NEW law being enacted); its
§2-10 is "Gjenforsikring/pensjonskasse" and has nothing to do with aksjeloven — the act only mentions
aksjeloven in a repeal-list and a cross-reference. Re-run PROPERLY (`parsemiss.py`/`sanity.py`/`final.py`)
by bounding to GENUINE aksjeloven amendment blocks via the parser's own `_BLOCK_HEADER`: 30 real aksje
blocks / 32 whole-provision instructions are detected (block detection works), and **0** target an absent
provision. **All 27 absent aksje provisions appear in NO genuine aksjeloven-headed block at all** — not
whole, not sub-unit, not chapter/avsnitt. So the parser is not dropping harvested aksje restatements; the
amending text simply isn't in an aksjeloven block in our LTI harvest. The lever does not exist.
LESSON: a datokode/`§ X`-proximity probe over multi-law acts is worthless — every big act mentions dozens
of laws and every law has a §2-10. Bound to the parser's real block header before claiming a parse-miss.

**Bottom line (corrected).** For answer-free convergence we are at a principled ceiling with **no clean
lever left**. Assembly (62%) is answer-limited (overwrite-safety). Oracle (3%) is gaming by definition.
Capture (36%) is NOT parse-misses — it is genuine harvest/coverage gaps (the amending act isn't in our
inputs, or amends via a reform-act header form we don't detect, or via renumbering where current §X ≠ the
historically-amended §Y) plus the block-add/renumber cases that hit the same overwrite wall. Raising the
number further requires either (a) more SOURCE harvest (expensive, network, diminishing, sometimes the
issue isn't digitised) or (b) an independent point-in-time oracle to safely arbitrate overwrites (the
Lovdata CD editions). Both are deferred. 599/829 (72.3%) stands as the honest answer-free ceiling.

## 2026-08-25b — Harvest-coverage lever investigated: post-2001 complete; pre-2001 gap years are NB digitisation HOLES (not fetchable). Lever closed.

Audited whether we've missed *available* Lovtidend issues (`coverage.py`/`pre2001.py`/`gapyears.py`).
Result: **post-2001 is 100% harvested** — every register-listed amending act for every dev law that
post-dates 2001 is in the LTI bulk (the ~17 unparsed ones are parse gaps: block/renumber/sub-unit forms,
already characterised). **Pre-2001**: our OCR holds ~1 Avd. I content volume/year for 1910–2000 EXCEPT
seven years entirely absent — 1976, 1980, 1982, 1984, 1987, 1988, 1989 — which carry ~18 dev-law amending
acts (oreign 8, rettsg 7, foreld 2, avtale 1).

**But those years are NB DIGITISATION HOLES, not harvest oversights.** Verified against the census
(`data/lovtidend_index.json`) that drove the 144k-page harvest: years we hold (1983/1985/1986) each have
~27 items titled *"Norsk lovtidend (trykt utg.). Avd. I. Lover og sentrale forskrifter"* (the content);
the gap years have **0** Avd. I content items — NB digitised only the *register/index* volumes
(*"register … : Avd. I, Avd. II. 1984 Vol. A"* — act titles + page numbers, NO law text) and Avd. II
regional regs. The harvester's own docstring already flagged these exact years as holes; a catalog search
`q="Norsk lovtidend 1984"` returns the register volumes and is easy to MISTAKE for content (I did, twice
— corrected here). So the ~18 missing pre-2001 dev-law acts are **not fetchable free**: the source text
was never scanned, and the free public alternatives don't cover pre-2001 (LTI starts 2001; sondreskarsten
2001; Lovdata CDs would, but encumbered/unacquired). **Harvest lever closed for the dev set.** 72.3%
stands; the only paths left are the (deferred, encumbered) Lovdata CDs or a bespoke re-OCR of physical
1980s gazettes NB never scanned.

METHOD LESSON (again): NB catalog `q=` ranks register/index and Avd. II volumes alongside content; never
infer "issue available" from a title match — check `_is_avdi` + `isDigital` + `pageCount` in the census,
or fetch a page and confirm it's law text, not an index.
