# External source repos (shared by Sungho Park, 2026-08-12) — relevance to lovhistorie

Sungho Park (NYU Stern) shared five GitHub repos on the "Historic versions of Norwegian laws"
email thread (Henrik + Bhuller + Hammersmark + Park). Most target *court judgments* (a separate
case-law project, not lovhistorie). Evaluated here against lovhistorie's needs — **statute**
point-in-time reconstruction, **deterministic, no-LLM-at-runtime** (see `docs/goal.md`). These are
**candidates to evaluate**, not vetted adoptions; the repo descriptions are Sungho's, unverified.

| # | repo | what it gives | relevance to lovhistorie |
|---|------|---------------|--------------------------|
| 1 | NationalLibraryOfNorway/lovdata-public-conversion-script | current consolidated Lovdata text + metadata (doc ID, ministry, legal area, effective/amendment dates, references) | **Low as a source** — current text only; cannot be a reconstruction input (violates the point-in-time rule; = the `return current text` flaw). *Possible* use: cross-check amendment **dates/references** metadata. We already have NLOD current dumps. |
| 2 | martgra/lovdata-pipeline | statute structural parsing: chapter/section headings, §, paragraph titles, **ledd**, cross-references, full text | **Highest** — the §/ledd/chapter structuring overlaps directly with `source/parse/{ledd,gazette}.py` and the `§N-M` heading gap. Worth mining for the **endringslov structuring parser** (the pre-2001 amendment lift) and the omnibus/name→datokode work. **Caveat:** repo is "statutes/RAG"-oriented — take only the **deterministic** parsing parts; no LLM/RAG in our reconstruction path. |
| 3 | doantumy/Efficiently-Summarizing-Norwegian-Legal-Texts | judgment XML → Sammendrag/Premiss/Slutning, KAPITTEL/AVSNITT | **None** for statutes (case-law). |
| 4 | worldwidelaw/legal-sources | case-level extraction: case ID, date, court, keywords, summary, judges, parties, case history | **None** for statutes (case-law; best schema for the *case* project). |
| 5 | StianOby/claude-legal-tools | retrieves Lovdata **Pro** decisions + metadata via browser auth | **Indirect** — case-oriented, but the **Lovdata-Pro browser-auth retrieval technique** could inform the held-out **ground-truth statute-version** acquisition (`docs/ground_truth.md`, currently a manual Henrik step). Ground-truth stays eval-only, never in the published corpus. |

## Actionable takeaways
- **Evaluate `martgra/lovdata-pipeline`'s §/ledd/chapter parser** against `source/parse/` — specifically
  whether it handles the `§N-M` chapter-section headings `build_enactment.py`/`gazette.py` miss, and
  whether its structuring helps split omnibus amendment acts. Deterministic components only.
- **Consider `StianOby/claude-legal-tools`** only if the manual Lovdata-Pro ground-truth pull
  (`docs/ground_truth.md`) needs automating — eval-only, never redistributed.
- Repos #1, #3, #4 are not useful here (#1 = current text; #3/#4 = case-law).
