# Enactment base from the gazette — proven on one law (2026-08)

The reconstruction needs a starting text: the law **as originally enacted**, from
Norsk Lovtidend (public domain), never from the current consolidated text. This note
records the first end-to-end proof and the levers the autonomous loop must pull.

## Pipeline (all offline / cached; deterministic at gate time)

1. `source/scrape/build_enactment.py` — locate the enactment issue/page in NB
   (full-title search → `find_page`), OCR-extract via `nb_lovtidend.page_text`
   (column-reflowed ALTO), cut from the law's title to the next `Lov nr.` heading,
   split into `{§N: text}` (line-anchored `§ N.` headings + the cross-ref-safe
   `metrics.provisions_ordered`). Writes `data/enactment/<datokode>.json`.
2. `source/parse/pipeline.enactment_base` reads that JSON — no network, no OCR, no
   current text. `data/enactment/*.json` is public-domain and committed.

Known enactment locations live in `build_enactment.LOCATIONS` (issue URN + page +
title needle). Locating is the fiddly part; the loop grows this registry.

## Proof: mesterbrevloven (lov/1986-06-20-35)

Enactment found at NB `digitidsskrift_2015102680007_013` p23 ("20. juni. Lov nr. 35 /
Lov om mesterbrev i håndverk og annen næring"), 10 provisions (§1–§10) extracted.
Wiring it moved convergence **1/12 → 3/12**, and the base-integrity guard (G3) still
passes — i.e. the OCR'd enactment genuinely differs from today's text, so this is
real reconstruction, not the copy-current cheat.

## Per-provision diagnostic → the levers (what the loop still owes)

| provisions | state | lever |
|---|---|---|
| §2, §4, §7 | match (§4 via whole-provision `replace`) | — |
| §1, §6 | flagged `subprovision` ops, stuck at enactment | **ledd engine** |
| §8, §9, §10 | enactment §8 = commencement; current §8 = other content | **renumbering / inserted §§** |
| §1a, §1-3 | added by later amendments, absent from enactment | **inserted provisions** |
| §3, §5 | 0.92 / 0.73 | **OCR fidelity** |

These are exactly the four hard problems in `docs/roadmap.md`. Convergence measures
them honestly per provision, so the loop has a per-provision worklist, not a single
opaque score.

## Next for scale

- Build enactment bases for the rest of the dev set (each needs a `LOCATIONS` entry).
- The locator (`build_enactment` search → page) is the step to automate for the full
  corpus; today it leans on the recorded issue/page.
