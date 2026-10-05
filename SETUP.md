# Setup — running lovhistorie from a fresh clone

For a collaborator (e.g. running with Claude Code) who wants to **reconstruct laws** or
improve the pipeline. See `CLAUDE.md` and `docs/reference/goal.md` for what the pipeline does
and the rules it holds to.

**Architecture in one line:** the pipeline is **one segmentation step → a deterministic
assembly layer** (`docs/decisions.md`, 2026-10-04). Segmentation (offline, LLM) produces
`data/segments.jsonl` — a flat, git-tracked, verbatim-anchored char-partition of every
Lovtidend issue. **Reconstruction at runtime reads that file + the frozen OCR and is pure
deterministic replay — no LLM, no answer key.** `data/segments.jsonl` IS the corpus and is in
git; you only need to restore the frozen OCR it points into.

## 1. Clone + dependencies

```bash
git clone git@github.com:hsigstad/lovhistorie.git
cd lovhistorie
python -m venv .venv && . .venv/bin/activate     # Python 3.11+
pip install -r requirements.txt
```

The reconstruction runtime needs only the standard deps. `OPENAI_API_KEY` / `sitekit` /
`pandas` are **not** needed to reconstruct laws or run the gate — they belong to the (offline)
build and the browsable site.

## 2. Restore the data you need (gitignored, large)

A clone already gives you the **corpus** (`data/segments.jsonl`, 259 issues), the **law
register**, and the **9 dev-set enactment bases**. What's gitignored is the bulk/encumbered
data. Pull from the shared Dropbox folder **`bi-dropbox:pipelines/lovhistorie/`** (6 archives +
`README_RESTORE.md` + `SHA256SUMS.txt`; ask Henrik for access). You almost certainly do **not**
need all of it:

| archive | restores to | needed for |
|---|---|---|
| **`lovtidend_text.tar.gz`** (88M) | `data/lovtidend_text/` | **reconstruction** — the frozen NB OCR that `segments.jsonl` points into. **This is the only archive you need to reconstruct corpus laws.** |
| `current.tar.gz` (8.6M) | `data/current/` | the convergence metric (NLOD current-text denominator) + `--list` sanity |
| `amendment_streams.tar.gz` | `data/` (loose) | the 9 dev-set laws' pre-built op streams (the gate) |
| `lti.tar.gz` (94M) | `data/lti/` | building NEW post-2001 bases |
| `llm_cache.tar.gz` | `data/llm_cache/` | reusing already-paid LLM segmentation when building new bases |
| `ground_truth_ENCUMBERED.tar.gz` (1.1M) | `data/ground_truth/` | the point-in-time eval ONLY (Lovdata Pro — licensed, internal, do **not** redistribute) |

Restore (each archive carries its own top-level dir, except `amendment_streams` which is loose):

```bash
mkdir -p _dl && rclone copy bi-dropbox:pipelines/lovhistorie/ ./_dl/ --include '{*.tar.gz,SHA256SUMS.txt}' -P
cd _dl && sha256sum -c SHA256SUMS.txt && cd ..   # verify (hashes shipped alongside)
tar xzf _dl/lovtidend_text.tar.gz -C data/     # the one you need for reconstruction
# ...restore the others only if you need the gate / eval / to build new bases
```

## 3. Reconstruct a law

Clone + `lovtidend_text.tar.gz` restored is enough. A CLI wraps the runtime:

```bash
python -m source.parse.reconstruct --list                       # what's reconstructable (datokodes)
python -m source.parse.reconstruct 2007-06-29-75                # latest text, all §§
python -m source.parse.reconstruct lov/2007-06-29-75 --as-of 2010-01-01
python -m source.parse.reconstruct 1997-06-13-44 --para §5-3    # one provision
python -m source.parse.reconstruct 2009-06-19-103 --json > out.json
```

Or from Python (what the CLI calls):

```python
from source.parse import pipeline
provs, flags = pipeline.reconstruct("lov/2007-06-29-75", as_of="2010-01-01")  # {para: text}, [unapplied ops]
```

**Coverage + honesty.** `--list` shows the datokodes with a reconstructable base. Enacted and
lightly-amended laws reconstruct well; heavily-amended laws reconstruct the base + apply what
the deterministic engine can, and **FLAG (never fabricate)** the ops it can't — flagged §§ are
left at their last-known text, and the CLI prints a flag summary. Flags are the known
sub-provision/renumber tail, not silent errors.

## 4. Sanity check (optional — needs `current` + `amendment_streams`)

```bash
python -m source.eval.gate      # anti-gaming guards + convergence on the 9-law dev set (~0.72)
```

Deliverable point-in-time eval (needs `ground_truth`): `python -m source.eval.status`.

## 5. Where to contribute

The reconstruction machinery is mature; the open fronts are (a) **growing the corpus** —
segment more Lovtidend issues into `segments.jsonl` (the offline subagent flow; see
`docs/done.md` 2026-10-05), (b) the **sub-provision/renumber application tail** that still
flags on heavily-amended laws, and (c) the **register-completeness queue** (`target-*` in
`classification_qa`) as the historical law register fills.

Key reading: `docs/decisions.md` (the architecture), `CLAUDE.md`, `docs/reference/goal.md`
(the rules), `docs/todo.md` (open work), `docs/done.md` (what's been done),
`docs/notes/lessons_and_pitfalls.md` (**read first**).
