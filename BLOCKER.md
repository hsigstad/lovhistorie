# BLOCKER — the 0.97 gate is unreachable on this dev set (needs a Henrik decision)

Written by the autonomous run (2026-08-07), after real progress, not prematurely.
The method is validated; the wall is **data coverage + dev-set composition**, provable
by arithmetic, not fixable by any deterministic code on data-in-hand.

## The method works (this session)

Corpus convergence **0.043 → 0.094**, all anti-gaming guards green, via: clean LTI
enactment bases (no OCR), `change_type`-driven replay, multi-provision block splitting.
On a **clean, post-2001 law** it reconstructs well — **tjenesteloven 27/33 (82%)**,
vphl climbing (23→36 and rising). So the pipeline is sound.

## The wall (arithmetic)

**574 of 938 dev provisions (61%)** live in six **pre-2001** laws — avtaleloven (1918),
oreigningslova (1959), foreldelsesloven (1979), rettsgebyrloven (1982), kjøpsloven
(1988), aksjeloven (1997). Their enactment predates the clean 2001 LTI dump, and any
provision not touched by a post-2001 whole-provision amendment has **no base at all**
→ scores ~0. **Even a perfect post-2001 engine caps corpus convergence at ~0.39.** So
0.97 on this dev set is mathematically impossible with the data we hold.

Root cause: **no clean pre-2001 statutory source in hand.** LTI is 2001+. The current
text is the answer key (off-limits). NB OCR is lossy (~half of never-amended
provisions fall below τ=0.98 on OCR noise alone), so it can't reach 0.97 either.

## Secondary finding (in-house fixable — NOT the blocker)

`amendments.jsonl.gz` truncates `new_text` at **4000 chars**, so the largest chapter
replacements lose their tail provisions (**119 in vphl**). Recoverable by re-deriving
those blocks from the full LTI amending-act XMLs (`data/lti/`), which we have. Worth
doing — it lifts the post-2001 ceiling — but it does not touch the 61% pre-2001 wall.

## Decisions needed

**1. Clean pre-2001 base source.**
- **(a) RECOMMENDED — structured Lovdata CD discs** (`docs/notes/lovdata_cd_2005.md`):
  consolidated per-law text at 1995/2000/2005 anchors. Anchor + clean post-2001 deltas
  = clean reconstruction, no OCR. Needs the NB AI Lab email (not yet sent).
- (b) NB OCR for the pre-2001 tail + an **OCR-calibrated (lower) τ** for that tail only.
- (c) something else.

**2. Gate / dev-set composition** (lives in `source/eval/gate.py`, which the loop is
forbidden to edit — so this one is yours to set).
- **RECOMMENDED — split the gate into two tracks:** a **post-2001 clean track** with
  the real target (proves the engine, achievable now) and a **pre-2001 track** with an
  OCR/anchor-calibrated target. A single blended 0.97 hides which shortfall is
  data-limited vs engine-limited.

## Recommendation

Reconstitute the convergence gate around **post-2001 laws now** (achievable target —
lets the loop actually converge and prove the engine), pursue the **Lovdata CD discs**
for pre-2001 in parallel, and **re-parse amendments from LTI** to remove the 4000-char
truncation. Clear this file with your call and I resume.
