# lovhistorie

Point-in-time text of Norwegian statutes — *gjeldende rett* over time, reconstructed
from public-domain sources (Norsk Lovtidend via Nasjonalbiblioteket + NLOD current
dumps). The law **as it read at any past date**, as a corpus we **own and can
publish** (public-domain statutory text + NLOD; åndsverkloven §14).

**Live site → https://hsigstad.github.io/lovhistorie/** — browse any dev-set statute
across time: scrub the date, see amendment redlines, and compare each reconstruction
against the official current text.

**Status (2026-08-25):** engine mature. Convergence **72.3%** on the 9-law dev set
(anti-gaming guards pass); deliverable point-in-time **μ 0.870** across held-out
law × date versions. Segmentation, amendment op-extraction and application are
**LLM-based but run offline** — the model emits line numbers / verbatim anchors /
pointers (never generated text), everything is substring-verified against
public-domain source and cached; the **runtime that replays them is deterministic**
and answer-key-free. See `docs/reference/goal.md`,
`docs/reference/evaluation.md`, `docs/reference/roadmap.md`.

**Pipeline (current vs legacy).** The pipeline is **one segmentation step → a deterministic
assembly layer** (`docs/decisions.md` 2026-10-04). *Current:* `source/scrape/segment_prompt.py`
+ the subagent fold `fold_segmentation.py` build **`data/segments.jsonl`** (the flat corpus, in
git); `source/parse/pipeline.py` → `replay.py` → `ledd.py` reconstruct from it deterministically
(CLI `source/parse/reconstruct.py`; no LLM at runtime). *Legacy:* the 2026-08 OpenAI build modules
(`source/llm/*`, `source/scrape/build_{applied,gazette,omnibus,pointer}.py`,
`source/parse/{endringslov,gazette,inforce}.py`) each carry a `# LEGACY` header — they only rebuild
cached op streams the 9 dev-set laws still replay, and the runtime never imports them.

**Run it yourself:** see `SETUP.md` (clone, dependencies, data restore) and `docs/todo.md`
for the open work (the pre-2001 enactment locator).

## Using the panel (for collaborators)

Get "law L as it read on date t" to join against case / outcome data — `source/consume.py`:

```python
from source import consume

consume.reliable_laws(0.7)                       # datokodes we reconstruct faithfully (2005-oracle fidelity >= 0.7)
consume.law_as_of("1997-06-13-44", "2005-12-31") # {paragraf_id: text} for aksjeloven as of that date
consume.law_as_of("1997-06-13-44")               # latest; date=None -> current
consume.catalog()                                # every validated law + reconstructable/fidelity/coverage flags
# join to a case:  consume.law_as_of(case.law_datokode, case.decision_date)
```

**Which laws to trust:** `docs/reference/laws_catalog.csv` (per-law `reconstructable`, `fidelity`,
`coverage`, `ocr_base`) and the honest state in `docs/reference/pit_coverage.md`. Short version:
the pipeline currently reconstructs **79** of the 154 laws with 2005 gold; fidelity over those is
**median ~0.56 (0 laws >= 0.90)** — dev-set convergence (72.3%) overstates it. Pick laws from the
catalog by `fidelity`; laws absent from it may still reconstruct but are unvalidated. Regenerate:
`python -m source.eval.pit_corpus && python -m source.consume build-catalog`.

**Why not just use existing tools?** Lovdata's free API and the open reconstructions
(`sondreskarsten/norwegian-laws`, `norgeslover.no`) seed their history with *today's*
text as a 2001 baseline, so they are silently wrong for provisions unamended by 2001.
Lovdata Pro has true historical versions but is subscription-gated with reuse limits.
This pipeline builds the corpus from the public-domain gazette instead — owned, and
correct back to 1877.

Migrated from earlier feasibility work.
