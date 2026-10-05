"""Fold a subagent's anchored issue-segmentation into the curated `segments.jsonl`.

INTENT: the deterministic half of the S2 locator fold-in (decisions.md 2026-10-04). A
    Claude subagent reads ONE frozen Lovtidend issue (public-domain OCR ONLY — answer-free)
    and returns, per act, its klass/target/title plus VERBATIM start/end anchors and (for
    enactments) per-provision anchors. This module takes that JSON and does the
    fabrication-safe, reproducible part: resolve each anchor to a char offset in the frozen
    text, substring-VERIFY it, and rebuild that issue as a partition.
    `fold_flat` is the CANONICAL path (decisions.md 2026-10-04 flatten): ONE flat typed
    char-partition per issue — every char in exactly one typed segment (act_heading /
    provision / amendment / toc / noise / …), page furniture split out as `noise`, a
    furniture-interrupted unit kept as multiple rows sharing `unit_key` (assembly concatenates
    by key). Hierarchy is denormalized (`datokode` FK + document order), no nesting.
    (`build_issue_rows`/`apply` are the earlier act-level + nested-provision form, retained
    until the flat migration runs over the whole corpus.)
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


# ---------------------------------------------------------------------------------------
# FLAT partition (the canonical form; decisions.md 2026-10-04 flatten). Every char of the
# issue lands in exactly one typed segment. Hierarchy is denormalized onto each row
# (`datokode` FK + document order); page furniture is split out as `noise`; a logical unit
# interrupted by furniture becomes multiple rows sharing `unit_key`.
# ---------------------------------------------------------------------------------------
_MON = r"(jan|feb|mars|apr|mai|juni|juli|aug|sep|sept|okt|nov|des)"
_FURNITURE = [re.compile(p, re.I) for p in (
    r"\d{1,4}",                                   # bare page number
    rf"{_MON}\.?\s+(Lov\s+)?[Nn]r\.?\s*\d+",      # "juli Lov nr. 69"
    rf"\d+\s+{_MON}\.?\s+[Nn]r\.?\s*\d+",         # "7 juli nr. 69"
)]


def _is_furniture(line: str) -> bool:
    s = line.strip()
    return bool(s) and any(p.fullmatch(s) for p in _FURNITURE)


def _line_spans(frozen: str, s: int, e: int):
    """Yield (start, end) char spans of each physical line within [s, e] (newlines kept on the
    line's trailing edge so spans tile [s, e] exactly)."""
    i = s
    while i < e:
        nl = frozen.find("\n", i, e)
        j = e if nl < 0 else nl + 1
        yield i, j
        i = j


# Kinds whose text is prose a running-header interrupts; furniture inside these is split out
# as `noise`. NOT front_matter/toc (page numbers there are legit content), signature, other.
_SPLIT_KINDS = {"provision", "amend_op", "amend_scope", "enactment_heading", "in_force",
                "repeal", "forskrift", "delegering", "kunngjoring", "anordning",
                "ikrafttredelse", "amend", "original"}


def _emit(rows, frozen, iid, s, e, kind, unit_key, **extra):
    """Emit a span. For prose kinds, split out runs of page-furniture lines as `noise` so a
    furniture-interrupted unit becomes several rows sharing `unit_key`."""
    if e <= s:
        return
    if kind not in _SPLIT_KINDS:
        rows.append(_flat_row(frozen, iid, s, e, kind, unit_key, **extra))
        return
    segs = []                                     # (start, end, is_furniture)
    for ls, le in _line_spans(frozen, s, e):
        f = _is_furniture(frozen[ls:le])
        if segs and segs[-1][2] == f:
            segs[-1] = (segs[-1][0], le, f)
        else:
            segs.append((ls, le, f))
    for a, b, f in segs:
        if f:
            rows.append(_flat_row(frozen, iid, a, b, "noise", f"noise@{a}"))
        else:
            rows.append(_flat_row(frozen, iid, a, b, kind, unit_key, **extra))


def tile_ordered(iid: str, segments: list[dict], frozen: str) -> tuple[list[dict], list[str]]:
    """Ordered-starts tiling (segment_prompt contract): resolve each segment's start_anchor to
    an offset (monotonically), then tile. Returns (rows, misses)."""
    placed, misses, pos = [], [], 0
    for seg in segments:
        sp = _anchor_span(frozen, seg.get("start_anchor", ""), pos) \
            or _anchor_span(frozen, seg.get("start_anchor", ""), 0)   # retry from 0 if order slipped
        if not sp:
            misses.append(f"{seg.get('kind')}: start anchor not found: {seg.get('start_anchor','')[:40]!r}")
            continue
        placed.append((sp[0], seg))
        pos = sp[0]
    return _tile_placed(iid, placed, frozen), misses


def _tile_placed(iid: str, placed: list[tuple], frozen: str) -> list[dict]:
    """Tile a resolved [(global_start, seg), ...] list: [start_i, start_{i+1}] so there are NO
    gaps by construction, global datokode/cite carry-forward, then furniture-split prose."""
    placed.sort(key=lambda x: x[0])
    rows, n = [], len(frozen)
    if placed and placed[0][0] > 0:               # agent should have started at 0 — flag the lead gap
        _emit(rows, frozen, iid, 0, placed[0][0], "other", "lead@0")
    _FIELDS = ("para", "op_kind", "from", "to", "position")
    # Ordered-starts carry-forward: the agent puts datokode on an enactment_heading and the
    # amended-law citation + instrument on an amend_scope; the following provisions/ops carry
    # neither and inherit by document order. An amend_op's OWN `target_cite` is the address
    # ("§ 4 femte ledd"), NOT the law — so ops always inherit the SCOPE's law, never their own.
    _INHERIT = {"provision", "amend_op", "amend_scope", "in_force"}
    cur_act = cur_cite = cur_instr = None
    for i, (s, seg) in enumerate(placed):
        e = placed[i + 1][0] if i + 1 < len(placed) else n
        kind = seg.get("kind") or "other"
        dk = seg.get("datokode")
        cite = instr = None
        if kind == "amend_scope":
            cur_cite, cur_instr = seg.get("target_cite") or None, seg.get("instrument") or None
            cite, instr, dk = cur_cite, cur_instr, dk or cur_act
        elif kind == "amend_op":
            cite, instr, dk = cur_cite, cur_instr, dk or cur_act   # inherit scope's law
        elif kind in ("provision", "in_force"):
            dk = dk or cur_act
        else:                                        # heading / standalone boundary
            cur_act, cur_cite, cur_instr = dk, None, None
        extra = {k: seg.get(k) for k in _FIELDS}
        extra["datokode"] = dk
        if instr:
            extra["instrument"] = instr
        if cite and kind in ("amend_scope", "amend_op"):
            extra["target_cite"] = cite
            if instr != "forskrift":                 # law register can't resolve forskrift targets
                extra["target"] = cite_to_datokode(cite)
        _emit(rows, frozen, iid, s, e, kind, _unit_key({**seg, "datokode": dk}, i), **extra)
    return rows


def _unit_key(seg: dict, i: int) -> str:
    dk = seg.get("datokode") or "?"
    k = seg.get("kind")
    if k == "provision":
        return f"{dk}:{seg.get('para')}"
    if k in ("amend_op", "amend_scope"):
        return f"{dk}:op{i}"
    return f"{dk}:{k}:{i}"


# ---------------------------------------------------------------------------------------
# Chunked segmentation for big/dense issues that overflow one subagent (output-token cap or
# under-segmentation). Split into overlapping line-aligned chunks; each chunk is segmented
# independently; stitch resolves each chunk's anchors to GLOBAL offsets within its window,
# dedups the overlap, and runs the global carry-forward + tiling (`_tile_placed`) — so a law
# whose heading is in one chunk and whose §§ are in the next still groups correctly.
# ---------------------------------------------------------------------------------------
def chunk_ranges(frozen: str, target: int = 250000, overlap: int = 12000) -> list[tuple]:
    """Line-aligned overlapping [start, end) char ranges covering the whole issue."""
    n, i, out = len(frozen), 0, []
    while i < n:
        end = min(i + target, n)
        if end < n:
            nl = frozen.find("\n", end)
            end = n if nl < 0 else nl + 1
        out.append((i, end))
        if end >= n:
            break
        nxt = max(i + 1, end - overlap)
        nl = frozen.rfind("\n", 0, nxt)
        i = nl + 1 if nl >= 0 else nxt
    return out


def stitch_chunks(iid: str, chunk_results: list[dict], frozen: str) -> tuple[list[dict], list[str]]:
    """chunk_results: [{cstart, cend, segments}]. Resolve each chunk's start_anchors to GLOBAL
    offsets WITHIN [cstart, cend] (monotonic), merge, dedup by global offset, then tile."""
    placed, misses, seen = [], [], set()
    for ch in sorted(chunk_results, key=lambda c: c["cstart"]):
        cstart, cend, pos = ch["cstart"], ch["cend"], ch["cstart"]
        for seg in ch.get("segments") or []:
            sp = _anchor_span(frozen, seg.get("start_anchor", ""), pos)
            if not sp or sp[0] >= cend:
                sp = _anchor_span(frozen, seg.get("start_anchor", ""), cstart)   # retry within window
            if not sp or sp[0] >= cend:
                misses.append(f"chunk@{cstart}: anchor not found: {seg.get('start_anchor','')[:40]!r}")
                continue
            g = sp[0]
            if g in seen:                       # overlap duplicate
                continue
            seen.add(g)
            placed.append((g, seg))
            pos = g
    return _tile_placed(iid, placed, frozen), misses


def fold_ordered(issue_results: list[dict]) -> dict[str, list[dict]]:
    """{iid: [flat rows]} from the ordered-starts agent output (segment_prompt.SCHEMA)."""
    out = {}
    for res in issue_results:
        iid = res["iid"]
        frozen = frozen_text(iid)
        if frozen is None:
            continue
        rows, _ = tile_ordered(iid, res.get("segments") or [], frozen)
        out[iid] = rows
    return out


def _flat_row(frozen, iid, s, e, kind, unit_key, **extra):
    row = {"issue_id": iid, "start": s, "end": e, "start_line": frozen.count("\n", 0, s),
           "head": _head(frozen[s:e]), "klass": kind, "unit_key": unit_key}
    row.update({k: v for k, v in extra.items() if v is not None})
    return row


def fold_flat(issue_results: list[dict]) -> dict[str, list[dict]]:
    """Return {iid: [flat rows]} — a complete typed char-partition per issue from the agent's
    acts+provisions output. amend/repeal acts are one coarse `amendment` row (target set) until
    ops are extracted; enactments explode into an `act_heading` + one `provision` row per §."""
    out = {}
    for res in issue_results:
        iid = res["iid"]
        frozen = frozen_text(iid)
        if frozen is None:
            continue
        located, _ = resolve_acts(frozen, res.get("acts") or [])
        located.sort(key=lambda a: a["start"])
        rows, cur = [], 0
        for a in located:
            s, e = a["start"], a["end"]
            if s > cur:
                _emit(rows, frozen, iid, cur, s, "toc" if cur == 0 else "noise", f"gap@{cur}")
            dk = a.get("datokode")
            if a.get("klass") == "original" and a.get("provisions"):
                provs = _resolve_provisions(frozen, s, e, a["provisions"])
                heading_end = provs[0]["start"] if provs else e
                _emit(rows, frozen, iid, s, heading_end, "act_heading", f"{dk}:heading",
                      datokode=dk, nr=a.get("nr"), date=a.get("date"), title=a.get("title"))
                for i, p in enumerate(provs):
                    pe = provs[i + 1]["start"] if i + 1 < len(provs) else e
                    _emit(rows, frozen, iid, p["start"], pe, "provision", f"{dk}:{p['para']}",
                          datokode=dk, para=p["para"])
            else:
                cite = a.get("target")
                _emit(rows, frozen, iid, s, e, a.get("klass") or "amendment", f"{dk}:body",
                      datokode=dk, nr=a.get("nr"), date=a.get("date"), title=a.get("title"),
                      target=cite_to_datokode(cite), target_cite=cite)
            cur = e
        if cur < len(frozen):
            _emit(rows, frozen, iid, cur, len(frozen), "noise", f"gap@{cur}")
        out[iid] = rows
    return out


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
