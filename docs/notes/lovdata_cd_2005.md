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
