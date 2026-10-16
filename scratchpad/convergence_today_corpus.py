"""Corpus-wide quality against TODAY (Henrik: measure vs today's laws, not the 2005 oracle).
For every reconstructable law with a current-dump answer key, score reconstruct(law, today) vs the
current text. Reports per-law mean char-sim + rate>=tau, and the corpus distribution. This is
CURRENT-TEXT accuracy (available for 328 laws), distinct from historical point-in-time fidelity
(only validatable where we hold past gold)."""
import json
import sys
import statistics
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.parse import pipeline
from source.eval import gate, metrics

laws = json.loads(open(_REPO / "scratchpad" / "scoreable_laws.json").read())
out = []
for i, law in enumerate(laws):
    dk = law.split("/")[-1]
    try:
        cur = gate.current_provisions(dk)
        recon = pipeline.reconstruct(law, None)[0]
    except Exception as e:
        continue
    tau = gate.TAU_OCR if pipeline.is_ocr_base(law) else gate.TAU
    keys = [p for p in cur if cur.get(p)]
    if not keys:
        continue
    sims = [metrics.similarity(recon.get(p, ""), cur.get(p, "")) for p in keys]
    mean = statistics.mean(sims)
    rate = sum(s >= tau for s in sims) / len(sims)
    out.append({"law": dk, "n": len(keys), "mean": round(mean, 4),
                "rate": round(rate, 4), "ocr": pipeline.is_ocr_base(law)})
    if (i + 1) % 25 == 0:
        print("...%d/%d" % (i + 1, len(laws)), flush=True)

json.dump(out, open(_REPO / "scratchpad" / "convergence_today.json", "w"))
means = [r["mean"] for r in out]
print("\n==== CONVERGENCE vs TODAY — %d laws scored ====" % len(out))
print("mean char-sim: mean=%.3f median=%.3f" % (statistics.mean(means), statistics.median(means)))
for thr in [0.95, 0.90, 0.85, 0.80, 0.70, 0.50]:
    print("  laws mean-sim >=%.2f : %3d" % (thr, sum(m >= thr for m in means)))
# provision-weighted rate>=tau over the whole corpus
tot = sum(r["n"] for r in out)
wrate = sum(r["rate"] * r["n"] for r in out) / tot
print("provision-weighted rate>=tau: %.3f  (total provisions=%d)" % (wrate, tot))
