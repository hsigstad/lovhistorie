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

    catalog()                       -> [{datokode, title, reconstructable, fidelity, coverage, ocr_base}]
    reliable_laws(min_fidelity=0.7) -> [datokode, ...]      (the laws worth joining against)
    law_as_of(datokode, date)       -> {paragraf_id: text}  (one law at a date; date=None -> latest)

The reliability columns come from the independent 2005 Lovdata-CD oracle (see docs/reference/
pit_coverage.md): `fidelity` is char-similarity of our 2005 reconstruction to that gold over
full-body provisions, `coverage` is how much of the law the gold even contains, `reconstructable`
is whether the pipeline has a base/stream for the law at all. Laws NOT in the catalog may still be
reconstructable, but we have not validated them.

Quickstart:
    from source import consume
    good = consume.reliable_laws(0.7)                       # laws we reconstruct faithfully
    text = consume.law_as_of("1997-06-13-44", "2005-12-31") # aksjeloven as of 2005-12-31
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
    """Validated laws with reliability flags. Reads docs/reference/laws_catalog.csv (build it with
    `python -m source.consume build-catalog`)."""
    if not CATALOG.exists():
        return []
    rows = list(csv.DictReader(open(CATALOG, encoding="utf-8")))
    for r in rows:
        r["reconstructable"] = r.get("reconstructable") == "1"
        r["ocr_base"] = r.get("ocr_base") == "1"
        for k in ("fidelity", "coverage"):
            r[k] = float(r[k]) if r.get(k) not in (None, "") else None
    return rows


def reliable_laws(min_fidelity: float = 0.7) -> list[str]:
    """Datokodes of reconstructable laws whose 2005-oracle fidelity is at least `min_fidelity`."""
    return [r["datokode"] for r in catalog()
            if r["reconstructable"] and (r["fidelity"] or 0) >= min_fidelity]


def build_catalog():
    """(Re)generate docs/reference/laws_catalog.csv by joining the 2005 pit report with law titles.
    Run `python -m source.eval.pit_corpus` first to refresh build/eval/pit_2005_corpus.csv."""
    from source.scrape.build_gt_lovdata_cd import _current_index
    if not _PIT.exists():
        raise SystemExit("run `python -m source.eval.pit_corpus` first (need build/eval/pit_2005_corpus.csv)")
    titles = {dk: v["title"] for dk, v in _current_index().items()}
    pit = list(csv.DictReader(open(_PIT, encoding="utf-8")))
    rows = [{"datokode": r["datokode"], "title": titles.get(r["datokode"], ""),
             "reconstructable": r["reconstructable"], "fidelity": r["fidelity_mean"],
             "coverage": r["coverage"], "ocr_base": r["ocr_base"]} for r in pit]
    rows.sort(key=lambda r: (-int(r["reconstructable"]), -float(r["fidelity"])))
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["datokode", "title", "reconstructable", "fidelity", "coverage", "ocr_base"])
        w.writeheader(); w.writerows(rows)
    print(f"wrote {CATALOG} ({len(rows)} laws, {sum(int(r['reconstructable']) for r in rows)} reconstructable)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build-catalog":
        build_catalog()
    else:
        print(__doc__)
