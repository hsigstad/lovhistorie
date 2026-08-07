# Done

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
