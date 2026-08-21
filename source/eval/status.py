"""Emit the current evaluation numbers as a committed, site-readable snapshot.

INTENT: `python -m source.eval.status` runs the SAME guards + convergence as the
    completion gate and writes docs/reference/status.json (machine-readable) + docs/reference/status.md
    (human page). The site headlines status.json, so "the number everyone sees" is a
    versioned artifact refreshed by one command — never a hand-typed figure that rots.
REASONING: the gate (source.eval.gate) is the source of truth for the metric; this
    module reuses its functions verbatim, so the published number can never drift from
    the gate's verdict. Requires the answer-key dump locally (same prerequisite as the
    gate); without it, convergence can't be computed and the existing snapshot is left
    untouched (exit 1) rather than overwritten with zeros.
ASSUMES: run from the repo root with the current NLOD dump present (data/current or
    $LOVHISTORIE_CURRENT_DIR).
"""
from __future__ import annotations

import datetime as _dt
import json
import statistics
import sys
from pathlib import Path

from source.eval import gate, ground_truth, harness
from source.parse import pipeline

ROOT = Path(__file__).resolve().parents[2]
STATUS_JSON = ROOT / "docs" / "reference" / "status.json"
STATUS_MD = ROOT / "docs" / "reference" / "status.md"

# datokode -> common law name, for readable per-law reporting (display only).
LAW_NAMES = {
    "1918-05-31-4": "avtaleloven",
    "1959-10-23-3": "oreigningslova",
    "1979-05-18-18": "foreldelsesloven",
    "1982-12-17-86": "rettsgebyrloven",
    "1986-06-20-35": "mesterbrevloven",
    "1988-05-13-27": "kjøpsloven",
    "1997-06-13-44": "aksjeloven",
    "2007-06-29-75": "verdipapirhandelloven",
    "2009-06-19-103": "tjenesteloven",
}


def _point_in_time():
    """Score reconstruction at HELD-OUT past dates vs the Lovdata-Pro ground truth — the
    DELIVERABLE metric (evaluation.md check 2), the thing convergence is only a proxy for.

    Uses the same scope + per-source τ as the gate (annexes out of scope; OCR-calibrated τ
    for OCR bases). Runs over any dev law that has ground-truth versions on disk
    (data/ground_truth/, encumbered + gitignored) — returns ([], {}) where none is present,
    exactly like convergence returns nothing without the current dump. NOTE the harness scores
    over the CURRENT provision set, so a provision not yet enacted at a past date is scored as
    correctly-absent (both empty) — the honest reading is the mean-similarity column, reported
    alongside the ≥τ rate. Repealed-stub scoping is NOT applied here (a repeal is date-dependent:
    a §repealed in 2019 was live at a 2001 date)."""
    recon = lambda dk, as_of: pipeline.reconstruct("lov/" + dk, as_of)[0]  # noqa: E731
    per, all_rates, all_means = [], [], []
    for _, dk in gate.DEV_LAWS:
        gt = ground_truth.versions_for(dk)
        if not gt:
            continue
        cur = gate.current_provisions(dk)
        if cur is None:
            continue
        sc = harness.evaluate_law(dk, recon, cur, gt, tau=gate.TAU, tau_ocr=gate.TAU_OCR,
                                  ocr=pipeline.is_ocr_base("lov/" + dk))
        per.append({
            "datokode": dk, "law": LAW_NAMES.get(dk, dk), "tau": sc.tau,
            "n_provisions": sc.n_provisions,
            "dates": [{"date": d, "rate": r, "mean": m} for d, r, m, _ in sc.pit],
        })
        all_rates += [r for _, r, _, _ in sc.pit]
        all_means += [m for _, _, m, _ in sc.pit]
    summary = {}
    if all_rates:
        summary = {"n_versions": len(all_rates),
                   "rate_mean": round(statistics.mean(all_rates), 4),
                   "similarity_mean": round(statistics.mean(all_means), 4)}
    return per, summary


