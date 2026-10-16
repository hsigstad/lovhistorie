"""Strict-mode (unique-today-reproduction + floor) across the non-OCR corpus, then validate every
strict-accept against held-out PAST gold. Answers: does the STRICT global gate yield accepts, and
are they correct at past dates (misplacement < 10%)?"""
import csv
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.parse import pipeline, ledd_apply
from source.eval import ground_truth, metrics
from source.eval import ledd_global_fit as F

laws = [r["datokode"] for r in csv.DictReader(open("docs/reference/laws_catalog.csv"))
        if r["reconstructable"].lower() in ("true", "1", "yes")
        and r["ocr_base"].lower() in ("false", "0", "no", "")]


def recon_para(law, date, resolver, para):
    orig = ledd_apply.make_fallback
    ledd_apply.make_fallback = (lambda tl: resolver) if resolver else (lambda tl: (lambda *a, **k: None))
    try:
        return pipeline.reconstruct(law, date)[0].get(para, "")
    finally:
        ledd_apply.make_fallback = orig


all_accepts = []
for dk in laws:
    law = "lov/" + dk
    accepted, fits = F.fit(law, dk, mode="strict")
    for f in fits:
        if f.accepted:
            all_accepts.append((dk, f.para, f))

print("STRICT accepts across %d laws: %d" % (len(laws), len(all_accepts)))
rows = []
for dk, para, f in all_accepts:
    law = "lov/" + dk
    r = F.make_global_resolver(law, dk, mode="strict")
    gts = dict(ground_truth.versions_for(dk))
    print("\n== %s %s off=%.3f best_today=%.3f" % (dk, para, f.off_sim, f.leaves[0][1]))
    used = False
    for date in sorted(gts):
        gold = gts[date]
        if para not in gold:
            continue
        off = recon_para(law, date, None, para)
        on = recon_para(law, date, r, para)
        if off == on:
            continue
        used = True
        s_off = metrics.similarity(off, gold[para])
        s_on = metrics.similarity(on, gold[para])
        v = "IMPROVED" if s_on > s_off + 1e-4 else ("CLOBBER" if s_on < s_off - 1e-4 else "neutral")
        rows.append(v)
        print("   %s off=%.3f on=%.3f %s" % (date, s_off, s_on, v))
    if not used:
        print("   (no past gold where the op changes this provision)")

print("\n==== STRICT VERDICT ====")
imp = rows.count("IMPROVED"); clb = rows.count("CLOBBER"); neu = rows.count("neutral")
print("validated cells=%d improved=%d clobber=%d neutral=%d" % (len(rows), imp, clb, neu))
if rows:
    print("misplacement = %.0f%%" % (100 * clb / len(rows)))
