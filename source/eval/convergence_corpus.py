"""Corpus-wide convergence-to-TODAY: the breadth quality signal (Henrik: measure vs today, not the
2005 oracle, across ALL laws we hold — not just the 154-law 2005-CD subset).

INTENT: `python -m source.eval.convergence_corpus` -> build/eval/convergence_today_corpus.csv, one row
    per reconstructable law that has a current-dump answer key: char-similarity of reconstruct(law, today)
    to the current NLOD text (mean + rate>=tau), n provisions, ocr flag. Feeds the consumer catalog
    (source.consume) and the public browser index (source.site.browser).
REASONING: this is CURRENT-TEXT accuracy — broad (every law with current text) and publishable (NLOD
    current dump is public-domain). It is NOT historical point-in-time fidelity (which needs past gold and
    is lower; convergence-to-current overstates it — see docs/reference/pit_coverage.md). Kept as a
    separate, clearly-labelled artifact so the two claims are never collapsed.
ASSUMES: run from repo root with the current NLOD dump present (data/current or $LOVHISTORIE_CURRENT_DIR).
    Current text is the harness answer key for the gate but PUBLIC-DOMAIN, so scoring against it and
    shipping the number is fine; it is never an INPUT to reconstruction (G1/G2 unaffected).
"""
from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path

from source.parse import pipeline
from source.eval import gate, metrics

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "eval" / "convergence_today_corpus.csv"


def reconstructable_scoreable() -> list[str]:
    """Laws with an amendment stream, a non-empty enactment base, AND a current-dump answer key."""
    out = []
    for law in pipeline._grouped(pipeline._stream_sig()):
        try:
            if not pipeline.enactment_base(law):
                continue
            if gate.current_provisions(law.split("/")[-1]) is None:
                continue
        except Exception:
            continue
        out.append(law)
    return out


def score_law(law: str) -> dict | None:
    dk = law.split("/")[-1]
    cur = gate.current_provisions(dk)
    if not cur:
        return None
    try:
        recon = pipeline.reconstruct(law, None)[0]
    except Exception:
        return None
    tau = gate.TAU_OCR if pipeline.is_ocr_base(law) else gate.TAU
    keys = [p for p in cur if cur.get(p) and not metrics.is_convention_annex(p)]
    if not keys:
        return None
    sims = [metrics.similarity(recon.get(p, ""), cur.get(p, "")) for p in keys]
    return {"datokode": dk, "n_provisions": len(keys),
            "current_fidelity": round(statistics.mean(sims), 4),
            "current_rate": round(sum(s >= tau for s in sims) / len(sims), 4),
            "ocr_base": int(pipeline.is_ocr_base(law))}


def build():
    laws = reconstructable_scoreable()
    print(f"scoring {len(laws)} reconstructable+scoreable laws vs today ...", flush=True)
    rows = []
    for i, law in enumerate(laws):
        r = score_law(law)
        if r:
            rows.append(r)
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(laws)}", flush=True)
    rows.sort(key=lambda r: -r["current_fidelity"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["datokode", "n_provisions", "current_fidelity",
                                           "current_rate", "ocr_base"])
        w.writeheader()
        w.writerows(rows)
    means = [r["current_fidelity"] for r in rows]
    print(f"wrote {OUT} ({len(rows)} laws)")
    print(f"  mean={statistics.mean(means):.3f} median={statistics.median(means):.3f} "
          f">=0.90:{sum(m >= 0.9 for m in means)} >=0.70:{sum(m >= 0.7 for m in means)}")
    return rows


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
