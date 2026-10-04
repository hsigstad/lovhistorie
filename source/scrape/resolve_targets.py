"""Work-the-queue pass: resolve `target-missing` amendment segments by LAW NAME.

INTENT: many amend/repeal segments in `data/segments.jsonl` have no `target` datokode
    because they cite the amended law by NAME ("om endringer i skatteloven", "lov om
    jordmødre") rather than by date+nr. Match that name against the public law register's
    titles and fill the target where the match is UNAMBIGUOUS (exactly one datokode).
REASONING: the amendment's own title is public source evidence for which law it targets;
    the register supplies the name->datokode map. Only single-match (unambiguous) fills are
    written — ambiguous names (e.g. two skatteloven) are left for human review, never guessed.
    This shrinks the biggest classification_qa bucket; the --diff gate confirms no regression.
ASSUMES: `data/segments.jsonl` + `data/law_register.jsonl`. Idempotent; zero LLM.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
SEG = _REPO / "data" / "segments.jsonl"
REG = _REPO / "data" / "law_register.jsonl"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _name_index(reg):
    short, longp = defaultdict(set), defaultdict(set)
    for e in reg:
        t = e.get("title") or ""
        for m in re.finditer(r"\(([^)]*lov[ae]n?[^)]*)\)", t, re.I):
            for tok in re.findall(r"\b\w+lov[ae]n?\b", m.group(1), re.I):
                short[_norm(tok)].add(e["datokode"])
        for tok in re.findall(r"\b\w+lov[ae]n?\b", t, re.I):
            short[_norm(tok)].add(e["datokode"])
        lm = re.search(r"\blov\s+om\s+(.+?)(?:\s*\(|$)", t, re.I)
        if lm:
            longp[_norm(lm.group(1))].add(e["datokode"])
    return short, longp


def _resolve(title, short, longp):
    for tok in re.findall(r"\b\w+lov[ae]n?\b", title or "", re.I):
        h = short.get(_norm(tok))
        if h and len(h) == 1:
            return next(iter(h))
    lm = re.search(r"\blov\s+om\s+(.+)$", title or "", re.I)
    if lm:
        p = _norm(lm.group(1))
        if p in longp and len(longp[p]) == 1:
            return next(iter(longp[p]))
        cand = {dk for ph, dks in longp.items()
                if len(p) > 8 and (ph.startswith(p) or p.startswith(ph)) for dk in dks}
        if len(cand) == 1:
            return next(iter(cand))
    return None


def run(write=True):
    reg = [json.loads(l) for l in open(REG)]
    short, longp = _name_index(reg)
    rows = [json.loads(l) for l in open(SEG)]
    filled = 0
    for s in rows:
        if s.get("klass") in ("amend", "repeal") and not s.get("target"):
            dk = _resolve(s.get("title"), short, longp)
            if dk:
                s["target"] = dk
                s["target_by"] = "name"      # provenance: resolved from the title, not parsed
                filled += 1
    if write and filled:
        with open(SEG, "w", encoding="utf-8") as fh:
            for s in rows:
                fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    return filled


if __name__ == "__main__":
    n = run()
    print(f"resolved {n} target-missing segments by name -> {SEG.relative_to(_REPO)}")
