# Todo

## Curated segmentation + law register (PLAN, 2026-10-02 — see decisions.md)

The long-term track. Harvest coverage is the binding constraint (register covers 10% of in-force laws),
not the engine. Build the backbone, make the segmentation a curated dataset, then hand off to Eivind.

- [x] **Law-identity register — bootstrap.** `source/scrape/build_law_register.py` → `data/law_register.jsonl`
  (1451 identities from the 224 indexed issues; public, oracle-free). Committed 76a1af6.
- [x] **Enrich register with Lovdata `gjeldende` (public in-force dataset).** Done 2026-10-04:
  `build_law_register.load_gjeldende()` parses identity+lifecycle (title, departement, legalArea,
  dateInForce) from the free no-auth download (`api.lovdata.no/.../gjeldende-lover.tar.bz2`, extracted to
  `data/lovdata_gjeldende/`, gitignored). Register 1451→2053; in-force universe complete (754, all with
  ministry/legal-area); `fulltext` + `lastChangedBy` NOT read (oracle). **CORRECTION to the prior plan:
  Lovdata is IN-FORCE ONLY — it does NOT include repealed laws, so it does NOT complete the historical
  register.** It completes the in-force universe + metadata and gives an in-force status signal.
- [ ] **Complete the HISTORICAL register (repealed laws) — the real lever is FULL-HARVEST SEGMENTATION,
  not a download.** No free top-down source lists repealed Norwegian laws (Lovdata excludes them;
  norgeslover.no seeds from current text). The only authoritative public record of every law ever enacted
  is Norsk Lovtidend itself → segment the full NB harvest (1877–2000) bottom-up; every enacted law surfaces
  by identity. Permanent residual: pre-1877 laws (e.g. Grunnloven 1814) are outside the harvest window.
  Two-tier target resolution: in `gjeldende` = old-but-in-force (coverage gap); in neither = repealed/
  pre-window or garble.
- [x] **Extend the G1 guard** to ban the reconstruction path from importing the law register. Done
  2026-10-04: `gate._REGISTER_LITERAL` + the import-scan ban `build_law_register` / `law_register.jsonl`
  in any `RECON_MODULES` file (text + AST). "Register flags, the gazette adjudicates" is now enforced in
  code, not trust. Verified: PASS on the real recon path, FIRES on a planted import/literal violation.
- [x] **Expand segmentation to the FULL NB harvest.** Done 2026-10-04: 914→1005/1033 issues (segmented
  the 91 normal; +2 laws, forskrift-heavy). 1172 distinct acts. 28 giant bound volumes SHELVED (1-giant
  probe: 1869–1911 repealed, 0 in-force recovery, ~600k tokens/9 laws — optional historical padding only).
- [x] **Build in-force bases via the locator (`build_from_index`).** Done 2026-10-04: 74/78 index-harvestable
  in-force laws built (95%), median-sim 0.80, 51/74 ≥0.5. In-force bases 9→83. Locator confirmed good at
  scale; sub-0.5 are amendment-capped not locator failures. (4 empties: 1978-06-02-37/38, 1978-06-09-50,
  1992-06-19-61 — bound-volume layout, revisit if needed.)
- [x] **Post-2001 LTI path measured.** Done 2026-10-04: 302/438 built, median-sim 1.00, 89% ≥0.5. TRUE
  in-force coverage = 385/754 (51%), ~321 ≥0.5. Undercount corrected (gazette-only probe said 11%).
- [ ] **Refresh the LTI dump to 2025–2026 — CORPUS-CURRENCY, not a metric lever (re-tagged HS 2026-10-04).**
  `data/lti` dirs stop at 2024; the 77 missing in-force laws (40 in 2025, 37 in 2026) are all NEW
  enactments. They reconstruct near-trivially (base ≈ current, no history) so they move NEITHER metric
  that matters: convergence runs on the fixed 9-law `gate.DEV_LAWS` (1918–2009), and point-in-time needs
  laws with history. The only thing they move is the in-force coverage COUNT (~51%→61%) — breadth padding
  with tautological wins, not the goal gate. Worth doing ONLY if "published corpus current through 2026"
  becomes an explicit deliverable goal, and then it's a MATCHED refresh (answer-key `data/current` +
  amendment stream in lockstep) — a one-sided dir top-up against a pre-2025 answer key would WORSEN the
  metric (reconstruct a 2026 state, grade vs a 2024 answer). Parked until that scope call.
- [ ] **~59 scattered per-law LTI gaps (2003–2024)** — individual empties/parse-fails; lower priority.
- [ ] **pre-1970 in-force tail (~100) = NB-gap** — NB digitised register/index-only for many old years, so
  largely unrecoverable from NB. The genuine hard residual; accept or seek a non-NB source.
