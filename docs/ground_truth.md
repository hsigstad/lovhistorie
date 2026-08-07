# Ground truth — Lovdata Pro historical versions (manual download)

## Purpose

The gold-standard evaluation ([evaluation.md](evaluation.md), check 2) compares our
reconstruction to Lovdata Pro's professionally-curated historical versions. This is
the **held-out test set** — the pipeline is *never tuned* on it, only scored.

## What to download  *(Henrik, via the Lovdata Pro subscription)*

A **stratified** sample spanning eras, sizes, and amendment intensity. Target
~**15–20 laws × 3–5 dates each ≈ 60–100 versions** — enough to measure, small
enough to be feasible manual work.

Stratify by:
- **Era of enactment**: 1900s · 1950s · 1980s · 1997–2005 · 2010s.
- **Size**: small (<10 §) · medium · large.
- **Amendment intensity**: rarely amended · heavily amended.
- Include the two we've already validated (**mesterbrevloven** LOV-1986-06-20-35,
  **Oppgaveregisteret** LOV-1997-06-06-35) for continuity.

For each law, grab its consolidated text **as of several dates** — e.g. ~5-year
spacing across its life, **plus** one date just-before and just-after a known
amendment (those bracket the hardest cases).

## How (Lovdata Pro)

Open the law → **"Historiske versjoner"** → pick a date → **save as HTML**
(preferred — structured, one clean `<a name="_X-Y">` anchor per provision, which the
parser uses; **better than PDF**). One file per `(law, date)`.

## Where to put it

- `data/ground_truth/<datokode>/<YYYY-MM-DD>.html` — the saved version.
  (`.txt` also works; `.html` is preferred. Parsed by `source/eval/lovdata_html.py`.)
- `data/ground_truth/index.csv` — manifest with columns:
  `datokode, valid_from_date, filename, source, era, size_class, amendment_intensity`.

The tree is git-ignored (encumbered, eval-only); only `index.csv` is tracked.
**Validated end-to-end** on the first item (aksjeloven §1997-06-13-44, 2003-01-01
HTML → 266 provisions parsed and scored).

## Licensing — keep the oracle separate from the output

These files are for **internal evaluation only**. They are **not redistributed**
and **not part of the published corpus** — the published corpus is built *solely*
from public-domain sources (NB Lovtidend + NLOD). This firewall keeps the eval
oracle (encumbered) separate from the owned output (unencumbered).

## Held-out discipline

Do not consult these while *building* the pipeline beyond the pass/fail metric —
they are the test set, and looking at them to fix specific cases would leak the
test into training and inflate the score.
