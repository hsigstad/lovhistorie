"""Bootstrap the curated SEGMENTATION dataset — `data/segments.jsonl`.

INTENT: emit a char-offset PARTITION of every law-bearing gazette issue — one row per
    segment {issue_id, start, end, start_line, head, klass, datokode, nr, date, target,
    title} covering the issue's frozen text with no gap or overlap (filler/TOC explicit).
    This is the git-tracked curated dataset (decisions.md 2026-10-04): the classifier
    BOOTSTRAPS it here once; thereafter it is hand/agent-corrected and `classification_qa`
    gates every edit. Reconstruction is a pure function of this file.
REASONING: canonical boundaries are CHAR offsets into the frozen per-issue text
    (`frozen_text` = "\\n".join(page.text)); `start_line` + `head` (first chars at `start`)
    ride along for human anchoring and automatic misalignment detection vs the raw. A
    per-issue sha (sidecar `segments_meta.json`) pins the frozen text so offsets are
    self-validating. Offsets come straight from segment_issue (verified headings, TOC-free).
ASSUMES: cached segmentation (`segment_issue`, populated by build_gazette/build_act_index);
    zero live LLM — a cache miss skips the issue rather than spending.
ANTI-GAMING: reads only public gazette OCR + its cached segmentation; never the answer key.
"""
from __future__ import annotations

import glob
import gzip
import hashlib
import json
import re
from pathlib import Path

from source.scrape.build_enactment import TEXT_DIR
from source.llm import segment_issue

_REPO = Path(__file__).resolve().parents[2]
OUT = _REPO / "data" / "segments.jsonl"
META = _REPO / "data" / "segments_meta.json"
RESULT_DIR = _REPO / "data" / "llm_cache" / "issue_acts_result"


class _CacheOnly:
    def __getattr__(self, k):
        raise RuntimeError("segmentation cache miss (live LLM blocked)")


def _head(text: str, n: int = 40) -> str:
    return re.sub(r"\s+", " ", text[:n]).strip()


def _row(issue_id, start, end, frozen, *, klass="filler", **kw):
    return {
        "issue_id": issue_id, "start": start, "end": end,
        "start_line": frozen.count("\n", 0, start),
        "head": _head(frozen[start:end]),
        "klass": klass,
        "datokode": kw.get("datokode"), "nr": kw.get("nr"), "date": kw.get("date"),
        "target": kw.get("target"), "title": kw.get("title"),
    }


def build() -> tuple[int, int]:
    issue_ids = [Path(p).name.split(".")[0] for p in glob.glob(str(RESULT_DIR / "*.json.gz"))]
    rows, meta = [], {}
    n_issues = 0
    for iid in issue_ids:
        f = TEXT_DIR / f"{iid}.jsonl.gz"
        if not f.exists():
            continue
        # The cached segmentation stores each act's `body`, which is an exact slice of the
        # frozen text — so `frozen.find(body)` recovers its exact offset with zero LLM.
        try:
            acts = json.loads(gzip.open(RESULT_DIR / f"{iid}.json.gz", "rt", encoding="utf-8").read())
        except Exception:
            acts = []
        if not acts:                         # forskrift-only / empty issue — not law-bearing
            continue
        pages = [json.loads(l) for l in gzip.open(f, "rt", encoding="utf-8")]
        frozen = "\n".join(p.get("text", "") for p in pages)
        for a in acts:
            b = a.get("body") or ""
            a["start"] = frozen.find(b) if b else -1
            a["end"] = a["start"] + len(b) if a["start"] >= 0 else -1
        acts = [a for a in acts if a.get("start", -1) >= 0]
        if not acts:
            continue
        acts.sort(key=lambda a: a["start"])
        n_issues += 1
        meta[iid] = {"sha": hashlib.sha256(frozen.encode()).hexdigest()[:16], "n_chars": len(frozen)}
        cur = 0
        for a in acts:
            s, e = a["start"], a["end"]
            if s > cur:                      # leading / inter-act filler (TOC, masthead, gaps)
                rows.append(_row(iid, cur, s, frozen))
            rows.append(_row(iid, s, e, frozen, klass=a.get("klass") or "unknown",
                             datokode=a.get("datokode"), nr=a.get("nr"), date=a.get("date"),
                             target=a.get("target"), title=a.get("title")))
            cur = e
        if cur < len(frozen):                # trailing filler
            rows.append(_row(iid, cur, len(frozen), frozen))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=0), encoding="utf-8")
    return n_issues, len(rows)


if __name__ == "__main__":
    ni, nr = build()
    print(f"wrote {nr} segments across {ni} law-bearing issues -> {OUT.relative_to(_REPO)}")
