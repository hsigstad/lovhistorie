"""Generalization screen: does the GLOBAL today-constraint ever find a beneficial pure-ledd
placement, or is today always blind (overwrite-mooted / already-matched)? Run fit() across the
non-OCR reconstructable laws; tally accepts (placements that beat abstain) + decision breakdown.
Uses only the current dump (fit comparator) — no HIST gold needed for the 'does today discriminate'
screen. Any law WITH accepts is then a candidate for past-gold validation."""
import csv
import collections
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.eval import ledd_global_fit as F

rows = list(csv.DictReader(open("docs/reference/laws_catalog.csv")))
laws = [r["datokode"] for r in rows
        if r["reconstructable"].lower() in ("true", "1", "yes")
        and r["ocr_base"].lower() in ("false", "0", "no", "")]

tot = collections.Counter()
accepts = []
t0 = time.time()
for i, dk in enumerate(laws):
    law = "lov/" + dk
    try:
        accepted, fits = F.fit(law, dk, mode="margin", delta=0.05)
    except Exception as e:
        print("  ERR %-16s %s" % (dk, str(e)[:60]))
        tot["ERR"] += 1
        continue
    dec = collections.Counter(f.decision for f in fits)
    for k, v in dec.items():
        tot[k] += v
    tag = ""
    if accepted:
        accepts.append((dk, len(accepted), [f.para for f in fits if f.accepted]))
        tag = "  <== ACCEPTS %d" % len(accepted)
    print("[%2d/%2d] %-16s searched=%2d accepted=%2d %s%s"
          % (i + 1, len(laws), dk, len(fits), len(accepted), dict(dec), tag))

print("\n==== SUMMARY  (%.0fs) ====" % (time.time() - t0))
print("laws=%d  decisions=%s" % (len(laws), dict(tot)))
print("laws WITH accepts:", accepts if accepts else "NONE  -> honest-null generalizes")
