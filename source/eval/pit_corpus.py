"""Corpus-wide point-in-time report against the 2005 Lovdata-CD gold.

INTENT: make the DELIVERABLE legible for collaborators. `status._point_in_time` scores only the 9
    dev laws; this scores EVERY law for which we extracted 2005 gold (data/ground_truth/2005/<dk>.json,
    built by scrape.build_gt_lovdata_cd.build_corpus), so a consumer can see, per law, how faithfully we
    reconstruct the 2005 state and how much of the law the (incomplete) NCC CD actually covers.

SCORING (honest to both sides): for each law we score reconstruct(law, as_of=2005-12-31) against the gold
    ONLY over provisions where the gold carries a FULL body (not a title-only TOC heading) and which exist
    in the current statutory set. This avoids the two confounds that made a single completeness number
    misleading: (a) NCC body-drops and (b) provisions ADDED after 2005 both show up as "gold missing",
    and scoring a reconstruction against missing gold would unfairly penalise it. We therefore report
    `fidelity` (mean char-similarity over checkable provisions) separately from `coverage` (how much of
    the law the CD gold even contains). OCR-base laws are scored at the OCR-calibrated tau, like the gate.

OUTPUT: build/eval/pit_2005_corpus.csv (per law) + a printed aggregate. No LLM, no answer key beyond the
    public-domain/NLOD 2005 gold. Run: python -m source.eval.pit_corpus
"""
from __future__ import annotations
import csv
import glob
import json
import statistics
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.eval import gate, metrics            # noqa: E402
from source.llm.extract_cd import _is_title_only  # noqa: E402
from source.parse import pipeline                # noqa: E402

GOLD_DIR = _REPO / "data" / "ground_truth" / "2005"
OUT_CSV = _REPO / "build" / "eval" / "pit_2005_corpus.csv"
MIN_CHECKABLE = 5          # fewer full-body gold provisions than this -> not a meaningful oracle for the law


def _law_rows():
    for f in sorted(glob.glob(str(GOLD_DIR / "*.json"))):
        dk = Path(f).stem
        if dk in ("corpus_manifest",) or not dk[0].isdigit():
            continue
        yield dk, f


def score_law(dk: str, gold_path: str):
    """Return a per-law record, or None if not scoreable (no current text / too few checkable provisions)."""
    try:
        gold = json.load(open(gold_path, encoding="utf-8"))
        cur = gate.current_provisions(dk)
    except Exception:
        return None
    if not cur or not gold:
        return None
    ocr = pipeline.is_ocr_base("lov/" + dk)
    tau = gate.TAU_OCR if ocr else gate.TAU
    statutory = [p for p in cur if not metrics.is_convention_annex(p)]
    in_gold = [p for p in statutory if p in gold]
    checkable = [p for p in in_gold if not _is_title_only(gold[p])]   # gold has a real body here
    if len(checkable) < MIN_CHECKABLE:
        return None
    try:
        recon = pipeline.reconstruct("lov/" + dk, "2005-12-31")[0]
    except Exception:
        return None
    n_recon = sum(1 for p in checkable if recon.get(p))
    recon_cov = n_recon / len(checkable)
    sims = [metrics.similarity(recon.get(p, ""), gold[p]) for p in checkable]
    return {
        "datokode": dk,
        "ocr_base": int(ocr),
        "n_statutory": len(statutory),
        "n_gold": len(in_gold),
        "n_checkable": len(checkable),
        "recon_cov": round(recon_cov, 3),         # fraction of checkable provisions the pipeline reconstructs
        "reconstructable": int(recon_cov >= 0.5),  # the pipeline actually has a base/stream for this law
        "coverage": round(len(in_gold) / len(statutory), 3) if statutory else 0.0,
        "fidelity_mean": round(statistics.mean(sims), 3),
        "rate_ge_tau": round(sum(s >= tau for s in sims) / len(sims), 3),
        "tau": tau,
    }


def report(write: bool = True):
    recs = []
    for dk, f in _law_rows():
        r = score_law(dk, f)
        if r:
            recs.append(r)
    recs.sort(key=lambda r: (-r["reconstructable"], -r["fidelity_mean"]))
    if write:
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(recs[0].keys()) if recs else
                               ["datokode", "ocr_base", "n_statutory", "n_gold", "n_checkable",
                                "recon_cov", "reconstructable", "coverage", "fidelity_mean", "rate_ge_tau", "tau"])
            w.writeheader(); w.writerows(recs)
    # The scoreable set splits into laws the reconstruction pipeline actually builds (recon_cov>=0.5) and
    # laws for which no base/stream exists (recon ~empty -> fidelity ~0). Only the former measures FIDELITY;
    # the latter measures the pipeline's RECONSTRUCTION-COVERAGE gap (we now hold more 2005 gold than we
    # can reconstruct). Report them apart so neither number is misread.
    rk = [r for r in recs if r["reconstructable"]]
    print(f"laws with >= {MIN_CHECKABLE} full-body 2005-gold provisions: {len(recs)}  ({sum(r['n_checkable'] for r in recs):,} checkable provisions)")
    print(f"RECONSTRUCTABLE by the current pipeline (recon_cov>=0.5): {len(rk)}  (the rest have no base/stream)")
    if rk:
        fid = [r["fidelity_mean"] for r in rk]
        ocr = [r for r in rk if r["ocr_base"]]
        clean = [r for r in rk if not r["ocr_base"]]
        print(f"\nFIDELITY over the {len(rk)} reconstructable laws (point-in-time @2005, char-sim over full-body gold):")
        print(f"  law-weighted mean {statistics.mean(fid):.3f}  median {statistics.median(fid):.3f}")
        if ocr:
            print(f"  OCR-base   {len(ocr):3d}: mean {statistics.mean([r['fidelity_mean'] for r in ocr]):.3f}")
        if clean:
            print(f"  clean-base {len(clean):3d}: mean {statistics.mean([r['fidelity_mean'] for r in clean]):.3f}")
        for band, lo, hi in [(">=0.90", 0.90, 1.01), ("0.70-0.90", 0.70, 0.90), ("0.50-0.70", 0.50, 0.70), ("<0.50", 0.0, 0.50)]:
            print(f"  laws fidelity {band}: {sum(1 for r in rk if lo <= r['fidelity_mean'] < hi)}")
    if write:
        print(f"\nwrote {OUT_CSV}")
    return recs


if __name__ == "__main__":
    report()
