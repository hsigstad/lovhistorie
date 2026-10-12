"""Deterministic application-layer re-splice — apply the curated `data/applications.jsonl`
pointer rows at build/runtime with NO LLM. Plugs into `replay` as `ledd_fallback`.

INTENT: convert the sub-provision ledd/punktum/bokstav ops that the regex `ledd.apply` cannot
    resolve on OCR bases (replay flags them today) into applied text — WITHOUT a runtime LLM and
    WITHOUT fabrication. An OFFLINE applicator (Claude subagents; see source/llm + the fold tool)
    reads the provision + the amendment and emits only POINTERS (op_kind + verbatim span anchors)
    into `data/applications.jsonl`. This module re-splices deterministically: locate the anchors in
    the CURRENT provision, splice the op's verbatim new_text in, return the result — or None (so
    replay keeps flagging, leaving the provision at last-known text).
REASONING: the model located; the code holds the text. Every published character is a verbatim slice
    of the public base (the removed span) or the amendment payload (new_text) — 0% fabrication by
    construction. Anchors are RE-RESOLVED every build, so a changed base degrades to "anchor not found
    -> None -> flagged" (safe last-known text), never to silently-wrong output. See
    docs/notes/llm_ledd_applicator.md (staleness rules).
ASSUMES: `data/applications.jsonl` rows {target_law, op_key, op_kind, span_start_anchor,
    span_end_anchor?, base_sha?}. op_key = sha16(target_law, instruction, new_text), computed
    identically here and by the offline populator, so the runtime fallback matches the right row.
ANTI-GAMING / G1: reads only public pointer rows + the public provision text; imports no
    source.llm, never the current/oracle dump or the register. Deterministic — safe on the runtime
    reconstruction path (unlike a live LLM, which stays offline).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
APPLICATIONS = _REPO / "data" / "applications.jsonl"


def op_key(target_law: str, instruction: str, new_text: str) -> str:
    """Stable content identity of an applied op (law + instruction + payload)."""
    tl = (target_law or "").split("/")[-1]
    h = hashlib.sha256("\x00".join([tl, instruction or "", new_text or ""]).encode("utf-8"))
    return h.hexdigest()[:16]


_cache: dict | None = None


def load_applications(path: Path = APPLICATIONS) -> dict:
    """{(target_law, op_key): row}. Cached; call reset_cache() after writing the file."""
    global _cache
    if _cache is None:
        _cache = {}
        if path.exists():
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                _cache[(r["target_law"], r["op_key"])] = r
    return _cache


def reset_cache():
    global _cache
    _cache = None


def _anchor_span(text: str, anchor: str, start: int = 0):
    """Whitespace-tolerant verbatim match of an anchor; (start, end) or None."""
    toks = (anchor or "").split()
    if not toks:
        return None
    m = re.compile(r"\s+".join(re.escape(t) for t in toks)).search(text, start)
    return (m.start(), m.end()) if m else None


def splice(provision: str, new_text: str, row: dict) -> str | None:
    """Apply one pointer row to the current provision. Re-resolves anchors (so a changed base
    fails safely) and returns the spliced text, or None (-> replay flags -> last-known text)."""
    ok = row.get("op_kind")
    s = _anchor_span(provision, row.get("span_start_anchor"))
    if not s:
        return None
    if ok == "insert_after":
        a = s[1]
        return provision[:a] + "\n" + (new_text or "") + provision[a:]
    e = _anchor_span(provision, row.get("span_end_anchor"), s[0])
    if not e:
        return None
    a, b = s[0], e[1]
    if ok == "delete":
        return provision[:a] + provision[b:]
    return provision[:a] + (new_text or "") + provision[b:]      # replace


def make_fallback(target_law: str):
    """Build the `ledd_fallback(provision, instruction, new_text, op_type)` closure replay calls
    when the regex ledd engine can't apply a sub-provision op. Looks up the curated application for
    this (law, op) and re-splices; returns None if absent/unresolvable (replay keeps flagging)."""
    apps = load_applications()
    tl = target_law.split("/")[-1]

    def fallback(provision, instruction, new_text, op_type):
        row = apps.get((tl, op_key(tl, instruction, new_text)))
        if not row:
            return None
        return splice(provision, new_text, row)

    return fallback
