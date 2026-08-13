# Done

## 2026-08-13 (cont.) — booklet validation loader built + scored end-to-end vs the oracle

- Built `source/eval/booklet_gt.py` — a PUBLIC-DOMAIN parallel to `ground_truth.py`: a registry of
  booklet snapshots (URN + body span + ajourført date) that OCR+parse (via the booklet heading
  repair) into `{para: text}` and cache, so the harness can score `reconstruct(datokode, date)`
  against a redistributable source. Held-out discipline noted in-module (a booklet used as a BASE
  must not also validate that law; kjøpsloven/rettsgebyr booklets are omitted, aksjeloven's 1997
  base is the gazette so its 2001 booklet is a legitimate validator).
- **End-to-end score, aksjeloven 2001-01-01 (τ=0.90, OCR-calibrated):**
  - **Content faithful:** booklet ↔ Lovdata-Pro oracle = **median 0.994**, 95% coverage (253/265).
    The PD booklet reproduces the encumbered oracle's *text*.
  - **As a numeric yardstick (same-frame):** reconstruct-2001 scores ≥0.90 on 50% vs Lovdata but
    41% vs booklet — a ~9pp gap. Diagnosed (again mostly segmentation, not OCR): ~half is **11
    residual extraction failures** (booklet provisions parsed as "," or a footnote — §5-18, §12-1,
    §6-24 …), the other ~half is intrinsic **OCR-vs-OCR** noise (scoring an OCR reconstruction against
    a scanned booklet double-counts OCR error).
- **Verdict:** PD booklets are a viable validation source for CONTENT now; to be a drop-in numeric
  substitute for the clean oracle they need (a) the 11 residual segmentation fails cleaned up
  (footnote-aware heading alignment), and (b) an OCR-vs-OCR-calibrated τ or a born-digital edition.

## 2026-08-13 (cont.) — heading-tolerant parser built (opt-in, regression-clean); booklets unlocked

- Built `_repair_headings` (LINE-ANCHORED): canonicalises OCR-garbled `§ N —M` section headings
  ("§ 1 —3", "§3— 4?") back to `§N-M.` so dense paperback særtrykk segment. `parse_provisions`
  gained a `repair_headings=False` flag; **only `build_booklet` opts in**.
- **Regression check drove the design.** Applied globally (unanchored) it regressed aksjeloven's
  gazette base 149→146 (canonicalised in-body cross-refs into phantom headings). Line-anchored still
  regressed it (any change to the already-tuned clean antiqua base displaces provisions). Conclusion:
  the gazette bases are already clean and do NOT benefit — so the repair is booklet-only. Full gate
  after rebuilding all booklet bases: aksjeloven 149, kjøpsloven 55, rettsgebyr 3, everything else
  identical, convergence **0.5621 unchanged**, guards PASS (base JSONs byte-identical → §N-M repair
  is a verified no-op for single-§ and gazette laws).
- **Booklet unlocked:** with the opt-in repair, the aksjeloven-2001 booklet parses at **95% coverage
  (253/265), median 0.994** vs the Lovdata-Pro 2001 oracle (was 26% / 0.60 pre-fix). The PD-booklet
  validation-set lever is now mechanically viable; next is banking booklets + held-out partitioning.

## 2026-08-13 (cont.) — PD-booklet validation set is VIABLE (corrected: parser, not OCR)

- **Question:** did we scrape all findable booklets, and can PD law booklets replace the encumbered
  Lovdata-Pro oracle? **Swept NB, ran the decisive cross-check — and then caught myself repeating the
  project's signature "blame OCR" trap.**
- **Sweep:** booklets NOT exhausted — unused PD snapshots exist (aksjeloven 2001, foreldelsesloven
  1992/1993, kjøpsloven 1991, rettsgebyr 1993).
