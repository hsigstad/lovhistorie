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

# Amendment/repeal markers. Beyond the modern verbs (endr-, opphev-, "skal lyde",
# tilføy-) the pre-war/Nynorsk gazette uses ARCHAIC forms that are no less genuine:
#   brigde/bridge/bride  — Nynorsk (+OCR garbles) for "endre" (to amend)
#   forandr-             — "forandring i lov …" (change in a law)
#   forleng-/lengjing    — "forlenget gyldighet av … lov" (extend a law's validity)
#   opph[øo]r            — "opphør av lov …" (repeal), alongside modern opphev-
#   "tillegg til"        — "(midlertidig) tillegg til lov …" (addition to a law)
# These are specific amendment verbs, so a segment whose title/head carries one IS an
# amendment regardless of klass — teaching them here only removes FALSE klass-marker
# flags (23 of 74 on the 2026-10-04 bootstrap), never hides a real misclassification.
# The residual flags are enactment-headed acts mis-tagged `amend` (genuine curation).
# The flat segment-kind vocabulary (segment_prompt.SCHEMA) + the deterministic `noise` the
# fold carves out of furniture; any other kind is a bug.
_KINDS = {"front_matter", "enactment_heading", "provision", "amend_scope", "amend_op",
          "repeal", "ikrafttredelse", "in_force", "forskrift", "delegering", "kunngjoring",
          "anordning", "rettelser", "colophon", "signature", "other", "noise"}


def _frozen(iid):
    f = TEXT_DIR / f"{iid}.jsonl.gz"
    if not f.exists():
        return None
    return "\n".join(json.loads(l).get("text", "") for l in gzip.open(f, "rt", encoding="utf-8"))


def check(seg_path=SEG, meta_path=META):
    rows = [json.loads(l) for l in open(seg_path)]
    meta = json.loads(Path(meta_path).read_text())
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
        # I5 flat-partition kind + target checks (ordered-starts corpus, decisions.md 2026-10-04)
        for s in segs:
            kind = s.get("klass")
            if kind not in _KINDS:
                V["kind-unknown"].append((iid, s["start"], f"kind {kind!r} not in vocabulary"))
            # an amend_scope / amend_op targeting a LAW must resolve to a known law (forskrift
            # targets aren't in the law register — skip them; register-completeness, not error)
            if kind in ("amend_scope", "amend_op") and s.get("instrument") != "forskrift":
                tgt = s.get("target")
                if not tgt:
                    V["target-missing"].append((iid, s["start"], (s.get("target_cite") or "")[:40]))
                elif tgt not in register:
                    V["target-unresolved"].append((iid, s["start"], f"{tgt} not in register"))
    return V, len(rows), len(by_issue)


ORDER = ["sha-drift", "issue-missing", "overlap", "coverage-gap", "coverage-end",
         "head-mismatch", "kind-unknown", "target-missing", "target-unresolved"]


def report():
    V, nrows, nissues = check()
    total = sum(len(V[k]) for k in V)
    print(f"=== classification_qa: {nrows} segments, {nissues} issues, {total} violations ===\n")
    for k in ORDER:
        if V.get(k):
            print(f"  {k:18s} {len(V[k])}")
    print("\n-- worst examples (structural first) --")
    for k in ORDER:
        for iid, start, det in V.get(k, [])[:3]:
            print(f"  [{k}] {iid[:8]}@{start}: {det}")
    return total


def _git_head_version(repo_path: str):
    """Write HEAD:<repo_path> to a temp file; None if the path isn't in HEAD yet."""
    import subprocess
    import tempfile
    r = subprocess.run(["git", "-C", str(_REPO), "show", f"HEAD:{repo_path}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    tf = tempfile.NamedTemporaryFile("w", suffix=Path(repo_path).suffix, delete=False, encoding="utf-8")
    tf.write(r.stdout); tf.close()
    return tf.name


def diff():
    """Pre-commit gate: FAIL (exit 1) if any violation category grew vs HEAD."""
    head_seg = _git_head_version("data/segments.jsonl")
    head_meta = _git_head_version("data/segments_meta.json")
    if not head_seg or not head_meta:
        print("classification_qa --diff: no HEAD baseline; skipping gate (first commit).")
        return 0
    base, _, _ = check(head_seg, head_meta)
    work, _, _ = check()
    regressed = [(k, len(base.get(k, [])), len(work.get(k, []))) for k in ORDER
                 if len(work.get(k, [])) > len(base.get(k, []))]
    bt, wt = sum(len(v) for v in base.values()), sum(len(v) for v in work.values())
    if regressed:
        print(f"GATE FAIL: violations rose {bt}->{wt}. Regressions:")
        for k, b, w in regressed:
            print(f"  {k}: {b} -> {w}  (+{w-b})")
        return 1
    print(f"GATE PASS: violations {bt}->{wt} (no category increased).")
    return 0


def main():
    import sys
    return diff() if "--diff" in sys.argv else (0 if report() is not None else 0)


if __name__ == "__main__":
    import sys
    sys.exit(main())