def collect() -> dict:
    """Run the gate's guards + convergence and package the numbers."""
    g1 = gate.guard_no_answer_key_import()
    g2 = gate.guard_runs_isolated()
    g3 = gate.guard_base_integrity()
    frac, matched, total, per_law, annex, strict, strict_frac, repealed = gate.convergence()
    pit_per, pit_summary = _point_in_time()
    guards_ok = not (g1 or g2 or g3)
    passed = guards_ok and frac >= gate.THRESHOLD
    return {
        "point_in_time": pit_per,
        "point_in_time_summary": pit_summary,
        "as_of": _dt.date.today().isoformat(),
        "convergence": round(frac, 4),            # OCR-calibrated (headline)
        "convergence_strict": round(strict_frac, 4),  # strict τ=0.98 for all laws
        "matched": matched,
        "matched_strict": strict,
        "total": total,                           # statutory denominator (annexes + repealed stubs excluded)
        "annex_out_of_scope": annex,
        "repealed_out_of_scope": repealed,
        "tau": gate.TAU,
        "tau_ocr": gate.TAU_OCR,
        "threshold": gate.THRESHOLD,
        "guards_pass": guards_ok,
        "guards": {"G1": not g1, "G2": not g2, "G3": not g3},
        "verdict": "PASS" if passed else "IN PROGRESS",
        "n_dev_laws": len(gate.DEV_LAWS),
        "per_law": [
            {"datokode": dk, "law": LAW_NAMES.get(dk, dk),
             "matched": m, "total": t, "tau": tau, "annex": a}
            for dk, m, t, a, tau in per_law
        ],
    }


