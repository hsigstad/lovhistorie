# Data

How the pipeline uses its datasets. Provenance and raw-file detail are out of scope here
(see the workspace data policy); this describes *how each input is consumed*. Large or
encumbered data lives outside git (`data/` is gitignored except public-domain bases and
catalog metadata) and stays local — see the `.gitignore` and
[reference/ground_truth.md](reference/ground_truth.md).

## Inputs

- **Norsk Lovtidend gazette text** (Nasjonalbiblioteket; public-domain, 1877→present) —
  the source of both the pre-2001 **enactment bases** (OCR'd from scanned gazettes) and
  the **amendment stream**: every *endringslov* that alters a statute is parsed from its
  gazette issue into per-provision operations (add / replace / repeal). Consumed by
  `source/scrape/` (harvest) and `source/parse/` (amendment extraction). Local text under
  `data/lovtidend_text/`, issue index `data/lovtidend_index.json`.
- **NLOD current dumps** (Lovdata's free *Norsk Lovdata Open Data* current text) — the
  clean machine-readable **current** text for 2001+ laws. Used two ways: as the
  **enactment base** for laws whose clean text predates all amendments, and as the
  **answer key** for the convergence metric (`data/current/`, read only by the eval
  harness — never by the reconstruction path; enforced by guard G1).
- **Ikrafttredelsesresolusjoner** (`sf-` in-force resolutions, in-corpus) — resolve the
  **true entry-into-force date** of each act (`source/parse/inforce.py`), so a repeal or
  amendment is withheld until it actually took effect rather than applied at passage.

## Reconstruction intermediates (built, `data/`)

Amendment operations are staged as resumable streams before replay:
`amendments*.jsonl.gz` (per-provision ops) and `amendment_blocks.jsonl.gz`;
`lti_amendments.jsonl.gz` (the *Lovtidend*-omnibus stream); `blanket_amendments.jsonl.gz`
(terminology-reform "ordet «A» endres til «B»" ops); `pre2001_amendments.jsonl.gz`;
`llm_amendments.jsonl.gz` (+ `llm_cache/` — LLM op-extraction, audited). `enactment/`
holds the reconstructed original-enactment bases; `inforce.jsonl.gz` the resolved dates.
`source/parse/pipeline.py` composes enactment base + ops → point-in-time text.

## Validation oracle (eval-only, encumbered)

- **Lovdata Pro historical versions** (`data/ground_truth/`) and booklet ground truth
  (`data/booklet_gt/`) — held-out gold for the point-in-time metric. **Eval-only, never
  redistributed**; gitignored and local. Nothing here enters the published corpus, and
  the reconstruction code cannot read it (guards G1–G3). See
  [reference/ground_truth.md](reference/ground_truth.md).

## Published outputs

Only public-domain material is published: reconstructed statutory text derived from Norsk
Lovtidend + NLOD, plus catalog metadata, code, and docs.
