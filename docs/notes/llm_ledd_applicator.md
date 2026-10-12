# LLM ledd-applicator — design note (2026-10-12)

**Status:** PLAN (deliberate-gated engine project; see docs/todo.md "ledd-on-OCR application engine").
Supersedes nothing yet — no code written. Prototype pending (budget).

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

## Open questions

- Partial-sentence edits ("i § X erstattes «A» med «B»") — word_replace is already handled
  deterministically in replay; confirm the applicator only owns the cases the regex engine flags.
- Insert-vs-replace on a bare "skal lyde" against an OCR base — assembly decides vs base; does the
  applicator need the surrounding ledd context to disambiguate? (Likely yes — pass the whole provision.)
- Cost/model tier: can a cheap tier do the bulk (as the OpenAI version used gpt-4.1-mini) with escalation
  only on the reasoning-hard supersession tail? Measure on the folketrygd validation.
