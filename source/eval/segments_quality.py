"""Base-QUALITY no-regression gate for curated `segments.jsonl` edits (the S1 signal).

INTENT: the SECOND half of the per-commit segmentation gate (decisions.md 2026-10-04).
    `classification_qa --diff` guards the PARTITION (no new gap/overlap/sha-drift/klass-
    marker/unresolved-target) — but an offset move can stay structurally valid while
    degrading the base TEXT (tighten a boundary wrongly, drop a provision, run into the
    next act). This module measures, for every law whose ENACTMENT offsets changed, the
    median per-provision similarity of its sliced base to the current text, and FAILS the
    commit if any touched law regresses vs HEAD. "Improvement" = structure-not-worse AND
    base-quality-not-worse on the touched laws.
REASONING: the enactment base of law X is the `klass=="original"` segment for datokode X —
    its char offsets slice the frozen issue into the body, which the deterministic
    provision splitter (build_enactment.parse_provisions, NO LLM) turns into {§N: text}.
    Scoring is RELATIVE (same law, HEAD offsets vs working offsets): amendment drift and
    the regex splitter's absolute weakness cancel, so the delta isolates the offset change.
    Missing current provisions score 0 (under-capture/mislocation must be visible); that
    penalty is constant across HEAD/working for a given law, so it never biases the delta.
ASSUMES: `data/segments.jsonl`, the frozen issues under data/lovtidend_text, and the
    current NLOD dump (the ANSWER KEY) at $LOVHISTORIE_CURRENT_DIR. If the answer key is
    absent (fresh clone), scoring is impossible → the gate SKIPS (never blocks).
ANTI-GAMING / G1: harness-side ONLY. It reads the answer key to MEASURE quality — exactly
    like `gate` and `reconstruction_qa` — and is NEVER imported by the reconstruction path
    (source.parse.*). Measuring against the answer key is not the same as building from it.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

from source.eval import gate, metrics
from source.eval.classification_qa import _git_head_version
from source.eval.reconstruction_qa import strip_running_headers
from source.scrape.build_enactment import TEXT_DIR, parse_provisions

_REPO = Path(__file__).resolve().parents[2]
SEG = _REPO / "data" / "segments.jsonl"
TOL = 0.02                        # ignore sub-2pt wobble (normalisation / reshuffle noise)
_REAL = re.compile(r"§\d+\w*$")   # a real provision id (not a chapter/annex key)

_frozen_cache: dict[str, str] = {}


def _frozen(iid: str) -> str | None:
    if iid in _frozen_cache:
        return _frozen_cache[iid]
    import gzip
    f = TEXT_DIR / f"{iid}.jsonl.gz"
    if not f.exists():
        return None
    txt = "\n".join(json.loads(l).get("text", "") for l in gzip.open(f, "rt", encoding="utf-8"))
    _frozen_cache[iid] = txt
    return txt


def enactment_bases(rows: list[dict]) -> dict[str, dict]:
    """datokode -> {issue_id, provisions: {para: [(start,end), ...]}} for enacted laws.
    FLAT model (decisions.md 2026-10-04): an enactment's provisions are the `klass=='provision'`
    rows carrying that datokode; a provision interrupted by furniture is several rows sharing a
    (datokode, para), reassembled by document order."""
    out: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: r["start"]):
        if r.get("klass") != "provision" or not r.get("datokode") or not r.get("para"):
            continue
        e = out.setdefault(r["datokode"], {"issue_id": r["issue_id"], "provisions": {}})
        e["provisions"].setdefault(r["para"], []).append((r["start"], r["end"]))
    return out


def median_sim_vs_current(datokode: str, base_ent: dict) -> float | None:
    """Median per-provision similarity of the enactment base to the current text. The base
    text of each § is the concatenation of its row-fragments (furniture skipped), stripped of
    running headers. None if the issue text / answer key is unavailable or current has no §N."""
    fr = _frozen(base_ent["issue_id"])
    if fr is None or not datokode or len(str(datokode).split("-")) != 4:
        return None
    try:
        cur = gate.current_provisions(datokode)
    except Exception:
        return None
    if not cur:
        return None
    base = {para: strip_running_headers(" ".join(fr[s:e] for s, e in sorted(spans)))
            for para, spans in base_ent["provisions"].items()}
    reals = [n for n in cur if _REAL.fullmatch(n)]
    if not reals:
        return None
    sims = [metrics.similarity(base.get(n, ""), cur[n]) for n in reals]
    return statistics.median(sims) if sims else None


def _basekey(ent: dict) -> tuple:
    """Identity for change-detection: the issue + every provision's span set."""
    return (ent["issue_id"],
            tuple(sorted((p, tuple(sorted(sp))) for p, sp in ent["provisions"].items())))


def _scores(rows: list[dict]) -> dict[str, float]:
    out = {}
    for dk, ent in enactment_bases(rows).items():
        sc = median_sim_vs_current(dk, ent)
        if sc is not None:
            out[dk] = sc
    return out


def report() -> int:
    rows = [json.loads(l) for l in open(SEG)]
    sc = _scores(rows)
    if not sc:
        print("segments_quality: no scorable laws (answer key absent?).")
        return 0
    vals = sorted(sc.values())
    print(f"=== segments_quality: {len(sc)} enactment bases scored vs current ===")
    print(f"  median {statistics.median(vals):.3f} | mean {statistics.mean(vals):.3f} "
          f"| >=0.5 {sum(v >= 0.5 for v in vals)}/{len(vals)}")
    print("  weakest 10:")
    for dk, v in sorted(sc.items(), key=lambda kv: kv[1])[:10]:
        print(f"    {dk}: {v:.3f}")
    return 0


def diff() -> int:
    """Pre-commit gate: FAIL (exit 1) if any law whose enactment offsets changed vs HEAD
    now reconstructs a WORSE base (median-sim drop > TOL). Skips cleanly with no baseline
    or no answer key."""
    head = _git_head_version("data/segments.jsonl")
    if not head:
        print("segments_quality --diff: no HEAD baseline; skipping (first commit).")
        return 0
    base_rows = [json.loads(l) for l in open(head)]
    work_rows = [json.loads(l) for l in open(SEG)]
    base_b, work_b = enactment_bases(base_rows), enactment_bases(work_rows)

    touched = [dk for dk in work_b if dk in base_b and _basekey(work_b[dk]) != _basekey(base_b[dk])]
    if not touched:
        print("segments_quality --diff: no enactment-base changes; nothing to score.")
        return 0

    regressions, moved = [], 0
    for dk in touched:
        sb = median_sim_vs_current(dk, base_b[dk])
        sw = median_sim_vs_current(dk, work_b[dk])
        if sb is None or sw is None:
            continue                       # unscorable (no answer key / issue) -> can't judge
        moved += 1
        if sw < sb - TOL:
            regressions.append((dk, sb, sw))

    if moved == 0:
        print(f"segments_quality --diff: {len(touched)} offsets moved but none scorable "
              "(answer key absent?); skipping.")
        return 0
    if regressions:
        print(f"GATE FAIL: {len(regressions)}/{moved} offset-moved laws lost base quality:")
        for dk, sb, sw in sorted(regressions, key=lambda r: r[2] - r[1]):
            print(f"  {dk}: {sb:.3f} -> {sw:.3f}  ({sw - sb:+.3f})")
        return 1
    print(f"GATE PASS: {moved} offset-moved laws, none regressed (> {TOL}).")
    return 0


def main() -> int:
    return diff() if "--diff" in sys.argv else report()


if __name__ == "__main__":
    sys.exit(main())
