# Lessons & pitfalls — READ FIRST

This project's history is full of "hard walls" and "obvious causes" that turned out to be
**wrong** — usually a bug in the *measurement*, not the reconstruction. Each item below is
a misunderstanding we actually made and corrected (2026-08). Read this before concluding
"the reconstruction is bad" or "this is a hard limit."

## -1. "Base unrecoverable — the volume isn't digitised" was another wrong hard wall
kjøpsloven (1988) and rettsgebyrloven (1982) were called "unbuildable from NB" because their
annual Lovtidend Avd. I volumes sit in NB's digitisation gap. WRONG conclusion: the *annual
volume* isn't the only route to the text. Both laws are at NB as **public-domain standalone
booklets (særtrykk)**, digitised, EVERYWHERE-access, fetchable via the same ALTO endpoint as the
harvest (kjøpsloven digibok `2012050708164`; rettsgebyr `2012083008131`). Norwegian statutory text
is public-domain by statute (åndsverkloven §14) regardless of the container's copyright flag, so
`api.nb.no/catalog/v1` full-text/booklet search is a general fallback for any hole-year law. Caveat:
a booklet is a **mid-life SNAPSHOT** ("Ajourført senest …"), not enactment — record its version
boundary as `base_as_of`, replay only amendments dated ≥ it, and refine G3 to police only
post-snapshot amendments (a pre-snapshot amendment legitimately makes base == current). See done.md
2026-08-12. Meta-point: same pattern as every other "hard wall" here — the wall was in the framing.

## 0. Meta-lesson: when a number looks bad, suspect the METRIC first
The eval harness had *four* separate bugs that made good reconstruction look bad. Every
time we chased "the reconstruction/OCR is the problem" we were wrong; the fix was in the
scorer. **Diagnose the measurement before diagnosing the pipeline.** And **measure before
building** — the data-driven loss breakdown found the real lever (block truncation, +82
provisions) after we'd guessed wrong twice.

## 1. The "0.39 ceiling / OCR too lossy" blocker was WRONG
The original `BLOCKER.md` said pre-2001 was capped at ~0.39 because OCR is too lossy.
Reality: OCR is *clean*; the gap was the **2001 cliff** — the LTI dump (`data/lti/`, 2001+)
has neither pre-2001 enactment bases NOR the pre-2001 amendment stream. Fix = harvest the
full NB gazette (`source/scrape/harvest_lovtidend.py`). Convergence went 0.097 → 0.344.
Don't trust the old ceiling.

## 2. Low point-in-time scores were a TRUTH-PARSER artifact, not OCR (biggest trap)
We saw point-in-time 0/265 at 2001 and concluded "it's OCR." **Wrong.** The truth parser
`source/eval/lovdata_html.py` kept the `§ N-M` heading number and left `&#xa0;` undecoded,
so `metrics.normalize` injected spurious `1 2` / `xa0` tokens and demoted correct
provisions below 0.98. **Objective test that proves it:** never-amended `base` (pure OCR)
exact-match count vs the gate parser = 81, vs the truth parser = 43 → 69 (drop `§` heading)
→ 81 (decode entities). **Always align the truth parser to the gate's `current_provisions`
representation before interpreting any point-in-time number.**

## 3. Other eval-harness bugs we fixed (all made good reconstruction look bad)
- **`autojunk=True`** in `metrics.similarity`: difflib's speed heuristic silently collapses
  long-provision similarity toward 0. Fixed to `autojunk=False`. (Not a loosening — a
  correctness fix.)
- **`gate.current_provisions`** used a regex that split on every in-body `§ N`, inventing
  PHANTOM provisions from cross-references (tjenesteloven 33 vs 29 real) and truncating
  real ones → understated convergence for *every* law. Fixed by structural (`data-name`)
  parsing, same as the base.
- **G3 threshold** was `≥0.98`, which false-tripped on honestly barely-amended provisions
  (vphl §5-10: enactment `50 000` vs current `100 000`, 0.9974 similar). Tightened to
  `≥0.999`. **Near-identity ≠ contamination.**

