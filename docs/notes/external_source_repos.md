# External source repos — relevance to lovhistorie

Five GitHub repos on historic versions of Norwegian laws, assessed against lovhistorie's needs.
Most target *court judgments* (a separate case-law project, not lovhistorie). Evaluated here
against lovhistorie's needs — **statute** point-in-time reconstruction, **deterministic,
no-LLM-at-runtime** (see `docs/goal.md`). These are **candidates to evaluate**, not vetted
adoptions; the repo descriptions are as given, unverified.

| # | repo | what it gives | relevance to lovhistorie |
|---|------|---------------|--------------------------|
| 1 | NationalLibraryOfNorway/lovdata-public-conversion-script | current consolidated Lovdata text + metadata (doc ID, ministry, legal area, effective/amendment dates, references) | **Low as a source** — current text only; cannot be a reconstruction input (violates the point-in-time rule; = the `return current text` flaw). *Possible* use: cross-check amendment **dates/references** metadata. We already have NLOD current dumps. |
| 2 | martgra/lovdata-pipeline | statute structural parsing: chapter/section headings, §, paragraph titles, **ledd**, cross-references, full text | **Highest** — the §/ledd/chapter structuring overlaps directly with `source/parse/{ledd,gazette}.py` and the `§N-M` heading gap. Worth mining for the **endringslov structuring parser** (the pre-2001 amendment lift) and the omnibus/name→datokode work. **Caveat:** repo is "statutes/RAG"-oriented — take only the **deterministic** parsing parts; no LLM/RAG in our reconstruction path. |
| 3 | doantumy/Efficiently-Summarizing-Norwegian-Legal-Texts | judgment XML → Sammendrag/Premiss/Slutning, KAPITTEL/AVSNITT | **None** for statutes (case-law). |
| 4 | worldwidelaw/legal-sources | case-level extraction: case ID, date, court, keywords, summary, judges, parties, case history | **None** for statutes (case-law; best schema for the *case* project). |
| 5 | StianOby/claude-legal-tools | retrieves Lovdata **Pro** decisions + metadata via browser auth | **Indirect** — case-oriented, but the **Lovdata-Pro browser-auth retrieval technique** could inform the held-out **ground-truth statute-version** acquisition (`docs/ground_truth.md`, currently a manual step). Ground-truth stays eval-only, never in the published corpus. |

## Actionable takeaways
- **Evaluate `martgra/lovdata-pipeline`'s §/ledd/chapter parser** against `source/parse/` — specifically
  whether it handles the `§N-M` chapter-section headings `build_enactment.py`/`gazette.py` miss, and
  whether its structuring helps split omnibus amendment acts. Deterministic components only.
- **Consider `StianOby/claude-legal-tools`** only if the manual Lovdata-Pro ground-truth pull
  (`docs/ground_truth.md`) needs automating — eval-only, never redistributed.
- Repos #1, #3, #4 are not useful here (#1 = current text; #3/#4 = case-law).

## Web sources (same thread — Manudeep/Sungho, 2026-08-05/08-12)

Three websites/collections surfaced in the same "Historic versions of Norwegian laws" thread.
None is a primary reconstruction source (they violate the point-in-time rule or are too partial),
but two are worth holding as a **fallback / cross-check** for the known NB gazette coverage holes.

| source | what it gives | relevance to lovhistorie |
|--------|---------------|--------------------------|
| `norgeslover.no/lover` ("Historisk visning" per law) | historic versions of laws, clickable per §/date | **Low as a source, useful as fallback/cross-check.** Like `sondreskarsten/norwegian-laws` it seeds history with *today's* consolidated text as a 2001 baseline → silently wrong for provisions unamended by 2001 (the exact flaw this pipeline exists to avoid). But it's a candidate **fallback for the NB harvest holes** (1891, 1976, 1980, 1982, 1984, 1987–89 → esp. **kjøpsloven 1988**, currently unrecoverable from NB — see `BLOCKER.md` item 3) and an independent point-in-time cross-check. Verify its true underlying source before trusting any pre-2001 wording. |
| `norgeslover.no/lovtidend-arkiv.php` | Lovtidend changes archive, incl. pre-2001 | **Redundant** — lovhistorie already harvested the full digitised **Norsk Lovtidend Avd. I 1877–2000** from NB (`source.scrape.harvest_lovtidend`). Keep only as a spot-check if an NB issue is missing/garbled. |
| `nb.no` student law-book digibok (`digibok_2023030748057`) | scanned student edition, subset of laws, PDF | **Marginal** — a partial subset in booklet form. Note lovhistorie *already* mines PD student booklets as a point-in-time **validation** set (`source/eval/booklet_gt.py`, e.g. aksjeloven-2001); this digibok is a candidate to add to that registry if its laws/years fill a gap, **not** a reconstruction base. |

## Note

This project was migrated from the earlier feasibility work in `projects/vague` (see the
root `CLAUDE.md`) — the same law-versioning effort, now the production pipeline.
