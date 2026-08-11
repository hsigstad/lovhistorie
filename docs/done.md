# Done

## 2026-08-11 (cont.) — 4000-char block truncation fixed: 0.262 → 0.343 (session)

- [x] **Diagnosed the loss** — categorized 527 non-converged provisions across based laws:
  low-sim 221, missing 217, flagged 89, concentrated on vphl (239, clean LTI data → pure
  replay failure) and aksjeloven (170). Root cause: `amendments.jsonl.gz` caps `new_text`
  at 4000 chars, so big "Kapittel N skal lyde:" blocks lose their tail provisions.
- [x] **Fixed it** — `source/scrape/rederive_blocks.py` (OFFLINE) re-derives full block
  text from the LTI amending-act XMLs, keyed by (act, target_law, instruction) →
  `data/amendment_blocks.jsonl.gz`. `amendments.py` reads that derived file and serves a
  patched stream to `load_ops`/`load_for`. **G1 kept clean**: all nl-*.xml/LTI access is
  offline-only; the RECON path reads only derived data files (verified G1 PASS).
- [x] **Anti-fabrication guarantee**: an override is accepted ONLY if its first 4000 chars
  reproduce the truncated original byte-for-byte (verified: 66/66 hold, 0 violations) —
  so the full text is the genuine continuation, never invented.