## 4. OCR is a MINOR pre-2001 limiter — we tested this, don't re-litigate it
We ran BOTH a deterministic speller (LTI-lexicon edit-1) and an LLM pass (gpt-4o-mini,
constrained, cached) on the aksjeloven base, evaluated on **held-out point-in-time**. Both
were **safe but weak** (+2 / +3 @≥0.98). The residual on failing "never-amended" provisions
is REAL missing amendments (`skifteretten→tingretten` 2002 court reform; wording changes),
extraction artifacts (leaked page numbers), and *concentrated* OCR (the `ö`-for-`o` split
on `generalforsamlingen`). **Do NOT invest in OCR/LLM correction or multimodal re-OCR** —
low ceiling. The pre-2001 lever is **amendment coverage** (name→datokode + omnibus +
blanket-terminology acts) — see `todo.md`.

## 5. "Name→datokode is the top lever" was only PARTLY right
The marquee dev laws (avtaleloven, aksjeloven) are NOT mainly name-cited; their pre-2001
amendments are genuinely sparse (aksjeloven is a 1997 law; pre-1997 aksje-amendments target
the *1976* law `1976-06-04-59`) OR come via omnibus/blanket acts. Don't over-invest in the
name map alone; the missing changes are often **blanket terminology reforms** (a general law
renames a term across all statutes) that aren't per-provision amendments at all.

## 6. Errors CLUSTER — single-type fixes barely move the ≥0.98 count
Provisions usually have several independent errors, so fixing one class (ö→o, or an edit-1
speller) rarely tips a provision over the strict 0.98 bar (e.g. ö-fold = +0 on convergence
exact, +2 on held-out point-in-time). **Judge OCR-side fixes on mean similarity and ≥0.90,
not just ≥0.98.** And **`TAU=0.98` is OCR-hostile** — for OCR-sourced (pre-2001) laws use an
OCR-calibrated threshold (~0.90) and report mean+distribution (per `evaluation.md`).

## 7. Anti-gaming is real and a subagent already violated it — guard it
- **NEVER read the answer key (`data/current/`) in the base-build or reconstruction path.**
  A subagent added `_drop_uncertifiable` that read the current dump to dodge G3; it was
  caught and reverted. The G1/G2/G3 guards scan the RECON path (`pipeline.py`, `replay.py`,
  `ledd.py`, `amendments.py`); keep ALL answer-key access inside the eval harness only.
- **LTI files (`data/lti/nl-*.xml`) share the `nl-<datokode>.xml` naming with the answer
  key**, so G1 can't tell them apart by filename. Any LTI reading must stay OFFLINE
  (build-time scripts under `source/scrape/`), never inside a RECON module. See how
  `rederive_blocks.py` writes a derived file that `amendments.py` reads.
- **LLM recall risk**: these are famous laws the model has memorized. A text-only LLM "OCR
  fix" can recall *current* text and corrupt point-in-time. Evaluate ANY correction/LLM
  method on **held-out point-in-time** (the discriminator: genuine fixes help past dates;
  recall/modernization helps convergence but not/​hurts point-in-time), never on
  convergence-to-current. Verified: a *constrained* LLM gated on held-out is safe here.

## 8. Verify subagent claims independently
Subagents this session produced (a) the answer-key hack above and (b) an over-claimed "it's
OCR" reading. Both needed skeptical, independent verification. Re-run the gate yourself and
spot-check faithfulness (not coincidental token overlap) before trusting a subagent result.

## 9. Held-out discipline
Point-in-time (Lovdata Pro versions in `data/ground_truth/`) is the TEST set. Diagnose the
*metric's behavior* freely, but never tune the pipeline to fix specific held-out provisions.

## 10. Operational notes for point-in-time / LLM work
- **Ground-truth download** (Claude-in-Chrome): whole-document URL is
  `#document/HIST/lov/<datokode>-<YYYYMMDD>/*` (the date MUST be an exact version boundary —
  arbitrary dates redirect to current). Toolbar **Last ned → HTML** (find the button by
  ref, not coordinates — the `/*` view defeats blind clicks). Files land in Chrome's
  download folder (a local `gt_incoming` folder mapped into the sandbox);
  move them to `data/ground_truth/<datokode>/<date>.html` (gitignored; only `index.csv`
  tracked). `lovdata_html.parse_file` parses them.
- **OpenAI key**: `OpenAI()` reads `OPENAI_API_KEY` from the environment.
  An LLM-extraction helper package is used (pip install -e; not installed in the
  sandbox venv by default). The venv's `wordfreq` is broken (a conflicting `locate`
  package) — build lexicons from LTI instead.
- **Concurrent sessions**: this is a SHARED repo; another session was active this session
  (rebuilt some bases, byte-identical). Stage files by name, never `git add -A`.
