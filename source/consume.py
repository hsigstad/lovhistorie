"""Consumer API for the reconstructed point-in-time statute panel.

INTENT: give collaborators (Eivind, Sungho, ...) a one-call way to get "law L as it read on date t"
    to join against case / outcome data, plus a catalog of which laws are reliable — so they consume
    the deliverable without reverse-engineering `pipeline.reconstruct` or guessing which laws to trust.
REASONING: a thin, documented wrapper (law_as_of) + a static reliability catalog (catalog/reliable_laws)
    is the lowest-effort unblock for downstream use; it adds no new pipeline logic, only a legible front door.
ASSUMES: the reconstruction pipeline (source.parse.pipeline) and, for the catalog, the 2005 pit report
    (docs/reference/laws_catalog.csv, generated from build/eval/pit_2005_corpus.csv). Read-only consumer layer.

For collaborators (Eivind, Sungho, ...) who want "law L as it read on date t" to join against
case / outcome data. Three entry points:

    catalog()                          -> [{datokode, title, n_provisions, current_fidelity,
                                            current_rate, hist_fidelity_2005, ocr_base}]
    reliable_laws(min_fidelity=0.85)   -> [datokode, ...]      (the laws worth joining against)
    law_as_of(datokode, date)          -> {paragraf_id: text}  (one law at a date; date=None -> latest)

RELIABILITY — two numbers, kept apart (do not collapse):
  - `current_fidelity` (the DEFAULT reliability signal) = char-similarity of reconstruct(law, today) to
    the official current NLOD text, mean over the law's provisions (`current_rate` = fraction >=tau). BROAD:
    we hold this for 328 laws, and it is publishable (NLOD current is public-domain). It measures
    CURRENT-TEXT accuracy. Built by `python -m source.eval.convergence_corpus`.
  - `hist_fidelity_2005` (the honesty caveat, where available) = char-similarity of reconstruct(law,
    2005-12-31) to the independent 2005 Lovdata-CD oracle. This is HISTORICAL point-in-time fidelity and is
    LOWER — current_fidelity OVERSTATES history (the last amendment sets today's text directly; see
    docs/reference/pit_coverage.md). Blank for laws with no 2005 gold.
Use current_fidelity to pick laws; read hist_fidelity_2005 as the discount for deep-historical joins.
The catalog lists the 328 reconstructable laws we can score against today; more are reconstructable but
unvalidated (no current-dump answer key). Laws NOT in the catalog may still reconstruct via law_as_of.

Quickstart:
    from source import consume
    good = consume.reliable_laws(0.85)                      # ~191 laws, strong current-text accuracy
    text = consume.law_as_of("2007-06-29-75", "2014-01-01") # verdipapirhandelloven as of 2014-01-01
    # join to a case: law_as_of(case.law_datokode, case.decision_date)
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

CATALOG = _REPO / "docs" / "reference" / "laws_catalog.csv"
_PIT = _REPO / "build" / "eval" / "pit_2005_corpus.csv"
_CONV = _REPO / "build" / "eval" / "convergence_today_corpus.csv"
_REGISTER = _REPO / "data" / "law_register.jsonl"
_FIELDS = ["datokode", "title", "n_provisions", "current_fidelity",
           "current_rate", "hist_fidelity_2005", "ocr_base"]


def _norm(datokode: str) -> str:
    """Accept '1997-06-13-44' or 'lov/1997-06-13-44' -> 'lov/1997-06-13-44'."""
    dk = datokode.strip()
    return dk if dk.startswith("lov/") else "lov/" + dk


def law_as_of(datokode: str, date: str | None = None) -> dict:
    """{paragraf_id: text} for one law as of `date` (YYYY-MM-DD), or latest if date is None.

    Thin wrapper over source.parse.pipeline.reconstruct (drops the flags tuple). Returns {} if the
    pipeline has no base/stream for the law. Check `catalog()` for which laws are reliable."""
    from source.parse import pipeline
    try:
        provs, _ = pipeline.reconstruct(_norm(datokode), date)
    except Exception:
        return {}
    return provs


def catalog() -> list[dict]:
    """Reconstructable laws scoreable against today, with reliability columns. Reads
    docs/reference/laws_catalog.csv (build it with `python -m source.consume build-catalog`)."""
    if not CATALOG.exists():
        return []
    rows = list(csv.DictReader(open(CATALOG, encoding="utf-8")))
    for r in rows:
        r["ocr_base"] = r.get("ocr_base") == "1"
        r["n_provisions"] = int(r["n_provisions"]) if r.get("n_provisions") else None
        for k in ("current_fidelity", "current_rate", "hist_fidelity_2005"):
            r[k] = float(r[k]) if r.get(k) not in (None, "") else None
    return rows


def reliable_laws(min_fidelity: float = 0.85, metric: str = "current") -> list[str]:
    """Datokodes whose reliability is at least `min_fidelity`. metric='current' (default) uses
    current-text accuracy (reconstruct-vs-today); metric='hist2005' uses the 2005-oracle historical
    fidelity (only the laws with 2005 gold qualify)."""
    key = "current_fidelity" if metric == "current" else "hist_fidelity_2005"
    return [r["datokode"] for r in catalog() if (r.get(key) or 0) >= min_fidelity]


def _titles() -> dict:
    """datokode -> title, from the public law-identity register (validation-side only)."""
    import json
    out = {}
    if _REGISTER.exists():
        for line in open(_REGISTER, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            dk = (d.get("datokode") or "").split("/")[-1]
            if dk:
                out[dk] = d.get("title") or d.get("korttittel") or ""
    return out


def build_catalog():
    """(Re)generate docs/reference/laws_catalog.csv from the today-convergence artifact (primary) +
    register titles + the 2005 pit report (historical caveat column, where available).
    Run `python -m source.eval.convergence_corpus` first (needs build/eval/convergence_today_corpus.csv)."""
    if not _CONV.exists():
        raise SystemExit("run `python -m source.eval.convergence_corpus` first "
                         "(need build/eval/convergence_today_corpus.csv)")
    titles = _titles()
    hist = {}
    if _PIT.exists():
        for r in csv.DictReader(open(_PIT, encoding="utf-8")):
            if r.get("reconstructable") == "1" and r.get("fidelity_mean") not in (None, ""):
                hist[r["datokode"]] = r["fidelity_mean"]
    rows = []
    for r in csv.DictReader(open(_CONV, encoding="utf-8")):
        dk = r["datokode"]
        rows.append({"datokode": dk, "title": titles.get(dk, ""),
                     "n_provisions": r["n_provisions"], "current_fidelity": r["current_fidelity"],
                     "current_rate": r["current_rate"], "hist_fidelity_2005": hist.get(dk, ""),
                     "ocr_base": r["ocr_base"]})
    rows.sort(key=lambda r: -float(r["current_fidelity"]))
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader(); w.writerows(rows)
    nhist = sum(1 for r in rows if r["hist_fidelity_2005"])
    print(f"wrote {CATALOG} ({len(rows)} laws scoreable vs today; {nhist} also have 2005 gold)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build-catalog":
        build_catalog()
    else:
        print(__doc__)
