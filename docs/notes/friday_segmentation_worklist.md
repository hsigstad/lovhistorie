# Friday segmentation worklist — target the coverage gap first

**Why (see `docs/done.md` 2026-10-05):** the dominant reconstruction gap (~45%) is amendment
**COVERAGE** — amendment-added §§ + missing ops living in the un-segmented issues. The segmenter
(~0% miss on what it processes) and OCR (~0%) are NOT the problem. So Friday's priority is segmenting
the issues richest in amendments, not giants-first.

**Scope:** 774 frozen-but-unsegmented issues (we already have the OCR text — no re-scraping). Ranked by
`skal lyde` amendment-restatement density (full ranked list: `friday_issue_priority.json`; regenerate
with `python docs/notes/rank_issues.py`). Total amendment markers waiting: **18,747**.

## Tiers (run in this order)

1. **Tier 1 — 292 regular issues with ≥5 amendments** (`giant=false`, `skal_lyde>=5`). Highest
   coverage-per-token; one-shot segmentable (≤600k). **Start here.** ~9,858 amendment markers live in
   the regular issues overall.
2. **Tier 2 — 91 giants** (>600k; bound annual volumes). They hold **~8,889 amendment markers (~47% of
   the total)** — NOT low-value, but need the chunker (250k chunks) + stitch. Do after Tier 1.
3. **Tier 3 — 239 regular issues with 1–4 amendments.** Marginal coverage.
4. **Skip / last — 152 regular issues with 0 `skal lyde`** (no amendments; forskrift/notice issues).

## Mechanics
- Subagent segmentation (`source/scrape/segment_prompt.py`) → fold (`fold_segmentation.stitch_chunks`
  for chunked, else `fold_ordered`) → `scratchpad fold_append.py` appends clean issues to
  `data/segments.jsonl`.
- Chunk sizes: giants 250k, dense issues 80k (output-token cap).
- After each batch: `classification_qa` + both `--diff` gates; commit via the pre-commit hook.
- **Cost:** full remainder ≈ the parked giant run (~82M tokens) + Tier 1. If budget is tight, Tier 1
  alone is the best coverage-per-token.

## Caveat
`skal lyde` counts amendments present in an issue, not specifically amendments to *in-force* laws (we
have no act→issue→target map for un-segmented issues — `act_index` covers only 39 of the 774). So the
ranking is "amendment-dense issues," a good proxy for coverage value but not filtered to in-force targets.
