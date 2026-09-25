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

**Why not just use existing tools?** Lovdata's free API and the open reconstructions
(`sondreskarsten/norwegian-laws`, `norgeslover.no`) seed their history with *today's*
text as a 2001 baseline, so they are silently wrong for provisions unamended by 2001.
Lovdata Pro has true historical versions but is subscription-gated with reuse limits.
This pipeline builds the corpus from the public-domain gazette instead — owned, and
correct back to 1877.

Migrated from earlier feasibility work.
