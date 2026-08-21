# Summary

**lovhistorie** reconstructs the **point-in-time text of Norwegian statutes** — "the law
as it read at date *t*" (*gjeldende rett* over time) — from public-domain sources, as a
corpus we **own and can publish**.

## What it builds

For each statute, the pipeline starts from the **original enactment** text and replays
**every amendment** in chronological order, taking both from **Norsk Lovtidend** (the
official gazette, public-domain via Nasjonalbiblioteket back to 1877) plus the free
**NLOD** current dumps. Replaying the amendment stream to any date *t* yields the statute
as it read at *t*; replaying to today should reproduce today's official text.

Crucially it is built **only** from public-domain inputs. Lovdata Pro's historical
versions are used **as a validation oracle only** and never enter the published corpus.

## How it is scored

Two metrics, both in [evaluation.md](reference/evaluation.md):

1. **Convergence** (the dev proxy) — rebuild each law to *today* from its gazette history
   and measure how often we land back on the official current wording, over a fixed 9-law
   development set. Three mechanical anti-gaming guards (no answer-key import, runs
   isolated, base-integrity) must pass for the number to count.
2. **Point-in-time accuracy** (the deliverable) — reconstruct each law as it read at a
   *past* date and score against held-out Lovdata Pro historical versions the pipeline is
   never tuned on.

The live numbers are the generated [Performance](reference/status.md) page; worked
provision-level output — every statute scrubbed through time, with reconstruction-vs-
official diffs — is the public site (https://hsigstad.github.io/lovhistorie/, generated
by `source/site/browser.py`). The machine-checkable completion condition compiles to
`python -m source.eval.gate`.

## Layout

`source/` (scrape / parse / eval / llm / site), `docs/`, `build/`, `data/`. The
reconstruction entrypoint is `source/parse/pipeline.py`; the reward signal is
`source/eval/gate.py`. Reference material (goal, evaluation, roadmap, ground-truth,
performance) lives under [docs/reference/](reference/); working notes under
[docs/notes/](notes/); data usage in [data.md](data.md).

See [reference/goal.md](reference/goal.md) for the autonomous goal, and
[reference/roadmap.md](reference/roadmap.md) for the phased plan.
