"""Enactment/act index: datokode -> {issue_id, klass, title, body_len}.

INTENT: the "one pass, tag every act" index that lets build_enactment.build_from_index(datokode)
    locate any act's issue WITHOUT a hand-authored LOCATIONS entry (the general path the
    build_enactment docstring anticipates). Aggregates the per-issue act segmentations that
    source/llm/segment_issue.py already caches (data/llm_cache/issue_acts_result/<issue>.json.gz).
REASONING: each act carries its OWN datokode (heading date+nr), unique per act, so the key
    locates exactly the issue+act that enacted that datokode. Building the index is then a cheap
    disk aggregation (no LLM). Rebuild after reprocessing issues (e.g. giant multi-year volumes,
    which need the datokode-dedup fix in segment_issue) so their recovered acts land here.
ASSUMES: segment_issue result caches exist on disk (populated by build_gazette / build_act_index
    runs); each act dict has datokode + body. G1-safe: reads only public-domain gazette-derived
    segmentations, never the current/answer text.
"""
from __future__ import annotations

import glob
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "data" / "llm_cache" / "issue_acts_result"
OUT = ROOT / "data" / "act_index.json"


def build() -> dict:
    files = sorted(glob.glob(str(RESULT_DIR / "*.json.gz")))
    index: dict[str, dict] = {}
    dup = 0
    for f in files:
        iid = Path(f).name[: -len(".json.gz")]
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            acts = json.loads(fh.read())
        for a in acts:
            dk = a.get("datokode")
            if not dk:
                continue
            body_len = len(a.get("body") or "")
            prev = index.get(dk)
            # Same act shouldn't appear in two issues; if it does (overlapping harvest),
            # keep the copy with the fuller body (most complete enactment text).
            if prev is not None:
                dup += 1
                if body_len <= prev["body_len"]:
                    continue
            index[dk] = {"issue_id": iid, "klass": a.get("klass"),
                         "title": (a.get("title") or "")[:120], "body_len": body_len}
    OUT.write_text(json.dumps(index, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"act_index: {len(index)} datokodes from {len(files)} issues "
          f"({dup} cross-issue duplicate datokodes; kept fuller body)")
    return index


if __name__ == "__main__":
    build()
