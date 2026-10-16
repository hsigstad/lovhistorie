"""Decisive test: are the margin-mode GLOBAL accepts CORRECT at held-out PAST dates, or today-overfits?
For each accepted (law, para), score reconstruct ON vs OFF against every PAST gold version where the
op is in force. Classify each as improved / clobbered / neutral -> the misplacement rate (pre-committed
criterion: accept only if past-gold correctness >= 90%, i.e. misplacement < 10%)."""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.parse import pipeline, ledd_apply
from source.eval import ground_truth, metrics, gate
from source.eval import ledd_global_fit as F

ACCEPTS = ["1981-05-22-25", "2003-06-06-39", "1998-07-17-56", "2003-12-19-124", "2003-03-14-15"]


def recon_para(law, date, resolver, para):
    orig = ledd_apply.make_fallback
    ledd_apply.make_fallback = (lambda tl: resolver) if resolver else (lambda tl: (lambda *a, **k: None))
    try:
        return pipeline.reconstruct(law, date)[0].get(para, "")
    finally:
        ledd_apply.make_fallback = orig


rows = []
for dk in ACCEPTS:
    law = "lov/" + dk
    tau = gate.TAU_OCR if pipeline.is_ocr_base(law) else gate.TAU
    r = F.make_global_resolver(law, dk, mode="margin", delta=0.05)
    accepted, fits = F.fit(law, dk, mode="margin", delta=0.05)
    acc_paras = [f.para for f in fits if f.accepted]
    gts = dict(ground_truth.versions_for(dk))
    for para in acc_paras:
        fit = next(f for f in fits if f.para == para)
        best = fit.leaves[0][1]
        second = fit.leaves[1][1] if len(fit.leaves) > 1 else None
        print("\n== %s %s  off=%.3f best_today=%.3f second=%s" %
              (dk, para, fit.off_sim, best, ("%.3f" % second if second is not None else "-")))
        any_gold = False
        for date in sorted(gts):
            gold = gts[date]
            if para not in gold:
                continue
            off = recon_para(law, date, None, para)
            on = recon_para(law, date, r, para)
            if off == on:
                continue                       # op not in force at this date, or no effect
            any_gold = True
            s_off = metrics.similarity(off, gold[para])
            s_on = metrics.similarity(on, gold[para])
            verdict = "IMPROVED" if s_on > s_off + 1e-4 else ("CLOBBER" if s_on < s_off - 1e-4 else "neutral")
            rows.append((dk, para, date, s_off, s_on, verdict))
            print("   %s  off=%.3f on=%.3f  %s" % (date, s_off, s_on, verdict))
        if not any_gold:
            print("   (no past gold where the op changes this provision)")

print("\n==== VERDICT TALLY ====")
imp = sum(1 for *_ , v in rows if v == "IMPROVED")
clb = sum(1 for *_ , v in rows if v == "CLOBBER")
neu = sum(1 for *_ , v in rows if v == "neutral")
n = len(rows)
print("scored on/off-differing past-gold cells: %d  improved=%d clobber=%d neutral=%d" % (n, imp, clb, neu))
if n:
    print("misplacement (clobber) rate = %.0f%%  (criterion: <10%%)" % (100 * clb / n))
