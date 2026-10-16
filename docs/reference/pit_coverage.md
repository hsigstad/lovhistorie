# Point-in-time deliverable: coverage & fidelity (2005 oracle)

**What this is.** An honest, corpus-wide read of how well we reconstruct the point-in-time text of
Norwegian statutes, scored against the independent 2005 Lovdata-CD gold (NLOD 2.0, built by
`source.scrape.build_gt_lovdata_cd.build_corpus`). Regenerate: `python -m source.eval.pit_corpus`
→ per-law table `build/eval/pit_2005_corpus.csv`. This complements the dev-set gate
(`source.eval.gate`, convergence over 9 laws) and the deliverable metric
(`status._point_in_time`, dev laws only) by covering the whole 2005-CD selection.

## The headline (2026-10-16)

- **2005 gold oracle:** 185 CD "Norges Lover" laws extracted; **142 are body-trustworthy** (>=85% of
  their extracted provisions carry a real body, not a TOC heading). 7,820 provisions total.
- **Reconstruction coverage is the binding constraint, not oracle coverage.** Of 154 laws with >=5
  full-body gold provisions, the current pipeline **reconstructs only 79** (the rest have no base/stream
  built — `reconstruct()` returns near-empty). *We now hold more point-in-time gold than we can
  reconstruct against.*
- **Fidelity over the 79 reconstructable laws (char-sim @2005, full-body gold only):** mean **0.53**,
  median **0.56**; **0 laws >=0.90**, 16 at 0.70-0.90, 27 at 0.50-0.70, 36 below 0.50.
- **This is well below dev-set convergence (72.3%).** The independent oracle shows convergence-to-current
  OVERSTATES historical fidelity — later clean LTI amendments overwrite the noisy base, so "current"
  looks good while the point-in-time state does not. (Sharpest on OCR bases: kjøpsloven conv 0.92 vs
  pit@2005 0.48.)

## Two metrics, kept apart (do not collapse into one "completeness" number)

- **body-completeness** (trust gate) = of the provisions the CD gold gives us, the fraction with a real
  body. Measures gold quality. INTRINSIC — not vs the current law (which would conflate NCC body-drops
  with provisions ADDED after 2005).
- **coverage** = fraction of the current statutory provisions the gold even lists. Reported for
  transparency; a law grown since 2005 legitimately has <100% coverage.
- **fidelity** (the deliverable) = char-similarity of `reconstruct(law, 2005-12-31)` to the gold, scored
  ONLY over provisions where the gold has a full body (fair to the reconstruction).

## Known limits of the 2005 oracle (why it is not the whole answer)

- The source is the NCC/norkart release, which is **body-incomplete for some large laws** (kjøpsloven
  60% body-complete; folketrygdloven 31%, helsepersonelloven 26% — and those last two are where the ledd
  applicator does most of its work, so the applicator's main footprint is unmeasurable here). The clean
  fix is the native structured CD discs (1995/2000/2005) — see `docs/notes/lovdata_cd_2005.md`.
- It is a **single date (2005)**. Crediting pre-2001 amendment work needs an earlier snapshot.

## Levers this exposes (for whoever picks this up)

1. **Reconstruction coverage** (79 → more): build bases/streams for the other ~75 CD laws that have gold
   but no reconstruction. Biggest immediate expansion of what the oracle can measure.
2. **Fidelity on OCR bases**: median 0.56 / none >=0.90 is the real deliverable ceiling today; the
   amendment-capture gap (`source.eval.loss_breakdown`: ~48% of dev-set misses are uncaptured `ny §`
   adds) is the quantified lever.
3. **Earlier CD editions** (Route B) for pre-2001 dates + the body-incomplete large laws.
