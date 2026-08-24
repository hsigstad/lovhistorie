"""POINTER-based holistic amendment application — reconstruct a provision by REFERENCE, not prose.

INTENT: the deterministic ledd engine mangles sub-provision ops on unmarked OCR bases (rettsgebyr §14:
    24 captured amendments -> 0.09). An LLM CAN consolidate them (§14 -> 0.8), but having it regenerate
    the full statutory text is (a) costly in output tokens and (b) a fabrication risk. Instead the model
    outputs only POINTERS — an ordered list of segments, each either {"amendment": N} (use that
    amendment's whole verbatim NEW text) or {"original_from","original_to"} (a verbatim span of the
    enactment) — and DETERMINISTIC code fetches the source text and assembles it. The model reasons
    about supersession/order (the hard part) but never emits statutory text.
REASONING: this makes the "0% fabricated" guarantee AUTOMATIC (every published character is a verbatim
    slice of base or an amendment, by construction — the model only chose references), collapses
    verification to "locate the base anchors", and cuts output ~30-100x so a cheap model (gpt-4.1-mini)
    handles the bulk at ~$0.0003/provision; only the reasoning-hard tail escalates. OFFLINE + cached;
    runtime replays the baked, verified text (rule 3).
ASSUMES: OPENAI_API_KEY; base_text + ops are public-domain (enactment + captured amendments), never the
    current/answer text (G1). `as_of` filters ops to a point in time so future/mis-dated ops don't
    overshoot.
ANTI-GAMING: reads only the public provision + its amendments (cached); the model emits only references,
    so it cannot leak or invent answer text. G1-safe.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
try:
    from llmkit import LLMCache
except ModuleNotFoundError:  # pragma: no cover
    _PKG = _REPO.parent.parent / "packages" / "llmkit"
    if _PKG.exists() and str(_PKG) not in sys.path:
        sys.path.insert(0, str(_PKG))
    from llmkit import LLMCache

from source.llm.target_localize import _build_norm, _hh, _locate, _norm

CACHE = LLMCache(_REPO / "data" / "llm_cache" / "pointer_apply")
_REASONING = ("o1", "o3", "o4", "gpt-5")

_SYS = (
    'Consolidate the statutory provision: decide, IN ORDER, which SOURCE each part of the FINAL '
    'consolidated text comes from. Do NOT write statutory text yourself.\n'
    'Return JSON {"segments":[...]} where each segment is EITHER\n'
    '  {"amendment": N}  -> use amendment N\'s whole NEW text, or\n'
    '  {"original_from":"<first ~5 words, verbatim>","original_to":"<last ~5 words, verbatim>"} '
    '-> a span copied from the ENACTMENT (ALWAYS give BOTH short anchors, never the whole text).\n'
    'Apply amendments in chronological order; a later "skal lyde" on the SAME part overrides earlier '
    'ones; drop repealed parts; insert "nytt/ny" parts. The concatenation of the segments must equal '
    'the provision\'s current consolidated text.\n'
    'CRITICAL — MIS-FILED AMENDMENTS: an amendment in the list may have been wrongly attributed to '
    'this provision. If an amendment\'s NEW text is about a clearly DIFFERENT legal subject than this '
    'provision (judged from the enactment text), it does NOT belong here — SKIP it entirely. Apply '
    'only amendments whose content fits this provision; if ALL amendments are mis-filed, return the '
    'enactment text unchanged.')


@dataclass
class PointerReport:
    model: str = ""
    n_segments: int = 0
    n_ops: int = 0
    unlocated: int = 0            # original spans whose anchors were not found (dropped)
    out_tokens: int = 0
    cached: bool = False
    valid: bool = True


def _ordered(ops, as_of):
    keep = [o for o in ops if (o.get("date") or "0000") <= as_of]
    keep.sort(key=lambda o: (o.get("date") or "", o.get("act") or ""))
    return keep


def _slice_base(base_text, a, b):
    """Verbatim base span from anchor `a` (start) to anchor `b` (end), whitespace-tolerant. None if
    either anchor is not located — flag-don't-fabricate. If `b` is empty, the model gave the whole
    span as `a` (a "keep the original" segment); accept it iff it is a verbatim (ws-tolerant) slice of
    the base — still 0% fabrication, just a coarser pointer."""
    a = str(a or "").strip()
    b = str(b or "").strip()
    if not a:
        return None
    if not b:
        nt, off = _build_norm(base_text)
        na = _norm(a)
        pos = nt.find(na)
        return base_text[off[pos]:(off[pos + len(na) - 1] + 1)] if pos >= 0 else None
    nt, off = _build_norm(base_text)
    i = _locate(a, base_text, nt, off, 0)
    if i < 0:
        return None
    j = _locate(b, base_text, nt, off, i)
    if j < 0:
        return None
    end = j + len(_norm(b))
    return base_text[i:(off[end - 1] + 1 if end <= len(off) else len(base_text))]


def apply(para, base_text, ops, *, client=None, model="gpt-4.1-mini", cache=CACHE, reextract=False,
          as_of="2025-12-31"):
    """(assembled_text, PointerReport). The model returns pointers; we assemble verbatim from source.
    None assembled text if nothing usable. Cached + G1-safe."""
    used = _ordered(ops, as_of)
    rep = PointerReport(model=model, n_ops=len(used))
    if not base_text or not used:
        rep.valid = False
        return None, rep
    block = "\n".join(
        f"[A{i}] {o.get('instruction')}  NEW={(o.get('new_text') or '')!r}"
        + (" (REPEAL)" if o.get("change_type") == "repeal" else "")
        for i, o in enumerate(used, 1))
    up = f"ENACTMENT:\n{base_text}\n\nAMENDMENTS:\n{block}"
    key = cache.key(f"ptr#{para}#{model}", _hh(_SYS, up), model)   # _SYS in key: prompt change busts cache
    hit = cache.get(key) if not reextract else None
    if hit is not None:
        content = hit.extraction.get("content", "")
        rep.out_tokens, rep.cached = hit.extraction.get("out", 0), True
    else:
        if client is None:
            from openai import OpenAI
            client = OpenAI()
        kw = dict(messages=[{"role": "system", "content": _SYS}, {"role": "user", "content": up}],
                  response_format={"type": "json_object"})
        if model.startswith(_REASONING):
            kw["max_completion_tokens"] = 16000
        else:
            kw["max_tokens"] = 2000
        try:
            r = client.chat.completions.create(model=model, **kw)
        except Exception:
            rep.valid = False
            return None, rep
        content = r.choices[0].message.content or ""
        rep.out_tokens = r.usage.completion_tokens if r.usage else 0
        cache.put(key, {"content": content, "out": rep.out_tokens}, doc_id=f"ptr#{para}", model=model)
    try:
        segs = json.loads(content).get("segments", [])
    except Exception:
        rep.valid = False
        return None, rep
    parts = []
    for s in segs:
        rep.n_segments += 1
        if "amendment" in s:
            m = re.search(r"\d+", str(s["amendment"]))
            i = int(m.group()) if m else 0
            if 1 <= i <= len(used):
                parts.append((used[i - 1].get("new_text") or "").strip())
        elif "original_from" in s:
            sl = _slice_base(base_text, s.get("original_from", ""), s.get("original_to", ""))
            if sl:
                parts.append(sl.strip())
            else:
                rep.unlocated += 1
    out = " ".join(p for p in parts if p)
    return (out or None), rep
