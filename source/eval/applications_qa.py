"""Gate for the curated application layer `data/applications.jsonl` (sibling of classification_qa /
segments_quality; same pre-commit --diff pattern).

INTENT: keep the pointer layer HONEST and NON-REGRESSING. For each law with applications, compare
    reconstruction WITH the layer vs WITHOUT it: `fired` = ops the regex engine flagged that the
    curated pointers now apply (anchors resolved + spliced). Report rows / fired / orphans. `--diff`
    FAILS if fired drops vs HEAD or orphan rows grow — so a base change that silently breaks pointers
    (anchors no longer resolve) is caught at commit, not shipped.
REASONING: `fired` is the layer's whole point and is self-validating — it counts ops that went from
    flagged to applied, which can only happen if the anchors resolve against the live provision. An
    orphan (op_key with no matching op in load_ops) means the underlying op changed (re-segmentation)
    and the row is stale. No oracle, no answer key.
ANTI-GAMING / G1: reads only the public pointer rows + public bases/ops via the deterministic
    pipeline; never the current/oracle dump or the register.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from source.parse import pipeline, replay, ledd_apply

_REPO = Path(__file__).resolve().parents[2]
APPS = _REPO / "data" / "applications.jsonl"


def _rows(path: Path):
    if not path or not path.exists():
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _measure(path: Path) -> dict:
    """Per-law: rows, fired (flags_off - flags_on), orphans. Uses `path` as the applications file."""
    ledd_apply._cache = None
    saved = ledd_apply.APPLICATIONS
    ledd_apply.APPLICATIONS = path
    try:
        rows = _rows(path)
        by_law = defaultdict(list)
        for r in rows:
            by_law[r["target_law"]].append(r)
        summary = {}
        for law, lrows in by_law.items():
            try:
                base = pipeline.enactment_base("lov/" + law)
                ops = pipeline.load_ops("lov/" + law)
            except Exception as e:
                summary[law] = {"rows": len(lrows), "error": str(e)[:50]}
                continue
            keys = {ledd_apply.op_key(law, o.get("instruction"), o.get("new_text")) for o in ops}
            orphans = [r for r in lrows if r.get("op_key") not in keys]
            _, flags_off = replay.replay(base, ops, ledd_fallback=None)
            _, flags_on = replay.replay(base, ops, ledd_fallback=ledd_apply.make_fallback("lov/" + law))
            summary[law] = {"rows": len(lrows), "fired": len(flags_off) - len(flags_on),
                            "orphans": len(orphans)}
        return summary
    finally:
        ledd_apply.APPLICATIONS = saved
        ledd_apply._cache = None


def _totals(summary: dict):
    fired = sum(s.get("fired", 0) for s in summary.values())
    orphans = sum(s.get("orphans", 0) for s in summary.values())
    rows = sum(s.get("rows", 0) for s in summary.values())
    return rows, fired, orphans


def report(path: Path = APPS) -> dict:
    summary = _measure(path)
    rows, fired, orphans = _totals(summary)
    print(f"=== applications_qa: {rows} rows, {len(summary)} laws, fired {fired}, orphans {orphans} ===")
    for law, s in sorted(summary.items(), key=lambda kv: -kv[1].get("fired", 0))[:15]:
        extra = f" ERROR {s['error']}" if s.get("error") else ""
        print(f"  {law}: rows={s.get('rows',0)} fired={s.get('fired',0)} orphans={s.get('orphans',0)}{extra}")
    return summary


def _head_file():
    r = subprocess.run(["git", "-C", str(_REPO), "show", "HEAD:data/applications.jsonl"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    f.write(r.stdout)
    f.close()
    return Path(f.name)


def diff() -> int:
    work = report(APPS)
    _, wf, wo = _totals(work)
    head = _head_file()
    if head is None:
        print("applications_qa --diff: no HEAD baseline; skipping gate (first commit).")
        return 0
    base = _measure(head)
    _, bf, bo = _totals(base)
    if wf < bf:
        print(f"GATE FAIL: fired dropped {bf} -> {wf} (a base change broke curated pointers, "
              f"or applications were removed). Re-derive the stale rows.")
        return 1
    if wo > bo:
        print(f"GATE FAIL: orphan rows grew {bo} -> {wo} (rows whose op no longer exists).")
        return 1
    print(f"GATE PASS: fired {bf} -> {wf} (no drop); orphans {bo} -> {wo} (no growth).")
    return 0


def main():
    if "--diff" in sys.argv:
        return diff()
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