- **Cross-check, FIRST (wrong) read:** aksjeloven-2001 booklet (`digibok_2023030748042`, ajourført
  exactly **2001-01-01**, matching a GT we hold) vs Lovdata-Pro 2001 = 26% coverage, mean 0.60. I
  labelled it "OCR too noisy — paperbacks can't replace the oracle." **That was wrong** (Henrik
  flagged it — lessons #0/#2/#8: suspect the measurement, not OCR).
- **Cross-check, CORRECTED read:** the failure was **`parse_provisions` not segmenting garbled
  `§ 1 —3` headings**, not char OCR. The OCR carries **279 of 293** headings; strict `_HEAD` matched
  only **71**, so parsed provisions swallowed everything to the next recognised heading (§21-1 came
  out 7110 chars vs GT's 172 — and where aligned, matched GT *verbatim*). **Repairing the heading
  token alone (identical OCR) → 94% coverage (250/265), median 0.991, mean 0.846, 63% ≥0.98 /
  73% ≥0.90.** So the booklet DOES reproduce the oracle; the limiter was our parser.
- **Consequence:** the PD-booklet validation-set lever is VIABLE, gated on a small deterministic
  heading-tolerance fix (not multimodal re-OCR). Corrected the todo entry. Method note for the
  lessons doc: I mis-attributed a segmentation bug to OCR and committed it — re-verify "it's OCR"
  claims by checking coverage/segment lengths before concluding. No pipeline code changed yet.

## 2026-08-13 — point-in-time harness now mirrors the gate's eval-scope rules (handoff consumed)

- Consumed the 2026-08-12T16-42 handoff: the two eval calibrations (convention-annex scoping +
  OCR-calibrated τ) lived only in the convergence gate, not the point-in-time harness
  (`source/eval/harness.py`, flat `tau=0.98`), so the deliverable metric would have diverged from
  convergence for pure eval-scope reasons once OCR-law / annex-bearing ground truth landed.
- **Single source of truth:** moved the annex predicate to `metrics.is_convention_annex` (`"/" in
  para`); `gate._is_convention_annex` is now an alias of it. `harness.evaluate_law/evaluate_corpus`
  hold annex articles out of scope automatically and take per-source τ (`tau` clean-LTI, `tau_ocr`
  for OCR laws; caller passes `ocr=`/`ocr_of=pipeline.is_ocr_base`). `LawScore` carries the τ used +
  `n_annex`; summary reports `annex_out_of_scope`.
- **Verified consistent:** driving the harness with the real pipeline reproduces the gate's per-law
  convergence EXACTLY for all 9 dev laws (@0.9 OCR / @0.98 clean) and the same 138 annex-out-of-scope;
  harness self-test green; gate unregressed (0.562 / 0.499, guards PASS). No reconstruction code touched.

## 2026-08-12 (cont.) — OCR-calibrated τ, DERIVED not guessed: strict 0.499 → OCR-calib 0.562 (session)

- **Calibrated τ_OCR from the OCR-fidelity distribution, not a round number.** On NEVER-AMENDED
  provisions (current == enactment → any gap is PURE OCR error, not reconstruction error;
  evaluation.md check 3), pooled across the 7 OCR-based laws (n=311): a clean mode ≥0.98 (167),
  a genuine-noise band [0.90,0.98) (45), then a distinct extraction-DEFECT tail below 0.90 (severe
  corruption — a base-build problem τ must NOT hide). Rescue-ratio test (definitely-correct
  never-amended : possibly-risky amended, in the band [τ,0.98)) holds **~4:1 from τ=0.97 down to
  0.90**, then collapses to ~2.6:1 at 0.85. So **τ_OCR = 0.90** is the floor that recovers the
  correct-but-noisy band and stops where the defect tail begins.
- **Implementation (per-source, transparent, Henrik sign-off):** `pipeline.is_ocr_base()` = the
  enactment `source` has no clean-LTI `lti` key (objective provenance set at build time — can't
  hand-pick). `gate.TAU_OCR=0.90` applies ONLY to OCR-based laws; clean-LTI laws keep 0.98. The gate
  now prints BOTH `convergence (OCR-calib)` and `convergence (strict τ)` + the τ used per law — the
  loosening is always visible, never silently the bar.
- **Result:** OCR-calibrated **0.562** (489/870) vs strict **0.499** (434/870). Guards G1/G2/G3 PASS.
  Per-law rescues (all OCR laws @0.90): avtaleloven 24→29, oreigningslova 14→16, foreldelsesloven
  12→18, rettsgebyr 2→3, mesterbrev 3→4, kjøpsloven 39→55, aksjeloven 125→149.
- **Honest residual risk:** τ_OCR also loosens ~11 AMENDED OCR provisions in [0.90,0.98) which the
  4:1 ratio says are *plausibly* OCR-noise but can't be individually confirmed as correct — hence
  the strict number stays reported. The BIGGER OCR lever remains the sub-0.90 defect tail
  (page-number/footnote leaks, boundary errors) — deterministic base-build fixes, not τ.

## 2026-08-12 (cont.) — "missing provisions" were treaty annexes: scope fix 0.431 → 0.499 (session)

- **Chased the missing-provision lever; it was mostly a DENOMINATOR artifact.** Classifying every
  current provision absent from recon: **138 of the 1008** are **convention articles bundled into the
  current NLOD text but incorporated BY REFERENCE** — kjøpsloven's CISG (`§cisg/a1…a94`, 92) and
  foreldelsesloven's limitation convention (`§fik/a1…a46`, 46). No Norsk Lovtidend act carries them,
  so they are **un-reconstructable by construction** (outside goal.md rule 2's reconstruct contract),
  not reconstruction failures. The genuine reconstruction-missing tail is small: kjøpsloven §1/§50/§71
  (OCR base-drops), foreldelsesloven §15a, ~35 renumber-targets (the hard `nåværende § X blir § Y` cases).
- **Fix (Henrik sign-off — "flag out-of-scope, report both"):** `gate._is_convention_annex(para)` =
  `"/" in para` — an OBJECTIVE structural namespace marker the NLOD dump itself uses; ordinary
  statutory ids (`§N`, `§N-M`, `§Na`) never contain "/", so it can't quietly drop merely-hard
  provisions. `convergence()` denominator is now STATUTORY provisions; annexes are reported as a
  separate flagged out-of-scope line, per-law and total (nothing hidden — evaluation.md: "the
  remainder flagged, never silently wrong"). Same class as the autojunk / phantom-provision / G3
  eval-harness correctness fixes.
- **Result:** convergence **0.431 → 0.499** (434/870 statutory), 138 convention-annex flagged
  out-of-scope. Guards G1/G2/G3 PASS. No reconstruction code changed — a metric-scope correction.
- **Session arc:** 0.344 → 0.391 (block pieces) → 0.431 (booklet bases) → 0.499 (annex scope). The
  remaining gap to 0.97 is now the genuine hard tail: pre-2001 OCR quality (τ-decision territory),
  renumbering, and post-2024 acts (LTI ends 2024). Diminishing returns / rising risk from here.

## 2026-08-12 (cont.) — ledd-engine lever MEASURED and deprioritised (measure-before-building)

- **Question:** the ledd engine flags 334 `change` ops across the dev set (258 ledd, 32 punktum,
  20 nr) — is finishing it the next big lever? **Measured answer: no.**
- **The flag count is misleading.** 91 of 334 flags are on provisions that are EMPTY at apply
  time (the provision was later wholesale-replaced by a `Kapittel N skal lyde` block, or never
  created) — a pre-rewrite ledd edit to a provision that no longer exists **does not affect
  convergence** (the final block replace determines current text). Of the rest, 147 are on
  unstructured OCR-blob bases (no ledd markers) and 96 on structured bases (many aksjeloven-OCR
  with noisy `(1) (1)` doubled markers).
- **True convergence-relevant ceiling = 56 provisions** (failing current provisions whose LAST op
  is a flagged ledd/punktum edit): aksjeloven 24, vphl 11, rettsgebyr 10, others ≤6. And these are
  the *riskiest* cases: `nytt … punktum` / `nytt nr. N` INSERTS need Norwegian legal-sentence
  segmentation (jf./nr./mv. abbreviations) → high fabrication risk for ~0.05 convergence. The one
  "safe" subset (plain whole-ledd replace on clean vphl) turned out to be artifact-entangled
  (empty `new_text`, doubled `(1) (1)`), not clean engine gaps. Doubled-marker collapse: 15
  provisions, crosses 0.98 for **0** (errors cluster — lessons #6). **No clean win exists here.**
- **τ-calibration measured** (the lever evaluation.md/lessons #6 actually prescribe for OCR laws):
  corpus convergence @0.98=0.431, @0.95=0.472, @0.90=0.499; split-τ (clean@0.98, OCR@0.90)=**0.485**.
  So the gap to 0.97 is **NOT** mainly metric strictness — even at τ=0.90 we're at ~0.50. Adopting a
  per-source τ is a legitimate metric-policy decision (Henrik's call — it moves the headline number)
  but buys only ~+55 provisions.
- **The ACTUAL remaining levers (redirect):** (1) **missing/renumbered provisions** — add-op coverage
  + `nåværende § X blir § Y` renumbering (kjøpsloven 125 missing, vphl cascade-empty); this is the
  large structural bucket. (2) **hard-OCR provisions** well below 0.90 on pre-2001 bases. (3) post-2024
  acts (LTI ends 2024 — permanently flagged). Ledd engine stays flag-don't-fabricate as-is.

## 2026-08-12 (cont.) — "unrecoverable" hole bases RECOVERED from PD booklets: 0.391 → 0.431 (session)

- [x] **Overturned the kjøpsloven/rettsgebyrloven "unbuildable from NB" blocker.** The 1982/1988
  annual Lovtidend Avd. I *content* volumes are a scattered NB digitisation gap (1980/82/84/87/88/89
  undigitised while neighbouring years are fine — missing scans, NOT a copyright wall). But the
  annual volume isn't the only route: **both laws exist at NB as public-domain, EVERYWHERE-access
  digitised standalone booklets (særtrykk)**, fetchable via the same ALTO endpoint the harvest uses.
  (Norwegian statutory text is public-domain by statute — åndsverkloven §14 — regardless of container.)
  - kjøpsloven `1988-05-13-27`: NB digibok `2012050708164` (1993 "med endringer"), body p5–28.
  - rettsgebyrloven `1982-12-17-86`: NB digibok `2012083008131` (1992), body p3–13.
- [x] **These are SNAPSHOT bases, not enactment** — each booklet self-declares its version boundary
  ("Ajourført med endringer, senest …"): kjøpsloven **1993-01-01**, rettsgebyr **1992-08-01**. So the
  booklet already bakes in the law's early amendments — which neatly sidesteps the pre-2001 gazette
  holes (we never needed the 1988–92 amendments; they're in the snapshot). Recorded as `base_as_of`.
- [x] **New snapshot-base machinery (deterministic, offline, faithful):**
  - `build_enactment.BOOKLETS` + `build_booklet()` — resilient page fetch (skips the blank cover/back
    pages NB 500s on), writes `base_as_of` into the enactment JSON. 96 / 29 provisions built.
  - `pipeline.base_as_of()` + `reconstruct()` now replays **only amendments dated ≥ base_as_of** on a
    snapshot base (pre-snapshot ones are already incorporated — double-applying would corrupt).
  - **G3 anti-gaming refinement (maintainer sign-off):** for a snapshot base, a provision amended only
    ON/BEFORE `base_as_of` is *legitimately* identical to current (the snapshot bakes it in), so G3
    now polices only **post-snapshot** amendments. Pure enactment bases (base_as_of None) check every
    amendment as before. Guards G1/G2/G3 **PASS** — no false-trip, and the base is a PD booklet, never
    the answer key (G1/G2 confirm the recon path stays isolated).
- [x] **Result:** convergence **0.391 → 0.431** (394 → 434/1008). kjøpsloven **0 → 39**/180,
  rettsgebyr **1 → 2**/38. Faithful — §3/§6/§9 kjøpsloven reconstruct at sim **1.000** vs current.
- **Residual (the next lever, not this task):** the two laws' remaining gap is (a) ~95 kjøpsloven
  current provisions ADDED post-1993 via add-ops we don't yet apply, (b) rettsgebyr fee amounts change
  almost yearly → post-1992 ledd edits the ledd engine flags, (c) leading footnote-digit OCR pollution
  ("Heving 1 (1)") nudging near-misses just under 0.98. All amendment-coverage / ledd-engine, separate.
- **Follow-up lever noted:** these PD booklets are themselves point-in-time snapshots at a known date —
  a candidate **public-domain validation set** to supplement/replace the encumbered, un-publishable
  Lovdata-Pro oracle (needs held-out partitioning: a booklet used as a base for law L can't validate L).

## 2026-08-12 (cont.) — chapter-block pieces inheriting `unknown` change_type: 0.344 → 0.391 (session)

- [x] **Diagnosed the biggest clean-source lever.** vphl (2007-06-29-75) sat at 142/300 on
  fully clean LTI data — pure engine. Categorized the 158 failures on the LIVE `load_ops`
  (`change_type`) path: 45 failing had a last op of `change_type="unknown"` that got FLAGGED,
  not applied. Root cause: chapter/part block replacements (`Kapittel N skal lyde`,
  `Etter kapittel M skal del … lyde`) are correctly split into per-`§` pieces by
  `pipeline._split_block`, but every piece **inherits the block's `change_type`** — which the
  offline classifier parsed as `unknown` for chapter-level instructions — so
  `replay._apply_change_type` refused them (its gate only accepted `add`/`change`). vphl's 2018
  MiFID II rewrite (chapters 1,2,8,9,10 + new del 4–6 §11-x) was entirely inert.
- [x] **Quantified before building**: 60 `unknown` ops carry a whole-provision `§ N.` body and
  all 60 are current provisions; `move`/`renumber`/`repeal` carry a `§`-body **0** times — so
  gating a fix on "new_text starts with `§`" is provably safe (can't mis-fire on a structural op).
- [x] **Fix** (`source/parse/replay.py`, `_apply_change_type`): a whole-provision `§ N.` body IS
  the provision's new enacted text regardless of the parsed `change_type`; apply it (heading
  stripped) ahead of the add/change gate, excluding `overskrift` heading-only and repeal.
  Faithful — the amending act's own text, never fabricated.
- [x] **Result**: convergence **0.344 → 0.391** (347 → 394/1008). vphl **142 → 189**/300.
  All other laws byte-identical (surgical). Guards G1/G2/G3 PASS. Faithfulness spot-checked:
  §11-1/§11-9/§13-1/§1-1 reconstruct at sim **1.000** vs current; §8-1 at 0.900 is an honest
  later-amendment residual (heading reworded by a still-later act), not fabrication.
- **Residual vphl (111 still failing)**: 94 `change`-flags are sub-provision (ledd) edits the
  ledd engine can't resolve (the next engine lever); ~29 missing are post-2024 acts (LTI ends
  2024 — flag, don't fabricate); 15 are repealed stubs whose current text is a prose
  `(Opphevet) … ved lov …` annotation we can't reconstruct verbatim (a metric-representation
  question, not an engine gap).

## 2026-08-12 (cont.) — OCR-correction experiments: OCR is NOT the pre-2001 limiter

- Ran BOTH a deterministic speller (LTI-lexicon Norvig edit-1) AND an LLM pass
  (gpt-4o-mini, constrained "fix char-level OCR only, change as few chars as possible",
  never told the law/date, cached) on the aksjeloven base, evaluated through the
  **held-out point-in-time harness** (the recall discriminator).
- **Both safe, both weak**: deterministic +2, LLM +3 (2001 ≥0.98). LLM char-edit rate
  **2.3%**, and it helped held-out **2001 MORE than 2024** — i.e. no modernization/recall
  bias. So a *constrained* LLM task gated on held-out point-in-time does NOT cheat here
  (useful: settles the "can we use LLMs" question — yes, for narrow held-out-eval'd tasks).
- **Residual diagnosis (the real finding)**: the still-failing "never-amended" provisions
  differ from current by REAL missing amendments — `§8-4`/`§16-19` `skifteretten→tingretten`
  (2002 court reform), `§20-5` a wording change — plus stray date-header artifacts. NOT OCR.
  These are labelled "never amended" only because our stream didn't resolve the
  omnibus/name-cited acts that changed them.
- **Conclusion**: OCR is a MINOR contributor; the pre-2001 limiter is **amendment coverage**
  (name→datokode + omnibus/blanket-terminology acts). Deprioritise OCR/LLM correction and
  multimodal re-OCR — low ceiling. Infra now in place: OpenAI key from the environment
  (`OPENAI_API_KEY`); a validated-safe held-out LLM-eval harness for any future narrow
  LLM task.

## 2026-08-12 — point-in-time metric UNBLOCKED (the real deliverable bar) (session)

- [x] **Cracked Lovdata-Pro historical-version acquisition via Claude-in-Chrome.** Whole-
  document view URL = `#document/HIST/lov/<datokode>-<YYYYMMDD>/*` (date must be an exact
  version boundary — arbitrary dates redirect to current). Download flow: toolbar
  "Last ned dokumentet" (find by ref, NOT coordinates — the /* view defeats blind clicks)
  → Format=HTML → submit → lands in a Chrome-download folder mapped into the sandbox
  (a local `gt_incoming` folder Chrome's download dir points at).
  `lovdata_html.parse_file` parses it. (Programmatic Blob download is blocked;
  the versions-list "bulk" download only yields a Referanseliste, not contents.)
- [x] **Found + fixed a truth-parser metric artifact** (was masquerading as "OCR").
  `lovdata_html.parse_file` kept the `§ N-M` heading number and left `&#xa0;` undecoded,
  so `normalize` injected spurious `1 2`/`xa0` tokens and demoted correct provisions below
  0.98. Objective test (never-amended `base`, pure OCR, exact-match count): vs the gate
  parser = 81, vs the truth parser = **43 → 69 (drop `§` heading) → 81 (decode entities)**.
  Fix: strip the leading `§ N-M` heading + `_html.unescape` in `lovdata_html.py`. This is
  an eval-harness correctness fix (maintainer sign-off, held-out metric) — same class as
  autojunk / G3 / phantom-reader. Not pipeline tuning.
- [x] **True point-in-time scores** — aksjeloven (1997-06-13-44), reconstruct(as_of) vs
  held-out Lovdata truth, ALIGNED parser:
  - **2024-01-01** (near-current): ≥0.98 **125/292 (0.43)**, ≥0.90 150/292, mean 0.70 —
    ≈ convergence-to-current (124/293), confirming the engine reconstructs recent past
    states as well as the gate measures.
  - **2001-01-01** (near-enactment): ≥0.98 **7/265 (0.03)**, ≥0.90 **128/265 (0.48)**,
    mean 0.80.
  - **Read (honest, resolved)**: the headline deflation was the metric artifact, now gone.
    The RESIDUAL 2001 gap IS genuine OCR — near enactment everything is OCR-sourced
    (base + pre-2001 gazette-OCR amendments), so provisions land ~0.90-0.97 (recognizable)
    but rarely hit the strict 0.98. So: post-2001/clean-source point-in-time is strong;
    pre-2001/OCR point-in-time is recognizable-not-exact and wants an OCR-calibrated τ.
- Ground-truth files (`data/ground_truth/1997-06-13-44/{2001-01-01,2024-01-01}.html`) are
  gitignored (encumbered oracle); only `index.csv` is tracked.

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
- [x] **Two eval-harness fixes (maintainer sign-off)**: G3 threshold ≥0.98→**≥0.999** (real
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
  default silently collapsed long-provision similarity toward 0). Maintainer sign-off.
- [x] **Mapped NB Lovtidend Avd. I coverage 1877–2000** — 1,033 items / ~144k pages,
  all public-domain; holes = 1891,1976,1980,1982,1984,1987,1988,1989. kjøpsloven (1988)
  unrecoverable from NB; other 5 pre-2001 dev laws fine (rettsgebyrloven via 1983).
- [x] **Scoped acquisition** — no bulk NB endpoint / no NCC Lovtidend subset exists;
  per-page ALTO is the only running-text source (~0.3GB text, ~16h).
- [x] **Built + launched the harvester** — `source/scrape/harvest_lovtidend.py`
  (newest-first, page-resumable, 6 workers) → `data/lovtidend_text/` (gitignored),
  work-list `data/lovtidend_index.json`. The full harvest was approved.
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
~0.39). Two decisions pending. Secondary: `amendments.jsonl.gz` truncates
`new_text` at 4000 chars (liftable from LTI XMLs).
