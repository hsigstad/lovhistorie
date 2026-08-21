# Roadmap — scaling to the full Norwegian corpus

Target: point-in-time text for the entire in-force statute corpus, back as far as
NB's Norsk Lovtidend reaches (**1877**). Ordering rationale: **without measurable
success (Phase 0), autonomous work is blind** — so evaluation comes first, then
single-law robustness, then scale, then deep history.

## Phase 0 — Evaluation infrastructure  *(FIRST; blocks autonomy)*

- Build the **eval harness** (`source/eval/`): convergence, point-in-time, OCR
  fidelity, reporting. Seed: `reconstruction_qa.py` (from earlier feasibility work).
- Assemble the **held-out ground-truth set** — download Lovdata Pro
  historical versions for a curated sample ([ground_truth.md](ground_truth.md)).
- Freeze metrics + pass bar ([evaluation.md](evaluation.md)).
- **Exit criterion**: a runnable eval that scores any pipeline version against
  ground truth. → autonomy can begin.

## Phase 1 — Robust single-law pipeline

- **Locate** — enactment + each amendment in the right Lovtidend volume/issue (NB
  full-text search + a **date-based fallback** for laws whose title recurs in many
  later amendment volumes).
- **Extract** — NB ALTO OCR, column reflow, running-header dedup, **ordered /
  cross-reference-safe** provision splitting.
- **Recipe** — the full amendment list per law from NLOD annotations
  (capture-then-filter; drop resolution/forskrift numbers).
- **Amendment ops** — **omnibus-section isolation** + a **ledd/punktum-level op
  engine** (the genuinely hard part). Every extracted op **validated** against
  ground truth before it is trusted.
- **Replay** — apply ops in ikrafttredelse order; must converge to current.
- Iterate on the eval set across eras/sizes until Phase-1 laws pass the bar.

## Phase 2 — Scale across the in-force corpus

- Run over the ~N in-force laws; **post-2001-amended laws first** (their amendment
  texts are machine-readable in the Lovtidend dumps — cleanest).
- Per-law convergence scorecards; **flag + queue** failures.
- Human-in-the-loop **only** on flagged provisions.

## Phase 3 — Deep history (pre-2001, older print)

- Pre-2001 amendments via NB Lovtidend OCR (rougher; more review).
- Extend back toward the 1877 floor; report the **fidelity curve by era**.

## Phase 4 — Outputs & release

- **Point-in-time query** (law as of any date).
- **Versioned corpus artifact** (git-backdated history and/or per-date snapshots).
- Public release under public-domain / NLOD terms.

## Known hard problems (carried from the feasibility work)

1. **Omnibus acts** — most amendments to small laws are buried in large multi-law
   acts; isolating the target law's section robustly across heterogeneous formats.
2. **Ledd-level ops** — `nytt fjerde ledd skal lyde`, `ledd blir nytt ledd`, etc.,
   need a sub-provision engine to rebuild full provision text.
3. **Op validation** — the critical safeguard: cross-check each op so wrong data
   never enters a version (Sondre per-commit diffs / Lovdata Pro as cross-checks).
4. **Locate robustness** — date-based fallback for recurring titles.
5. **OCR curve** — pre-~1900 fraktur is rougher; budget review by era.

Full technical background: [statutory law versioning](../notes/statutory_law_versioning.md).
