# Plan — a separate 2005-baseline reconstruction (2005 → today)

Status: PROPOSED (2026-08-25). A second, parallel reconstruction that starts from the **2005 Lovdata-CD
consolidated snapshot** and rolls forward with post-2005 amendments only. Does NOT touch the existing
from-enactment (1918→today) pipeline.

## Is it a good idea? YES. The 2005 baseline is NOT bad.

**Why it's strong.** Nearly all of the from-enactment pipeline's error is PRE-2005: OCR'd gazette/booklet
bases (the 62% "assembly-failure" miss bucket) + pre-2001 capture gaps. Post-2005 is the easy regime:
the LTI amendment bulk is **100% harvested and clean** for every dev law (verified in the coverage audit,
2026-08-25). A clean 2005 base + clean post-2005 amendments sidesteps the whole hard part.

**The workload is small** (post-2005 changed provisions per dev law):
avtale 8 · oreign 16 · foreld 24 · rettsg 32 · kjøp 23 · aksje 154 · vphl 275 (post-2005 enacted → clean
enactment base already) · tjeneste 2. From a clean 2005 base the *static majority* of each law is
trivially — and legitimately — correct; only the "changed" column needs reconstruction, via clean ops.

**Base text quality is good.** avtaleloven/oreigningslova 2005 gold scored μ0.79/0.81 as ground truth;
the kjøp/aksje weakness is SEGMENTATION, not text quality. So the base is sound once segmented.

**It matches the real use case.** Most consumers (incl. the `vague` project) need "the law as of date t"
for t in [2005, today], not 1918→today. This delivers exactly that, at much higher fidelity.

## Legitimacy — keep the two pipelines strictly separate

Seeding from a 2005 snapshot is **legitimate for a 2005→today pipeline** (it makes no pre-2005 claim) but
would **game** the from-enactment pipeline (which does). So: the historical pipeline NEVER uses the 2005
base; the 2005 pipeline uses it by construction.

Guard/metric change: G3 base-integrity (base ≠ current for amended §s) assumes an old base. Under a 2005
base, *unchanged* provisions have base == current — legitimate (they didn't change). So the honest
headline metric for this pipeline is **accuracy on provisions that CHANGED 2005→today** (base ≠ current);
overall convergence (static gimmes included) is reported alongside but is NOT the achievement. Anti-gaming
test: correctly reconstruct the changed provisions from the 2005 base via public post-2005 amendments.

## Architecture (maximise reuse, zero overwrite)

- `pipeline.reconstruct(law, as_of, base="enactment")` — add a `base` param.
  - `base="enactment"` (default, unchanged): `enactment_base` + all ops.
  - `base="2005"`: `base_2005(law)` + ops filtered to `date > 2005-12-31`.
- New `pipeline.base_2005(law)`: the segmented 2005 CD snapshot (built offline, cached). Post-2005-enacted
  laws (vphl 2007, tjeneste 2009) fall back to their clean enactment base.
- **Reuse unchanged:** the replay engine, `load_ops` (add a date-floor arg), pointer/holistic apply, every
  amendment stream, AND the existing LLM base-segmenter (`source/llm/segment.py` + `base_segment` cache,
  already used for enactment `LLM_BASE_LAWS`).
- Eval: `source/eval/gate.py --base 2005` (or a sibling `gate_2005`) — separate convergence + threshold,
  headlined on changed-provision accuracy. The historical gate is untouched.
- Site: `source/site/browser.py` gains a base selector; dropdown **"History: [Since 2005 ▾ | Full
  history]"**, defaulting to *Since 2005*. Two cached reconstruction passes per law.

## Next step — the LLM-assisted segmenter (shared prerequisite, triple payoff)

Segment each 2005 CD law block into `{para: clean statutory text}`, dropping Lovdata's amendment notes,
footnote definitions, CISG-annex articles, and allmennaksjelov parallels (the interleaving that defeated
the regex segmenter for kjøp/aksje). Reuse `source/llm/segment.py`'s boundaries-only segmenter.

