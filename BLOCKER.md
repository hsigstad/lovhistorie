# BLOCKER — two decisions needed before the gate can reach PASS

Written by the autonomous run (2026-08-07). The reconstruction engine and the
anti-gaming gate work; convergence is honest (0.043 corpus). But raising it to the
0.97 bar is blocked on two things I can't resolve deterministically without your call.
Nothing here is a code bug — both are design decisions.

## Evidence gathered this run

- **Enactment base proven on 1 law** (mesterbrevloven): located in NB Lovtidend,
  OCR'd, 10 provisions cached, convergence 1/12→3/12, base-integrity guard green.
- **Locating fails for everything else.** Automated locate (full-title search →
  hefte → `Lov nr. N` page) found **0 of 8** other dev laws. Hand-checking
  rettsgebyrloven (nr 86, Dec 1982): its enactment is **not** in any hefte NB's
  full-text search surfaces — the 1982 issue isn't discoverable by title/nr at all.
- **The metric is OCR- and renumbering-bound.** For mesterbrevloven's 7 never-amended
  provisions that *are* in the enactment base (current should ≈ enactment), only
  **2/7 clear 0.98**: §3=0.92, §5=0.73 (OCR noise); §8=0.34, §9=0.01, §10=0.10
  (enactment §N ≠ current §N after 40 years of renumbering the per-§ op table doesn't
  encode). No-LLM + flag-don't-fabricate forbid cleaning either up.

## Decision 1 — how do we acquire enactment text at scale?

Locating each law's original text in the gazette by search does not generalise.
Options:

- **(a) RECOMMENDED — structured Lovdata CD native discs.** The "real lead" in
  `docs/notes/lovdata_cd_2005.md`: the native discs (≈1995/2000/2005, now out of DB
  protection) are *consolidated per-law* — clean text at several historical anchors,
  sidestepping **both** locating **and** OCR. Needs the email to NB AI Lab that note
  already flags as not-yet-sent. Single highest-leverage unblock.
- **(b) Build a (year, law-nr) → issue → page index for NB Lovtidend.** Real
  multi-turn infra, uncertain payoff, and still leaves the OCR ceiling (Decision 2).
- **(c) Hand-record `LOCATIONS` for the eval set only** (~15–20 laws). Feasible for
  measurement, not for the corpus deliverable.

## Decision 2 — what is the success oracle, given OCR?

Convergence-to-current compares reconstruction against the **clean** NLOD text, but
our reconstruction is **OCR'd** — so even a perfect reconstruction loses ~half its
provisions at τ=0.98 to OCR noise alone. Options:

- **(a) RECOMMENDED — make point-in-time vs Lovdata Pro the real gate.** That was
  always the un-gameable deliverable bar (`docs/goal.md` rule 1); it uses *clean*
  historical text, so it isn't OCR-bound. Demote convergence-to-current to a
  directional dev signal. Needs your Lovdata Pro downloads (`docs/todo.md`).
- **(b) Cancel OCR on both sides.** Score reconstruction against **NB's OCR of the
  current text** (not clean NLOD), so OCR error largely cancels and the metric
  measures reconstruction, not transcription. Deterministic, no downloads — but only
  meaningful if acquisition stays OCR-based (i.e. not option 1a).
- **(c) Lower τ** — rejected: hides real reconstruction errors behind OCR slack.

## My recommendation

**1a + 2a**: get clean consolidated text from the Lovdata CD discs (email NB AI Lab),
and judge success on point-in-time vs Lovdata Pro. That removes both the locating and
the OCR problems at once and matches the deliverable we actually want. If the discs
fall through, fall back to **1b + 2b** (index + OCR-cancelled metric), which is fully
in-house but more engineering and lower fidelity.

Clear this file (and tell me which option) to resume the loop.