- [x] **`segments.jsonl` as curated truth.** Done 2026-10-04: `build_segments.py` → char-offset partition
  (2459 segs / 312 law-bearing issues), filler explicit, `start_line` + `head` anchors + frozen sha
  (`segments_meta.json`); offsets via `frozen.find(body)` (zero LLM); `segment_issue` now emits start/end.
  Partition structurally clean (0 gap/overlap-end/sha-drift/head-mismatch).
- [x] **`classification_qa.py` invariant suite (report).** Done 2026-10-04: coverage/overlap/sha/head +
  klass↔marker + target-resolve. Baseline 388 violations = the work queue (target-missing 284, klass-marker
  74, overlap 10, target-unresolved 20).
- [x] **classification_qa `--diff` pre-commit gate.** Done 2026-10-04: fails if any violation category
  grows vs HEAD; installed as local `.git/hooks/pre-commit` (reinstall on fresh clones). Verified both
  ways — blocks a degrading edit, allows an improving one.
- [~] **Work the queue (ongoing).** Queue 388→353→**330**. Passes 2026-10-04: (1) `resolve_targets.py`
  filled 35 target-missing by law name (284→249, gated); (2) taught `classification_qa._AMEND_MARK` the
  archaic amendment/repeal verbs (brigde/bridge, forandr-, forleng-/lengjing, opph[øo]r, "tillegg til") —
  klass-marker **74→51**, a pure false-positive removal (each cleared segment's title/head carries a real
  amendment verb; verified by eye). REMAINING, now characterised:
  - **klass-marker 51** — NOT a regex gap any more; these are enactment-headed acts ("Lov nr. N om
    <own-name>") mis-tagged `amend` by the bootstrap classifier, plus a few over-capturing TOC chunks
    (e.g. `om folkeregistrering` body = a 6k-char TOC slice; `om brigde i lov om omsetningsavgift` = 27k).
    Fix = klass curation (amend→enact) + re-segmentation, NOT a marker tweak. Entangled with `overlap`.
  - **target-missing 249** — richer name/subject matching; but many target laws simply aren't in the
    register → register-completeness, not resolvable here.
  - **target-unresolved 20** — CONFIRMED pure register-incompleteness (2026-10-04): all 20 are distinct
    repealed/old datokodes 1890–2000 absent from the register (in-force-only gjeldende + indexed issues
    don't cover them). Resolves only when the HISTORICAL register is complete (full-harvest segmentation).
  - **overlap 10** — duplicate-body `find` edge cases — switch to native segment offsets once chunk
    caches refreshed.
- [ ] **Two-level omnibus blocks** — split each omnibus `amend` segment into per-target sub-blocks
  (`I … II …`), each resolving to one target law (the ~38% multi-target acts).
- [ ] **`applied_ops` reproducibility drift (noticed 2026-10-02).** `data/applied_ops.jsonl.gz` is
  untracked; the on-disk Aug-23 artifact scores 601/829, but regenerating it
  (`python -m source.scrape.build_applied`, warm cache) yields 599 — a silent −2 the current cache/code no
  longer reproduces. The "good" 601 copy lives only on disk. Either commit the artifact or find the drift
  before any clean rebuild silently drops 2 provisions.
- [ ] **Eivind handoff (PARKED until next week, HS 2026-10-02).** Labour-market laws under-covered
  (only folketrygdloven well-covered); don't reply today. Repo self-serves once register + segments +
  classification_qa are in place. (Manudeep thread "Historiske lover (1990-tallet)"; HS promised info ~Fri,
  now deferred.)

## Locator → `segments.jsonl` fold-in (PRIORITY, 2026-10-04 — see decisions.md)

> **RESUME POINT (2026-10-05, HS paused at usage limit):** flat corpus = **253/312 small issues
> committed**; chunker validated. PENDING: stitch+fold the 16 flagged + validated giant (→ ~270), then
> run the 42 giants (~82M tokens, approved "Full") → full ~312. Full resume plan + caveats in
> `docs/notes/handoffs/2026-10-05T10-00-00_corpus-giants-resume.md`. Giant/flagged chunk runs were STOPPED;
> scratchpad + same-session Workflow cache won't survive the reset, so expect a clean re-run (chunk files
> regenerate deterministically via `chunk_ranges`).

The locator is BUILT and validated for normal issues (~71% ≥0.5, ~5% true mislocation; 74/78 in-force
bases at median-sim 0.80). It is NO LONGER the binding constraint. The next move is to make its output
PERMANENT and OWNED: `segments.jsonl` is THE corpus artifact, the locator becomes its offline bootstrap,
and we improve the file one gated commit at a time (decisions.md 2026-10-04). Ordered:

- [x] **S1 — second commit-gate signal (base-quality no-regression).** Done 2026-10-04:
  `source/eval/segments_quality.py` (`report` + `--diff` gate). For each law whose enactment
  (`klass=original`) offsets change vs HEAD, it slices the frozen issue, splits with the deterministic
  `parse_provisions` (no LLM), and compares median per-provision similarity to current — RELATIVE
  (HEAD-offsets vs working-offsets), so amendment drift cancels and the delta isolates the offset change.
  FAILs if any touched law drops > 0.02; skips cleanly with no baseline / no answer key. Verified: no-change
  skips, improvement passes, regression FAILs (exit 1, e.g. 1.000→0.049). Also made the gate REPRODUCIBLE:
  `source/eval/install_hooks.py` (tracked) writes the two-signal `.git/hooks/pre-commit` (classification_qa
  --diff THEN segments_quality --diff) — run `python -m source.eval.install_hooks` on fresh clones.
  NOTE: current `report` shows median 0.000 / 13-of-57 ≥0.5 — a faithful diagnosis that segments.jsonl holds
  the WEAK raw offsets today (e.g. 2000-07-07-68's "original" is a 223-char TOC fragment). That is exactly
  what S2 fixes; S1 ensures S2 can only move those scores UP. V2: handle chapter-section (§N-M) ids (the
  current `_REAL` regex scores only flat §N laws) and upgrade to full reconstruction once S3 lands.
- [ ] **S2 — fold the locator's refined offsets INTO `segments.jsonl`.** Replace `build_segments.py`'s
  `frozen.find(body)` with the locator's start (`locate_body`) + `_NEXT_LAW`/LLM end, stored as NATIVE
  char offsets (kills `overlap-10`). One commit per issue-batch, each passing S1 + `--diff`.
- [ ] **S3 — repoint `enactment_base`/`build_from_index` to READ `segments.jsonl`** (the `datokode`,
  `klass=original` row → slice the frozen issue). Zero live LLM at build time; retire the throwaway
  `build/enactment/<datokode>.json`.
- [ ] **S4 — archive the old locator (ONLY after S2/S3).** Archive the LIVE locate path + the regex
  locator stack (`_regex_start`, `_HEAD`/`_repair_headings`; per the 2026-08-14 "retire regex only after
  migration" policy). `locate_body`/`segment_issue` survive as OFFLINE correction tools that write curated
  offsets, never a runtime path.
- [~] **S2 via CLAUDE SUBAGENTS, not OpenAI (decided HS 2026-10-04).** Pilot + 6-issue Workflow proved the
  base path: subagent given ONLY public OCR returns verbatim-anchored acts + provisions (reading through OCR
  §-glyph garbles "S 2."→§2 the regex drops); base 2000-07-07-68 0.000→**0.976**, planteforedler 0→0.905.
  $0 OpenAI; reproducibility lives in the git-tracked file. Infra committed (6568b87). Next: implement the
  v2 schema below, re-validate the 6-batch, scale to ~121.
- [ ] **SEGMENTATION SCHEMA v2 — finalized from two stress-tests (2026-10-04).** The two tests pulled
  OPPOSITE ways: whole-§/ledd wants THIN ops (verbatim verb + payload span, no decomposition); renumber/
  word-replace/positional-insert want STRUCTURED fields or downstream must re-parse OCR-dirty prose / align
  content that doesn't exist (chapters). Resolution — **located-not-computed, but "located" includes typed
  fields WHEN the value is stated verbatim in the instruction** (copying `«kostnadsprøving»` into a `from`
  field is locating, not computing); only BASE-dependent facts (insert-vs-replace on a bare "skal lyde",
  resolving "de fire eksisterende") are left to assembly. Deep nested addresses STAY as prose inside the
  anchor (never decomposed into {ledd,nr,bokstav} — test 1's warning). Schema:
  FLATTENED (HS 2026-10-04, stress-tested): ONE flat char-partition per issue — every char in exactly one
  typed segment (no nested arrays). Supersedes the choice-b nesting; collapses "classify everything" +
  "smallest segments" into one principle. Flat stress-test (furniture-interrupted §17 + chapter
  renumber+heading + inserted treaty block) verdict: tiles cleanly, nothing forces overlap/non-linearity.
  ```
  segment = { issue_id, start, end, start_line, head,
    kind: masthead|toc|act_heading|preamble|provision|amend_scope|amend_op|in_force|forskrift|signature|noise,
    unit_key,                   # groups fragments of ONE logical unit split by furniture (assembly concats by key)
    datokode?,                  # FK: the act this segment belongs to (on act_heading + all children)
    nr?, date?, title?,         # act_heading
    para?,                      # provision
    target?, target_cite?, instrument?,   # amend_scope header ("I lov/forskrift …") + amend_op
    op_kind?,                   # amend_op: set_text|repeal|renumber|word_replace|insert
    payload_start?, from?, to?, position? }   # amend_op (payload_start = offset new text begins)
  ```
  Rules: (1) hierarchy is DENORMALIZED — the act = the run of same-`datokode` segments in order; no nesting.
  (2) **Granularity FLOOR — never segment INSIDE a provision/op payload.** Inserted structured blocks
  (a whole chapter, treaty articles "Art 1 … Art 2 …") = ONE `amend_op` payload; their internal ledd/§/
  article structure is parsed ON DEMAND by ASSEMBLY against the base, never stored in the partition. This is
  the ONE thing flat can't represent (nesting) — and we avoid it by deferring, not encoding. (3) A unit split
  by page furniture = multiple segments sharing `unit_key` + a `noise` segment between; reconstruction
  concatenates by key. (4) ONE instruction may yield MULTIPLE ops (chapter renumber+heading = renumber +
  set_text, same unit_key). (5) `address`/scope lives in the segment text (assembly parses it, doesn't
  re-emit). (6) `set_text` = bare "skal lyde" (assembly decides replace-vs-insert vs base); `insert` =
  explicit "ny/nytt/skytes inn/inntas". Reconstruction-time caveats (assembly, not schema): OCR
  de-hyphenation/de-wrap when concatenating fragments; validate+flag unequal-length renumber ranges.
- [ ] **S5 — full-corpus run POPULATES `segments.jsonl`** (not a throwaway dir), gated on S1. This is the
  deferred "clean corpus run", now re-stated against the current stack's bar (see below), not the stale
  regex-era numbers.
- [ ] **The 22 giant bound volumes (>600k chars) — SPLIT + fan out to separate agents (HS 2026-10-04).**
  Too large for one subagent context (up to 3.7M chars ≈ ~930k tokens). Plan: split each giant at
  reasonable boundaries (per-year, or at detected act-cluster gaps), hand each chunk to its own subagent,
  then stitch the anchored results back against the single frozen issue text (offsets are global, so
  chunk-local anchors still resolve via `frozen.find`). Low in-force value (old repealed laws) but needed
  for a complete historical register. Do AFTER the 121 normal issues validate the per-issue path.

The items below are the pre-reframe residuals, now SUBORDINATE to the fold-in:

## Out-of-sample / full-corpus scaling (OPEN FORK, 2026-09-25 — see done.md)

Out-of-sample probe (2026-09-25): post-2001 generalizes (random 0.748 ≈ dev 0.808); pre-2001 is
consistent where bases build (0.56–0.73, dev range) but blocked on enactment **base construction**, not
the engine. Two structural blockers surfaced: enactment location is hand-curated (`LOCATIONS`, 9 laws
only; the "search-based locator" is unimplemented), and the harvest is bimodal (89 files are 400+ pp
bound volumes that `segment_issue` under-segments — this also caps existing `build_gazette` recovery).

**Locator BUILT (2026-09-30).** Chose fork (B) and implemented the general path — no more hand-authored
`LOCATIONS`:
  - `source/llm/segment_issue.py`: dedup by **datokode** (date+nr), not nr — fixes the giant multi-year
    volumes (the "89 files" root cause was cross-year nr collisions, NOT a page/token cap). Verified: the
    1975 decade-volume went 77 → 138 acts and dokumentavgift (1975-12-12-59) is now located. Single-year
    issues unchanged (datokode-dedup ≡ nr-dedup there), so no `build_gazette` regression.
  - `source/scrape/build_act_index.py`: aggregates the cached per-issue segmentations into
    `data/act_index.json` (datokode → issue). The "tag every act" index.
  - `source/scrape/build_enactment.py::build_from_index(datokode)`: locate via the index → segment body →
    base, zero hand-curation.
  - **VALIDATED on well-behaved laws:** via the index (no LOCATIONS) aksje scores 0.66 ≈ its hand-curated
    0.65, mester 0.64, energiloven 0.66 — the locator reproduces hand-curated quality.

- [x] **Gap B — enactment-body boundaries — LARGELY FIXED (2026-09-30).** Root cause was two-fold:
  `segment_issue` anchors the table-of-contents entry ("Lov nr. N om <title> <pageno>"), not the real body
  heading ("Lov nr. N / Lov om <title>"), and its body END is unreliable. `build_from_index` now (a) relocates
  the start via the canonical enactment-heading regex (nr + "Lov om" + title, title truncated at the TOC page
  number) picking the occurrence followed by real §§, and (b) cuts the end at the next `_NEXT_LAW` gazette
  heading (deterministic, as `_law_text`), flagging bodies <200 chars or with no §. **Validated 5/6:**
  planteforedler 0.21→0.73, enhetsregister 0.21→0.59 (both = grep/hand quality), aksje 0.66, mester 0.64,
  energiloven 0.66 — all via the index, zero hand-authored LOCATIONS.
  - [ ] **Residual: older-bound-volume END boundary.** In older bound multi-year volumes (e.g. the 1975
    volume holding dokumentavgift) the heading is the BARE short title ("Dokumentavgift.\n§ 1.") and there is
    NO "Lov nr … Lov om" between acts — the next act just RESTARTS § numbering. `build_from_index` now locates
    the START correctly in this layout (title-immediately-followed-by-§1 fallback), but the END over-captures:
    `_NEXT_LAW` finds no boundary so the body runs to the volume footer (dokumentavgift base_n 46 vs 14, 0.00).
    Tried + rejected (both hurt): a "Lov nr M != nr" boundary (misses — no Lov nr in this layout) and a
    "second standalone § 1" boundary (cut mid-law — the law's own § 1 recurs). Needs a boundary robust to the
    bare-title/§-restart layout without regressing modern issues (or split giant volumes per year first). This
    layout is the ~pre-1970 bound volumes; modern-heading pre-2001 laws are handled (5/6 validated).
- [~] **Full-corpus index pass — LARGELY DONE 2026-10-04.** `data/act_index.json` now = 1172 datokodes
  from 1005/1033 issues (was 1170 from 914). Remaining: 28 giant bound volumes unsegmented (shelved — old
  repealed laws, 0 in-force recovery, ~600k tokens each; need a chunked LLM pass or per-year split).
- [ ] **Locator quality gate before a "clean" corpus run — PREMISE SUPERSEDED 2026-10-04.** The ~48% /
  ~30%-mislocated figures were the REGEX locator; the current LLM locate+segment stack is ~71% ≥0.5 /
  ~5% mislocation (done.md 2026-10-01/10-04). The gate now lives in S1 above (answer-free base-quality
  no-regression as the second commit-gate signal), and S5 re-states the corpus-run bar against the current
  stack. Still TODO: re-measure the honest bar on a fresh random sample (cold LLM spend — needs HS sign-off)
  and tag the residual ~5% mislocation tail. Over-capture remains a silent failure without the S1 quality
  signal — which is exactly why S1 is built first.
- [ ] (independent) triage the ~1/4 of post-2001 acts that parse to **0 current provisions**
  (amending/structural acts vs a current-parser schema gap) before any full-corpus denominator.
- Lovdata CD (fork A) remains complementary — clean bases + eval oracle — but no longer the only pre-2001
  path now that the locator works.

## Next engine work (the real remaining lift)

> **Ceiling reality (2026-08-13, from `loss_breakdown`).** The 0.97 gate is **not reachable
> on this dev set**: hitting it needs +355 of the 381 misses (~93% of *everything*), but 8%
> is char-OCR noise with a proven low ceiling (lesson 4) and 29% is the risky ledd/renumber
> tail. Best case, stacking every safe + risky lever, tops out ~**0.90–0.94**. This is
> expected — `goal.md` calls the 0.97 target "provisional until the held-out set is
> assembled", and the *real* deliverable bar is the held-out point-in-time metric (blocked on
> the manual Lovdata-Pro download below), not convergence. **Do not lower `gate.THRESHOLD`
> without Henrik sign-off** (that is the anti-gaming "loosen the bar" move). Keep working the
> safe capture lever; when it is exhausted, the honest stop is a `BLOCKER.md`, not chasing OCR.

- [ ] **Amendment coverage — THE lever, now QUANTIFIED (2026-08-13, `source.eval.loss_breakdown`).**
  Correcting OCR (deterministic OR LLM) barely helps; the residual gap on "never-amended"
  provisions is REAL missing amendments (e.g. skifteretten→tingretten 2002 court reform,
  wording changes) whose amending acts our gazette parser didn't resolve. Three sub-levers:
  (a) ~~**name→datokode map**~~ — MEASURED ~ZERO 2026-08-13 (see done.md): across all 1033 harvested
  issues, TOC-title name-citation of the dev laws is 0 (avtale/foreld/rettsg/mester/kjøp), so a name
  map recovers nothing on the dev set. The pre-2001 residual is harvest COVERAGE + blanket reforms;
  (b) ~~**omnibus acts**~~ — MEASURED SMALL 2026-08-13 (see done.md): LTI stream already well-targeted
  (1/304 header rows mis-file a dev law); pre-2001 `I lov <dev-cite>` secondary headers only 3/6/1 for
  avtale/foreld/kjøp. Not worth a full-stream rebuild; the pre-2001 gap is (a)/(c), not omnibus;
  (c) **blanket terminology reforms** — sweeping renames (skifteretten→tingretten) applied
  across all laws; may need special handling.
  **Quantified (loss_breakdown, 381 misses):** the single biggest, SAFEST lever is amendment
  *capture* — **184 of 381 misses (48%) have ZERO op** in our stream targeting that provision
  (`uncaptured-amdt` 100 + most of `base-missing` 84, whose examples §9a/§38a-c/§5a/§15a are
  uncaptured `ny §` adds). Solving capture is deterministic + flag-safe and would move
  convergence ~0.56 → ~0.75–0.80. NEXT: start with omnibus multi-target in `gazette.py` +
  applying `ny §` adds. Run `python -m source.eval.loss_breakdown` for the current attribution.
- [ ] ~~OCR/LLM correction, multimodal re-OCR~~ — TESTED + DEPRIORITISED (2026-08-12,
  see done.md): safe but low ceiling; OCR is a minor contributor.
- [x] ~~**Evaluate `martgra/lovdata-pipeline` §/ledd/chapter parser**~~ — DROPPED (~2026-09): pipeline
  pivoted to LLM segmentation/op-extraction (`source/llm/`), so a deterministic structural parser is
  obsolete. See `docs/notes/external_source_repos.md`.
- [ ] **Renumber-target provisions (~35, the hard residual) — via TEXT-SIMILARITY MATCHING (prototyped
  2026-08-14, see done.md).** Instead of parsing `nåværende §X blir §Y`, align consecutive versions by
  `metrics.similarity` (bipartite mutual-best above threshold): a high text-match under a different id = a
  renumber → recover the id-remap from content. Deterministic, fabrication-free (alignment only). Prototype
  recovered vphl §20-1/§20-3 (renumbered from §16-x) and safely flagged genuine gaps. Productionise: a
  `source/parse/align.py` matcher; use it to resolve flagged renumber/move ops and for ledd-level alignment
  (the ledd engine's positional-address failures) and as a text-based validation matcher.
- [ ] **OCR base-drops (small, safe).** A handful of real statutory provisions are dropped by base
  OCR extraction — kjøpsloven §1/§50 (l/1 confusion: "§ l."), §71; foreldelsesloven §15a. Fix the
  `_HEAD` regex / booklet page span. ~4 provisions, low risk.
- [ ] ~~**ledd engine — finish insert/nr/punktum ops.**~~ MEASURED + DEPRIORITISED 2026-08-12
  (see done.md): true convergence ceiling is only ~56 provisions and they are the *riskiest*
  (INSERT `nytt … punktum` needs legal-sentence segmentation → fabrication risk). Not worth it vs
  the missing-provision lever. Keep flag-don't-fabricate.
- [ ] **Preserve nr/bokstav markers in whole-provision replacement bodies.** `endringslov`/
  `gazette` strip `1. 2.` / `a) b)` markers from `§X skal lyde` / `Kapittel N skal lyde`
  bodies, so a later `nr. 4 skal lyde` finds no list and flags (~77 flagged nr ops). The
  ledd *engine* already handles these when markers are present — this is upstream.
- [ ] **Unnumbered-ledd on OCR bases** — `parse_provisions` collapses whitespace, so
  pre-2001 laws (unnumbered ledd) lose ledd boundaries and the engine can't split them.
  Preserve line breaks in the OCR base to enable ledd editing there (LTI already does this).
- [ ] **PD booklets as a public-domain point-in-time VALIDATION set — VIABLE; needs a
  heading-tolerant parser (NOT an OCR problem).** Corrected 2026-08-13 (I first mis-blamed OCR —
  the project's signature trap). Catalog sweep found unused PD snapshots: aksjeloven 2001
  (`digibok_2023030748042`), foreldelsesloven 1992/1993, kjøpsloven 1991, rettsgebyr 1993. The
  aksjeloven-2001 cross-check (ajourført exactly 2001-01-01, vs the Lovdata-Pro 2001 GT we hold)
  looked bad at first (26% coverage, mean 0.60) — but that was **`parse_provisions` failing to
  segment garbled `§ 1 —3` headings, not OCR**: the OCR carries 279 of 293 headings; the strict
  `_HEAD` regex matched only 71. **Repairing the heading token (same OCR) → 94% coverage (250/265),
  median 0.991, mean 0.846, 63% ≥0.98 / 73% ≥0.90.** So the booklet DOES reproduce the oracle.
  DONE 2026-08-13: heading-tolerant parser built (`_repair_headings`, line-anchored, opt-in via
  `parse_provisions(repair_headings=True)`, booklet-only — the clean gazette bases don't benefit and
  a global repair regressed aksjeloven, so it's off by default; regression-clean). aksjeloven-2001
  booklet now parses 95% coverage / median 0.994 vs the 2001 oracle. NEXT:
  - (a) ~~**bank booklets as a PD validation set** — a loader yielding `{para: text}`.~~ DONE
    2026-08-13: `source/eval/booklet_gt.py` (registry + cache), aksjeloven-2001 scored vs the oracle
    end-to-end — content faithful (booklet↔oracle median 0.994) but a ~9pp same-verdict gap
    (see done.md). Two residual items before it's a drop-in numeric oracle substitute:
    - ~~11 segmentation fails~~ PARTLY DONE 2026-08-13: `_is_failed_extraction` flags/drops 8/11
      unambiguous garbage (zero collateral); gap 9.1→7.3pp. Recovering the rest needs layout-aware
      OCR (footnote-zone detection lost in flattened ALTO) — five deterministic re-extraction
      attempts all regressed, so not worth more heuristics; 3 fragments remain flagged-absent.
    - **OCR-vs-OCR τ** (now the DOMINANT residual) — scoring an OCR reconstruction against a scanned
      booklet double-counts OCR; needs a lower τ than the clean-oracle 0.90, or a born-digital edition.
  - (b) **held-out partition** — a booklet used as a base for law L must NOT also validate L
    (encoded: `booklet_gt.BOOKLETS` omits kjøpsloven/rettsgebyr, whose booklets ARE their bases).
  - (c) re-test **aksjeloven-2001 as a cleaner BASE** now the parser lands (median 0.994 vs 2001 GT
    beats the noisy gazette base's 149/293 — build it with base_as_of=2001-01-01 and compare).
  - (Booklet-as-cleaner-BASE for foreldelse still unproven: 1993 base-only 14/33 @0.9 vs gazette 18/33.)
- [ ] **Sub-provision REPLACE/ADD (ledd `… skal lyde`) — the deferred +3, blocked on ledd-engine idempotency,
  NOT in-force.** Enabling `whole_only=False` now nets +3 but with 3 replacement regressions (§21-15/§5-27/§16-9)
  that are DOUBLE-APPLICATION (a whole-provision rebuild + an in-force sub-op on one §; the ledd engine isn't
  idempotent). PROVEN not-in-force: all three acts are triggered/in force per the in-force index. Needs an
  idempotent `ledd.apply` (detect the change is already present, skip) before `whole_only=False` is clean.
- [ ] **In-force resolver follow-ups** (the resolver itself is DONE 2026-08-14 — `source/parse/inforce.py`,
  see done.md; these two refinements remain):
  - [ ] **Per-provision partial scope for "delt ikraftsetting"** — act-level resolution assigns the earliest
    trigger date to ALL of a split act's ops, so a provision in a LATER (or never-triggered) batch is
    over-applied (e.g. aksjeloven `2019-03-15-6` §4-13 → resolved 2020-01-01 but that § came later). Parse the
    "§§ X trer i kraft …, resten senere" scope from each resolution body for full fidelity. Refines the
    point-in-time tail; not a convergence lever.
  - [ ] **Extend the resolver to the EXTERNAL amendment stream** (`amendments.jsonl.gz`), not just the LTI
    re-parse stream — resolve `date_in_force_resolved` by `act_refid` at load in `pipeline.load_ops` (or a
    one-off patch pass), so the whole point-in-time deliverable benefits, not only the omnibus-recovery rows.

## LLM structural segmentation (boundaries-only) — see docs/thinking.md

- [ ] **Productionise the boundaries-only segmenter** (concept CALIBRATED 2026-08-14, see done.md:
  aksjeloven-2001 booklet 69→253 provisions from one prompt, 100% substring-verified, matched the hand-tuned
  regex). Path: (a) add deterministic invariant guards to the extractor — monotonic + non-overlapping + coverage
  + heading-matches-number — as the Pydantic validator (llmkit), flag/repair the residual out-of-order boundary
  the prototype hit; (b) try a stronger model (gpt-4.1 / Claude) to close the 2-provision gap; (c) chunk long
  laws by chapter with overlap; (d) wire as an OPT-IN per-law path in `parse_provisions` (like repair_headings,
  OCR-base laws only — clean LTI bases keep the deterministic path). Cache + audit via llmkit (reproducible
  build input, not a gate-time call). G1: the model sees only public-domain OCR, never current/oracle text.
- [ ] **Amendment op-extractor (boundaries-only) — CONCEPT VALIDATED 2026-08-14 (see done.md Calibration 4):**
  gpt-4.1 resolved 27/27 target laws in an omnibus act (vs our parser's 6) and matched our aksjeloven ops
  exactly. REMAINING: payload slicing — the free-form payload line-RANGE was 0/80 substring-verified (LLM
  arithmetic weakness). Fix: LLM returns only the INSTRUCTION line per op; slice the payload deterministically
  from there to the next instruction (mirror the base segmenter), or use verbatim anchors. Then substring-
  verify every payload (the fabrication guarantee must hold on the amendment side too). This could recover the
  omnibus sections our stream drops + the renumber/move ops (vphl-2018 MiFID drag).
- [ ] **Productionise the base swap (the GO):** `source/parse/llm_segment.py` via llmkit (cached,
  Pydantic-validated; monotonic/coverage/heading-matches-number invariants in the validator; audit). Wire
  opt-in per-law into `enactment_base`/`build_enactment` for OCR-base laws (clean LTI keeps deterministic).
  Run the gate; expect the OCR pre-2001 tail to lift. Then retire `_HEAD`/`_repair_headings`/`_GARBLED_SECT`
  for those laws. Extend the base segmenter to the anchor mode for line-break-poor sources.
- [ ] **Phase 2 — amendment-side LLM swap** (pre-2001 gazette endringslov): identify every amending act for a
  law across the harvest, LLM-parse each into ops (line-labels or anchors), merge into the stream. Validated in
  isolation (27/27 laws, ops exact, payloads source-verified); this wires it into the pipeline + gate.
- [ ] **Phase 2 — ledd application (the 35% bucket): LLM boundaries + similarity alignment.** `source/parse/
  align.py` BUILT 2026-08-14 (`target_ledd` content-targets the amended ledd with a margin criterion,
  version-robust + idempotent — validated on vphl §3-1; `find_renumbers`/`mutual_best` for the renumber tail).
  REMAINING: (a) LLM ledd-boundary extractor (segment a provision into ledds, boundaries-only) so OCR bases
  can be split; (b) an idempotent `ledd.apply` that uses `align.target_ledd` (skip if already_applied, flag if
  unmatched) + end-state alignment verification; (c) wire into replay behind the gate, then flip
  `whole_only=False` cleanly (the double-application blocker is solved by idempotency). PERF: `find_renumbers`
  is O(n²) — run it only over id-UNMATCHED provisions (prefilter), not the full set.

## Measurement side (point-in-time fairness)

- [ ] **Recon-side footnote entanglement (the follow-up the GT fix exposed).** On some vphl provisions the
  RECONSTRUCTION carries footnote-ish cross-reference text (from LTI amendment bodies / current-text notes),
  so once the GT footnotes are removed those provisions drop (vphl 2021 rate 0.777→0.713; §2-8/§9-35/§21-16
  recon_has_footnoteish=True, plus others). Strip the same footnote apparatus on the recon/base side so both
  sides are symmetric. Should recover the two wobble versions (vphl 2021, aksjeloven 2024) and lift clean-law
  point-in-time further. Measurement/parse-side, deterministic; verify with the per-provision no-regression guard.
- [ ] **tjenesteloven §29 "Endringer i andre lover" — editorial redaction, FLAGGED not chased.** Lovdata
  consolidates the consequential-amendment list to "– – –"; our base carries the enacted enumeration.
  Reproducing "– – –" would overfit the oracle's editorial convention. If ever worth it, handle like a
  convention annex (scope out "Endringer i andre lover"-type provisions), not by trimming the base.

## Follow-up — extend to forskrifter

- [ ] **Extend the pipeline to sentrale forskrifter** (currently lover-only). Sources
  and structure are identical, so most of the reuse is free: the Lovtidend delta
  stream already carries `sf-…` acts alongside `nl-…`; `gjeldende-sentrale-forskrifter.tar.bz2`
  is the current consolidated base; and `sondreskarsten/norwegian-laws` already versions
  ~5,123 forskrifter back to the 2001 floor (the source zip has the `historie/` wordings).
  Work needed: (a) add a few forskrifter to the eval/ground-truth set (they're not scored
  today), (b) flip the recipe filter — `source/parse/nlod_recipe.py` currently *drops*
  res./forskrift instruments as noise, but for forskrift-as-target the amending instrument
  *is* a forskrift/resolusjon. Post-2001 first (nearly free given Sondre's corpus); pre-2001
  forskrifter inherit the same clean-base / OCR issues as pre-2001 laws.

## Manual (ground truth for the eval)

- [ ] **Download Lovdata Pro historical versions** for the ground-truth eval set.
  Spec: `docs/ground_truth.md`. Save each as **HTML** ("Historiske versjoner" →
  date → save-as-HTML). Drop them in the repo root (I'll file + parse them) or
  directly into `data/ground_truth/<datokode>/<YYYY-MM-DD>.html`.
  - Priority 8: aksjeloven `1997-06-13-44` (started — 2003 done), rettsgebyrloven
    `1982-12-17-86`, avtaleloven `1918-05-31-4`, oreigningslova `1959-10-23-3`,
    kjøpsloven `1988-05-13-27`, verdipapirhandelloven `2007-06-29-75`,
    mesterbrevloven `1986-06-20-35`, tjenesteloven `2009-06-19-103` (negative control).
  - Then: tinglysingsloven `1935-06-07-2`, utleveringsloven `1975-06-13-39`,
    Statens pensjonskasse `1949-07-28-26`, bioteknologiloven `2003-12-05-100`,
    utlendingsloven `2008-05-15-35`, Oppgaveregisteret `1997-06-06-35`.
  - ~3–5 dates per law, spread across its life, bracketing major amendments.
  - This unblocks the point-in-time metric → autonomous work via the `goal` skill.
  - **Prediction — PARTLY CONFIRMED 2026-08-13.** aksjeloven (OCR base) point-in-time at held-out
    2001/2003 = rate 0.52-0.54 / mean ~0.80, ≈ its convergence 0.556 → the engine reconstructs past
    states as well as the current one (no date-specific failure); point-in-time is now wired into
    `status` (see done.md). STILL TO DO: 1-2 HIST versions for a CLEAN-base law (vphl `2007-06-29-75`
    conv 0.66 / tjenesteloven `2009-06-19-103` conv 0.90) — the decisive test that the deliverable is
    STRONG for clean laws (expect point-in-time ≈ their higher convergence) and OCR bases are the drag.
