"""Fold a subagent's anchored issue-segmentation into the curated `segments.jsonl`.

INTENT: the deterministic half of the S2 locator fold-in (decisions.md 2026-10-04). A
    Claude subagent reads ONE frozen Lovtidend issue (public-domain OCR ONLY — answer-free)
    and returns, per act, its klass/target/title plus VERBATIM start/end anchors and (for
    enactments) per-provision anchors. This module takes that JSON and does the
    fabrication-safe, reproducible part: resolve each anchor to a char offset in the frozen
    text, substring-VERIFY it, and rebuild that issue's rows as a clean two-level partition
    (acts tiled with explicit filler). For enactment (klass=original) rows, the per-provision
    (§) boundaries are resolved from their anchors and NESTED on the row as
    `provisions: [{para, start, end}]` (absolute offsets into the frozen issue) — so
    `segments.jsonl` is the single canonical artifact (decisions.md 2026-10-04 choice b).
REASONING: the model emits only POINTERS (anchors) into the public source — never text — so
    0% content fabrication is automatic (every span is a slice of the frozen OCR, checked).
    Anchors are matched whitespace-tolerantly (the agent joins words with spaces; the OCR has
    newlines) via a \\s+ token regex. An act whose anchor does not resolve is DROPPED
    (flag-don't-fabricate), never guessed.
ASSUMES: frozen issues under data/lovtidend_text; `data/segments.jsonl` + `segments_meta.json`
    exist (the frozen text is unchanged, so each issue's pinned sha/n_chars stay valid).
ANTI-GAMING / G1: reads only public OCR + the agent's pointers; never the current dump /
    oracle / register. Harness-side tooling; not on the reconstruction path.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

from source.scrape.build_enactment import TEXT_DIR

_REPO = Path(__file__).resolve().parents[2]
SEG = _REPO / "data" / "segments.jsonl"


def frozen_text(iid: str) -> str | None:
    f = TEXT_DIR / f"{iid}.jsonl.gz"
    if not f.exists():
        return None
    return "\n".join(json.loads(l).get("text", "") for l in gzip.open(f, "rt", encoding="utf-8"))


def _head(text: str, n: int = 40) -> str:
    return re.sub(r"\s+", " ", text[:n]).strip()


def _anchor_span(frozen: str, anchor: str, start: int = 0):
    """Whitespace-tolerant verbatim match of an anchor; returns (start, end) or None."""
    toks = anchor.split()
    if not toks:
        return None
    m = re.compile(r"\s+".join(re.escape(t) for t in toks)).search(frozen, start)
    return (m.start(), m.end()) if m else None


def resolve_acts(frozen: str, acts: list[dict]) -> tuple[list[dict], list[str]]:
    """Resolve each act's start/end anchor to offsets; substring-verify. Returns
    (located, misses). An act whose start or end anchor doesn't resolve is dropped."""
    located, misses = [], []
    for a in acts:
        s = _anchor_span(frozen, a.get("start_anchor", ""))
        if not s:
            misses.append(f"{a.get('datokode')}: start anchor not found")
            continue
        e = _anchor_span(frozen, a.get("end_anchor", ""), s[0])
        if not e:
            misses.append(f"{a.get('datokode')}: end anchor not found")
            continue
        if e[1] <= s[0]:
            misses.append(f"{a.get('datokode')}: end before start")
            continue
        located.append({**a, "start": s[0], "end": e[1]})
    return located, misses


_MONTHS = {"januar": "01", "februar": "02", "mars": "03", "april": "04", "mai": "05",
           "juni": "06", "juli": "07", "august": "08", "september": "09",
           "oktober": "10", "november": "11", "desember": "12"}
_CITE = re.compile(
    r"(\d{1,2})\.?\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\s+nr\.?\s*(\d+)", re.I)


def cite_to_datokode(cite: str | None) -> str | None:
    """Parse a Norwegian law citation ('lov [av] DD. <month> YYYY nr. N …') to a datokode
    YYYY-MM-DD-N. None if no full date+nr is present (name-only citation)."""
    if not cite:
        return None
    m = _CITE.search(cite)
    if not m:
        return None
    d, mon, y, nr = m.groups()
    return f"{y}-{_MONTHS[mon.lower()]}-{int(d):02d}-{int(nr)}"


