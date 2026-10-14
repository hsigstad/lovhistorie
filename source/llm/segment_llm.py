# OFFLINE segmentation via llmkit/OpenAI (gpt-4.1) — the Claude-weekly-free alternative to the
# Opus/Sonnet Workflow subagents. NOT the runtime path (runtime reads the folded segments.jsonl).
"""llmkit (OpenAI) issue SEGMENTER — same ordered-starts contract as segment_prompt, via one cached
API call per issue/chunk instead of a Workflow subagent.

INTENT: evaluate (and, if quality holds, run) segmentation off the Claude subscription weekly.
    Returns {"segments": [...]} in the segment_prompt.SCHEMA shape, so fold_segmentation.tile_ordered /
    stitch_chunks consume it unchanged.
REASONING: locate-not-compute (verbatim start anchors; deterministic tiling). Shares the canonical
    instruction text with the subagent prompt (segment_prompt.PROMPT_TEMPLATE) so the two paths don't
    drift. Harder task than the applicator (long OCR, many anchors, gap-free) — VALIDATE vs the Claude
    segmentation before trusting it (docs/notes/llm_ledd_applicator.md model note).
ASSUMES: OPENAI_API_KEY; the issue text is public-domain OCR (G1). Offline only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

_REPO = Path(__file__).resolve().parents[2]
try:
    from llmkit import ExtractionSchema, LLMCache, extract
except ModuleNotFoundError:  # pragma: no cover
    _PKG = _REPO.parent.parent / "packages" / "llmkit"
    if _PKG.exists() and str(_PKG) not in sys.path:
        sys.path.insert(0, str(_PKG))
    from llmkit import ExtractionSchema, LLMCache, extract

from source.scrape import segment_prompt

MODEL = "gpt-4.1"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "segment_llm")

# System prompt = the canonical subagent instructions minus the "read this file" framing (the issue
# text is supplied inline in the user message instead). Keeps the two paths in lockstep.
_body = segment_prompt.PROMPT_TEMPLATE.split("## What the issue looks like", 1)[1]
SYSTEM = ("You are segmenting one issue of *Norsk Lovtidend* (the Norwegian official gazette), OCR'd "
          "from a public-domain scan. The issue's full text is given in the user message. Work solely "
          "from that text.\n\n## What the issue looks like" + _body).replace("__CHECKLIST__", "(none provided — rely on the text)")


class _Seg(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    kind: str = ""
    start_anchor: str = ""
    datokode: str = ""
    para: str = ""
    target_cite: str = ""
    instrument: str = ""
    op_kind: str = ""
    from_: str = Field("", alias="from")
    to: str = ""
    position: str = ""


class IssueSegmentation(ExtractionSchema):
    schema_name: ClassVar[str] = "lovhistorie_segmentation"
    schema_version: ClassVar[str] = "v1"
    segments: list[_Seg] = []


def segment_text(text: str, *, client=None, model: str = MODEL, cache: LLMCache = CACHE,
                 reextract: bool = False, max_tokens: int = 16000) -> dict:
    """Return {"segments": [...]} (segment_prompt.SCHEMA shape) for one issue/chunk, or empty."""
    if not text:
        return {"segments": []}
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    from llmkit.cache import text_hash
    try:
        res = extract(doc_id="segment#" + text_hash(text), text=text,
                      system_prompt=SYSTEM, user_prompt=text,
                      schema=IssueSegmentation, model=model, cache=cache, client=client,
                      reextract=reextract, use_structured_outputs=True, schema_in_cache_key=True,
                      max_tokens=max_tokens)
    except Exception as e:
        print(f"  segment error: {str(e)[:100]}", file=sys.stderr)
        return {"segments": []}
    if not res.valid or res.parsed is None:
        return {"segments": []}
    out = []
    for s in res.parsed.segments:
        d = s.model_dump(by_alias=True)
        out.append({k: v for k, v in d.items() if v})      # drop empty fields
    return {"segments": out}