- [x] **Result**: convergence **0.262 → 0.343** (346/1008). vphl **61 → 142**/300;
  aksjeloven 123 → 124. vphl missing provisions 114 → 72. Guards G1/G2/G3 PASS.
  66 blocks re-derived; skipped ops are forskrift/no-LTI or >2024 acts (LTI ends 2024,
  e.g. vphl's lov/2026-02-06-3) — left truncated, not guessed.

## 2026-08-11 — harvest complete; pre-2001 bases + amendment stream wired (session)

- [x] **Harvest 100%** — 1,033 issues / 143,963 pages (Norsk Lovtidend Avd. I 1877–2000).
  Hardened `harvest_lovtidend.py` after suspend-induced crashes: `resolve_urn` retries,
  one item's failure no longer aborts the run.
- [x] **Full pre-2001 amendment stream** — `gazette.py --build` over the whole corpus:
  **6,087 ops / 253 laws** (was 822 partial). Wired into replay: `amendments.load_for`
  now merges the LTI (2001+) + gazette-OCR (pre-2001) streams (deduped, date-ordered).
- [x] **3 of 4 pre-2001 dev bases built** (OCR, honest, guards PASS, no answer-key read):
  avtaleloven 1918 (**24/45**), oreigningslova 1959 (**14/33**), foreldelsesloven 1979
  (**12/79**). `build_enactment.py` tweaks: `_HEAD` accepts `(`-closed headings (1979
  layout); `_law_text` optional `end_needle` (1918 bound-annual boundary).
- [x] **Result**: convergence **0.215 → 0.262** (264/1008). Session trajectory:
  0.043 → 0.097 → 0.119 → 0.215 → 0.262. Guards G1/G2/G3 PASS.
- **Two confirmed hole casualties** (unbuildable from NB, digitisation gaps): kjøpsloven
  (1988) and **rettsgebyrloven (1982)** — verified: 0 harvested 1982/83 issues contain
  "Lov om rettsgebyr". Its 62 amendments are ready but the base needs a fallback source.
- **Load-bearing limiter identified**: the **name→datokode gap** — avtaleloven/aksjeloven/
  foreldelsesloven are amended by acts citing them BY NAME, so their pre-2001 amendments
  (~0 resolved) are missing; their convergence is base-only for now.

## 2026-08-10 (cont. 3) — ledd engine tail: bokstav/nr/multi-ledd (session)

- [x] **Preserved list markers** in `parse_lovdata_xml` (inject `a) `/`1. ` from
  `data-li-identifier` before tag-strip) — symmetric across base + answer key (score-
  neutral). Rebuilt LTI bases.
- [x] **Extended `ledd.apply`** for nr/bokstav (clean-consecutive-run validation, recurses
  for nested `ledd nr.7 bokstav b`) and multi-ledd range/pair inserts (split new_text on
  its own `(N)` markers, exact-count check, renumber). Flags on any unresolved address.
- [x] **Result**: 0.2143 → **0.2153** (small, as expected — the rare tail; nr 21 apply/
  77 flag, multi-ledd 5/5). No regression, guards PASS, anti-fabrication verified
  (§5-14 → 1.0, faithful). **Next big lever (honest, out of this scope):** the gazette
  amendment parser (`endringslov.py`/`gazette.py`) drops nr/bokstav markers from whole-
  provision/chapter `skal lyde` bodies, so sub-provision edits on replaced provisions
  can't resolve — preserving those markers would unlock ~77 flagged nr ops.

## 2026-08-10 (cont. 2) — §N-M OCR parser + aksjeloven base (session)

- [x] **Fixed the OCR base parser for chapter-section laws** (`build_enactment.py`):
  `_HEAD` now accepts `§N-M.`; `_NEXT_LAW` rewritten reflow-tolerant (keys on
  `Lov nr. N` + following `Lov om` title line, so running-page-headers don't false-match).
  mesterbrev (§N) regression-checked OK.
- [x] **Built aksjeloven (1997-06-13-44) OCR base** from NB 1997 Nr.14: 263/293 provisions
  (§N-M), honest gazette text, boundary clean (no allmennaksjeloven leak), ~30 correctly
  dropped/flagged (mangled OCR headings) not fabricated. No answer-key read (verified).
- [x] **Result**: aksjeloven **26 → 122/293** (+96); overall convergence **0.119 → 0.214**
  (216/1008). Guards G1/G2/G3 PASS. Honest session trajectory: 0.043 → 0.097 → 0.119 → 0.214.

## 2026-08-10 (cont.) — ledd engine + honest eval harness (session)

- [x] **Ledd engine** (`source/parse/ledd.py` rewritten): compositional addresser
  (ledd → punktum → bokstav) over a structure-preserving base; replace/insert/repeal;
  returns None (flag) on any unresolved address — verified faithful, 0 fabrication
  (2 faithfulness bugs found + fixed; §5-9 independently audited). 100+ previously-
  flagged vphl sub-provision ops now apply.
- [x] **Structure-preserving LTI base** (`build_enactment.parse_lovdata_xml`): keys on
  `data-name`, keeps ledd as newlines + bokstav markers (LTI XML tags every ledd/punkt).
- [x] **Caught + reverted an answer-key-coupling hack** — a subagent had the base build
  read the current dump to dodge a G3 false-positive; removed (base asserts honest LTI
  text only).
- [x] **Two eval-harness fixes (Henrik sign-off)**: G3 threshold ≥0.98→**≥0.999** (real
  contamination normalizes to ~1.0; honest barely-amended vphl §5-10=0.9974 no longer
  false-trips); `gate.current_provisions` now parses the answer key **structurally via
  data-name** (was inventing phantom provisions from in-body § cross-refs + truncating).
- [x] **Result**: honest convergence **0.097 → 0.119** (120/1008). vphl **37 → 61**/300
  (ledd engine + structured base); tjenesteloven honest **26/29** (was phantom-inflated
  20/33). Guards G1/G2/G3 all PASS.

## 2026-08-10 — overturned the 0.39-ceiling blocker; started the NB harvest (session)

- [x] **Disproved the "OCR too lossy / 0.39 ceiling" diagnosis.** NB gazette OCR is clean
  (~0.99 where a provision is untouched; antiqua pre-1900). Real gap = the **2001 cliff
  twice**: LTI has neither pre-2001 bases nor the pre-2001 amendment stream. Plus a metric
  bug and two parser bugs — not OCR noise. (see updated `BLOCKER.md`.)
- [x] **Metric correctness fix** — `source/eval/metrics.py` now `autojunk=False` (difflib's
  default silently collapsed long-provision similarity toward 0). Henrik sign-off.
- [x] **Mapped NB Lovtidend Avd. I coverage 1877–2000** — 1,033 items / ~144k pages,
  all public-domain; holes = 1891,1976,1980,1982,1984,1987,1988,1989. kjøpsloven (1988)
  unrecoverable from NB; other 5 pre-2001 dev laws fine (rettsgebyrloven via 1983).
- [x] **Scoped acquisition** — no bulk NB endpoint / no NCC Lovtidend subset exists;
  per-page ALTO is the only running-text source (~0.3GB text, ~16h).
- [x] **Built + launched the harvester** — `source/scrape/harvest_lovtidend.py`
  (newest-first, page-resumable, 6 workers) → `data/lovtidend_text/` (gitignored),
  work-list `data/lovtidend_index.json`. Henrik approved the full harvest.
- [x] **Built the gazette structuring parser** — `source/parse/gazette.py`: TOC-anchored
  act inventory (date, nr, class, target-law datokode ~96% resolved), disjoint nr-ordered
  body slicing (boundary-checked, 0 bleeds), `--build` emits the pre-2001 amendment stream
  to `data/pre2001_amendments.jsonl.gz` in the LTI `amendments.jsonl.gz` schema. Hardened
  `endringslov.py` for OCR reality (colon-optional `skal lyde`, subunit rejoin, broadened
  terminators/new-provision/whole-law forms). On the 1999-2000 cache: 822 ops / 51 target
  laws (classify: replace 372, subprovision 377, repeal 72). Gate guards unaffected.

## 2026-08-07 — eval gate + clean-LTI reconstruction (session)

- [x] **Completion gate** (`source/eval/gate.py`): one exit code = three anti-gaming
  guards (no-answer-key-import via AST, runtime isolation, base-integrity) + corpus
  convergence over a fixed dev set. All guards verified to fire when cheated. This is
  the machine-checkable `/goal` condition.
- [x] **Reconstruction entrypoint** (`source/parse/pipeline.py`): `reconstruct()` +
  `enactment_base()` + `load_ops()` (change_type-aware, multi-provision block split).
- [x] **Clean enactment bases from the LTI dump** (`source/scrape/build_enactment.py`
  `build_post2001` / `build_from_lti`): post-2001 laws parsed from
  `data/lti/` (clean digital, no OCR). Also the OCR gazette path (`build`) proven on
  mesterbrevloven.
- [x] **change_type-driven replay** (`source/parse/replay.py`): add/change/repeal,
  heading-stripped whole-provision text, sub-provision → ledd engine, flag
  renumber/move/unknown. Legacy `kind` path kept for run_convergence.
- [x] Dev set expanded to 9 laws (1918–2009); corpus convergence **0.043 → 0.094**.
- [x] Established that convergence is a data-in-hand objective metric (no Lovdata Pro
  needed) and that `/goal` (not `/loop`) is the right autonomous driver.

**Key finding that stopped the run** (see `BLOCKER.md`): 574/938 dev provisions (61%)
are pre-2001 laws with no clean base → 0.97 gate mathematically unreachable (ceiling
~0.39). Two decisions pending for Henrik. Secondary: `amendments.jsonl.gz` truncates
`new_text` at 4000 chars (liftable from LTI XMLs).
