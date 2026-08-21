# Done

## 2026-08-21 (cont.) — ITERATION 1: pre-2001 recovery is FLAT on convergence (a real reason, not a bug)

- **Dev-set A/B (with vs without the pre-2001 gazette_recovered stream): 571 → 571, +0 on EVERY
  dev law**, despite recovering 34 ops. This is the honest iteration-1 result under the AIM (general
  fixes, whole dev set). Segmentation cache complete (626/626 dev-year issues, disk-cached).
- **Why flat — a GENERAL reason, and it re-confirms the standing OCR-base finding:**
  1. **Convergence measures CURRENT text, which reflects the LATEST amendment per provision.**
     Pre-2001 amendments are mostly SUPERSEDED: avtaleloven §38's current text needs the 2015 act
     (post-2001), so the recovered 1983 §38 is the wrong version; §37 needs the 1995 act. Recovering
     an OLD amendment doesn't move convergence-to-current. Pre-2001 recovery's real payoff is
     **POINT-IN-TIME** (historical states), NOT convergence — it should be measured there.
  2. **Act-finding recall is only 38/100** — the LLM segmenter produces a matching datokode for just
     38 of the 100 register dev-amending acts (62% missed, mostly 1960s–70s: older OCR / date
     resolution). So even the final-is-pre-2001 amendments (e.g. §37←1995) are often not recovered.
  3. The one provision whose FINAL amendment is pre-2001 AND would help convergence — avtaleloven
     **§36 (1983 general clause)** — is reached by the localizer but its op is dropped by tight-slice
     extraction (recovered only §37/§38). Directed whole-act extraction gets §36, but that was
     reverted as avtaleloven-tuning; the general version is a target-focused extraction prompt.
- **Consequence for the AIM.** Pre-2001 recovery is **not a convergence lever** for the dev set (it is
  a point-in-time lever). The convergence residual for the OCR-base dev laws is **OCR base quality +
  ledd**, exactly as the docs concluded — now re-confirmed empirically (recovering real pre-2001
  amendments moved convergence 0). Valid "very good reason" per the working method: *convergence
  reflects the latest amendment; pre-2001 amendments are superseded or OCR-base-floored.*
- **Next general levers (for CONVERGENCE, in priority):** (a) OCR base quality for the OCR-base laws
  (the actual binding constraint — the enactment base text is noisy); (b) act-finding recall (general
  segmentation/date fix) + target-focused extraction — but these only pay off on the small set of
  pre-2001-FINAL provisions. To measure pre-2001 recovery's REAL value, run the POINT-IN-TIME metric
  (needs held-out Lovdata-Pro versions), not convergence.

## 2026-08-21 (cont.) — segmenter WIRED into build_gazette: pre-2001 corpus unlocked

- **HS approved the regex sweep (KILL brittle parsers; keep verify-gates + canonicalizers + the
  deterministic scorer; XML→lxml). Started with the segmenter (highest-value KILL).** `build_gazette`
  now segments each issue with `source.llm.segment_issue` instead of `gazette.parse_issue`
  (parse_toc/split_bodies) — killing that regex dependency and the `_ANY_ACT_HEAD` body-trim (the
  segmenter already slices bodies) and the `issue_year` heuristic (year comes from the NB catalog
  index, id→year). Removed the `gazette` + `_cite_regex` imports from build_gazette.
- **Validated end-to-end on 1983 (the year gazette.parse_issue gave 0 acts for its TOC-less issues):
  27 issues / 28 acts scanned (was 0), and the fully-LLM path (segment→localize→extract) recovered
  `lov/1983-03-04-4 §37 [repeal]` + `§38 [change]` for avtaleloven** — the first pre-2001 amendments
  ever recovered for it. Fixed an id-mapping bug (Path.stem leaves ".jsonl" on ".jsonl.gz"; index ids
  are the bare hash) that made the year filter match 0.
- **Remaining: §36 (the general clause) still slips the OP EXTRACTOR** (even on gpt-4.1) though the
  segmenter+localizer reach its section — a within-section extraction/slicing detail (the 1983 act names
  avtaleloven in both a flat TOC-list and the real "gjøres følgende endringer: § 36 skal lyde:" block;
  the section slice likely grabs the list mention). Next: full pre-2001 gazette sweep + re-measure
  convergence (gap-fill), then the endringslov/ledd LLM rewrites (each A/B'd).

## 2026-08-21 (cont.) — LLM act-segmenter built + full regex audit

- **`source/llm/segment_issue.py` — LLM act-segmenter (the 80%-bottleneck fix).** Localize-then-verify:
  the model locates each "Lov nr. N" act heading (verbatim anchor + nr + date + title), the deterministic
  layer verifies the anchor is a real source slice, reads the nr, resolves the datokode from the act's OWN
  date (no mis-firing issue-year heuristic), dedups running-header repeats by nr, and slices bodies.
  Chunked with overlap; mini model. Returns the same dict shape as gazette.parse_issue for drop-in use.
  VALIDATED on issue 60d9006a (which gazette.parse_issue gives 0 acts): located 5 acts incl.
  **nr 4 1983-03-04 [amend] "om endringer i avtaleloven" (datokode 1983-03-04-4)** — the act that adds
  §36. Unlocks the ~127k pages behind the 0-act parse failure. NOT yet wired into build_gazette (that
  wiring + removing the gazette regex segmenter is a KILL pending HS sign-off).
- **Full regex audit (HS directive: outlaw regexes; flag warranted ones).** 4 parallel agents, ~90 sites
  across 32 files. Findings in docs/decisions.md (regex-audit section). Buckets: (A) KILL = brittle
  parsers over free OCR/gazette prose — gazette `_CITE`/`_TOC_ENTRY`/`_BODY_HEAD`/`classify`/`issue_year`
  (→ segmenter), endringslov `_SET`/`_SET_INV`/`_NEWCHAP`/`_REPEAL`/`_ANY_SET`, build_enactment
  `_NEXT_LAW`/`_HEAD`/`_GARBLED_SECT`, lti_amendments `_BLOCK_HEADER`/instruction-classifiers, ledd
  instruction-ADDRESSING (`_RANGE`/ordinal/punktum/bokstav/nr) + punktum splitter, pipeline
  `_HEAD_ID`/`_BLOCK`/`_CHAP_SPLIT`, replay `_SUBUNIT`/`_HEADING`, amend `_SECTION` (dead). (B) structured
  NLOD/LTI XML parsed by regex → convert to lxml. (C) WARRANTED KEEP: verify/pre-gates that sit ON TOP of
  the LLM (`_AMENDATORY`, `_AMEND_ACT`, `_CLEAN_PARA`, gazette.check_boundaries, gate G1 AST scans),
  controlled-format canonicalization (whitespace, id/datokode/filename, ledd `(N)`/`a)`/`1.` markers with
  consecutiveness guards), and — critically — the **metrics.py SCORING normalizers**, which are MESSY but
  MUST stay deterministic (LLM-ifying them would break score reproducibility). eval/ files are all
  eval-only (not the reconstruction path). Sequencing: land segmenter, then endringslov/ledd LLM rewrites
  one at a time, each A/B'd against convergence (omnibus lesson: don't big-bang).

## 2026-08-21 (cont.) — pre-2001 ROOT CAUSE: gazette segmenter fails 80% of issues

