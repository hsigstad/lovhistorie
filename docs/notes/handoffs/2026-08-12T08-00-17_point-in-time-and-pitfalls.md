# Session handoff — 2026-08-12T08-00 — point-in-time metric + pitfalls consolidation

**Read `docs/notes/lessons_and_pitfalls.md` first** — this session was mostly *correcting*
earlier misunderstandings; that doc consolidates them so they aren't repeated.

- **What's done this session:** full NB gazette harvest; gazette structuring parser +
  pre-2001 amendment stream; ledd engine; 4000-char block-truncation fix; 5 pre-2001 OCR
  bases; a diacritic OCR post-correction; and — the big one — the **point-in-time
  deliverable metric unblocked, validated, and its truth parser aligned**. Convergence
  0.043 → 0.344, guards green. All committed to `master` (no remote → commits are the
  handoff).

- **Partial verification (act on this):** point-in-time is validated on **aksjeloven only**
  (2001 + 2024). I *predicted* clean-data laws (vphl 2007-06-29-75, tjenesteloven
  2009-06-19-103) will score much higher at past dates (their 2024-equivalent already
  matches convergence) but **did not verify** it. Next session: download 1–2 HIST versions
  each via the flow in the lessons doc §10 and confirm — it's the cleanest evidence that the
  engine reconstructs *clean* past states well.

- **Next lift (not started):** pre-2001 amendment coverage — name→datokode, omnibus acts
  (parse ALL targets, not just the first), and blanket terminology reforms
  (skifteretten→tingretten). First step is to QUANTIFY each sub-lever's share before
  building (see `todo.md`). OCR/LLM correction and multimodal re-OCR were tested and
  DEPRIORITISED — don't redo them.

- **Noticed but not acted on:** a concurrent session was active in this shared repo (rebuilt
  1918/1959/1979 bases at 07:35, byte-identical). Stage files by name; expect company.

- **Scratchpad (ephemeral, will vanish):** the OCR deterministic + LLM experiment scripts
  and the LLM cache live in the session scratchpad, not the repo. Findings are in `done.md`;
  re-run from that description if needed. OpenAI key: `projects/scheme/.env`.
