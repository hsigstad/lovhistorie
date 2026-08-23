"""LLM ledd-marker for OCR enactment bases — inserts (N) ledd markers so the ledd engine can address
sub-provisions.

INTENT: the pre-2001 OCR enactment bases are flattened prose with NO ledd markers, so an amendment
    like "§ 21 annet ledd skal lyde:" cannot address the 2nd ledd → the ledd engine returns None and
    the op is DROPPED (avtaleloven applies 0/6 sub-provision amendments; aksjeloven, whose XML base
    HAS (N) markers, applies 94/131). Marking the ledd boundaries in each OCR provision unblocks all
    those amendments. The ledds ARE in the text (as consecutive numbered paragraphs); they're just
    unmarked. This localizes each ledd's start (verbatim anchor) and inserts a "(N) " marker.
REASONING: localize-then-verify — the model emits the first few words of each ledd (a verbatim
    source slice); the deterministic layer locates it and inserts the marker. A not-found anchor is
    skipped (flag-don't-fabricate); the provision text between markers is untouched source. OFFLINE
    base-prep (like segment.py), so runtime reconstruction stays deterministic (rule 3).
ASSUMES: OPENAI_API_KEY; `text` is a public-domain OCR provision body (never the current/answer text).
ANTI-GAMING: reads only the public OCR provision + the model's boundary anchors (cached). G1-safe.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import ClassVar

_REPO = Path(__file__).resolve().parents[2]
try:
    from llmkit import ExtractionSchema, LLMCache, extract
except ModuleNotFoundError:  # pragma: no cover
    _PKG = _REPO.parent.parent / "packages" / "llmkit"
    if _PKG.exists() and str(_PKG) not in sys.path:
        sys.path.insert(0, str(_PKG))
    from llmkit import ExtractionSchema, LLMCache, extract

from pydantic import BaseModel

from source.llm.target_localize import _build_norm, _locate, _norm

MODEL = "gpt-4.1-mini"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "ledd_marks")
PROMPT = """You are given the text of ONE provision (§) of a Norwegian statute, as OCR'd running prose.
A provision is made of one or more LEDD (numbered paragraphs / clauses). In the original law each
ledd is a separate paragraph, but the OCR has run them together without numbers.

TASK: identify where each ledd BEGINS (after the first — the first ledd starts at the very beginning).
For each ledd after the first, return `anchor`: the first 4-8 words of that ledd, copied VERBATIM from
the text, so it can be located. A new ledd is a new top-level clause/paragraph (often starting a new
sentence with a new grammatical subject: "Dersom …", "Har …", "En …", "Blir …", "Kongen …"), NOT a
mid-sentence continuation or a sub-list item. If the provision is a single ledd, return an empty list.
Copy anchors verbatim; order them as they appear."""


class LeddStart(BaseModel):
    anchor: str


class LeddStarts(ExtractionSchema):
    schema_name: ClassVar[str] = "lovhistorie_ledd_starts"
    schema_version: ClassVar[str] = "v1"
    starts: list[LeddStart] = []


def mark_ledds(text: str, *, client=None, model: str = MODEL, cache: LLMCache = CACHE,
               reextract: bool = False, doc_id: str = "") -> str:
    """Return `text` with '(N) ' ledd markers inserted at each located ledd start. Idempotent: if the
    text already has (1)/(2) markers, returns it unchanged. Falls back to the original text on any
    failure (never fabricates structure)."""
    if re.search(r"\(\s*[12]\s*\)", text):        # already marked (e.g. clean XML base)
        return text
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    try:
        res = extract(doc_id=f"ledd#{doc_id}#{hash(text) & 0xffffffff:x}", text=text,
                      system_prompt=PROMPT, user_prompt=text, schema=LeddStarts, model=model,
                      cache=cache, client=client, reextract=reextract,
                      use_structured_outputs=True, schema_in_cache_key=True, max_tokens=2000)
    except Exception:
        return text
    if not res.valid or res.parsed is None or not res.parsed.starts:
        return text
    norm_text, offsets = _build_norm(text)
    cuts = []
    cursor = 0
    for s in res.parsed.starts:
        pos = _locate(s.anchor, text, norm_text, offsets, cursor)
        if pos > 0:
            cuts.append(pos)
            cursor = pos + 1
    if not cuts:
        return text
    # boundaries: [0, cut1, cut2, …, len] → segments, each prefixed with its "(N) " marker
    bounds = [0] + cuts + [len(text)]
    segs = [f"({i + 1}) {text[bounds[i]:bounds[i + 1]].strip()}" for i in range(len(bounds) - 1)]
    return " ".join(" ".join(segs).split())


if __name__ == "__main__":
    import json
    from source.parse import pipeline
    base = pipeline.enactment_base(sys.argv[1] if len(sys.argv) > 1 else "lov/1918-05-31-4")
    for p in ["§21", "§17"]:
        print(f"{p}:", repr(mark_ledds(base.get(p, ""))[:200]))
