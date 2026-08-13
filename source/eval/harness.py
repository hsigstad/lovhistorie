"""Eval harness: score any reconstruction pipeline against ground truth.

INTENT: be the reward signal for autonomous work (docs/goal.md). Given a
    pipeline `reconstruct(datokode, as_of)`, produce the metrics in
    docs/evaluation.md — convergence-to-current, point-in-time accuracy vs the
    held-out Lovdata Pro set, and OCR fidelity — with per-provision flags and the
    full distribution (not just the mean).
REASONING: the pipeline is decoupled behind a small interface so the harness is
    ready before the pipeline is; a trivial baseline (return current text at every
    date) is included as a self-test — it must score HIGH convergence but LOW
    point-in-time, exactly the naive-baseline failure the real pipeline must beat.
ASSUMES: `reconstruct(datokode, as_of)` returns {paragraf_id: text}; as_of=None
    means "current". Current NLOD provisions are supplied per law.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from source.eval import metrics


# ---- the pipeline interface (implemented in Phase 1; scored here) ---------- #
# def reconstruct(datokode: str, as_of: str | None) -> dict[str, str]: ...


def provision_list(current_text):
    """Ordered list of paragraf ids from the current text's body (dedup, in order)."""
    seen, order = set(), []
    for m in re.finditer(r"§\s*(\d+(?:-\d+)?[a-z]?)", current_text):
        p = "§" + m.group(1)
        if p not in seen:
            seen.add(p)
            order.append(p)
    return order


def _score_pair(recon: dict, truth: dict, order, tau):
    """Per-provision similarity of recon vs truth; returns (rate, mean, flags)."""
    sims, flags = [], []
    for p in order:
        s = metrics.similarity(recon.get(p, ""), truth.get(p, ""))
        sims.append(s)
        if s < tau:
            flags.append((p, round(s, 3)))
    rate = sum(1 for s in sims if s >= tau) / len(sims) if sims else 0.0
    return rate, (statistics.mean(sims) if sims else 0.0), sims, flags


@dataclass
class LawScore:
    datokode: str
    convergence_rate: float = 0.0
    convergence_mean: float = 0.0
    convergence_flags: list = field(default_factory=list)
    pit: list = field(default_factory=list)   # [(date, rate, mean, flags)]
    n_provisions: int = 0                       # STATUTORY provisions scored
    n_annex: int = 0                            # convention annexes held out of scope
    tau: float = 0.98                           # the threshold actually applied


def evaluate_law(datokode, reconstruct, current_provs, gt_versions=(),
                 tau=0.98, tau_ocr=None, ocr=False):
    """Score one law. current_provs / gt_versions values are {para: text}.

    Applies the SAME two eval-scope rules as the convergence gate so the point-in-time
    (deliverable) number stays consistent with convergence:
    - convention-annex articles (metrics.is_convention_annex) are held OUT of scope;
    - OCR-based laws use the OCR-calibrated `tau_ocr` (pass ocr=True), clean-LTI laws
      use the strict `tau`. Callers resolve `ocr` via pipeline.is_ocr_base.
    """
    eff_tau = tau_ocr if (ocr and tau_ocr is not None) else tau
    order = [p for p in current_provs if not metrics.is_convention_annex(p)]
    sc = LawScore(datokode=datokode, n_provisions=len(order),
                  n_annex=len(current_provs) - len(order), tau=eff_tau)
    # 1. convergence: reconstruct "current" and compare to authoritative current
    recon_cur = reconstruct(datokode, None)
    sc.convergence_rate, sc.convergence_mean, _, sc.convergence_flags = _score_pair(
        recon_cur, current_provs, order, eff_tau)
    # 2. point-in-time vs the held-out ground truth
    for date, gt in gt_versions:
        r, m, _, fl = _score_pair(reconstruct(datokode, date), gt, order, eff_tau)
        sc.pit.append((date, round(r, 3), round(m, 3), fl))
    return sc


def evaluate_corpus(datokoder, reconstruct, current_of, gt_of,
                    tau=0.98, tau_ocr=None, ocr_of=None):
    """Aggregate over laws. current_of/gt_of are callables datokode->{para:text} /
    datokode->[(date,{para:text})]. `ocr_of` (datokode->bool, e.g. pipeline.is_ocr_base)
    selects the OCR-calibrated τ per law; omit it to score every law at the strict `tau`.
    Returns (per-law scores, summary dict)."""
    scores = [evaluate_law(dk, reconstruct, current_of(dk), gt_of(dk),
                           tau=tau, tau_ocr=tau_ocr,
                           ocr=bool(ocr_of(dk)) if ocr_of else False)
              for dk in datokoder]
    conv = [s.convergence_rate for s in scores]
    pit = [rate for s in scores for (_, rate, _, _) in s.pit]
    summary = {
        "n_laws": len(scores),
        "convergence_rate_mean": round(statistics.mean(conv), 4) if conv else None,
        "point_in_time_rate_mean": round(statistics.mean(pit), 4) if pit else None,
        "laws_below_bar": [s.datokode for s in scores if s.convergence_rate < s.tau],
        "annex_out_of_scope": sum(s.n_annex for s in scores),
        "tau": tau,
        "tau_ocr": tau_ocr,
    }
    return scores, summary


def print_scorecard(scores, summary):
    print(f"{'law':22}{'conv':>7}{'convμ':>8}  point-in-time (rate per date)")
    for s in scores:
        pit = " ".join(f"{d}:{r}" for d, r, _, _ in s.pit) or "(no ground truth)"
        print(f"{s.datokode:22}{s.convergence_rate:7.3f}{s.convergence_mean:8.3f}  {pit}")
    print(f"\nlaws={summary['n_laws']}  convergence μ={summary['convergence_rate_mean']} "
          f"point-in-time μ={summary['point_in_time_rate_mean']}  (bar τ={summary['tau']})")


if __name__ == "__main__":
    # Self-test: a naive baseline that returns the current text at EVERY date.
    # Expected: convergence ~1.0 (trivially), point-in-time LOW where the law
    # changed — the harness must expose that gap.
    current = {"§1": "kongen kan bestemme at ...", "§2": "kongen tildeler mesterbrev ..."}
    gt = [("2005-01-01", {"§1": "kongen kan bestemme at ...", "§2": "OLD 2005 wording ..."})]
    baseline = lambda dk, as_of: current  # noqa: E731
    sc = evaluate_law("SELFTEST", baseline, current, gt)
    print("convergence:", round(sc.convergence_rate, 3),
          "| point-in-time 2005:", sc.pit[0][1], "(should be < 1.0 — §2 changed)")
