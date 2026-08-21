"""Diff reconstruction amendment-capture against the register (source/eval/build_register.py).

INTENT: score how completely our parsed amendment streams reproduce Lovdata's own amendment
    graph, and split every miss into a RECOVERABLE bucket (act already harvested, section
    dropped — fixable by re-parsing) vs an ABSENT bucket (never harvested), so effort goes to
    the omnibus re-parse before the harder harvest/OCR tail. Per target law and corpus-wide.

For each target law, compare the set of amending acts Lovdata records (register, the ORACLE)
against the acts our parsed streams captured, and classify every miss:

  * MIS-TARGETED — the missed act IS in our streams, amending some OTHER law (it was
    harvested; its section for THIS law was dropped, typically an omnibus mono-collapse).
    Recoverable by re-parsing the act text — no new harvest.
  * ABSENT — the act appears in no stream at all: a genuine harvest / OCR coverage gap.

EVAL-ONLY: reads the register, which is derived from the answer key. Reporting only.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
REGISTER = HERE / "data" / "amendment_register.jsonl.gz"
STREAMS = ["amendments.jsonl.gz", "lti_amendments.jsonl.gz",
           "pre2001_amendments.jsonl.gz", "blanket_amendments.jsonl.gz",
           "llm_amendments.jsonl.gz"]
_ID = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]+)")

# a reference set of old, small codes to spotlight
OLD_LAWS = {
    "lov/1918-05-31-4": "avtaleloven 1918",
    "lov/1988-05-13-27": "kjøpsloven 1988",
    "lov/1979-05-18-18": "foreldelsesloven 1979",
    "lov/1939-02-17-1": "gjeldsbrevlova 1939",
    "lov/1980-02-08-2": "panteloven 1980",
    "lov/1965-06-18-6": "sameigelova 1965",
    "lov/1969-06-13-26": "skadeserstatningsloven 1969",
    "lov/1918-08-14-3": "tvangsfullbyrdelse(1918)",
}


def _load_register():
    gt = defaultdict(set)  # target_law -> {amending act ids}
    for line in gzip.open(REGISTER, "rt", encoding="utf-8"):
        r = json.loads(line)
        a = _ID.search(r["act_id"])
        if a:
            gt[r["target_law"]].add(a.group(1))
    return gt


def _load_captured():
    cap = defaultdict(set)          # target_law -> {amending act ids}
    all_amending = set()            # every act id that amends ANY law in our streams
    for s in STREAMS:
        p = HERE / "data" / s
        if not p.exists():
            continue
        for line in gzip.open(p, "rt", encoding="utf-8"):
            r = json.loads(line)
            tl = r.get("target_law") or ""
            tm = _ID.search(tl)
            am = _ID.search(r.get("act_refid") or "")
            if am:
                all_amending.add(am.group(1))
            if tm and am:
                cap[f"lov/{tm.group(1)}"].add(am.group(1))
    return cap, all_amending


def report():
    gt = _load_register()
    cap, all_amending = _load_captured()

    tot_gt = tot_hit = tot_mis = tot_abs = 0
    per_law = []
    for law, acts in gt.items():
        got = cap.get(law, set())
        hit = acts & got
        miss = acts - got
        mistargeted = {m for m in miss if m in all_amending}
        absent = miss - mistargeted
        tot_gt += len(acts); tot_hit += len(hit)
        tot_mis += len(mistargeted); tot_abs += len(absent)
        per_law.append((law, len(acts), len(hit), len(mistargeted), len(absent)))

    print("=== CORPUS TOTALS (register = oracle floor) ===")
    print(f"amending-act edges in register : {tot_gt}")
    print(f"  captured                     : {tot_hit}  ({100*tot_hit//max(tot_gt,1)}%)")
    print(f"  MIS-TARGETED (recoverable)   : {tot_mis}  ({100*tot_mis//max(tot_gt,1)}%)  <- omnibus re-parse")
    print(f"  ABSENT (harvest/OCR gap)     : {tot_abs}  ({100*tot_abs//max(tot_gt,1)}%)")
    print()

    print("=== SPOTLIGHT: old/small codes ===")
    print(f"{'law':32} {'GT':>3} {'hit':>3} {'mis-tgt':>7} {'absent':>6}")
    for law, name in OLD_LAWS.items():
        acts = gt.get(law)
        if not acts:
            print(f"{name:32}  (not in register)")
            continue
        got = cap.get(law, set()); miss = acts - got
        mt = len({m for m in miss if m in all_amending}); ab = len(miss) - mt
        print(f"{name:32} {len(acts):3d} {len(acts & got):3d} {mt:7d} {ab:6d}")
    print()

    # laws where the recoverable (mis-targeted) loss is largest — the fix's payoff ranking
    print("=== TOP 20 laws by RECOVERABLE (mis-targeted) misses — omnibus re-parse payoff ===")
    per_law.sort(key=lambda x: -x[3])
    print(f"{'law':22} {'GT':>3} {'hit':>3} {'mis-tgt':>7} {'absent':>6}")
    for law, ngt, nhit, nmt, nab in per_law[:20]:
        print(f"{law:22} {ngt:3d} {nhit:3d} {nmt:7d} {nab:6d}")


if __name__ == "__main__":
    report()