def _resolve_provisions(frozen: str, body_start: int, body_end: int, anchors: list[dict]) -> list[dict]:
    """Resolve each provision anchor to a char span within the enactment body; each § runs
    to the next located §, the last to body_end. Unresolvable anchors are dropped. Returns
    [{para, start, end}] (absolute offsets), monotonic and non-overlapping by construction."""
    marks = []
    for p in anchors or []:
        sp = _anchor_span(frozen, p.get("anchor", ""), body_start)
        if sp and body_start <= sp[0] < body_end:
            marks.append((sp[0], p.get("para")))
    marks.sort()
    out = []
    for i, (pos, para) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else body_end
        out.append({"para": para, "start": pos, "end": end})
    return out


def build_issue_rows(iid: str, acts: list[dict], frozen: str) -> tuple[list[dict], list[str]]:
    """Rebuild one issue's segment rows as a tiled two-level partition from located acts.
    Overlapping acts are a hard error (the agent returned an inconsistent segmentation)."""
    located, misses = resolve_acts(frozen, acts)
    located.sort(key=lambda a: a["start"])
    rows, cur = [], 0
    for a in located:
        s, e = a["start"], a["end"]
        if s < cur:
            misses.append(f"{a.get('datokode')}: overlaps previous act (start {s} < {cur})")
            continue
        if s > cur:
            rows.append(_row(iid, cur, s, frozen))                      # filler
        provs = None
        if a.get("klass") == "original" and a.get("provisions"):
            provs = _resolve_provisions(frozen, s, e, a["provisions"])
        # the subagent returns `target` as a human citation; the register is keyed by
        # datokode, so parse it (keep the raw citation in `target_cite` for provenance).
        cite = a.get("target")
        tgt = cite_to_datokode(cite) if a.get("klass") in ("amend", "repeal") else None
        rows.append(_row(iid, s, e, frozen, klass=a.get("klass") or "unknown",
                         datokode=a.get("datokode"), nr=a.get("nr"), date=a.get("date"),
                         target=tgt, target_cite=cite, title=a.get("title"), provisions=provs))
        cur = e
    n = len(frozen)
    if cur < n:
        rows.append(_row(iid, cur, n, frozen))                          # trailing filler
    return rows, misses


def _row(iid, start, end, frozen, *, klass="filler", provisions=None, **kw):
    row = {
        "issue_id": iid, "start": start, "end": end,
        "start_line": frozen.count("\n", 0, start),
        "head": _head(frozen[start:end]),
        "klass": klass,
        "datokode": kw.get("datokode"), "nr": kw.get("nr"), "date": kw.get("date"),
        "target": kw.get("target"), "title": kw.get("title"),
    }
    if kw.get("target_cite"):
        row["target_cite"] = kw["target_cite"]
    if provisions:
        row["provisions"] = provisions
    return row


def apply(issue_results: list[dict], seg_path: Path = SEG) -> dict:
    """Replace rows for each touched issue with the subagent-derived partition; keep all
    other issues' rows. Writes segments.jsonl. Returns a summary (touched/dropped/misses).
    Caller runs the gates + commits — this only stages the working-tree edit."""
    rows = [json.loads(l) for l in open(seg_path)]
    touched = {r["iid"] for r in issue_results}
    kept = [r for r in rows if r["issue_id"] not in touched]
    summary = {"issues": 0, "acts_located": 0, "prov_laws": 0, "misses": []}
    new_rows = []
    for res in issue_results:
        iid = res["iid"]
        frozen = frozen_text(iid)
        if frozen is None:
            summary["misses"].append(f"{iid}: frozen text missing")
            continue
        acts = res.get("acts") or []
        irows, misses = build_issue_rows(iid, acts, frozen)
        new_rows.extend(irows)
        summary["issues"] += 1
        summary["acts_located"] += sum(1 for r in irows if r["klass"] != "filler")
        summary["prov_laws"] += sum(1 for r in irows if r.get("provisions"))
        summary["misses"].extend(misses)
    out = kept + new_rows
    out.sort(key=lambda r: (r["issue_id"], r["start"]))
    with open(seg_path, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return summary
