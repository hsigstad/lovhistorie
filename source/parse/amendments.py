"""Load parsed Lovtidend amendments for a law — the replay input.

INTENT: hand the replay engine a clean, ordered stream of ops per law from the
    upstream Lovtidend parse (data/amendments.jsonl.gz), so the omnibus-isolation
    problem is already solved and the engine sees only this law's changes.
REASONING: filter by target_law, sort by *resolved* entry-into-force date; classify
    each op from its instruction (full replace / add / repeal / sub-provision).
ASSUMES: data/amendments.jsonl.gz has one row per (act, target_law, provision op)
    with fields target_law, instruction, new_text, change_type,
    date_in_force_resolved. This file is a DERIVED, git-ignored input (from the
    Lovtidend dumps); it is not an answer key (it is enactment+amendment source).
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "amendments.jsonl.gz"

_PARA = re.compile(r"§\s*(\d+(?:-\d+)?[a-z]?)")


def classify(instruction: str):
    """(paragraf_id, kind) where kind ∈ {replace, add, repeal, subprovision, other}."""
    instr = instruction or ""
    m = _PARA.search(instr)
    para = "§" + m.group(1) if m else None
    if re.search(r"oppheves", instr):
        return para, "repeal"
    if re.search(r"\bny\s+§", instr, re.I):
        return para, "add"
    if re.search(r"\b(?:ledd|punktum|bokstav|nr\.)\b", instr):
        return para, "subprovision"
    if para and "skal lyde" in instr:
        return para, "replace"
    return para, "other"


# The pre-2001 amendment stream, OCR-parsed from the NB Lovtidend gazette by
# source.parse.gazette (--build). Same schema as the LTI dump; it is enactment+
# amendment SOURCE (public-domain gazette), NOT an answer key — LTI only covers
# 2001+, so this is the only source of pre-2001 amendments. Absent → skipped.
PRE2001 = DATA.parent / "pre2001_amendments.jsonl.gz"


def _ops_from(path: Path, target_law: str):
    """Parse one jsonl.gz amendment file into ops for `target_law` (unordered)."""
    ops = []
    if not path.exists():
        return ops
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("target_law") != target_law:
                continue
            para, kind = classify(d.get("instruction"))
            ops.append({
                "para": para,
                "kind": kind,
                "instruction": d.get("instruction"),
                "new_text": d.get("new_text"),
                "date": d.get("date_in_force_resolved") or d.get("date_in_force"),
                "act": d.get("act_refid"),
            })
    return ops


def load_for(target_law: str, data: Path = DATA):
    """Ordered ops for one law (target_law like 'lov/1986-06-20-35'), merging the LTI
    stream (2001+) with the gazette-OCR pre-2001 stream, sorted by resolved in-force
    date. The two cover disjoint date ranges (pre-2001 vs 2001+); dedup by
    (act, para, date, instruction) guards the boundary against any overlap."""
    ops = _ops_from(data, target_law) + _ops_from(PRE2001, target_law)
    seen, uniq = set(), []
    for o in ops:
        key = (o["act"], o["para"], o["date"], o["instruction"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(o)
    uniq.sort(key=lambda o: (o["date"] or "", o["act"] or ""))
    return uniq


def target_laws(data: Path = DATA):
    """Set of target_law ids present (for corpus iteration)."""
    seen = set()
    with gzip.open(data, "rt", encoding="utf-8") as fh:
        for line in fh:
            seen.add(json.loads(line).get("target_law"))
    return seen
