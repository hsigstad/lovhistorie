"""Breadth eval — reconstruction quality across the clean-base corpus, not just the dev set.

INTENT: the 9-law dev set (gate) is a HARD, OCR-heavy subset chosen to stress the hardest
    cases; it understates quality on the clean-base majority. This measures reconstruction
    (LTI enactment base + amendments) against the current text for post-2001 laws present in
    BOTH the LTI dump and the current dump — the ~366 clean-base statutes the tools are meant
    to scale to. Result (2026-08-16, n=62): mean ≥0.90 rate 0.833, median 0.887.
REASONING: reconstructs IN MEMORY (parse_lovdata_xml base → replay), so it writes no
    enactment JSONs and touches no dev artifacts. Clean bases (LTI) carry no OCR floor, so
    τ=0.98/0.90 rates reflect amendment coverage + engine quality, not scanning noise.
ASSUMES: the current NLOD dump at data/current/ (answer key, harness-only — same G-guards as
    the gate; this is an eval, never a recon input). Excludes the dev laws.
"""
from __future__ import annotations

import glob
import re
import statistics
from pathlib import Path

from source.scrape.build_enactment import parse_lovdata_xml, lti_path
from source.parse import pipeline, replay
from source.eval import gate, metrics

ROOT = Path(__file__).resolve().parents[2]
DEV = {dk for _, dk in gate.DEV_LAWS}


def candidates():
    """Non-dev datokodes present in BOTH the LTI dump (post-2001 enactment) and the current
    dump — clean-base laws we can score end-to-end."""
    def dks(pattern, group):
        out = set()
        for f in glob.glob(pattern):
            m = re.match(r"nl-(\d{8})-(\d+)", Path(f).stem)
            if m:
                s = m.group(1)
                out.add(f"{s[:4]}-{s[4:6]}-{s[6:8]}-{int(m.group(2))}")
        return out
    cur = dks(str(ROOT / "data" / "current" / "nl-*.xml"), 1)
    lti = dks(str(ROOT / "data" / "lti" / "*" / "nl-*.xml"), 1)
    return sorted((cur & lti) - DEV)


def score_law(dk: str):
    """(n_provisions, rate>=.98, rate>=.90, mean_sim) reconstructing dk in memory, or None."""
    cur = gate.current_provisions(dk)
    if not cur:
        return None
    base = parse_lovdata_xml(Path(lti_path(dk)).read_text(encoding="utf-8", errors="ignore"))
    provs, _ = replay.replay(base, pipeline.load_ops("lov/" + dk), as_of=None)
    order = [p for p in cur if not metrics.is_convention_annex(p)]
    if not order:
        return None
    sims = [metrics.similarity(provs.get(p, ""), cur[p]) for p in order]
    return (len(order), sum(s >= 0.98 for s in sims) / len(order),
            sum(s >= 0.90 for s in sims) / len(order), statistics.mean(sims))


def run(step: int = 5, limit: int = 80):
    """Score a spread sample of the clean-base corpus; print the distribution."""
    sample = candidates()[::step][:limit]
    r90, r98, low = [], [], []
    for dk in sample:
        try:
            s = score_law(dk)
        except Exception as e:                       # data issue on one law must not abort
            low.append((dk, "ERR", str(e)[:40]))
            continue
        if not s:
            continue
        r90.append(s[2]); r98.append(s[1])
        if s[2] < 0.5:
            low.append((dk, s[0], round(s[2], 2)))
    print(f"breadth: {len(r90)} non-dev clean-base laws")
    print(f"  rate >=.90: mean {statistics.mean(r90):.3f}  median {statistics.median(r90):.3f}")
    print(f"  rate >=.98: mean {statistics.mean(r98):.3f}")
    print(f"  laws with >=.90-rate above 0.8: {sum(x >= 0.8 for x in r90)}/{len(r90)}; below 0.5: "
          f"{sum(x < 0.5 for x in r90)}")
    print(f"  low outliers: {low[:10]}")
    return r90


if __name__ == "__main__":
    run()
