"""Offline populator for the application layer `data/applications.jsonl` — the applicator's
extract + fold glue (sibling of scrape/fold_append.py, for ledd application rather than segmentation).

INTENT: make populating/growing `applications.jsonl` reproducible and gated, not a scratch flow.
    `extract` captures every flagged sub-provision op of a law WITH the provision-state it applies to
    (via a RECORDING replay fallback) and writes per-op case files for the applicator subagent;
    `fold` takes the applicator's span-anchor results, splice-VERIFIES each on the recorded provision,
    and writes verified POINTER rows into applications.jsonl (merge/replace by (law, op_key)).
REASONING: the applicator (apply_prompt.SCHEMA, Claude subagents) only LOCATES spans; this module does
    the fabrication-safe deterministic part — verify the anchors resolve + splice cleanly, else DROP the
    row (flag-don't-fabricate). op_key = ledd_apply.op_key(law, instruction, payload), identical to the
    runtime lookup, so a written row is the one the runtime fallback will use. base_sha pins the
    provision-state for staleness detection. The runtime (ledd_apply) re-verifies anyway, so a stale
    row degrades to "anchor not found -> flagged -> last-known text", never to wrong output.
ASSUMES: public bases/ops via the deterministic pipeline; reads no current/oracle dump or register (G1).
    Between extract and fold, run the applicator Workflow over the case files (see
    docs/notes/llm_ledd_applicator.md "RUN").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from source.parse import pipeline, replay, ledd_apply
from source.scrape import apply_prompt

_REPO = Path(__file__).resolve().parents[2]
APPS = _REPO / "data" / "applications.jsonl"
DEFAULT_OUTDIR = Path("/tmp/lovhist_apply_cases")


def extract(law: str, outdir: Path = DEFAULT_OUTDIR):
    """Capture flagged sub-provision ops of `law` with their provision-state; write case files."""
    dk = law.split("/")[-1]
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    base = pipeline.enactment_base("lov/" + dk)
    ops = pipeline.load_ops("lov/" + dk)
    rec = []

    def fb(provision, instruction, new_text, op_type):
        rec.append({"instruction": instruction, "payload": new_text, "provision": provision})
        return None                                  # record only; leave the op flagged

    replay.replay(base, ops, ledd_fallback=fb)
    seen, cases = set(), []
    for c in rec:
        if not (c["payload"] and len(c["payload"]) > 15 and c["provision"] and len(c["provision"]) > 20):
            continue
        k = (c["instruction"], c["payload"], c["provision"])
        if k in seen:
            continue
        seen.add(k)
        cases.append(c)
    for i, c in enumerate(cases):
        (outdir / f"case_{i}.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "meta.json").write_text(json.dumps({"dk": dk, "cases": cases}, ensure_ascii=False), encoding="utf-8")
    jobs = [{"idx": i, "path": str(outdir / f"case_{i}.json")} for i in range(len(cases))]
    (outdir / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    print(f"extracted {len(cases)} flagged sub-provision cases for {dk} -> {outdir}")
    print(f"next: run the applicator Workflow (apply_prompt.build_prompt + SCHEMA, model sonnet) over "
          f"{outdir}/jobs.json, save results.json, then: apply_fold fold --meta {outdir}/meta.json --results results.json")
    return cases


def apply(meta_path: Path, out_path: Path, reextract: bool = False, model: str = None):
    """Run the llmkit (OpenAI) applicator over a meta.json's cases -> results.json (fold input).
    Cheap + cached: replaces the one-subagent-per-op Workflow. Offline; OPENAI_API_KEY required."""
    from source.llm import ledd_apply_llm
    model = model or ledd_apply_llm.MODEL
    meta = json.loads(Path(meta_path).read_text())
    cases = meta["cases"]
    results = []
    for i, c in enumerate(cases):
        loc = ledd_apply_llm.locate(c["provision"], c["instruction"], c["payload"], model=model, reextract=reextract)
        if loc:
            results.append({"idx": i, **loc})
        if (i + 1) % 25 == 0:
            print(f"  applied {i + 1}/{len(cases)} (located {len(results)})")
    Path(out_path).write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    print(f"located {len(results)}/{len(cases)} ops for {meta['dk']} -> {out_path}")
    return results


def fold(meta_path: Path, results_path: Path, apps_path: Path = APPS):
    """Splice-verify the applicator results on the recorded provisions; write verified pointer rows."""
    meta = json.loads(Path(meta_path).read_text())
    dk, cases = meta["dk"], meta["cases"]
    results = {r["idx"]: r for r in json.loads(Path(results_path).read_text())}
    new_rows, skipped = [], []
    for i, c in enumerate(cases):
        r = results.get(i)
        if not r:
            skipped.append((i, "no result")); continue
        probe = {"op_kind": r.get("op_kind"), "span_start_anchor": r.get("span_start_anchor"),
                 "span_end_anchor": r.get("span_end_anchor")}
        spliced = ledd_apply.splice(c["provision"], c["payload"], probe)
        if spliced is None:
            skipped.append((i, f"anchors unresolved ({r.get('op_kind')})")); continue
        if spliced == c["provision"]:
            skipped.append((i, "no-op splice")); continue
        row = {"target_law": dk, "op_key": ledd_apply.op_key(dk, c["instruction"], c["payload"]),
               "op_kind": r.get("op_kind"), "span_start_anchor": r.get("span_start_anchor"),
               "base_sha": hashlib.sha256(c["provision"].encode("utf-8")).hexdigest()[:16]}
        if r.get("span_end_anchor") and r.get("op_kind") != "insert_after":
            row["span_end_anchor"] = r.get("span_end_anchor")
        new_rows.append(row)

    merged = {}
    if Path(apps_path).exists():
        for line in open(apps_path, encoding="utf-8"):
            line = line.strip()
            if line:
                rr = json.loads(line)
                merged[(rr["target_law"], rr["op_key"])] = rr
    for rr in new_rows:
        merged[(rr["target_law"], rr["op_key"])] = rr
    with open(apps_path, "w", encoding="utf-8") as fh:
        for rr in merged.values():
            fh.write(json.dumps(rr, ensure_ascii=False) + "\n")
    ledd_apply.reset_cache()
    print(f"folded {len(new_rows)} verified rows for {dk} ({len(merged)} total in file); skipped {len(skipped)}")
    for i, why in skipped[:12]:
        print(f"  skip case {i}: {why}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ep = sub.add_parser("extract")
    ep.add_argument("--law", required=True, help="datokode, e.g. 1999-07-02-64")
    ep.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    ap2 = sub.add_parser("apply")
    ap2.add_argument("--meta", required=True)
    ap2.add_argument("--out", required=True)
    ap2.add_argument("--model", default=None)
    ap2.add_argument("--reextract", action="store_true")
    fp = sub.add_parser("fold")
    fp.add_argument("--meta", required=True)
    fp.add_argument("--results", required=True)
    a = ap.parse_args()
    if a.cmd == "extract":
        extract(a.law, a.outdir)
    elif a.cmd == "apply":
        apply(a.meta, a.out, a.reextract, a.model)
    else:
        fold(a.meta, a.results)