def render_md(d: dict) -> str:
    pct = f"{d['convergence'] * 100:.1f}%"
    pct_strict = f"{d['convergence_strict'] * 100:.1f}%"
    thr = f"{d['threshold'] * 100:.0f}%"
    tau = f"{d['tau'] * 100:.0f}%"
    tau_ocr = f"{d['tau_ocr'] * 100:.0f}%"
    guards = "PASS" if d["guards_pass"] else "FAIL"
    rows = []
    for r in d["per_law"]:
        if r["total"]:
            tcell = f"@{int(round(r['tau'] * 100))}%" if r.get("tau") else ""
            acell = f" (+{r['annex']} annex)" if r.get("annex") else ""
            cell = f"{r['matched']}/{r['total']} {tcell}{acell}"
        else:
            cell = "current text absent"
        rows.append(f"| {r['law']} (`{r['datokode']}`) | {cell} |")
    table = "\n".join(rows)

    # Point-in-time (deliverable) section — only when ground truth is present on disk.
    pit_summary = d.get("point_in_time_summary") or {}
    if pit_summary:
        prows = []
        for r in d["point_in_time"]:
            for v in r["dates"]:
                prows.append(f"| {r['law']} (`{r['datokode']}`) | {v['date']} | "
                             f"{v['rate'] * 100:.1f}% | {v['mean']:.3f} |")
        pit_md = f"""## Point-in-time accuracy — the deliverable

The decisive metric (evaluation.md check 2): reconstruct each law **as it read at a past
date** and score against the held-out **Lovdata Pro** historical version — text the pipeline
is scored on but never tuned on. Reported as the ≥τ rate **and** the mean character-similarity
(the honest reading, since the score runs over the current provision set).

**Point-in-time μ: {pit_summary['similarity_mean']:.3f} similarity** &nbsp;·&nbsp;
{pit_summary['rate_mean'] * 100:.1f}% at ≥τ &nbsp;·&nbsp; over {pit_summary['n_versions']}
held-out (law × date) versions. Point-in-time **tracks convergence** — the engine reconstructs
past states about as well as the current one, so convergence is a validated proxy (no
date-specific failure); the residual is the same ledd / OCR / capture tail.

| Law | As of | ≥τ rate | mean similarity |
|---|---|---|---|
{chr(10).join(prows)}

"""
    else:
        pit_md = ("## Point-in-time accuracy — the deliverable\n\n"
                  "The decisive metric (evaluation.md check 2) requires held-out Lovdata Pro "
                  "historical versions in `data/ground_truth/` (encumbered, local-only). None "
                  "present on this machine — download per `docs/reference/ground_truth.md` to populate "
                  "this section.\n\n")

    annex_note = ""
    if d.get("annex_out_of_scope"):
        annex_note = (f"\n\n**Scope.** {d['annex_out_of_scope']} bundled treaty-convention "
                      f"articles (e.g. the CISG in kjøpsloven), incorporated *by reference* and "
                      f"never published as a Norsk Lovtidend amendment, are held out as "
                      f"**out-of-scope** — un-reconstructable from the pipeline's inputs by "
                      f"construction — and reported separately, never counted as failures.")
    if d.get("repealed_out_of_scope"):
        annex_note += (f" A further {d['repealed_out_of_scope']} **repealed-provision stubs** — "
                       f"slots NLOD keeps with an '(Opphevet)' placeholder and an editorial repeal "
                       f"note after the provision is repealed — are likewise out-of-scope: the "
                       f"reconstruction correctly drops the repealed provision, so there is no "
                       f"statutory text to match, only Lovdata's annotation.")
    return f"""<!-- GENERATED by `python -m source.eval.status` — do not edit by hand. -->
# Performance

**Convergence: {pct}** (OCR-calibrated) &nbsp;·&nbsp; {d['matched']}/{d['total']}
statutory dev-set provisions &nbsp;·&nbsp; **{pct_strict}** at the strict ≥{tau} bar
&nbsp;·&nbsp; anti-gaming guards **{guards}** &nbsp;·&nbsp; as of {d['as_of']}.

## What this number means

*Convergence* is the share of provisions in the **current** official statute text
that our reconstruction reproduces to high character-identity — where the
reconstruction is built **only** from the original enactment plus every amendment
replayed from **Norsk Lovtidend**, and is **never shown the current text**. In plain
terms: *rebuilding each law from scratch out of its gazette history, how often do we
land back exactly on today's official wording?*

It is measured over a fixed **{d['n_dev_laws']}-law development set** ({d['total']}
statutory provisions), with the denominator being *every* statutory current provision
— so "reconstruct only the easy provisions" cannot inflate the score. The pass bar is
**≥{thr}**.

**Two thresholds, both reported.** A provision counts as reproduced at **≥{tau}**
character-identity for laws whose base is clean machine-readable text (2001+), and at
an **OCR-calibrated ≥{tau_ocr}** for the older laws whose base is OCR'd from scanned
gazettes/booklets — a bar *derived* from the pure-OCR error floor on never-amended
provisions (where any gap is OCR noise, not a reconstruction mistake), not chosen to
flatter the number. The strict all-laws-≥{tau} figure ({pct_strict}) is always shown
alongside so the calibration is transparent.{annex_note}

**Why it is trustworthy.** Three mechanical anti-gaming guards run alongside the
number and must all pass for it to count (they are **{guards}** now):

- **G1 no-answer-key-import** — the reconstruction code provably cannot read the
  current text (enforced by AST, not trust).
- **G2 runs-isolated** — with the current text physically removed, reconstruction
  still produces output, proving it does not depend on the answer.
- **G3 base-integrity** — an amended provision's enactment base must *differ* from
  today's text, so no law is silently seeded from the answer.

**Convergence is the dev proxy, not the final bar.** Reproducing *today's* text is
necessary but not sufficient (two errors can cancel). The deliverable metric is
**point-in-time accuracy** against held-out Lovdata Pro historical versions — the law
as it read at a *past* date, which the pipeline is scored on but never tuned on. See
[Evaluation](evaluation.html) and [Goal](goal.html).

{pit_md}## Per-law breakdown

Provisions reproduced at each law's threshold (`@98%` clean-base, `@90%` OCR-base);
`annex` = treaty-convention articles held out of scope.

| Law | Converged |
|---|---|
{table}

## Refresh this number

```
python -m source.eval.status     # recompute from the local data, rewrite this page
```

Requires the current NLOD dump locally (`data/current/` or `$LOVHISTORIE_CURRENT_DIR`).
`bash build.sh deploy` runs this automatically when the data is present, so the
published site always carries the latest figure.
"""


def main() -> int:
    d = collect()
    if not d["total"]:
        print("status: no current-text data found — snapshot left unchanged.",
              file=sys.stderr)
        print("        place the NLOD dump at data/current/ or set "
              "$LOVHISTORIE_CURRENT_DIR.", file=sys.stderr)
        return 1
    STATUS_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    STATUS_MD.write_text(render_md(d), encoding="utf-8")
    print(f"status: convergence {d['convergence'] * 100:.1f}% "
          f"({d['matched']}/{d['total']}), guards "
          f"{'PASS' if d['guards_pass'] else 'FAIL'} — wrote "
          f"{STATUS_JSON.name} + {STATUS_MD.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
