# Lovdata CD 2005 in NCC — investigated, not a drop-in anchor (2026-08)

**Idea:** Lovdata's final CD edition (autumn 2005) is out of database protection and
NB AI Lab released its content as NLOD 2.0 inside the Norwegian Colossal Corpus
(`NbAiLab/NCC`). A *consolidated 2005 snapshot of the whole corpus* would be the
base anchor we lack (roll forward with machine-readable amendments → clean modern
window, no gazette OCR; plus free corpus-wide ground truth at 2005).

**What we found (checked the actual docs):**
- Confirmed: NLOD 2.0, autumn-2005 content — `lovdata_cd_norgeslover_2005`
  (1,419 docs), `sentrale_forskrifter_2005` (11,745), `odelsting_2005` (~1,987
  Ot.prp), rundskriv, local forskrifter. Not gated. Fields: `id, doc_type, text`.
- **But in NCC it is fragmented, not per-law.** ~1,270 words/doc — a mix of whole
  small laws, *fragments* of large laws (start mid-law, e.g. "§418 …", "Art 8. …",
  "0 Endret ved lov …"), and endringslov texts. Many fragments have **no title**.
- **The id is a sequential `lovdata_cd_NNNNN`, not a datokode** — so mapping a doc
  to its law needs title/content matching, and titleless fragments make that hard.

**Verdict:** the *content* is real and ownable, but the NCC form is LLM-training
chunks — reassembling clean per-law point-in-time text is a real parsing project of
uncertain fidelity. **Not the plug-and-play 2005 anchor.**

**The real lead — native structured discs.** Database protection lapses at 15 years,
so every Lovdata CD edition up to ~2010 is now free, and the *native discs are
structured* (consolidated per-law), unlike the NCC fragments. Multiple editions
(≈1995/2000/2005) would give multiple clean anchors → collapses the gazette-OCR
burden. NB (legal-deposit) almost certainly holds the disc series.

**Actions (not done yet):** email NB AI Lab — (a) is the *structured* 2005 lovdata
data available (pre-chunking)? (b) are *earlier* editions releasable? Until then:
keep the gazette + amendments pipeline as primary; treat NCC as supplementary.

Access notes for re-check: NCC is 46 sharded jsonl (~30 GB), source-ordered; the
lovdata block is in the last shard(s). `curl -Ls <resolve-url> | grep -m1
lovdata_cd_norgeslover_2005` works (the resolve URL redirects — need `-L`). The
datasets-server /rows stops serving ~row 1.32M, so the lovdata block isn't
API-reachable.

---

## 2026-08-25 — REVISITED: verdict upgraded. Access solved; extraction works; FIRST independent point-in-time numbers.

The 2026-08 verdict ("not plug-and-play, uncertain fidelity") is **too pessimistic given today's access.**

**Access is now trivial.** The lovdata_cd_2005 content is a dedicated HF dataset **`norkart/lovdata`** — a
248 MB parquet, `doc_type`-labelled, no 30 GB NCC shard-wrangling, no 1.32M-row API limit. The 1,386
`lovdata_cd_norgeslover_2005` docs are a **contiguous, id-ordered block** (id 32965–34488). Concatenating
in id-order rebuilds the full 2005 law corpus (~11 M chars). Builder: `source/scrape/build_gt_lovdata_cd.py`.

**Per-law extraction is SOLID.** The old note's fear ("titles indistinguishable from cross-refs") was
wrong: the CD marks each law with a clean header **`<enactment-year> <Name> - <abbrev>.`** (e.g.
`1997 Aksjeloven - asl.`, `1918 Avtaleloven - avtl.`; small laws just `<year> <Name>.`). Splitting on it
gives 248 correctly-bounded per-law blocks with Lovdata's own amendment-provenance notes intact.

**Scope: only 4 of 9 dev laws are in 'Norges Lover'** (it's a curated selection): avtaleloven(1918),
oreigningslova(1959), kjøpsloven(1988), aksjeloven(1997). foreldelses-/rettsgebyrloven are NOT in the
selection; vphl(2007)/tjeneste(2009) postdate the 2005 edition.

**FIRST independent point-in-time numbers** (our `reconstruct(law, as_of=2005-12-31)` vs the Lovdata-CD-2005
gold, per-provision char-similarity; `cur_μ` = 2005-gold-vs-today, a parse-quality check):

| law | §matched | ≥τ | pit_μ | cur_μ | status |
|---|---|---|---|---|---|
| avtaleloven | 40 | 45% | **0.788** | 0.853 | TRUSTWORTHY |
| oreigningslova | 33 | 52% | **0.809** | 0.926 | TRUSTWORTHY |
| kjøpsloven | 86 | 10% | 0.428 | 0.424 | parse-limited (not real) |
| aksjeloven | 266 | 12% | 0.445 | 0.440 | parse-limited (not real) |

For avtale/oreign the numbers are internally consistent (`cur_μ` high → clean gold parse) and match a key
claim: **our 2005 reconstruction scores ≈ our CURRENT convergence** for these laws (avtale current 35/45,
oreign 17/31) — the first *independent* evidence that convergence-vs-current is a valid proxy for the
point-in-time deliverable (previously only checkable via encumbered Lovdata Pro or the contaminated
Skarsten replay). kjøp/aksje are dragged by a first-cut provision **segmenter** that drops ~half of
large-law provisions (empty gold bodies for e.g. aksje §16-6, while §1-1/§5-3/§10-7 parse perfectly at
0.99) — `cur_μ 0.42` proves the low score is a parse artifact, not a reconstruction failure.

**Remaining work (bounded):** replace `build_gt_lovdata_cd.parse_provs` (a period-anchored regex) with the
pipeline's `target_localize` segmenter (heading-vs-cross-reference on noisy prose) so aksje/kjøp gold parses
cleanly; then wire all 4 laws into `source/eval/status._point_in_time` as a public, on-disk point-in-time
oracle (unlike Lovdata Pro, this is NLOD 2.0 / publishable). Output lives in `data/ground_truth/2005/`
(gitignored like the rest of ground_truth; regenerate with `python -m source.scrape.build_gt_lovdata_cd`).