- **Chasing avtaleloven's missing pre-2001 amendments (§36 etc.) to the bottom: they ARE in the OCR
  we hold, but locked behind gazette ISSUE SEGMENTATION.** `gazette.parse_issue` returns **0 acts for
  833/1033 harvested issues (80%, ~127k OCR pages)** — because `parse_toc` requires an "Innhold" TOC
  header and `split_bodies` keys on `"Lov nr. N\n"`, but most issues have no "Innhold" and headings like
  `"Lov nr. 3."` (period). Proof: the issue holding avtaleloven §36 ("En avtale kan … virke urimelig …
  god forretningsskikk") has 34 "Lov nr." headings + 4 "gjøres følgende endringer" sections yet parses
  to 0 acts (and is mis-tagged year 1969, so `--years 1983` skipped it too). So the pre-2001 recovery
  can only see 20% of the OCR — THE pre-2001 bottleneck, far bigger than avtaleloven.
- **This is a brittle-regex failure, exactly the class HS flagged.** The fix is an LLM-based (localize-
  then-verify) act segmenter that finds "Lov nr. N" act boundaries WITHOUT depending on the Innhold TOC
  or one heading format — unlocking ~127k pages. Highest-value pre-2001 lever by far.
- **Removed the brittle cite pre-filter (HS directive: don't let a regex gate the LLM).** `build_gazette`
  no longer uses a per-target `_cite_regex` to pick candidate acts (it silently killed avtaleloven recall:
  OCR "nr. 4om", date-only and name cites all missed). It now localizes EVERY amending act (broad "I lov"
  gate) and lets the LLM resolve targets, filtering resolved sections to the target set; `--model` allows
  mini for a cheap full sweep. `_cite_regex` (still used by build_omnibus candidate discovery) hardened
  for the OCR "nr. Nom" defect. NB: this is the correct method but currently yields 0 avtaleloven ops —
  blocked DOWNSTREAM by the 80% segmentation failure above, not by the regex.
- **Register-as-oracle decision (HS question):** the amendment register is the right GROUND TRUTH for
  coverage (which acts should amend which law) and for harvest prioritization + cross-checking the LLM —
  but NOT a reconstruction INPUT: it is answer-key-derived (using its amendment graph defeats convergence
  integrity, G1) and only knows surviving provisions (useless for point-in-time's historical states). The
  structure it states is re-derivable from public OCR, which is what keeps the corpus honestly public.

## 2026-08-21 (cont.) — avtaleloven deep-dive: TWO engine bugs fixed; recovery = gap-fill only

- **The register "lift" didn't move the deliverable, so we opened the actual reconstruction.**
  Per-provision diagnosis of avtaleloven's 12 failing provisions (recon vs current): **~9 are
  amendment-related, only 2 OCR** — vindicating the "missing amendments" hypothesis. Breakdown:
  6 need PRE-2001 acts absent from all streams (harvest gap: §36 needs 1983-03-04-4, §37 1983+1995,
  §23 1984, §17 1962/1985, §27 1985); 3 are provisions ADDED by amendments we HAVE but never built
  (§9a, §38a, §38b); 2 OCR (§3, §41); 1 base gap (§4).
- **Engine bug 1 — replay never INSERTED new provisions.** A whole-provision "§ N skal lyde:" whose
  new_text lacks the '§ N.' heading was routed to `ledd.apply` on an empty base → None → dropped, so
  a § ADDED by amendment (avtaleloven §9a) was never created. Fix in `replay._apply_change_type`:
  set the provision body directly, **INSERT-ONLY** (guarded by `_CLEAN_PARA` + `para not in doc`) —
  a bare-body op must never overwrite an existing correct provision (that caused −15 vphl / −10 foreld
  when first tried without the guard). §9a 0.00→0.98.
- **Engine bug 2 — chapter-add blocks never split.** A whole-chapter add ("4de kapitel. … § 38 a. …
  § 38 b. …") was emitted as ONE op (para "§kapittel4"), burying §38a/§38b. `pipeline._split_chapter`
  splits on inline '§ N. <Capitalised title>' (period+title distinguishes a heading from a cross-ref).
- **Recovery is now GAP-FILL ONLY.** Merging the recovery streams as OVERRIDES regressed the dev set
  (−37) because recovered op *content* is noisier (OCR/LLM) and overwrote correct clean-base provisions.
  `load_ops` now applies a recovered op only when the PRIMARY streams provide NO op for that provision
  — recovery adds the §s the primary streams miss (avtaleloven §9a), never overrides. Net effect with
  both engine fixes + gap-fill recovery: **convergence 568→571 (+3), 0.6828→0.6888, guards G1/G2/G3 PASS.**
  Per-law: avtale +1, rettsg +2, vphl +1, aksje −1 (residual). Engine fixes ALONE (recovery off) = 570.
- **avtaleloven now 33→34 shipped.** Its remaining upside is NOT free: (a) §38/§38a want recovery to
  OVERRIDE a weak primary op — blocked by gap-fill until recovery op-quality improves; (b) §36/§37/§23
  need the 5 specific pre-2001 acts HARVESTED (1962/1983/1984/1985/1995 — not in OCR, 0 hits). The
  fixes are GENERAL (any law with amendment-added provisions / chapter adds benefits).

## 2026-08-21 (cont.) — pre-2001 tail triaged + Tier-1 gazette recovery built

- **Pre-2001 tail quantified (register vs streams):** register has 811 pre-2001 amending acts /
  1,716 edges, only **10% captured**; 582 acts absent. NONE of the absent are on disk in data/lti
  (electronic LTI is 2001+) → it's a HARVEST-era gap, but with a large recoverable PARSE sub-layer.
  By decade: **1990s absent 212 / captured 174 (45%)** — well-harvested, gap is parse; 1980s 197/13
  (patchy harvest — index near-empty for 1980, 1984, 1987–89); pre-1980 145/0 (harvest 2–3 issues/yr).
- **Three tiers:** (1) parse the OCR we already hold (1990s + harvested 1980s) — cheapest, no network;
  (2) fill harvest holes 1980–2000 (targeted NB re-harvest of ~5 near-empty years); (3) pre-1980 broad
  NB harvest+OCR (hardest, lowest yield). Proof for Tier-1: the 1994 sea-code act (sjøloven,
  1994-06-24-39) names "Lov 31. mai 1918 nr. 4 om avslutning av avtaler" in a consequential-amendments
  list sitting UNPARSED in our OCR.
- **Tier-1 built — `source/scrape/build_gazette.py`:** the SAME localize-then-verify path fed each
  amending act's OCR body (segmented by gazette.parse_issue) instead of LTI XML; writes a SEPARATE
  `data/gazette_recovered.jsonl.gz` (no collision with a running LTI sweep). `_bound_body` trims the
  ~10% oversized bodies (OCR mis-segmentation bleeds the issue tail) at the next differing "Lov nr. <m>"
  heading, else caps at 60KB — logged, not silently trusted. Wired as a 5th load_ops stream + into
  register_gaps. Validated end-to-end on one 1994 issue: **108 ops, 15 acts → 23 laws**, all verbatim-
  anchored.
- **IMPORTANT metric caveat — the register cannot cleanly score pre-2001 precision.** It records only
  amendments to CURRENTLY-LIVE text, so 1994 amendments to since-repealed/renumbered provisions
  (e.g. 1994-06-24-24 → 1991-07-04-47 §16 renumber) are absent from it and look like FPs though they
  are REAL and exactly what POINT-IN-TIME reconstruction needs. Pre-2001 precision needs a Lovdata-Pro
  HIST spot-check or hand audit, not the register. The ops remain verbatim-faithful (anchor + amendatory
  guard + catalog resolve).
- **Deliberately NOT run yet:** the full gazette sweep (all pre-2001 issues) — it would contend for the
  API rate limit with the still-running 2001+ LTI full sweep. Ready to launch after that completes:
  `python -m source.scrape.build_gazette` (optionally `--years 1990 …` to bound).

## 2026-08-21 (cont.) — omnibus recovery via LLM localize-then-verify (format-agnostic)

- **The fix for the mis-targeted 24% (prev entry), built to NOT be another regex.** Instead of
  broadening `amend._SECTION` per act layout (whack-a-mole), `source/llm/target_localize.py` has the
  model LIST every amended-law mention (verbatim `anchor` + `law_cite` tokens); the verifier then
  (a) locates each anchor as a verbatim source position (whitespace-tolerant + shortened-prefix
  fallback), (b) checks `law_cite ⊂ anchor` (hallucination gate), (c) resolves the cite to a datokode
  (`gazette.datokode`, fails safe), and (d) slices the act between consecutive anchors. Drop-in
  replacement for the `_SECTION` regex; new layouts need zero new code. Determinism moved from PARSING
  to VERIFYING — same anti-fabrication guarantee as amend.py's payload anchors, now on the TARGET too.
- **Recall-first by design:** the model localizes (high recall across layouts), the proven per-section
  op extractor runs UNCHANGED (no truncation, ~96% payloads located), and every unresolvable mention is
  streamed to `data/omnibus_unresolved.jsonl.gz` — recall loss is MEASURED, never silent.
- **Validated on the archetype** — "Lov om retting av feil m.m. i lovverket" (2003-06-20-45, the
  128-op act the external stream mono-collapsed onto straffeloven): localizer found **127 mentions →
  123 resolved sections (96.8%)**, and **avtaleloven §14 siste ledd (repeal) is recovered** — the exact
  op the mono-collapse lost. The 4 unresolved are all date-ONLY cites (old laws named without "nr. N");
  correctly logged, and the next recall lever is a date→datokode catalog fallback.
- **Wiring:** `source/scrape/build_omnibus.py` sweeps PUBLIC act text (candidate acts discovered by an
  act citing a target's date+nr — NOT the register/answer key), writes `data/omnibus_recovered.jsonl.gz`
  (same schema); `pipeline.load_ops` gains it as a 4th merged+deduped stream; `register_gaps` scores it.
  amend.extract_ops gained an additive `sections=` param (use localized sections instead of `_split_sections`).
  All G1-safe (public act + cached model anchors only).
- **Bounded validation sweep (7 register-flagged old codes, 91 public-signal candidate acts) — LIFT,
  register-scored:** avtaleloven **4→11** (recoverable misses **6→0** — everything left is pre-2001
  harvest), panteloven **18→33**, foreldelsesloven **8→18**, skadeserstatningsloven **12→15**,
  kjøpsloven **2→3**. **Precision 100%** (75 distinct (act,law) pairs, 0 not in the register oracle).
- **One precision failure found + fixed:** an applicative cross-reference ("Lov … § 2-1 GJELDER FOR …",
  making another law apply — not a change) was localized as a target. Added a public-source amendatory-verb
  guard (`_AMENDATORY`, keyed on `\blyde\b` etc. — NOT "skal lyde" adjacent, since the provision sits
  between "skal" and "lyde": "skal § 21 nr. 3 tredje punktum lyde:"); dropped sections are logged to
  omnibus_unresolved (measured). First-cut guard over-dropped real amendments (avtaleloven 11→7) — the
  `\blyde\b` fix restored full recall at 100% precision. Lesson: recall-guard regexes need the
  provision-between-verb form.
- **Remaining recall lever (measured, not silent):** date-ONLY citations of old laws ("Lov 17. mars 1916 om
  …" with no "nr. N") don't resolve via gazette.datokode → logged as `cite-unresolved`. A date→datokode
  catalog fallback (public: build from the LTI act corpus' own citations) is the next recall step.
- **Next:** full-corpus sweep (all ~2882 acts, cached/resumable — recovers the ~1968 mis-targeted edges
  corpus-wide, not just the 7 spotlight laws) + the date-only fallback. Then re-gate convergence/point-in-time.

## 2026-08-21 — amendment REGISTER built; reopens the "omnibus exhausted" call

- **New eval artifact.** `source/eval/build_register.py` parses every `changesToParent` provenance
  annotation in the NLOD current dump into `data/amendment_register.jsonl.gz` (one row per
  amending-act × target-law × provision × op) + `data/register_index.json` (act → affected laws).
  **32,759 edges, 3,079 amending acts (1,151 multi-law), 554 laws.** This is Lovdata's own amendment
  graph — the ORACLE view. Eval-only (reads the answer key; gitignored, per lessons #7); content is
  public-domain NLOD so it *can* be published as a deliverable, but deliberately, not via recon path.
- **Validated:** register reproduces avtaleloven's amendment history exactly (17 acts, incl. §36 under
  the 1983 general-clause act 1983-03-04-4) and correctly explodes the omnibus "Lov om retting av feil
  m.m. i lovverket" (2003-06-20-45) into **72 laws / 108 ops** — with avtaleloven §14 among them.
- **`source/eval/register_gaps.py` — corpus-wide capture audit vs the register:** of 7,975 amending-act
  edges, we capture **3,975 (49%)**. Of the misses, **1,947 (24% of all edges) are MIS-TARGETED** — the
  act IS in our streams amending some OTHER law, its section for this law dropped (omnibus mono-collapse),
  **recoverable by re-parse, no new harvest** — and 2,053 (25%) are ABSENT (harvest/OCR gap).
- **This partly REVISES the 2026-08-13 "omnibus multi-target lever is single-digit / deprioritised" call.**
  That measurement counted *misfiled* rows inside the structured LTI stream; it missed the *dropped
  secondary-target* failure mode in the gazette/merged stream, which a by-act provenance-anchored count
  shows is the dominant recoverable gap — 24% of the whole amendment graph, worst for old/small codes that
  are only ever secondary targets (avtaleloven 4/17, kjøpsloven 2/7, gjeldsbrevlova 0/13, forvaltningsloven
  1967-02-10-0 **0/57 captured, 28 recoverable**). 66% of ≥10-op acts in the stream are mono-targeted.
- **Next (not yet done):** wire the existing `source/llm/amend._split_sections` (`I lov <cite>` splitter,
  already used by the LLM path + blanket.py) into the DETERMINISTIC gazette/LTI extractor so each op block
  is re-headed to its own section's law. Targets resolve from the ACT text (public), NOT the register
  (answer key). `register_gaps` top-20 = the payoff ranking. Coordinated w/ the live Lovhistorie session
  (source_ref per register row = anchor for its "show source excerpt" button).

## 2026-08-16 (cont.) — EEA-annex scope-out (triage category B): 2012-12-14-81 0.07 → 0.75

- **`is_convention_annex` now also recognizes the `§a<digit>` article form** (data-name "aN", body "Art N …")
  — EEA-regulation / treaty articles incorporated BY REFERENCE, the same un-reconstructable class as the CISG
  "/" annexes, just a different NLOD id marker. Requested by HS; a structural scope-out, NOT a loosening.
- **Verified safe:** across ALL 755 current laws, EVERY `§a<digit>` is an "Art N" incorporated article — 0 are
  real statutory provisions (a real suffix is `§Na`/`§1a`, never `§a1`). So the id form is an objective,
  hand-pick-free marker, exactly like the "/" namespace.
- **Impact:** the target EEA-incorporation law 2012-12-14-81 goes **0.07 → 0.75** (42 of its 46 provisions are
  §aN annex; the 4 real statutory provisions reconstruct fine — the 0.07 was an artifact of scoring
  incorporated-regulation text). Dev gate UNCHANGED at 0.6852 (dev laws use the "/" CISG form, already scoped;
  no dev §aN). 13 laws corpus-wide carry §aN annexes and benefit; the 62-law breadth sample happens to include
  few, so its aggregate is flat, but the fix is correct corpus-wide. Guards PASS.

## 2026-08-16 (cont.) — outlier TRIAGE: the low tail is 3 identifiable causes, none a tooling failure

Root-caused the breadth low outliers (≥.90-rate < 0.5). Three categories:
- **(A) A regex PARA-PARSING bug.** `lti_amendments._PARA` had `\d+…\s*[a-z]?` — the `\s*` before the
  suffix grabs the "s" from "skal", so "§ 1 skal lyde" parsed as **§1s**; the whole-provision op never keyed
  to §1 (Statens pensjonsfond §1 stayed EMPTY → rate 0.0). The fix (`[a-z](?![a-z])` — a letter not followed
  by a letter; keeps real spaced suffixes "§ 2-11 a") is CORRECT and lifts the outlier (0.0→0.25) + breadth
  (+0.006) — **but it REGRESSED the dev set −3** (568→565): enabling the previously-suppressed ops surfaces a
  not-in-force/ordering interaction (the bug was accidentally masking 3 bad ops). Per zero-regression, REVERTED;
  the para bug + its in-force coupling are logged for when the in-force gate lands. Real bug, not shippable
  alone.
- **(B) EEA-annex incorporation.** 2012-12-14-81 (base 4, current 46): the §aN provisions are "Art 1", "Art 2"
  … — EEA-regulation articles INCORPORATED BY REFERENCE (same class as kjøpsloven's CISG), un-reconstructable
  from Lovtidend, but `is_convention_annex` (keys on the "/" marker) misses the §aN form → they drag the score.
  A measurement-scoping fix (extend the annex predicate to the §aN incorporated-regulation form) — clean-ish,
  but needs care that §aN is never a real provision, so deferred to a scoping pass.
- **(C) Heavy rewrite / uncaptured whole-provision amendments.** vaktvirksomhet (2001-01-05-1), markedsførings-
  loven (2009-01-09-2): base-vs-current ≈0 despite ops — the law was substantially reworded/expanded and the
  whole-provision replacement amendments aren't captured or don't apply. Amendment COVERAGE (data), the known
  limit.
- **Conclusion: the outliers are NOT tooling failures** — they're one regex bug (fixable, gated on in-force),
  annex-incorporation (measurement), and amendment coverage (data). The breadth median (0.89) is robust; the
  low tail is a per-law triage list with identified causes, not a systematic gap.

## 2026-08-16 (cont.) — BREADTH: pipeline generalizes to the clean-base corpus (median 0.89, far above dev 0.685)

- **`source/eval/breadth.py`** — reconstruction quality across the clean-base corpus, not the 9-law dev set.
  For non-dev post-2001 laws present in BOTH the LTI dump and the current dump (366 candidates), it builds the
  LTI enactment base IN MEMORY (no enactment JSONs written), replays amendments, and scores vs current.
- **Result (n=62): mean ≥0.90 rate 0.833, MEDIAN 0.887; mean ≥0.98 rate 0.748. 47/62 (76%) reconstruct ≥80%
  of provisions at ≥0.90; only 3 below 0.5.** Quartiles Q1=0.80 / Q2=0.89 / Q3=0.96.
- **This reframes the quality story.** The dev-set convergence 0.685 is a PESSIMISTIC, OCR-heavy subset (the 9
  dev laws were chosen to stress the hardest pre-2001/booklet cases). On the clean-base MAJORITY of the corpus
  — the ~366 post-2001 statutes the tools scale to — reconstruction is strong (median 0.89), no OCR floor.
  The tools built this session (base segmenter, amendment extractor, align, blanket parser) are validated at
  breadth, which the 9-law gate never measured. The genuine deliverable is: clean-base laws reconstruct at
  ~0.89 median ≥0.90-rate corpus-wide, plus the point-in-time μ 0.879; the OCR pre-2001 tail is the minority
  drag. Low outliers (2005-12-21-123 rate 0.0, 2001-01-05-1 0.18) are individual base/coverage issues (LTI act
  not a clean enactment, or missing amendments), not systematic — a per-law triage list, not a tooling gap.

## 2026-08-16 (cont.) — blanket-reform parser BUILT (correct); confirms the dev-set convergence CEILING

- **`source/parse/blanket.py`** — captures terminology reforms "ordet/uttrykket «A» endres til «B»" /
  "endres «A» til «B»" / "«A» erstattes med «B»", attributed to the target-law block (`I lov <cite>` split),
  applied in `pipeline.reconstruct` as a deterministic `str.replace` over provisions containing term A. Uses a
  RELIABLE regex (guillemets are unambiguous delimiters — the right tool per decisions.md, not a fragile
  judgment) and DROPS the fragile "§§ 10 første ledd, …" scope list (term A is specific, so applying A→B
  wherever A appears in the law reproduces the listed scope robustly). Skips `«§ 54» til «§ 70»` cross-ref
  renumbers (structural, not terminology). Source-specified replace → no fabrication.
- **Correct + safe, but +0 on the dev set: only 1 dev-law reform exists** (rettsgebyr
  Rikstrygdeverket→Arbeids- og velferdsdirektoratet — applied cleanly, 0 old-term left, no regression). The
  reforms that hit MANY laws (Aetat, vegkontoret, skifteretten→tingretten) target NON-dev laws, so the parser
  is valuable at CORPUS scale but the 9-law dev set doesn't measure it. The dev-set modernization gaps
  (avtaleloven §38 "nogen gaat ind paa"→"noen på grunn av") are PRE-2001 spelling drift + uncaptured
  rewordings, NOT post-2001 «X»→«Y» term reforms, so the LTI parser can't reach them.
- **CONCLUSION — the dev-set convergence (0.6852) is at its practical CEILING.** Three levers built this
  session (LLM amendment parsing, align ledd targeting, blanket-reform parser) are each correct + safe + zero-
  regression, and each is +0 on the dev set — because the dev-set residual is the fundamental limits already
  named in decisions.md: OCR fidelity + pre-2001 coverage. Further dev-set convergence needs OCR correction
  (fabrication-risky, declined) or more pre-2001 harvest, NOT more parsers. The value of these tools is (a)
  CORPUS BREADTH (they help the ~750 non-dev statutes) and (b) the POINT-IN-TIME deliverable (μ 0.879,
  clean-base ~0.96+ — the project's actual strength). The productive next work is breadth or the deliverable,
  not the 9-law convergence gate.

## 2026-08-16 (cont.) — ledd content-first targeting; and the "35% ledd bucket" is OVER-ATTRIBUTED

- **`ledd.apply` REPLACE now addresses by CONTENT first (align), ordinal as fallback** — restructured so an
  out-of-ordinal-range op (e.g. "§9-15 syvende ledd" when the provision now has 3 ledds, an earlier repeal
  having shortened it) is rescued by content match instead of flagged. Correct + version-robust; **no-regression
  check improved 0 / REGRESSED 0** (the dev set doesn't exercise version-shift enough to cross τ, but it's the
  right logic and helps the broader corpus / point-in-time).
- **The decisive finding: the `loss_breakdown` `engine-gap:ledd` bucket (97, 37%) is OVER-ATTRIBUTED.** Making
  the LLM sub-provision ops correct + applying them (this + prior entry) did NOT shrink it. Traced avtaleloven
  §38 (0.34, "engine-gap:ledd"): its recon is the 1918 ENACTMENT spelling ("Har nogen gaat ind paa"), current
  is MODERN ("Har noen på grunn av"), and §38 has **no op at all** — the nearby §38*b* ledd ops were
  mis-associated. So its gap is **OCR-era spelling drift + an uncaptured blanket modernization reform**, not a
  ledd-application failure. Many of the 97 are like this (OCR / blanket-reform / base), which correct
  sub-provision ops cannot fix.
- **Honest conclusion (dev set): the amendment/ledd thread has reached its productive end here.** The LLM
  amendment parsing (correct attribution — fixed the §21-15-class corruption, applied-wrong 31→24) and align
  ledd targeting are correct + safe, but the DEV-SET residual is dominated by the fundamental limits already
  named in decisions.md — **OCR fidelity + uncaptured (blanket) reforms** — not ledd application. Further
  dev-set convergence needs either OCR correction (fabrication-risky, declined) or a blanket-reform capture
  parser ("uttrykket «A» endres til «B» i følgende bestemmelser: …"), not more ledd work. The ledd machinery
  remains valuable for the broader corpus + point-in-time; TODO: refine `loss_breakdown` so `engine-gap:ledd`
  doesn't absorb OCR/reform/base gaps (mis-attribution inflates the apparent lever).

## 2026-08-16 — LLM amendment ops WIRED (correct attribution + payloads); gain gated on the ledd ENGINE

- **Refactored `amend.py` to PER-SECTION extraction** — split the act on `I lov <cite>` (not the fragile
  `_BLOCK_HEADER`, which required "gjøres følgende endringer" and over-ran), one LLM call per target-law
  section (`AmendmentOps` schema), with `only_targets` to skip laws we don't score. This fixed the real
  `whole_only=False` blocker, which was NOT payload over-capture alone but **block MIS-ATTRIBUTION**:
  act 2021-04-23-22's `§21-15 annet ledd annet punktum` belongs to **finansforetaksloven** (which also has a
  §21-15); the regex over-ran the block and filed it onto **vphl**, corrupting vphl §21-15. Per-section
  attribution fixes it (§21-15 → finansforetaksloven, 137-char payload not the regex's 1168), verified.
- **Built `data/llm_amendments.jsonl.gz` (456 sub-provision ops over the 88 dev-law delta-acts)** and wired it
  into `pipeline.load_ops` as a third stream (gitignored, dated via inforce, per-section anchor payloads
  source-verified). Robustness: per-section `try/except` (one section can't kill the build), 90s client
  timeout, `only_targets` dev filter.
- **Result: clean merge, NO regression** (guards PASS, §21-15 correctly NOT on vphl), but convergence barely
  moves — **OCR-calib UNCHANGED 0.6852, strict τ +2 (493→495)**. Diagnosis: the LLM ops reach replay correctly
  but the **ledd ENGINE flags ~90 of vphl's sub-provision ops** (can't resolve the address on the base). So
  the ledd bucket is limited by APPLICATION, not parsing — as predicted. Correct parsing was necessary but not
  sufficient.
- **NEXT (the actual 35% unlock): ledd APPLICATION.** LLM ledd-segmentation (split a provision into ledds —
  boundaries-only, so OCR bases become addressable) + `align.target_ledd` content-targeting inside the ledd
  engine, so the ~90 flagged ops apply. The parsing foundation (this entry) + `align` idempotency/targeting
  (shipped) + this stream are the prerequisites. Also cleaned up the dead single-call path (amend_ops prompt +
  AmendmentExtraction/Block schemas).

## 2026-08-14 (cont.) — LLM amendment op-extractor BUILT (source/llm/amend.py); completeness needs iteration

- **Built `source/llm/amend.py` + `AmendmentExtraction` schema + `prompts/amend_ops_system.txt`** (llmkit,
  boundaries-only): parses an amending act into ops keyed to the amendment-stream schema, with payloads
  located by verbatim head/tail ANCHORS and sliced from the source (so a sub-provision payload has a CORRECT
  boundary, unlike the regex over-capture). Anchor not found → op FLAGGED + dropped (fabrication-safe).
- **Anchor mechanism works:** on act `2021-04-23-22`, **11/11 payloads source-verified, 0 flagged**, reasonable
  payload lengths.
- **But extraction COMPLETENESS on hard omnibus acts needs prompt iteration.** On that act's vphl block the LLM
  got §17-1 but MISSED the §21-15 punktum op — so I could not directly A/B the 1168-char over-capture. NB the
  REGEX also fails on this block (4 vphl ops all `paragraph=None`, still over-capturing 1168/1488) — the act is
  genuinely hard for both; it is not a clean validation case. The anchor PAYLOAD-boundary fix is sound; the gap
  is op RECALL on dense multi-block acts (prompt/chunking iteration — mirror the base segmenter's per-block
  approach; consider one call per target-law block).
- **Status:** the module is the foundation for the `whole_only=False` unlock but is NOT yet wired in — that
  needs (a) extraction-completeness iteration to match/beat regex op-recall, then (b) merge LLM sub-provision
  ops over the regex ones in the stream, then (c) flip `whole_only=False` behind the per-provision no-regression
  gate (idempotency + content-targeting from the prior entry are already in place). Prototype scripts +
  collected amendment bodies in scratch.

## 2026-08-14 (cont.) — ledd idempotency + version-robust targeting: 0.673 → 0.685 (+10, zero regression)

- **Wired `align` into `ledd.apply` (replace + insert branches):** (a) IDEMPOTENCY — skip when a ledd
  already equals the new text (`align.target_ledd(...).already_applied`), the double-application fix; (b)
  VERSION-ROBUST TARGETING — address the ledd by CONTENT (argmax-similarity with a margin) not the
  version-dependent ordinal, falling back to the ordinal when the content match is ambiguous.
- **Clean +10 on the SHIPPED path:** convergence **0.6731 → 0.6852** (558 → 568), guards PASS, **per-provision
  no-regression check: improved 10, REGRESSED 0** (verified my ledd.py vs committed, both whole_only=True). The
  gain is on the EXTERNAL amendment stream's ledd ops (LTI whole_only=True emits only whole-provision + sub-unit
  repeals, so the win comes from the external stream's sub-provision replaces now applying idempotently +
  content-targeted).
- **`whole_only=False` (full sub-provision replace/add) STILL deferred — but the blocker is now precisely
  diagnosed and it is NOT idempotency.** Enabling it nets +9 gross but with 3 per-provision regressions
  (§21-15 1.0→0.729, §5-27 0.981→0.659, §67 0.943→0.81). Traced §21-15: its op `§21-15 annet ledd annet
  punktum skal lyde:` carries a **1168-char payload** (a punktum is one sentence) — the regex LTI parser
  **OVER-CAPTURED the payload boundary** (the `applied-wrong`/block-truncation bucket), so a punktum-replace
  blows the provision to 2752 chars. This is exactly what the **LLM amendment anchor extractor fixes (96%
  payloads source-verified)** and the regex can't → `whole_only=False` is BLOCKED ON the LLM amendment payload
  extractor, not the ledd engine. Idempotency + targeting (this entry) are the prerequisite; the LLM payloads
  are the unlock. `lti_amendments.build(whole_only=...)` is now threaded (default True) for that future flip.

## 2026-08-14 (cont.) — ledd reconstruction design: LLM boundaries + similarity alignment (the 35% bucket)

- **`loss_breakdown` reframed phase-2:** the biggest miss bucket is `engine-gap:ledd` (35%, 95 provisions)
  — sub-provision ops. Parsing is easy; safe APPLICATION is the hard part. Also quantified the fundamental
  ceilings (answered "why not 100%"): OCR character noise 11% (irreducible — we slice source, never
  LLM-correct chars → OCR bases cap ~0.90–0.94), amendment coverage 24% (data/harvest, not algorithm), ledd
  application 35%, renumber/move 6%. Clean-base laws have no OCR floor (vphl enactment 0.997).
- **Design + prototype: LLM + similarity solves ledd application (Henrik's insight), fabrication-safe.**
  Three sub-problems, all solved (see docs/thinking.md): (1) ledd segmentation → the boundaries-only LLM one
  level down; (2) WHICH ledd → target by TEXT SIMILARITY not the version-dependent ordinal; (3) idempotency
  → skip if the target already equals the new text.
- **Prototype on vphl §3-1 (6 ledds) — all three confirmed:**
  - targeting: similarity discriminates cleanly (0.89 for the amended ledd vs 0.1–0.37 for the rest), agrees
    with the ordinal on the un-shifted provision;
  - **version-shift (the killer case): after a simulated earlier insert, the ORDINAL picks the WRONG ledd
    (0.37) while SIMILARITY picks the RIGHT one (0.89)** — content-match is version-robust, ordinals aren't;
  - **idempotency: after applying, sim(target, new_text)=1.000 → re-application SKIPS** — directly solves the
    double-application bug that blocked the deferred sub-provision +3.
- **Application is deterministic + verified:** REPLACE by argmax-similarity (skip if ≈1); INSERT by ordinal +
  end-state alignment check; REPEAL by match + verify-absence; then align reconstructed ledds to the endpoint
  1-1 by similarity and FLAG on mismatch. Content is always a source slice; no ledd text is generated.
  NEXT: build `source/parse/align.py` (similarity matcher) + the ledd boundaries-only extractor, wire into
  replay behind the gate.

## 2026-08-14 (cont.) — base-migration crank: LLM base helps ONLY heading-detection-failure laws (scoped)

- **Cranked the next OCR laws behind the gate; the disciplined outcome is a scope finding, not a blanket
  migration.** oreigningslova (nynorsk): LLM base built clean (36 provisions, 0 dropped, 100% substring) but
  convergence **18 → 18** (no change) — its `§` headings parse fine with regex; the 15 misses are
  content/amendments, not segmentation. REVERTED (per decisions.md: migrate only on a confirmed win).
- **Diagnosed the other candidates — same story:** mesterbrev regex base is 10/10 correct ids (its 4/11 is
  the later-added §1a + amendments, not segmentation); rettsgebyr is a 1992 SNAPSHOT base (base_as_of), so its
  4/34 is snapshot+amendment confounding, not a clean segmentation gap.
- **Scope conclusion (recorded in `build_enactment.LLM_BASE_LAWS` comment):** the LLM base wins specifically
  on heading-DETECTION failures — old period-less layouts (avtaleloven ✓, 30→33) and garbled-`§N-M` booklets
  (aksjeloven-2001 booklet ✓, 192 vs 153). The clean-heading gazette dev laws (foreldelse/oreigning/mesterbrev)
  don't benefit. So on the DEV SET, avtaleloven is the base-segmentation win; the broader payoff is the full
  pre-2001 corpus at scale (many old-layout/booklet statutes) + the booklet-GT path, not the remaining 9-law
  dev set. `LLM_BASE_LAWS` stays {avtaleloven}; the gate-gated crank is the mechanism to add more when a real
  win appears (e.g. if booklet bases are adopted).

## 2026-08-14 (cont.) — LLM base segmenter PRODUCTIONISED + wired into the gate (0.669 → 0.673)

- **Built `source/llm/` (llmkit convention):** `schemas.py` (`BaseSegmentation` — boundaries-only,
  ExtractionSchema), `prompts/segment_base_system.txt` (law-agnostic heading prompt), `segment.py`
  (`segment_base()` — llmkit-cached + Pydantic-validated + structured-outputs extraction, gpt-4.1, with
  deterministic invariant-repair (monotonic/dedup), a **build-time substring assertion** that RAISES if any
  provision isn't a verbatim source slice, and a heading-matches-id cross-check). Cache at
  `data/llm_cache/base_segment/` (gitignored). G1-safe: sees only public-domain OCR.
- **Wired opt-in into `build_enactment`:** `LLM_BASE_LAWS = {avtaleloven}` (extend post-gate); `build(dk)`
  routes those laws through `_segment_law` → the LLM base, tagging `source.llm=True`. Clean LTI bases keep the
  deterministic path.
- **Gate confirms it in production:** avtaleloven **30 → 33/45 @≥0.90**, overall convergence **0.6695 →
  0.6731** (555 → 558 statutory provisions), **all guards PASS** (G1/G2/G3 — the LLM base clears the
  anti-gaming base-integrity check), zero regression elsewhere. avtaleloven base is 40/40 substring-verified
  (100% source-faithful), 0 dropped, 0 id-mismatch. Point-in-time μ unchanged (no held-out GT for avtaleloven).
- **This is the productionisation milestone:** the validated LLM base is now a real, cached, audited,
  fabrication-guarded build input in the pipeline. NEXT: extend `LLM_BASE_LAWS` to the other weak OCR laws
  (oreigning/mesterbrev/kjøp/rettsgebyr) one at a time behind the gate; add the anchor mode for line-break-poor
  sources; then phase-2 amendment-side swap. Migrate the cache to llmkit's schema-aware key when convenient.

## 2026-08-14 (cont.) — END-TO-END base swap validated: LLM base beats regex base in the real pipeline (GO)

- **Assembled the LLM base into the ACTUAL reconstruction** (same amendment stream, same replay) and scored
  convergence-to-current — the go/no-go for defaulting the LLM path on OCR-base laws. avtaleloven (1918, the
  documented hard case: old layout, period-less `§ N (tittel)` headings, 45 statutory provisions):
  - LLM base 40 provisions, **substring 40/40 (100% source-faithful)**, vs regex base 39.
  - base-only vs current: **LLM 30/45 μ0.766 vs regex 27/45 μ0.721**.
  - base + amendments (full convergence): **LLM 33/45 μ0.809 vs regex 30/45 μ0.764** — **+3 provisions,
    +0.045 μ, end-to-end, in the real pipeline, only the base swapped.**
- **Two OCR laws now confirm the base swap wins:** aksjeloven-2001 booklet (LLM base 192 vs regex 153 @≥0.90
  vs the 2001 oracle) + avtaleloven (33 vs 30 @≥0.90 convergence). **VERDICT: GO** to default the LLM-segmented
  base for OCR-base laws (opt-in per law, clean LTI bases keep the deterministic path). The amendment-side LLM
  swap (pre-2001 gazette endringslov) is phase 2 — bigger (identify + LLM-parse every amending act across the
  harvest), and validated in isolation already (27/27 laws, ops exact, payloads source-verified via line-labels
  or anchors).
- **Production path:** `source/parse/llm_segment.py` via llmkit (cached, Pydantic-validated with the
  monotonic/coverage/heading-matches-number invariants in the validator; audit trail), wired opt-in into
  `enactment_base`/`build_enactment` for OCR-base laws. G1-safe: the model sees only public-domain OCR. Then
  re-run the gate — expect the OCR pre-2001 tail (the biggest deterministic drag) to lift, and eventually
  retire `_HEAD`/`_repair_headings`/`_GARBLED_SECT` for those laws.

## 2026-08-14 (cont.) — amendment payloads fixed (instruction-line slice) + similarity-matching for renumbers

- **Amendment payload extraction (Calibration 4 gap) FIXED.** Free-form payload line-RANGES were 0/80
  substring-verified (LLM-arithmetic weakness). Switched to the base's mechanism: LLM returns only the
  INSTRUCTION line per op; payload sliced deterministically (instruction_i → next instruction). One catch:
  the LTI XML flattened to plain text via `_xml_text` has almost NO newlines (tags → spaces), so line-
  numbering was meaningless; re-extracted with a newline-preserving strip (block tags → `\n`, 547 real
  lines). Result: **payloads 64/80 = 80% substring-verified** (was 0); remaining 20% are boundary edge-cases
  (off-by-one / multi-line joins), flaggable, not fabrication. Amendment extractor now validated end-to-end:
  structure (27 laws), ops (exact), payloads (source-verified). NB: LTI is the wrong long-term testbed (already
  clean/structured — our parser handles it); the LLM's value is on pre-2001 GAZETTE amendments (OCR, real lines).
- **ANCHOR fallback for text WITHOUT line breaks (Henrik's idea) — validated.** When the source has no
  reliable line structure (flattened XML; the 0-newline LTI plain text where line-numbering scored 0/80), the
  LLM returns per op the FIRST and LAST ~6 tokens of the payload VERBATIM; deterministic code `find()`s the
  head then the tail (from a monotonic cursor → repeated anchors resolve to the next occurrence, enforcing
  order) and slices `source[head:tail]`. On the 0-newline text: **76/79 payloads (96%) located and
  source-sliced, 3 flagged not-found** (anchor didn't match exactly → flag, no fabrication). aksjeloven
  payloads §4-4 532 / §4-11 1480 chars ≈ our parser's 540 / 1495. The head/tail are LOCATING QUOTES, not
  content — the corpus text is the source slice between them, and a paraphrased anchor fails `find()` and
  flags. So: line numbers when the text is line-structured (OCR gazettes), anchors otherwise — both keep
  content as verbatim source slices with the substring guarantee, both self-verify.
- **Similarity-based identity matching over time (Henrik's idea) — PROTOTYPED, deterministic, fabrication-safe.**
  Track a provision/ledd by TEXT not id, so renumbers (`nåværende §X blir §Y`) and restructures are recovered
  from content. Pure alignment via `metrics.similarity` — links existing units, never generates, so
  fabrication-free by construction. On vphl @2021 (the MiFID-restructure drag): recovered **2 real renumbers**
  (GT §20-1↔recon §16-1 sim 0.92; §20-3↔§16-3 sim 0.96) that id-matching missed, and correctly **flagged 52 as
  genuinely missing** (best match <0.90 → NOT force-matched — the safety property). Diagnostic bonus: it shows
  vphl-2018's drag is mostly MISSING CONTENT (52), not renumbering (2) — so the amendment extractor is the
  bigger vphl-2018 lever and similarity-matching is the complementary tool for the ~35-provision renumber tail
  + ledd alignment + as a text-based validation matcher (catch LLM-mis-numbered-but-text-right cases).

## 2026-08-14 (cont.) — LLM boundaries-only segmentation: CALIBRATED (concept validated, safety proven)

- **Direction written up in `docs/thinking.md`** and prototyped (scratchpad, not committed): an LLM reads
  line-numbered OCR and returns ONLY `{paragraf_id, heading_line}` per provision — never text; deterministic
  code slices the source. Every provision string is a verbatim source slice → content fabrication is
  structurally impossible (the substring guarantee); fabrication reduces to bounded, self-detecting
  localization error.
- **Calibration 1 — foreldelsesloven (easy, `§ N.` period-headings):** LLM found 32 provisions, monotonic,
  **32/32 substring-verified**, and MATCHED the regex parse (sim 0.347 vs 0.342). Validates safety + no-harm;
  no upside because the regex already segments period-headings fine (the 46 missing ids are the out-of-scope
  limitation-convention annex, `§fik/aN`, which neither method can nor should recover).
- **Calibration 2 — aksjeloven-2001 booklet (the documented 71-of-279 heading failure), truth = 2001 oracle,
  265 statutory provisions:**
  - strict `_HEAD` regex: **69** found, 17 @≥0.90, median 0.000 (the catastrophic segmentation failure).
  - repaired regex (current best, hand-tuned `_repair_headings`/`_GARBLED_SECT`): 253 found, 153 @≥0.90,
    median 0.921, substring 190/253 (75%).
  - **LLM segmentation (gpt-4o-mini, ONE prompt, no repair stack): 253 found, 151 @≥0.90, median 0.915,
    substring 251/251 (100%).**
  - Takeaways: (a) the LLM reproduces the hand-tuned repaired-regex result generically, from one prompt,
    turning 69→253 with no bespoke code; (b) it is MORE source-faithful (100% substring vs the regex's 75% —
    the regex's OCR post-correction alters text); (c) it emitted one non-monotonic boundary, which the
    deterministic monotonic invariant CAUGHT (flag-don't-fabricate working) — the invariant guards are
    load-bearing, as `thinking.md` predicted.
- **Calibration 3 — base segmenter v2 (gpt-4.1 + invariant-repair) BEATS the regex.** Same aksjeloven-2001
  booklet: gpt-4.1 found 264 provisions, **0 dropped by the monotonic/dedup guard** (clean), **264/265
  truth-ids, 192 @≥0.90, median 0.938, substring 264/264 (100%)**. That is **+39 well-reconstructed
  provisions over the hand-tuned repaired regex (153→192)** and +11 ids, 100% source-faithful, one prompt,
  no per-law code. The stronger model + guard closed the gap and passed it — the LLM base segmenter is now
  strictly better than the regex stack on the hardest documented case.
- **Calibration 4 — amendment op-extractor (gpt-4.1), omnibus act lov 2019-03-15-6.** Same boundaries-only
  discipline extended to amendments: LLM emits per-op `{target_law, target_paragraf, op_type, payload span}`,
  deterministic code slices payloads. Two-level schema (block→law→ops). Results:
  - **Target-law attribution: 27/27 resolved — the LLM found ALL 27 amended laws; our `lti_amendments`
    parser catches only 6** (misses 21, incl. dev-law foreldelsesloven). Solves the documented "omnibus
    multi-target" lever outright.
  - **Op identification exact** on aksjeloven: LLM `[§4-4, §4-11]` = ours.
  - **Gap: payload extraction 0/80 substring-verified** — free-form payload line-RANGES are unreliable (the
    same LLM-arithmetic weakness as char offsets, now on end-lines). FIX = reuse the base mechanism: LLM
    returns the INSTRUCTION line only; slice payload deterministically to the next instruction (or verbatim
    anchors). Boundaries, not arithmetic. One more iteration.
- **Honest read:** base segmentation is now a clear WIN over the regex (Calibration 3), and amendment
  STRUCTURE/attribution is a clear win too (Calibration 4: 27 vs 6 laws, exact op match). The remaining piece
  is amendment PAYLOAD slicing via the instruction-line method (safety-critical; the substring guarantee must
  hold there too). NEXT: (a) the payload-line fix; (b) the end-to-end test — LLM base + LLM amendments vs the
  held-out point-in-time on a pre-2001 OCR law, zero per-version regression = go/no-go to default the LLM path
  for OCR-base laws. Production impl uses llmkit (cached, Pydantic-validated, audited); invariants in the
  validator; G1-safe (model sees only public-domain source).

## 2026-08-14 (cont.) — GT footnote-table drop: deliverable rate 0.564 → 0.782 (μ 0.857 → 0.879)

- **`lovdata_html.py` now drops the Lovdata FOOTNOTE apparatus from the ground-truth parse.** The
  export appends editorial cross-references ("Se § X", "Jf. lov Y") as a two-column table
  `[footnote-index, note-text]` at the end of each provision; the old parser tag-stripped these INTO
  the scored GT text, but neither the current-text reader (parse_lovdata_xml) nor the reconstruction
  carries them, so clean-law provisions read ~10-20% longer on the GT side and were scored as
  near-misses. Removing them is the symmetric, correct thing — the same class as the strip_annotation
  provenance strip. **Maintainer sign-off 2026-08-14.**
- **SEMANTIC discriminator, not a font-size heuristic:** `_is_footnote_table` = every `<tr>` has
  exactly two `<td>` and the first is a BARE integer (the note index). A first cut on "table contains
  9pt" over-removed vphl's STATUTORY tables (§9-16a/§10-15a) — the semantic test preserves them (identical
  aggregate, no statutory-table loss).
- **Result (deliverable / point-in-time): μ 0.857 → 0.879, rate 0.564 → 0.782.** Convergence UNCHANGED
  at 0.6695 (the gate doesn't use lovdata_html), guards PASS. Clean laws now strong across dates:
  vphl 2009 **0.990**/0.913, 2014 **0.977**/0.863, enactment **0.997**; tjenesteloven **0.964**/0.966 &
  **0.963**/0.931. OCR aksjeloven 2001/2003 also up (rate 0.52→0.71 — footnotes hit OCR laws too).
- **Two small wobbles, traced + honest:** vphl 2021 (rate 0.777→0.713) and aksjeloven 2024 (−0.01). NOT
  over-removal (semantic test only touches footnote tables) — a SEPARATE recon-side entanglement: on some
  vphl provisions the RECONSTRUCTION itself carries footnote-ish text (from LTI amendment bodies), so
  removing the GT footnotes exposes that recon junk. Follow-up (strip footnote-ish text on the recon side
  too), logged in todo — not a blocker; the net is strongly positive.
- **Deliverable story now:** clean-base point-in-time reconstructs past states at ~0.96-0.99 (enactment
  near-perfect); the two named drags are the OCR pre-2001 tail and the renumber/move structural tail
  (vphl 2018 MiFID still 0.536). The recon-side footnote entanglement is the next fidelity lever.

## 2026-08-14 (cont.) — strip_annotation COMPLETENESS fix (nynorsk + in-force footnotes): 0.662 → 0.670

- **Traced tjenesteloven's high-mean/low-rate point-in-time** (mean 0.91, rate 0.24) to its cause —
  and it was NOT a base-extraction bug (my first guess) NOR amendments (every miss ops=0). It split
  three ways: (i) §28 scored 0.72 on an unstripped **in-force footnote** the metric missed; (ii) §29
  is Lovdata's **editorial redaction** of the "Endringer i andre lover" list to "– – –" (our base
  faithfully carries the enacted enumeration — flag, don't chase); (iii) the ~17 "near" misses are
  NOT reconstruction errors — recon matches CURRENT text at convergence 0.955; the Lovdata GT
  provisions are ~10-20% longer, i.e. a **lovdata_html.py oracle-parse length inflation** (depresses
  clean-law point-in-time; separate measurement-side item, see todo).
- **Root cause of (i) = `strip_annotation` was INCOMPLETE, not a base bug.** It was bokmål-only, so
  nynorsk provenance ("Endra/Oppheva ved lov …") leaked, and it stripped NO in-force-footnote form, so
  bare "(ikr. … iflg. res. …)" notes and the "<marker> Fra <date> iflg. res. … nr. <n>." footnote
  (§28) survived into the scored text. Completing it (nynorsk verbs + in-place removal of in-force
  notes) is a CORRECTNESS fix of the same class as the signed-off `autojunk` fix — it removes
  non-statutory provenance the strip already targeted, never statutory text. **Maintainer sign-off
  2026-08-14** (recorded in the docstring).
- **Two subtleties caught by a per-provision no-regression guard** (mandatory for a metric change):
  (a) the verb match must stay CASE-SENSITIVE — lowercase "… som endret ved forordning (EU) …" is
  STATUTORY prose, not provenance (an early re.I version cut vphl §3-5 0.97→0.38); (b) in-force notes
  appear INLINE mid-provision followed by more law text (aksjeloven §10-23 "… (ikr. …) I. Lån med rett
  …"), so they must be REMOVED IN PLACE, not truncated-at-first-occurrence; and (c) the footnote marker
  differs by source — current NLOD renders "1 1 Fra", Lovdata GT renders "0 Fra" — so the marker is
  `(?:\d+\s+)+`, not a fixed pair (this is why the first pass moved convergence but not point-in-time).
  Final guard: **19 provisions improve, 0 regress** across all 1008.
- **Result: convergence 0.6622 → 0.6695 (+6, 549→555), guards PASS, zero τ-regression. Point-in-time
  μ 0.855 → 0.857; tjenesteloven 0.911/0.913 → 0.921/0.923** (§28 → 1.0 on the held-out set). §29 stays
  flagged (editorial "– – –"); the lovdata_html length-inflation is the next measurement-side lever.

## 2026-08-14 (cont.) — clean-base point-in-time CURVE (7 more GT versions); 2018 vphl dip = MiFID-II renumber act

- **Henrik downloaded 6 more Lovdata-Pro HIST versions** — 4 more vphl (`2007-06-29-75`: enactment
  2007-06-29, 2009-12-21, 2018-07-20, 2021-10-04) + 2 tjenesteloven (`2009-06-19-103`: 2009-12-28,
  2020-07-01). Filed to `data/ground_truth/<dk>/`, registered in `index.csv`, scored (held-out: filed +
  scored, not inspected). Aggregate point-in-time now **n=10, μ=0.855, rate 0.555**.
- **The clean-base curve (vphl, τ=0.98):** enactment **0.997** (our enactment base ≈ Lovdata's text —
  validates the base build) · 2009-12-21 **0.967** · 2014-01-01 **0.968** · 2018-07-20 **0.529** ·
  2021-10-04 **0.846**. **tjenesteloven** (clean, 29 prov): 2009 **0.911**, 2020 **0.913** (mean ~0.91
  confirms clean laws ≈0.90+; low rate is n=29 granularity at τ=0.98). So OUTSIDE the 2018 dip, clean-base
  point-in-time is 0.85–0.97 — strong, and far above OCR-base aksjeloven (~0.80).
- **The 2018-07-20 dip to 0.529 is DIAGNOSED (from our own op stream, not the GT):** a single 186-op act,
  **`lov 2018-06-15-35`** (MiFID II/MiFIR implementation), rewrites+renumbers vphl wholesale. At 2018-07-20
  the reconstruction carries 55 flags (10 renumber + 7 unknown + move ops we FLAG-don't-fabricate), so the
  mid-restructuring state diverges; by 2021 later whole-provision replacements (`lov 2019-06-21-41`, 73 ops)
  overwrite those §§ with full new bodies we CAN apply, healing it back to 0.846. **Not a clean-base
  failure — it's the renumber/move structural tail** (the known hard residual in todo.md), now with
  concrete point-in-time cost. A big consolidating amendment is worst right after it lands and self-heals
  as clean replacements supersede the renumbers.
- **Observation (not acted on — would risk tuning on GT):** tjenesteloven shows high mean (~0.91) but low
  rate (~0.25) — provisions cluster just BELOW τ=0.98, a systematic near-miss (formatting/whitespace?) on
  an otherwise clean law. If real, a normalization could lift rate a lot; investigate structurally later.
- **Takeaway for the deliverable:** clean-base reconstruction is publishable-strong (0.85–0.997 across
  vphl/tjeneste dates, enactment near-perfect); the two drags are (i) OCR pre-2001 bases and (ii) the
  renumber/move tail right after big consolidating acts — both already on the ledger, neither a surprise.

## 2026-08-14 (cont.) — DECISIVE clean-base point-in-time result: vphl 2014 → 0.968

- **Henrik downloaded the vphl (`2007-06-29-75`) 2014-01-01 Lovdata-Pro HIST version** — the clean-base
  test CLAUDE.md/todo flagged as the highest-value step. Filed to `data/ground_truth/2007-06-29-75/`,
  registered in `index.csv`, scored via `source.eval.status` (held-out discipline: filed + scored, not
  inspected).
- **Result: verdipapirhandelloven, point-in-time as of 2014-01-01, 300 provisions → mean similarity
  0.968, rate 0.69 @ τ=0.98.** Versus the OCR-base aksjeloven (~0.80 mean, ~0.52-0.61 rate @ τ=0.90).
  This CONFIRMS the central thesis: on a clean (born-digital-era) enactment base the reconstruction of a
  PAST state is near-perfect (mean 0.968), and its rate (0.69) tracks its convergence (0.66) — so **the
  deliverable is strong for clean laws; OCR bases are the measured drag**, not a date-specific failure.
- **Aggregate point-in-time μ 0.807 → 0.847** (n_versions 3→4), rate_mean 0.555 → 0.589. The gitignored
  html stays local; only `index.csv` is tracked.
- NEXT (what to ask Henrik for): 2-3 MORE vphl dates across its life (turns one snapshot into a curve) +
  1-2 tjenesteloven (`2009-06-19-103`, conv 0.90 — expect the highest point-in-time) + at least one date
  bracketing a DEFERRED amendment to exercise the new in-force resolver on real GT.

## 2026-08-14 — in-force resolver WIRED (point-in-time deliverable): true ikrafttredelse dates replace the act-date approximation

- **Built `source/parse/inforce.py`** — resolves an amending act's TRUE entry-into-force date
  from two public-domain, offline LTI signals (the follow-up the 2026-08-13 in-force-date entry
  named; NO new harvest needed, the data was already in-corpus): (1) the act's own
  `<dd class="dateInForce">` — a concrete ISO date, else "Kongen bestemmer/fastsetter" (deferred);
  (2) for deferred acts, the triggering `sf-` ikrafttredelsesresolusjon ("(Delt) ikraftsetting av
  lov <cite> …", ~1,189 of them) whose own `dateInForce` is concrete and whose title cites the
  triggered act. Resolution = concrete act date, else earliest trigger date (act-level grain for
  "delt ikraftsetting"), else None (flag-don't-fabricate). Writes a git-ignored, rebuildable cache
  `data/inforce.jsonl.gz`.
- **Coverage:** 2,882 acts → **2,322 resolved (80.6%)** — 1,279 concrete own-date, 1,043 deferred-
  but-triggered, 560 deferred-untriggered (no trigger found → keep fallback). **1,179 acts have a
  true in-force date LATER than their passage date** — precisely the states point-in-time was
  getting wrong.
- **Wired into `lti_amendments.parse_act`**: `date_in_force_resolved = inforce.resolved_date(act) or
  act_date` (fallback preserves old behaviour where unresolved → no regression). `date_in_force`
  stays the passage date. A full `lti_amendments` rebuild now refreshes the index first so it can't
  go stale after a re-harvest (the lazy cache only builds when ABSENT). Rebuilt the stream: **606 of
  1,502 ops (40%) now carry a corrected, later in-force date**, across many laws incl. dev-set
  kjøpsloven.
- **Convergence UNCHANGED at 0.6622, guards PASS, zero τ-regression** — as expected: the convergence
  pass is `as_of=None`, which applies every op regardless of date, so op *dates* don't gate it (the
  2026-08-13 diagnosis). The whole benefit is point-in-time.
- **Point-in-time correctness DEMONSTRATED:** kjøpsloven §7's "fjerde ledd oppheves" (act
  `2002-06-21-34`, passed 2002-06-21, in force 2002-07-01) is now correctly WITHHELD until 2002-07-01
  (§7 keeps its fourth ledd at as_of=2002-06-21, drops it at 2002-07-01) — previously it applied 10
  days early, at the act date. The measured deliverable μ is unchanged at **0.807** because all 3
  held-out GT versions are aksjeloven at 2001/2003 and every deferred act the resolver corrects is
  post-2003 (excluded at those dates either way) — the fix is correct but this GT set doesn't exercise
  a passage-vs-in-force straddle. A clean-base HIST version (vphl/tjeneste, `docs/ground_truth.md`)
  with a mid-life date would move the needle.
- **Deferred (documented in todo):** per-provision partial scope for "delt ikraftsetting" (e.g.
  aksjeloven `2019-03-15-6` §4-13 is act-resolved to 2020-01-01 but that specific § was in a later/
  never batch — act-level over-applies it; still strictly less-early than the act date). Not a
  convergence lever; refines the point-in-time tail.

## 2026-08-13 (cont.) — the −6 was a BLOCK-HEADER LEAK (not in-force); fixed + sub-unit repeals enabled: 0.655 → 0.662

- **RESOLVED the sub-provision −6 — and the earlier same-session "blocked on a res-harvest" call was wrong.**
  Kept digging one step past it. The aksjeloven regressions (§4-13/§5-10/§13-18/§4-24) were NOT
  not-yet-in-force ops — they were **allmennaksjeloven (`1997-06-13-45`) ops mis-attributed to aksjeloven
  (`…-44`)** via a missed block boundary. `lov 2019-03-15-6`'s consequential-amendments chapter introduces
  its nr. 44 block with "**I** lov 13. juni 1997 nr. 44 … gjøres følgende endringer:" but its nr. 45 block
  with "**Lov av** 13. juni 1997 nr. 45 … gjøres følgende endringer:". `_BLOCK_HEADER` required the "I lov"
  prefix, so the nr. 45 block was never bounded and ALL of allmennaksjeloven's VPS ops (§4-13 "registrering i
  en verdipapirsentral" etc. — a *public*-company concept that was never private aksjeloven's §4-13) leaked
  into the nr. 44 block. Same bug-class as the earlier section-vs-block fix, via a header form it missed.
- **Fix (deterministic, no network):** broadened `_BLOCK_HEADER` to accept `(?:I\s+lov|Lov(?:\s+av)?)` before
  the cite. Safe — the "gjøres følgende endringer:" anchor is the real guard and `[^§]*?` can't span a prior
  block's ops (they contain §), so preamble title lines can't false-match. Global effect: +96 correctly-bounded
  blocks across 83 acts, all resolving; the derived stream grew 735 → 1,502 correct missing sections. Under the
  shipped whole-provision path convergence is UNCHANGED at 0.655 (correctness-neutral; the leaked ops weren't
  moving the whole-provision score) — but it flips `whole_only=False` from **net 0 → net +3**.
- **Then captured a CLEAN +6 by enabling SUB-UNIT REPEALS (the safe subset), keeping sub-provision replace/add
  off.** The `whole_only=False` gains split perfectly by op TYPE: all 6 gains are ledd *repeals*
  ("§ X annet ledd oppheves" — kjøpsloven §7/§17/§32/§35/§45/§67, the 2002 forbrukerkjøp reform, from a
  concrete-dated in-force act), all 3 residual regressions are ledd *replacements* ("… skal lyde"). Sub-unit
  repeals are safe: replay routes them through `ledd.apply`, which flags-and-leaves-intact on an unresolved
  address (the 2026-08-13 over-deletion fix), never emptying a §. Enabled them in `_parse_block` (default path).
  **Result: convergence 0.6550 → 0.6622 (+6, 543→549), strict τ 0.5754 → 0.5826, guards PASS, ZERO τ-regression**
  (verified per-provision; the lone non-crossing move is §31 0.747→0.629, already failing, recon longer-not-
  emptied — no score impact, no corruption). Deliverable point-in-time μ unchanged at 0.807 (the +6 are
  kjøpsloven; all 3 held-out GT versions are aksjeloven).
- **The residual −3 replacements (§21-15/§5-27/§16-9) are NOT in-force — I proved it.** Built an in-force
  resolution index from the corpus itself (the ikrafttredelsesresolusjoner are `sf-` forskrifter already in
  `data/lti/`, NOT a missing harvest as I'd first concluded): 1,173 "Ikraftsetting av lov …" resolutions →
  1,007 triggered acts. All three regressing acts ARE triggered/in force (2021-04-23-22 → 2021-07-01,
  2020-11-20-128 → 2021-01-01, etc.), so applying their sub-provision REPLACEMENTS should help but instead
  garbles — i.e. the blocker is **ledd-engine idempotency / double-application** (a whole-provision rebuild +
  an in-force sub-op on one §), the risky ledd tail already deferred, NOT in-force dates. The `sf-` in-force
  index remains available for future point-in-time gating, but convergence doesn't need it.
- **Net: +6 clean (0.662), one deterministic parse fix + one safe scope widening. Deferred: sub-provision
  replace/add (ledd double-application — needs an idempotent ledd apply, then the sf- in-force gate for the
  point-in-time side).**

## 2026-08-13 (cont.) — in-force-date lever DIAGNOSED: the sub-provision −6 is NOT-YET-IN-FORCE ops, not op-ordering (needs a res-harvest, corpus lacks it) [SUPERSEDED same day — see entry above: the −6 was a header leak, and the res-data was already in-corpus as sf- docs]

- **Set out to "resolve true ikrafttredelse dates" — the follow-up the LTI-omnibus entry named as the
  key remaining convergence lever ("unlocks sub-provision +6, op-ordering correctness").** Measured the
  `whole_only=False` net-zero at PROVISION grain to find WHY, per lesson 0.
- **The +6 / −6 is concrete and stable:** **+6** = kjøpsloven §7/§17/§32/§35/§45 (all one act, `2002-06-21-34`)
  + vphl §3-5; **−6** = aksjeloven §4-13/§5-10/§5-27/§13-18/§16-9/§4-24. Net matched@τ unchanged (543).
- **Root cause of the −6 is NOT out-of-order application (the earlier hypothesis) — it is ops from acts
  that are NOT (yet) in force.** Traced §4-13: its 1997 base already equals current (0.998, provision
  unchanged since enactment), yet `whole_only=False` applies three ops from **lov 2019-03-15-6** (the
  verdipapirsentral reform) → re-inserts a "nytt fjerde ledd", renumbering (4)(5)→(5)(6) → 0.629. The
  attribution is CORRECT (the act really has those §4-13 ops); the problem is **current NLOD §4-13 still
  shows the PRE-2019 text** — lov 2019-03-15-6 is `<dd class="dateInForce">Kongen bestemmer</dd>` +
  "de ulike bestemmelsene kan settes i kraft til ulik tid", i.e. deferred and (for these §§) never
  triggered. Applying it at the act date fabricates a not-in-force state. `2019-03-15-6` recurs in 4 of
  the 6 losses (§4-13/§5-10/§13-18/§4-24). (Ruled out the snapshot-contamination alternative: post-1997
  inserts §18-5/§3-3a/§14-11a/§8-2a/§5-7a/§8-2b are ALL absent from the base, so aksjeloven's base is a
  genuine ~1997 enactment, not a modern consolidation — convergence/point-in-time integrity intact.)
- **The LTI XML carries a clean, structured, public-domain in-force field** — `<dd class="dateInForce">`:
  concrete ISO date (`2001-01-01`, 1,279 acts) OR "Kongen bestemmer/fastsetter" (deferred, 1,589 acts).
  G1-safe (LTI source, offline build), unlike the NLOD "(i kraft … iflg. res. …)" parenthetical (answer key).
- **But the field alone can't gate the −6 safely.** Of 156 dev-law amending acts, **97 are deferred** — and
  MOST deferred acts DID enter force (the King triggered them; they're reflected in current, e.g. vphl §3-5's
  deferred acts drive a GAIN). Blanket-skipping deferred ops would drop dozens of real amendments and regress
  broadly. Distinguishing "deferred-and-in-force" from "deferred-and-not-in-force" (2019-03-15-6) needs the
  **triggering ikrafttredelsesresolusjon** (the `res-` document, published separately in Lovtidend Avd. I).
- **The corpus does not contain it.** `data/lti/` = 2,882 `nl-` (laws) + 33,511 `sf-` (forskrifter), **zero
  `res-` docs**; the pre-2001 `data/lovtidend_text/` harvest predates these 2019 acts. So the safe form of
  this lever is **blocked on a new harvest of post-2001 ikrafttredelsesresolusjoner** (network), not a parse.
- **What is shippable now (deferred, low yield):** wire `date_in_force_resolved` from the concrete ISO
  `dateInForce` field (1,279 acts) for correct ORDERING + true point-in-time dates. Measured ~0 convergence on
  the dev set (ordering isn't the binding constraint — whole-provision ops overwrite) and unmeasurable on
  point-in-time (all 3 held-out GT versions are aksjeloven, whose acts are deferred not concrete). Deferred to
  bundle with the res-harvest, which is what actually turns the field into the +6.
- **Net: the "+6 sub-provision" is real but gated on ikrafttredelsesresolusjon data we don't hold, NOT on op
  ordering. `whole_only=True` stays the shipped path; convergence unchanged at 0.655, guards PASS.** The honest
  higher-value step remains the deliverable-side one (a clean-base Lovdata-Pro HIST version), per CLAUDE.md.

## 2026-08-13 (cont.) — LTI omnibus re-parse recovers dropped amendments: 0.638 → 0.655, deliverable → 0.807

- **Reopened the "missing amendments" lever — and corrected an earlier wrong call.** The current NLOD
  dump annotates each provision with the acts that amended it ("Endret ved lov 4 mars 1983 nr. 4"). Using
  that as a DIAGNOSTIC (target list only — amendment text comes from public sources), compared the full
  amendment history to what we captured: ~279 acts across dev laws, ~151 missing. Most missing POST-2001
  acts are **omnibus acts** — one act amends dozens of laws — whose full text we ALREADY hold in `data/lti/`
  (2,882 clean act XMLs). The external `amendments.jsonl.gz` captured only SOME laws' sections per act and
  dropped the rest (e.g. lov 2009-06-19-48 amends 34 laws; 8 captured). So this is a PARSING gap in data on
  disk, not a scraping gap. (My earlier "omnibus is small / safe levers exhausted" was measured too
  narrowly — inside the pre-parsed stream, not the original acts. Lesson 0 again.)
- **Built `source/scrape/lti_amendments.py`** (offline build; reads `data/lti/`, NEVER a recon module —
  anti-gaming lesson 7). Splits each act on the true op-block boundary — the `I lov <cite> … gjøres
  følgende endringer:` header (NOT the `<section>` tag) — resolves each block's target law, and extracts
  ops structurally (instruction = the `defaultP`; new text = the following content articles). Writes the
  MISSING `(act,target)` sections to `data/lti_amendments.jsonl.gz` (gitignored, derived); `pipeline.load_ops`
  merges it with dedup. Full run over 2,882 acts in 6s → 735 recovered whole-provision sections.
- **Two bugs found + fixed in the loop (both were corrupting attribution):**
  - *Section-vs-block mis-attribution:* a new-enactment act's consequential-amendments chapter (e.g.
    angrerettloven 2014-06-20-27) holds several `I lov <cite>` blocks in ONE `<section>`; splitting on
    `<section>` lumped other laws' ops (sales/marketing law) under avtaleloven and wrongly deleted its
    §14/§15. Fixed by splitting on the `I lov <cite>` headers across the whole body.
  - *Sub-provision content leakage:* ledd/punktum/nr op new-text is bounded only by the next instruction, so
    it can leak across op boundaries (corrupted aksjeloven §12-6/§10-12). **v1 scope = WHOLE-PROVISION
    replace/add ONLY** (self-contained; own heading). Same net gain, ZERO per-law regression; sub-provision
    bounding is the documented follow-up.
- **Result: convergence 0.6381 → 0.6550** (+14: vphl 201→211, aksjeloven 174→178), guards PASS, **no law
  regressed**, recoveries verbatim (§21-1 0.992, §4-7 1.000, §4-20 1.000, §10-6 0.978). **Deliverable
  point-in-time μ 0.804 → 0.807** (aksjeloven 2024 rate 0.601→0.611; 2001/2003 correctly unchanged — the
  recovered acts are post-2007).
- **Follow-ups:** (a) ~~sub-provision op recovery~~ MEASURED net-zero 2026-08-13 (`whole_only=False`):
  +6 provisions but −6 regressions on the dev set. The regressions are DOUBLE-APPLICATION — a sub-provision
  op ("nytt sjette ledd skal lyde") applied to a provision a later whole-provision op already rebuilt with
  that ledd (§5-10 0.998→0.887, §4-13 0.998→0.629). ROOT CAUSE: op `date` is the ACT date, not the true
  ikrafttredelse, so sub- and whole-provision ops on one § apply out of order + the ledd engine isn't
  idempotent. Sub-provision recovery needs TRUE in-force dates first (the `date_in_force_resolved` TODO);
  the `whole_only=False` path exists to re-measure once that lands. (b) ~~blanket-terminology sections~~
  MEASURED-ZERO 2026-08-13: 68 blanket-substitution sections across LTI, only 8 touch a dev law, and
  applying them converts **0** currently-missed dev provisions (the dev laws have no term-ONLY misses;
  §7-2 helps 0.438→0.495 but has other diffs). Not worth a new op type for the dev set — revisit only if
  a full-corpus run shows term-only misses elsewhere. (c) pre-2001 acts (~55, gazette/OCR — harder).
  **Net: the LTI omnibus lever is fully exploited by whole-provision v1 (+14); both extensions measured
  not-worth-it. The remaining real convergence lever is TRUE ikrafttredelse dates (unlocks sub-provision
  +6 and general op-ordering correctness), then the pre-2001 gazette tail.**

## 2026-08-13 (cont.) — sub-unit-repeal over-deletion BUG fixed: 0.621 → 0.638, deliverable 0.786 → 0.804

- **The ledd scoping surfaced a real correctness bug (the opposite of fabrication risk — over-deletion).**
  `replay._apply_change_type` handled `change_type="repeal"` with `doc.pop(para)` — so a SUB-UNIT repeal
  ("§ 21-1 femte ledd oppheves", "nr. 3 oppheves") DELETED THE WHOLE PROVISION. Flagship: vphl §21-1 was
  built correctly by the 2019 "Kapittel 21 skal lyde" block, then wiped by a 2024 fifth-ledd repeal.
  ledd.py's own docstring warned of exactly this ("§4 pkt.b oppheves wrongly deletes all of §4") — the
  change_type path just skipped the guard.
- **Measured 38 provisions wrongly emptied** (aksjeloven 23, vphl 8, rettsgebyr 6, oreig 1) before fixing.
- **Fix:** a repeal whose instruction names a ledd/punktum/nr/bokstav routes to `ledd.apply`; if the engine
  can't resolve the address cleanly it **FLAGS and LEAVES THE PROVISION INTACT** — never deletes the whole
  § on a sub-unit repeal (flag-don't-fabricate; a kept provision is far closer to current than an empty one).
  Whole-provision repeals ("§ X oppheves", no sub-unit) still pop as before (verified: §5-11 stays absent).
- **Result: convergence 0.6212 → 0.6381** (+14: aksjeloven 163→174, vphl 198→201), guards PASS, no law
  regressed. Faithful recoveries verbatim (§21-1 0.992, §13-1 0.997, §10-1 0.993).
- **Deliverable moved TOO — the thesis in action:** point-in-time μ **0.786 → 0.804** similarity
  (aksjeloven 2024 rate 0.563 → 0.601); 2001/2003 correctly UNCHANGED (those repeals took effect later).
  A legitimate convergence fix lifted the held-out deliverable by the same mechanism — exactly what
  point-in-time≈convergence predicted.
- Note: a few repealed-STUB provisions whose only repeal in our stream is a sub-unit one (§3-9, §8-4) are
  now kept present (honest — we lack the whole-repeal act); they are is_repealed_stub-scoped-out, so
  convergence is unaffected. The remaining ~24 of the 38 are kept-but-still-below-τ (need the actual ledd
  removal + other changes) — no longer sim 0, a strict improvement.

## 2026-08-13 (cont.) — ledd engine SCOPED (provision-level): hard/risky tail, one bounded-safe subset

- **Measured the 89 `engine-gap:ledd` misses at provision level** (instrumented `ledd.apply`'s None-returns
  + classified each gap provision by base source/structure). Op-INSTANCE view is dominated by blob bases
  (462), but the PROVISION split is what matters:
  - **42 blob/absent-OCR** (37 blob + 5 absent) — pre-2001 OCR laws whose base is a flat blob with no ledd
    boundaries, so any ledd op flags. A base-structure fix (preserve ledd line breaks in OCR extraction, the
    "unnumbered-ledd on OCR bases" todo) — BUT entangled with the pre-2001 amendment-CAPTURE gap (exhausted),
    so low direct provision yield. avtale 2, oreig 8, foreld 7, rettsgebyr 13, mester 2, aksjeloven 5.
  - **11 absent** (6 clean + 5 OCR) — the ledd op targets a provision empty at apply time (wholesale-replaced
    later / never built). NOT ledd-recoverable at all.
  - **~36 structured** (aksjeloven OCR/num 23 + vphl clean/num 14 + clean/nl 3) — engine-side, but the
    failures are cascading (a prior flagged op left the provision short a ledd), noisy inline markers
    ("(1)(1)" doubles), non-consecutive nr/bokstav runs, punktum-split <2, or INSERT punktum/ledd (34+6
    op-instances — the RISKY segmentation cases, fabrication risk per goal.md).
- **Verdict — confirms the standing deprioritisation.** The clean, no-fabrication subset is small: vphl's
  ~14-17 **clean-structured REPLACE** ops (overwrite a located ledd/nr/punktum on a clean LTI base — safe,
  no segmentation). That's the ONE bounded-safe ledd lever (~+15 provisions, 0.62→~0.64), and it is
  high-value BECAUSE vphl is a clean-base law where point-in-time is predicted strong — so it lifts the
  deliverable, not just an OCR-capped proxy. Everything else (blob bases, inserts, marker-noise, absent) is
  the hard/risky/entangled tail. No engine code changed — a scoping measurement.

## 2026-08-13 (cont.) — FIRST real deliverable number: point-in-time measured + wired into status

- **Ran the actual deliverable metric (evaluation.md check 2) for the first time** — the ground truth
  was already on disk (aksjeloven Lovdata-Pro HTML at 2001/2003/2024). Drove `harness.evaluate_law`
  with the real pipeline + gate scope/τ.
- **Result — point-in-time TRACKS convergence** (the todo prediction, now confirmed with held-out data):
  aksjeloven convergence(current) rate 0.556 / mean 0.746; point-in-time **2001 rate 0.536 / mean 0.805**,
  **2003 rate 0.519 / mean 0.800**, 2024 rate 0.563 / mean 0.752. Past states reconstruct as well as (mean
  slightly BETTER than) the current one → no date-specific failure; the residual is the same ledd/OCR/capture
  tail as convergence. The harness convergence (0.556) equals the gate's aksjeloven number exactly → scoring
  is consistent. **This validates convergence as a proxy**: legitimate convergence gains move the deliverable.
- **Strategic consequence:** a *snapshot base* (booklet ajourført at a later date) would GAME this — it lifts
  convergence-to-current by replaying fewer amendments but breaks point-in-time at dates BEFORE the snapshot.
  So snapshots are legitimate ONLY for hole-year laws that have no clean enactment (kjøpsloven, rettsgebyr);
  for laws with a true enactment base, a snapshot base is proxy-gaming. Snapshots-as-validation (PD booklet
  oracle) are measurement, redundant where we already hold the Lovdata-Pro version.
- **Wired into `status`:** `status._point_in_time()` runs over any dev law with `data/ground_truth/` versions
  (encumbered, local-only — graceful "none present" fallback otherwise), same scope/τ as the gate; NOT
  repealed-stub-scoped (a repeal is date-dependent). `status.json`/`status.md` now headline
  **point-in-time μ 0.786 similarity / 53.9% ≥τ over 3 versions** ALONGSIDE convergence. The project now
  reports the deliverable, not only the proxy. Caveat noted in-code: the harness scores over the CURRENT
  provision set, so the mean-similarity column is the honest reading at past dates.
- **Next (cheap + decisive):** 1–2 Lovdata-Pro versions for a CLEAN-base law (vphl conv 0.66 / tjeneste 0.90)
  to confirm point-in-time≈convergence holds there too → would show the deliverable is strong for clean laws
  and the OCR bases are the residual drag. See `docs/ground_truth.md`.

## 2026-08-13 (cont.) — name→datokode lever MEASURED ~zero on dev set; safe pre-2001 levers exhausted

- **Question:** does resolving name-cited amend acts ("endr. i avtalelova") recover the pre-2001
  uncaptured provisions (todo lever a)? **Measured across ALL 1033 harvested issues: no.** TOC-title
  name-citation of the dev laws is essentially ZERO — avtaleloven 0, foreldelse 0, rettsgebyr 0,
  mesterbrev 0, kjøp 0; oreigning's 1 "name" hit is a DIFFERENT law ("vederlag ved oreigning"). A
  name→datokode map would recover nothing on the dev set. Confirms lesson 5 (name-map "only partly
  right") emphatically.
- **Consequence — the two safe pre-2001 levers are both spent:** neither name-citation (0) nor
  omnibus-secondary (`I lov <dev-cite>` body headers: 3/6/1) explains the pre-2001 under-capture
  (avtaleloven has just 9 amendment rows for a 1918 law). The missing amendments (e.g. avtaleloven §36,
  the 1983 general clause) are NOT surfacing as parseable standalone/omnibus acts in the current
  harvest — the residual is harvest/TOC COVERAGE of specific amending issues + blanket terminology
  reforms, not a resolution bug we can regex away.
- **State:** convergence **0.621** is the practical ceiling of the current harvest + deterministic
  approach. Further gains need one of: (i) risky ledd engine (fabrication risk — deferred), (ii) more
  SOURCE work (targeted re-harvest of missing amending issues / OCR base re-fetch — network), or
  (iii) the point-in-time deliverable, which is gated on the manual Lovdata-Pro download. No code
  changed — a measurement that (correctly) prevented building a zero-yield name map.

## 2026-08-13 (cont.) — omnibus multi-target lever MEASURED and deprioritised (measure-before-building)

- **Question:** is the omnibus sub-lever (todo (b): `gazette.py`/streams attribute an omnibus act's
  ops to a single first-cited target, losing secondary-law amendments) a big win? **Measured: no.**
- **LTI stream (`amendments.jsonl.gz`) is already well-targeted:** of 304 rows whose instruction opens
  with an `I lov <cite>` omnibus section header, exactly **1** mis-files a dev law (foreldelse §15 under
  the 1976 aksjelov). Target resolution is upstream and essentially correct — nothing to fix here.
- **Pre-2001 gazette signal is single-digit:** harvest scan for `I lov <dev-cite>` secondary-target
  section headers found **3** (avtaleloven) / **6** (foreldelse) / **1** (kjøpsloven) occurrences — and
  not all parse to a matching provision. Captured amendment rows per pre-2001 dev law (avtaleloven 9,
  mesterbrev 4, kjøpsloven 4) are LOW, but the gap is **name-citation + parse/harvest coverage**, not
  omnibus mis-targeting: e.g. avtaleloven §36 (the 1983 general clause) simply isn't present as a
  parseable date-cited amendment. So the pre-2001 under-capture is the name→datokode / blanket-reform
  problem (todo (a)/(c)), a harder low-yield tail — NOT the omnibus split.
- **Decision:** do NOT rebuild the full pre-2001 stream for a ~single-digit omnibus gain (real
  regression risk across 105k rows for <10 provisions). Consistent with the session's ceiling finding
  and lesson 0. No code changed — a measurement that redirected effort away from a low-yield build.

## 2026-08-13 (cont.) — repealed-provision stubs scoped out (objective marker): 0.592 → 0.621

- **Scope correction, same class as the convention-annex rule (needs Henrik confirm, like that one).**
  NLOD keeps a REPEALED §'s slot as a placeholder: title `(Opphevet)`/`(Oppheva)` + a
  `changesToParent` editorial note ("Opphevet ved lov …"), NO statutory text. The replay correctly
  replays the repeal op and DROPS the provision, so it can never match the annotation — an
  un-reconstructable non-statutory placeholder, exactly like a treaty annex.
- **Objective marker (not similarity-based, not hand-picked):** `metrics.is_repealed_stub(text)` =
  parsed body opens with the closed parenthetical past participle `(Opphevet)`/`(Oppheva)`. Tightened
  after a caught false positive — foreldelsesloven §32 `(Opphevelse eller endring av andre lover.)` is
  a LIVE consequential-amendments clause (the NOUN), restored to scope; the `)` after `et`/`a` excludes it.
- **CURRENT-CONTEXT ONLY.** A repeal is date-dependent (a §repealed in 2019 was live at a 2010 date), so
  this is applied ONLY to convergence-to-current (gate + loss_breakdown), NEVER the point-in-time harness.
- **Result: convergence 0.5920 → 0.6212** (denominator 870 → 829, −41 repealed stubs; matched UNCHANGED
  at 515 → confirms all 41 were previously misses, none coincidentally matched). Strict 0.524 → 0.550.
  Guards G1/G2/G3 PASS. Dual-reported in the gate + status page (41 repealed out-of-scope, separate line).
  Bulk are vphl (post-2007 churn); also rettsgebyr §21-24, aksjeloven §2-8/§18-5, kjøpsloven §4, oreig §9/§14.
- loss_breakdown: 314 misses now (was 355). No reconstruction code changed — a metric-scope correction.

## 2026-08-13 (cont.) — spaced-letter suffix fix: lettered `ny §` adds now resolve, 0.562 → 0.592

- **Acted on loss_breakdown's top safe lever.** The letter suffix of a provision id is often
  rendered/OCR'd with a SPACE before it ("Ny § 5-8 a skal lyde:", body "§ 5-8 a.Opplysninger…",
  "I kapittel 4 skal ny § 38 c lyde:"). The id parsers (`§\s*(\d+(?:-\d+)?[a-z]?)`) captured
  `§5-8`, so the whole-provision add misfiled and the real `§5-8a` stayed missing. Quantified
  first (`scratchpad`): **32 of 37 lettered-id misses had exactly this spaced-op form.**
- **Fix (period-anchored, deterministic).** New `pipeline._heading_id` / `_HEAD_ID` accept a
  spaced suffix ONLY when a period follows (`§ 5-8 a.`) — the period disambiguates a real suffix
  from a following word or preposition ("§ 5 i loven", "§ 27 første ledd"), which have no period
  and never match. Wired into `_leading_para` + `_split_block`; `replay._HEADING` strip widened
  with the same period-guard alternation (a bare `\s*[a-z]?` would have eaten the 'f' of "første").
- **Result: convergence 0.5621 → 0.5920 (489 → 515, +26), strict 0.499 → 0.524 (+22). No law
  regressed** (aksjeloven 149→163, vphl 189→198, avtaleloven/foreldelse/rettsgebyr +1). Guards
  G1/G2/G3 PASS. loss_breakdown: base-missing 84→63, total misses 381→355.
- **Faithfulness spot-checked (lesson 8):** recovered provisions match VERBATIM — aksjeloven §1-5a
  0.983, avtaleloven §38c 0.995, foreldelsesloven §15a 0.996 (heading stripped, body identical).
  vphl §5-8a stays 0.0 and correctly so: added 2010, repealed (opphevet) 2024 → replay removes it,
  while NLOD keeps an annotated "(Opphevet)" stub — we did NOT fabricate a stub to match.
- Residual lettered misses need the ledd engine (sub-provision edits like "§ 5 a nr. 3 … skal
  lyde") or are genuine capture gaps (3, e.g. mesterbrev). Next safe lever: base-extraction drops
  (plain original ids absent from OCR bases, e.g. aksjeloven §1-1/§2-12, vphl §1-4) + omnibus.

## 2026-08-13 (cont.) — loss_breakdown diagnostic: attributed all 381 misses; 0.97 unreachable, capture is the lever

- **Built `source/eval/loss_breakdown.py`** (harness-side; reuses the gate's exact scope +
  per-source τ, so its miss count == the gate's `total - matched` = 381). Classifies every
  convergence miss into ONE cause bucket mapped 1:1 onto the todo levers; writes
  `build/eval/loss_breakdown.md`. This is the "measure before building" step the amendment-
  coverage todo item had been waiting on.
- **Attribution (489/870 converge, 381 miss):**
  - `uncaptured-amdt` 100 (26%) — provision carried but NO op targets it and text differs a lot.
  - `base-missing` 84 (22%) — absent from recon AND no op (examples §9a/§38a-c/§5a/§15a are
    uncaptured `ny §` adds; a few plain-id OCR base-drops / renumber targets).
  - `engine-gap:ledd` 96 (25%) — op present, ledd/sub-provision engine can't apply (risky lever).
  - `applied-wrong` 51 (13%) — whole-provision op applied but result far off (truncation / wrong-op).
  - `engine-gap:struct` 17 (4%) — renumber/move id-remap.
  - OCR fidelity 33 (8%) — char noise, proven low ceiling (lesson 4).
- **Headline #1 — the lever:** **184/381 (48%) have ZERO amendment op** in our stream (uncaptured-amdt
  + the uncaptured-add half of base-missing). Amendment *capture* — omnibus multi-target parsing in
  `gazette.py` (currently first-target-only) + applying `ny §` adds — is the biggest, safest,
  flag-compatible lift; solving it plausibly moves convergence ~0.56 → ~0.75–0.80.
- **Headline #2 — the ceiling:** **0.97 is not reachable on this dev set** (needs +355 of 381,
  ~93% of everything; 8% OCR is capped, 29% is the risky tail). Realistic all-levers ceiling
  ~0.90–0.94. Consistent with goal.md ("targets provisional until the held-out set exists") — the
  deliverable bar is the held-out point-in-time metric, still blocked on the manual Lovdata-Pro
  download. Did NOT touch `gate.THRESHOLD` (lowering it needs Henrik sign-off; anti-gaming).
- Read-only against the dev set; no reconstruction code changed. Committed `01940a0`.

## 2026-08-13 (cont.) — booklet extraction cleanup: flag garbage, not fabricate (gap 9.1→7.3pp)

- Chased the 11 near-zero booklet provisions from the aksjeloven-2001 cross-check. Root cause: the
  dense særtrykk interleaves "Jfr. §…" footnotes with INLINE headings on the same OCR lines, so
  `provisions_ordered` sometimes locks onto a footnote §-token (§5-18 → ",", §12-1 → ", § 13-2 …").
- **Tried to RECOVER them five ways — all regressed** (title-anchored heading detection 12–38% cov;
  "Jfr."-strip 42%; aggressive fragment-drop lost 12–15 real provisions). The mess is pervasive
  (many real provisions also carry leading footnote contamination), so there is no clean deterministic
  re-extraction at reasonable effort.
- **Shipped the safe move (flag-don't-fabricate): `booklet_gt._is_failed_extraction`** drops only
  UNAMBIGUOUS garbage (<8 real chars, or a reference-dominated fragment) — catches **8/11** true
  failures with **ZERO** real provisions lost. A GT entry we couldn't extract is now absent, never a
  spurious 0.0. Result: same-verdict gap **9.1% → 7.3%** (mean 0.078 → 0.057); booklet↔oracle median
  **0.994** unchanged; coverage 92%.
- **Honest residual:** the remaining ~7pp is now mostly the INTRINSIC OCR-vs-OCR penalty (scoring an
  OCR reconstruction against a scanned booklet) plus 3 uncaught fragments — an OCR-vs-OCR τ or
  born-digital editions, NOT more extraction heuristics. (This is the "other half" flagged last entry.)

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
