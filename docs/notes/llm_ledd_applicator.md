# LLM ledd-applicator — design note (2026-10-12)

**Status:** BUILT end-to-end 2026-10-12 (see done.md). Deterministic core
(`source/parse/ledd_apply.py`) + gate (`source/eval/applications_qa.py`, in the pre-commit hook) +
wiring (`pipeline.reconstruct` via replay's `ledd_fallback`) + applicator prompt
(`source/scrape/apply_prompt.py`) are committed; first 35 applications (helsepersonelloven) landed.
REMAINING: track the offline populator (extractor + fold, currently scratch) as a module; a
SOURCE-ONLY confidence guard for the ~1/17 mis-location tail; scale to more laws (one gated commit each).

## Problem

Per-law point-in-time fidelity is bottlenecked by **sub-provision application**, not by amendment
coverage (done.md 2026-10-12). `replay._apply_change_type` applies whole-§ replacements, but sends
sub-provision ops (ledd / punktum / nr / bokstav / sub-unit repeal) to the deterministic
`parse/ledd.py`, which returns `None` on OCR bases that lack clean ledd markers — so the op is
**flagged, not applied** (flag-don't-fabricate). The provision is left at last-known text and misses
current. folketrygdloven (`1997-02-28-19`): 1,626 flagged ops, **1,300 of them `change`**. Post-2001
ops are already present (1,654 of 1,966 for folketrygd) — they just don't apply.

## Idea (HS 2026-10-12): a general, flexible LLM applicator

An LLM reads the base provision + the amendment instruction and **locates** the span to edit, emitting
only POINTERS (never statutory text) — deterministic code splices. Char-level, so it handles OCR garble
and ledd-counting that the regex engine can't.

**This already exists in the LEGACY layer** (sidelined by the 2026-08 pivot, not refuted):
- `source/llm/apply_op.py` — localize-then-verify: LLM returns the start+end **anchors** of the span to
  replace/delete in the base; code splices the op's verbatim `new_text` in. 0% fabrication by
  construction (edit = located source span -> given verbatim new_text).
- `source/llm/pointer_apply.py` — holistic: LLM emits an ordered reference list
  (`{amendment:N}` | `{original_from, original_to}`); code assembles. Reasons about supersession/order;
  never writes text. ~30-100x cheaper output; cheap model handles the bulk.

So the work is a **PORT into the current segments path**, not an invention.

## Refinement: anchors, not raw offsets

Emit verbatim **anchors** (first ~N words of each boundary), NOT integer char offsets — the project
already found LLM offset *arithmetic* unreliable (todo: a past payload line-range test was 0/80
substring-verified), while the anchor -> whitespace-tolerant-search -> offset pattern is what makes
`scrape/segment_prompt.py` + `fold_segmentation` work at scale. Same safety guarantee, far more robust.

## Plan

1. **Offline precompute, Claude subagents** (not OpenAI — per decisions.md 2026-10-04), cached via
   llmkit. For each flagged sub-provision op on a segments-based in-force law, call the applicator with
   `(provision text reconstructed-so-far, op instruction, op payload span)`. It returns span anchors
   (+ optional payload sub-span for partial-sentence edits). Deterministic splice + **substring-verify**
   both the removed span (vs base) and inserted span (vs the public amendment payload); unlocatable ->
   flag (unchanged behaviour).
2. **Bake into the runtime as verified provision text** — the same shape as the dev-set applied-ops
   stream, extended to the broad corpus. Runtime stays deterministic and answer-key-free (G1/G2/G3 hold:
   the model sees only public base + public amendment payload, never the current/oracle dump; every
   published character is a verbatim slice of public source).
3. **Idempotency** (the todo's `whole_only=False` blocker): detect when the edit is already present and
   skip, so re-application doesn't double-apply; verify end-state. Needed before enabling sub-provision
   replaces globally.
4. **Validate on folketrygd's flagged `change` ops first** — measure the lift vs current; then a spread
   sample. Expect the biggest movers to be the heavily-ledd-amended laws (folketrygd, tax laws) that
   score ~0.0-0.5 today.

## Safety (G1) — the invariant that must hold

LLM sees only public-domain text (OCR base + the amendment's own payload), never the current/oracle
dump or the law register. It emits only pointers/anchors. Deterministic code fetches + splices + 
substring-verifies every span. Offline + cached -> reproducible build input, never a runtime call. An
unverifiable pointer is flagged, not guessed. This is the same contract the segmenter already honours.

## Prototype 1 (2026-10-12) — plumbing validated, quality test confounded

10 flagged `change` ops on folketrygd `1997-02-28-19`, Sonnet subagents emitting span anchors ->
deterministic splice. Result:
- **Plumbing works:** 10/10 anchors resolved whitespace-tolerantly; splice clean; fabrication-safe
  (payload verbatim amendment, removed span verbatim base slice). Agents showed real comprehension
  (flagged OCR-duplicated ledd, reasoned about which paragraph is the true "andre ledd").
- **Quality unmeasurable from this sample (my selection error):** I picked the LOWEST-sim-vs-current
  provisions. Those are low *because they were later reformed away* — folketrygd ch.10 (rehabiliteringspenger)
  was replaced by arbeidsavklaringspenger (2010). E.g. §10-14 has ONE op (2000) but its payload scores
  0.01 vs current (current 190 chars vs payload 1549) — current §10-14 is a different provision. No correct
  application of an intermediate op can reach 2026 current. Only the one genuinely-operative op improved
  (§20-2 insert_after, 0.07 -> 0.30).
- **LESSON — validation needs no oracle if done right:** compare the applicator's output to the
  DETERMINISTIC `ledd.apply` on CLEAN-base provisions where the engine SUCCEEDS (same inputs -> same
  output). Matching there = strong evidence of correctness on the OCR bases where the engine fails (its
  actual job). Do this before scoring anything vs current; and when scoring vs current, restrict to
  provisions whose LAST op is the one applied (else later reform confounds).

## Prototype 2 (2026-10-12) — CONCEPT VALIDATED vs the deterministic engine (no oracle)

The oracle-free validation from Prototype 1's lesson: 12 clean-base (LTI) sub-provision ops on
`2001-05-18-21` / `2001-06-15-53` where the deterministic `ledd.apply` SUCCEEDS; ran the applicator
(Sonnet) on the same inputs; compared spliced output to the engine's output.
- **10/12 exact match; mean similarity-to-engine 0.977; 10/12 >=0.95.** Covered nytt-punktum inserts,
  første/andre-ledd replaces, whole-§, and a nested `andre ledd andre punktum innledningen`.
- The 2 near-misses are NOT fabrication: §4 (0.93) the applicator inserted the new ledd right after
  ledd 1 while the engine appended it after a `Kapittel 2` heading that bled into the base (applicator
  arguably MORE correct); §36 (0.80) a hard nested lead-in-before-a-list address, partial diff.
- Conclusion: the applicator reproduces the known-correct engine by READING (not regex), so it should
  carry to the OCR bases where the regex engine returns None — its actual job. 0% fabrication holds
  (every char is a verbatim slice of base or the amendment payload). **Green light to build for real.**

Build order (the larger follow-on, not this session): (1) module `source/llm/ledd_apply.py` (or revive
`apply_op.py`) with the anchor schema + deterministic splice + substring-verify, cached via llmkit,
Claude-subagent backend; (2) wire as the `ledd_fallback` in `replay._apply_change_type` (offline
precompute -> baked verified text, runtime stays deterministic); (3) idempotency guard before
`whole_only=False`; (4) measure the in-force convergence lift (expect the folketrygd/tax ledd-heavy laws
to move most). Validate each step vs the engine on clean bases + the gate on the 9 dev laws.

## Artifact design (HS 2026-10-12): applications as a git-tracked, continuously-improved layer

The applicator's OUTPUT is a curated artifact, exactly parallel to `segments.jsonl` (decisions.md
2026-10-04: "segments.jsonl is THE corpus artifact, improved one gated commit at a time"). NOT an
ephemeral runtime computation.

- **`data/applications.jsonl` (git-tracked), POINTERS ONLY** — one row per applied op:
  `{target_law, para, op_key, op_kind, span_start_anchor, span_end_anchor}`. No statutory text: the
  removed span is a verbatim slice of the public base, the inserted text is the segments `amend_op`
  payload (public). Same G1 guarantee as segments.jsonl — the model emits anchors, deterministic code
  holds the text.
- **Build = deterministic re-splice** from anchors + public base + payload. Zero live LLM at runtime.
- **Improve loop** identical to the segmentation fold: offline applicator PROPOSES rows for flagged ops;
  human/agent corrects a bad anchor; each change a gated commit.
- **Gate = `applications_qa`** (sibling to classification_qa / segments_quality, same pre-commit hook):
  every tracked application's anchors resolve + substring-verify against the base; no regression vs HEAD.
- **Separate file, not a field on the amend_op row:** an op lives in issue X but amends law Y, so the
  application pointer is into law Y's provision — cross-referential, keyed by `(target_law, op)`. Two
  clean layers: segments = WHAT each amendment says; applications = WHERE/HOW each op lands on the base.
- **SETTLED: per-provision HOLISTIC pointers** (the `pointer_apply.py` model: one ordered
  `{base_span | payload}` list producing the final provision in a single pass), NOT per-op sequential
  splices. Decided on the staleness argument below — holistic entries depend only on the fixed enactment
  base + the payloads, so one op changing re-derives ONE provision's entry instead of cascading through
  later anchors.

### Staleness / future-proofing (HS 2026-10-12) — the artifact must degrade to "flagged", never to wrong text

The risk: the base a pointer points into can change (re-segmented enactment base, changed payload). Rules
that make this foolproof — staleness degrades to today's safe behaviour and is LOUD, never silent:
1. **Anchors, not raw offsets** — resolved by search at build time, so offset shifts elsewhere don't
   break a span (raw offsets would). First line of defence.
2. **Re-verify on every build (the core guarantee)** — the build never trusts the stored pointer: it
   re-resolves the anchor and SUBSTRING-VERIFIES the removed span vs current base and inserted text vs
   current payload. Mismatch -> flag-don't-fabricate: the op reverts to unapplied, provision falls back
   to last-known text. Worst case of a stale pointer = "looks like today" (pre-applicator), NEVER
   corrupted law text.
3. **Dependency fingerprints** — each row carries a sha of the base-provision-state + payload it was
   derived against (mirrors segments_meta.json pinning frozen text). Hash mismatch -> row is STALE ->
   must re-derive, not silently re-apply.
4. **Gate surfaces it** — `applications_qa --diff` fails on any application that no longer
   resolves/verifies or is fingerprint-stale: a blocking, countable, visible condition at commit.
5. **Regenerable cache, stable keys** — keyed by content-stable op identity (amending datokode +
   instruction + seq), not line numbers; "outdated" = re-run the offline applicator on the invalidated
   subset, review, re-commit. One provision, no cascade.

Through-line: the file is a set of RE-VERIFIED pointers, not stored text. Staleness can only make a
provision revert to its safe last-known state AND raise a gate flag — it cannot produce silently-wrong
output. (Same principle already protects segments.jsonl: offsets pinned by a frozen-text sha; the
Lovtidend OCR scan is immutable, so segment offsets are stable in practice — applications point at the
reconstructed enactment, which CAN move, so the fingerprint + re-verify matter more here.)

## Open questions

- Partial-sentence edits ("i § X erstattes «A» med «B»") — word_replace is already handled
  deterministically in replay; confirm the applicator only owns the cases the regex engine flags.
- Insert-vs-replace on a bare "skal lyde" against an OCR base — assembly decides vs base; does the
  applicator need the surrounding ledd context to disambiguate? (Likely yes — pass the whole provision.)
- Cost/model tier: can a cheap tier do the bulk (as the OpenAI version used gpt-4.1-mini) with escalation
  only on the reasoning-hard supersession tail? Measure on the folketrygd validation.
