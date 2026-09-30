# Setup — running lovhistorie from a fresh clone

For a collaborator (e.g. running with Claude Code) who wants to reconstruct laws or
improve the pipeline. The reconstruction *runtime* is deterministic; the *build* of new
law bases uses an LLM (offline, cached). See `CLAUDE.md` and `docs/reference/goal.md` for
what the pipeline does and the rules it holds to.

## 1. Clone + dependencies

```bash
git clone git@github.com:hsigstad/lovhistorie.git
cd lovhistorie
python -m venv .venv && . .venv/bin/activate     # Python 3.11+
pip install -r requirements.txt                  # pydantic, openai, llmkit (from public GitHub)
export OPENAI_API_KEY=...                         # your own; needed only to BUILD new bases
```

`llmkit` installs straight from its public repo (`github.com/hsigstad/llmkit`). `sitekit`
(the browsable site) and `pandas` (the 2005-CD eval builder) are **not** needed to build
law bases or run the gate.

## 2. Restore the data (gitignored, large)

The public-domain scrape + inputs are large (gitignored). Ask Henrik for the shared
Dropbox folder, then restore these into `data/`:

| archive | restores to | needed for |
|---|---|---|
| `lovtidend_text.tar.gz` | `data/lovtidend_text/` | pre-2001 bases + gazette amendment recovery (**the scrape**) |
| `lti.tar.gz` | `data/lti/` | post-2001 bases + the national amendment stream |
| `current.tar.gz` | `data/current/` | convergence denominator (NLOD current text) |
| `amendment_streams.tar.gz` | `data/` (loose) | amendment ops + catalog index |
| `llm_cache.tar.gz` | `data/llm_cache/` | **reuse already-paid LLM segmentation** (huge: skips re-segmenting the corpus) |

The shared folder also includes `ground_truth_ENCUMBERED` (`data/ground_truth/`), used only
for the point-in-time eval. It is **not required** for convergence (the working metric, which
scores against `data/current`, public NLOD). It derives from **Lovdata Pro** (a licensed
commercial source): treat it as internal, do not redistribute further, and check it against
your institution's Lovdata licence.

## 3. Sanity check

```bash
python -m source.eval.gate      # anti-gaming guards + convergence on the 9-law dev set (~0.72)
```

Reconstruct one law (deterministic, no LLM/key):

```python
from source.parse import pipeline
prov = pipeline.reconstruct("lov/2007-06-29-75")      # {para_id: text}
```

## 4. Where to contribute

The open item is the **pre-2001 enactment locator** — see the "Out-of-sample / full-corpus
scaling (OPEN FORK)" section in `docs/todo.md`, and the 2026-09-25 entry in `docs/done.md`
for the findings. In short: post-2001 bases build automatically (`build_post2001`), but
pre-2001 laws currently need a hand-authored `LOCATIONS` entry; the automated path is to
segment each enactment-year issue (`source/llm/segment_issue.py`, already cached in
`data/llm_cache/issue_acts`) and match acts by datokode — needing (a) large-volume chunking
(89 harvest files are 400+ pp) and (b) reliable enactment-body extraction.

**Convergence is answer-free** (scores against public NLOD current text), so you can iterate
the locator without any encumbered ground truth.

Key reading: `CLAUDE.md`, `docs/reference/goal.md` (the rules), `docs/todo.md` (open work),
`docs/done.md` (what's been tried), `docs/notes/lessons_and_pitfalls.md` (read first).