Validate: segmented-2005 ≈ current for UNCHANGED provisions (target `cur_μ ≥ ~0.95`) — the parse-quality
gate. Payoff is threefold: (a) unblocks the held-back kjøp/aksje **point-in-time** gold; (b) produces the
`base_2005` the new pipeline needs; (c) one pass segments all 248 CD laws → clean 2005 bases for the whole
corpus (well beyond the dev set).

## Phasing

- **Phase 0 (STARTED 2026-08-25):** LLM segmenter on the 4 present dev laws. Findings below.
- **Phase 1:** `base_2005()` + `reconstruct(base="2005")` + date-floored replay; 2005-gate; report
  changed-provision accuracy (expected high).
- **Phase 2:** site dropdown (default Since-2005); both histories viewable per law.
- **Phase 3 (later):** segment all 248 CD laws → a 2005 baseline for the full national corpus.
- **Phase 1:** `base_2005()` + `reconstruct(base="2005")` + date-floored replay; 2005-gate.
- **Phase 2:** site dropdown (default Since-2005); both histories viewable per law.
- **Phase 3 (later):** segment all 248 CD laws → a 2005 baseline for the full national corpus.

## Phase 0 findings (2026-08-25) — small laws done, large laws hit the messy-CD-OCR wall

**Validation metric corrected.** `cur_μ` (2005-gold vs today) conflates a bad parse with a *legitimate*
2005→today change. The right parse-quality gauge is **`cur_μ` on STATIC provisions only** (no post-2005
op) — those should match today.

**Approach validated + reused `source/llm/segment.segment_base`** (LLM locates heading *lines*, we slice
verbatim → 0% fabrication). Pipeline: line-structure the reflowed CD block (newline before each `§N`/note)
→ `segment_base` → deterministic clean (strip `0 Endret…`, `N Jfr…` footnote defs, `Art N` CISG-annex,
inline footnote digits).

**Results.** avtaleloven/oreigningslova (small, clean CD text): already at μ0.79/0.86 with the regex
parser and validate cleanly — DONE, wired into the eval. kjøpsloven/aksjeloven (large, messy CD OCR):
segmenter lifted kjøp static μ 0.42(regex)→0.59(LLM), but NOT to the ≥0.95 target. Remaining blockers,
all law-specific CD-layout OCR artifacts:
- **cross-ref-as-heading truncation:** the LLM sometimes labels a citation (`§55` inside §61) as a
  heading; `segment_base._repair` enforces only line-monotonicity, so a backward-id boundary truncates
  the real provision to just its title. Adding id-monotonic repair helped aksje not at all and *broke*
  kjøp (17 provisions — the CISG "Art" annex numbering poisons the monotonic chain).
- **allmennaksjelov parallels** (`asal. §5-23`) interleaved through aksjeloven, and **footnote
  definitions** interspersed between ledd, contaminate bodies.
- **ledd-(1) drop:** a provision's first ledd occasionally splits to the wrong slice.

**Assessment.** The 2005 CD text for the LARGE laws is genuinely messy (the original note's "real parsing
project of uncertain fidelity" keeps proving right). Boundary-location by LLM is the right tool but needs
more than a thin wrapper: candidate options for the next pass —
1. **Per-provision anchor extraction** (pointer_apply-style: LLM returns clean start+end verbatim anchors
   per provision, excluding notes/annex/parallels) instead of boundaries-only + regex cleaning.
2. **Prompt-harden** `segment_base` for the CD format (reject `asal.`/`Art`/citations explicitly) + a
   chapter-aware id-monotonic repair that resets at the CISG-annex boundary.
3. **Scope down:** ship the 2005 baseline for the laws that extract cleanly (avtale/oreign + the
   post-2005-enacted vphl/tjeneste that need no CD base) and treat kjøp/aksje as a known hard tail.

NOT yet productionised (prototype in scratchpad). Small-law point-in-time is already live; large-law
gold + base stays held back in `build_gt_lovdata_cd.TRUSTED` until one of the above lands.
