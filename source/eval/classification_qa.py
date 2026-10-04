"""Invariant checker for the curated segmentation (`data/segments.jsonl`).

INTENT: run cheap, answer-free invariants over the segmentation partition and emit a
    RANKED list of likely-wrong segments — both the human/agent work queue (`report`) and
    the basis of the per-edit pre-commit gate (monotonic non-degradation; decisions.md
    2026-10-04). Checks: per-issue char COVERAGE (no gap) + NO OVERLAP; frozen-text SHA
    (offsets still aligned to the raw); HEAD anchor matches; klass<->marker agreement;
    amendment TARGET resolves against the public law register.
REASONING: correctness of the skeleton must be mechanically verifiable without the answer
    key — partition arithmetic + regex on the segment's own source text + register
    membership. Everything here reads public gazette text + the register; never the answer.
ASSUMES: `data/segments.jsonl`, `data/segments_meta.json`, `data/law_register.jsonl`, and
    the frozen issues under data/lovtidend_text.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from source.scrape.build_enactment import TEXT_DIR

_REPO = Path(__file__).resolve().parents[2]
SEG = _REPO / "data" / "segments.jsonl"
META = _REPO / "data" / "segments_meta.json"
REG = _REPO / "data" / "law_register.jsonl"

_AMEND_MARK = re.compile(r"\b(endr|opphev|skal lyde|tilf[øo]y)", re.I)
_LAWHEAD = re.compile(r"\blov\b.{0,30}\bnr\.?\s*\d+", re.I)


def _frozen(iid):
    f = TEXT_DIR / f"{iid}.jsonl.gz"
    if not f.exists():
        return None
    return "\n".join(json.loads(l).get("text", "") for l in gzip.open(f, "rt", encoding="utf-8"))


def check():
    rows = [json.loads(l) for l in open(SEG)]
    meta = json.loads(META.read_text())
    register = {json.loads(l)["datokode"] for l in open(REG)}
    by_issue = defaultdict(list)
    for r in rows:
        by_issue[r["issue_id"]].append(r)

    V = defaultdict(list)   # invariant -> [ (issue, start, detail) ]
    for iid, segs in by_issue.items():
        segs.sort(key=lambda r: r["start"])
        n = meta.get(iid, {}).get("n_chars")
        # I1/I2 partition: tile [0, n] with no gap/overlap
        cur = 0
        for s in segs:
            if s["start"] > cur:
                V["coverage-gap"].append((iid, cur, f"gap {cur}..{s['start']}"))
            elif s["start"] < cur:
                V["overlap"].append((iid, s["start"], f"overlaps prev end {cur}"))
            cur = max(cur, s["end"])
        if n is not None and cur != n:
            V["coverage-end"].append((iid, cur, f"ends {cur} != n_chars {n}"))
        # I3 alignment: frozen sha still matches the pin
        fr = _frozen(iid)
        if fr is None:
            V["issue-missing"].append((iid, 0, "frozen text gone"))
        elif meta.get(iid, {}).get("sha") != hashlib.sha256(fr.encode()).hexdigest()[:16]:
            V["sha-drift"].append((iid, 0, "frozen sha != pinned -> offsets suspect"))
        else:
            for s in segs:        # I4 head anchor still at start
                if s["head"] and s["head"] != re.sub(r"\s+", " ", fr[s["start"]:s["end"]][:40]).strip():
                    V["head-mismatch"].append((iid, s["start"], "head != text@start"))
        # I5 klass<->marker + target
        for s in segs:
            kl, title = s.get("klass"), (s.get("title") or "")
            if kl in ("amend", "repeal") and not _AMEND_MARK.search(title + " " + (s["head"] or "")):
                V["klass-marker"].append((iid, s["start"], f"{kl} w/o amend marker: {title[:40]!r}"))
            if kl == "filler" and _LAWHEAD.search(s["head"] or "") and (s["end"] - s["start"]) > 80:
                V["filler-has-law"].append((iid, s["start"], f"filler contains a law heading: {s['head'][:40]!r}"))
            if kl in ("amend", "repeal"):
                tgt = s.get("target")
                if not tgt:
                    V["target-missing"].append((iid, s["start"], title[:40]))
                elif tgt not in register:
                    V["target-unresolved"].append((iid, s["start"], f"{tgt} not in register"))
    return V, len(rows), len(by_issue)


def main():
    V, nrows, nissues = check()
    order = ["sha-drift", "issue-missing", "overlap", "coverage-gap", "coverage-end",
             "head-mismatch", "filler-has-law", "klass-marker", "target-missing", "target-unresolved"]
    total = sum(len(V[k]) for k in V)
    print(f"=== classification_qa: {nrows} segments, {nissues} issues, {total} violations ===\n")
    for k in order:
        if V.get(k):
            print(f"  {k:18s} {len(V[k])}")
    print("\n-- worst examples (structural first) --")
    for k in order:
        for iid, start, det in V.get(k, [])[:3]:
            print(f"  [{k}] {iid[:8]}@{start}: {det}")
    return total


if __name__ == "__main__":
    main()
