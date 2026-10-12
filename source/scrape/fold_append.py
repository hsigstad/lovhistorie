"""Incremental append tool for the curated segmentation corpus (`data/segments.jsonl`).

INTENT: the orchestration half of the Friday full-harvest segmentation
    (docs/notes/friday_segmentation_worklist.md). `build_segments.py` BOOTSTRAPS the
    corpus once from cached segmentations; this appends NEW issues one gated batch at a
    time from fresh Claude-subagent output. Two modes:
      prepare --iids a,b,...   Write each issue's frozen OCR to <outdir>/<iid>.txt (one-shot)
          or <outdir>/<iid>_<cidx>.txt (chunked, if chars > --chunk-threshold), build the
          segment_prompt per unit, emit <outdir>/jobs.json. A Workflow then runs one
          subagent per unit (segment_prompt.SCHEMA) and collects {iid,cidx,cstart,cend,segments}.
      fold --results r.json    Group results by iid, fold via fold_segmentation.stitch_chunks
          (chunked) or tile_ordered (one-shot), REPLACE that iid's rows in segments.jsonl
          (untouched issues kept VERBATIM so the diff is only the new/changed issues), refresh
          segments_meta.json. The caller then runs the two commit gates + commits.
REASONING: all fold LOGIC is the tracked fold_segmentation.py (anchors -> offsets, verify,
    tile, furniture-split); this is thin I/O around it. Order-preserving write + verbatim
    retention of untouched issues keeps each batch a clean, reviewable, pure-addition diff.
ASSUMES: frozen issues under data/lovtidend_text; data/segments.jsonl + segments_meta.json exist.
ANTI-GAMING / G1: reads only public OCR + the agent's verbatim pointers; never the current
    dump / oracle / register. Offline harness tooling; not on the reconstruction path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from source.scrape import fold_segmentation as F
from source.scrape import segment_prompt as P

_REPO = Path(__file__).resolve().parents[2]
SEG = _REPO / "data" / "segments.jsonl"
META = _REPO / "data" / "segments_meta.json"
DEFAULT_OUTDIR = Path("/tmp/lovhist_seg_jobs")


def _meta_for(frozen: str) -> dict:
    return {"sha": hashlib.sha256(frozen.encode()).hexdigest()[:16], "n_chars": len(frozen)}


def _chunk_prompt(path, cidx, ntot):
    """The one-shot prompt, re-headed to say the file is a PORTION of a larger issue."""
    note = (f"NOTE: this file is PORTION {cidx+1} of {ntot} of one Lovtidend issue (it was "
            f"split for size). Segment ONLY what is in this file. It may begin or end "
            f"mid-unit; still give a verbatim start_anchor for every unit that STARTS in "
            f"this portion. Front matter / colophon appear only in the first/last portion.\n\n")
    return note + P.build_prompt(path, [])


def prepare(iids, outdir=DEFAULT_OUTDIR, target=80000, overlap=12000, chunk_threshold=100000):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for iid in iids:
        frozen = F.frozen_text(iid)
        if frozen is None:
            print(f"SKIP {iid}: frozen text missing", file=sys.stderr)
            continue
        if len(frozen) > chunk_threshold:
            ranges = F.chunk_ranges(frozen, target=target, overlap=overlap)
            for cidx, (cs, ce) in enumerate(ranges):
                txt = outdir / f"{iid}_{cidx}.txt"
                txt.write_text(frozen[cs:ce], encoding="utf-8")
                jobs.append({"iid": iid, "cidx": cidx, "cstart": cs, "cend": ce,
                             "txt": str(txt), "prompt": _chunk_prompt(str(txt), cidx, len(ranges))})
        else:
            txt = outdir / f"{iid}.txt"
            txt.write_text(frozen, encoding="utf-8")
            jobs.append({"iid": iid, "cidx": None, "cstart": 0, "cend": len(frozen),
                         "txt": str(txt), "prompt": P.build_prompt(str(txt), [])})
    (outdir / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    nchunk = sum(1 for j in jobs if j["cidx"] is not None)
    print(f"prepared {len(jobs)} jobs ({len(set(j['iid'] for j in jobs))} issues, "
          f"{nchunk} chunk-units) -> {outdir/'jobs.json'}")
    return jobs


def _fold_one(iid, items, frozen):
    """items = list of {segments, cidx?, cstart?, cend?} for ONE iid -> (rows, misses)."""
    if any(it.get("cidx") is not None for it in items):
        chunk_results = [{"cstart": it["cstart"], "cend": it["cend"],
                          "segments": it.get("segments") or []} for it in items]
        return F.stitch_chunks(iid, chunk_results, frozen)
    return F.tile_ordered(iid, items[0].get("segments") or [], frozen)


def fold(results_path, seg_path=SEG, meta_path=META):
    results = json.loads(Path(results_path).read_text())
    by_iid = defaultdict(list)
    for r in results:
        by_iid[r["iid"]].append(r)
    meta = json.loads(Path(meta_path).read_text()) if Path(meta_path).exists() else {}

    # Preserve the EXISTING issue order + untouched lines VERBATIM (no re-serialization),
    # so untouched issues are byte-identical and the diff shows only new/changed issues.
    order, lines_by_iid = [], defaultdict(list)
    if Path(seg_path).exists():
        for l in open(seg_path):
            iid = json.loads(l)["issue_id"]
            if iid not in lines_by_iid:
                order.append(iid)
            lines_by_iid[iid].append(l if l.endswith("\n") else l + "\n")
    for iid in by_iid:
        if iid not in lines_by_iid:
            order.append(iid)

    summary = {}
    for iid, items in by_iid.items():
        frozen = F.frozen_text(iid)
        if frozen is None:
            summary[iid] = {"error": "frozen missing"}
            lines_by_iid.pop(iid, None)
            continue
        # Guard: a chunked issue with an empty chunk would collapse that chunk's whole span
        # into one swallowing segment (silent coverage loss). Refuse to fold it — re-run the
        # empty chunk first. One-shot issues may legitimately be tiny, so only guard chunked.
        empty = [it.get("cidx") for it in items if not it.get("segments")]
        if empty and any(it.get("cidx") is not None for it in items):
            summary[iid] = {"error": f"empty chunk(s) {empty} — re-run before folding"}
            lines_by_iid.pop(iid, None)
            continue
        rows, misses = _fold_one(iid, items, frozen)
        rows.sort(key=lambda r: r["start"])
        lines_by_iid[iid] = [json.dumps(r, ensure_ascii=False) + "\n" for r in rows]
        meta[iid] = _meta_for(frozen)
        summary[iid] = {"rows": len(rows), "misses": len(misses),
                        "amend_op": sum(1 for r in rows if r["klass"] == "amend_op"),
                        "provision": sum(1 for r in rows if r["klass"] == "provision"),
                        "other": sum(1 for r in rows if r["klass"] == "other")}
        if misses:
            summary[iid]["miss_samples"] = misses[:5]

    total = 0
    with open(seg_path, "w", encoding="utf-8") as fh:
        for iid in order:
            for l in lines_by_iid.get(iid, []):
                fh.write(l)
                total += 1
    Path(meta_path).write_text(json.dumps(meta, ensure_ascii=False, indent=0), encoding="utf-8")
    print(json.dumps({"folded_issues": len(by_iid), "total_rows_now": total,
                      "per_issue": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prepare")
    pp.add_argument("--iids", required=True, help="comma-separated issue ids")
    pp.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    pp.add_argument("--target", type=int, default=80000)
    pp.add_argument("--overlap", type=int, default=12000)
    pp.add_argument("--chunk-threshold", type=int, default=100000)
    fp = sub.add_parser("fold")
    fp.add_argument("--results", required=True)
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.iids.split(","), a.outdir, a.target, a.overlap, a.chunk_threshold)
    else:
        fold(a.results)
