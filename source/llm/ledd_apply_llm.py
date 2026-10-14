# OFFLINE populator for the application layer (data/applications.jsonl). NOT the runtime path.
# Runtime application is deterministic (source/parse/ledd_apply.py re-splices the stored anchors);
# this module only PROPOSES the anchors offline via a cached OpenAI call, cheaply + reproducibly.
"""llmkit (OpenAI) ledd-APPLICATOR — locate the span an amendment edits; emit only anchors + op_kind.

INTENT: the scalable offline backend for `apply_fold` — replaces the one-Claude-subagent-per-op
    prototype (~38k tokens/op) with a direct cached OpenAI call (~3k tokens/op, ~$0.0003 on a mini
    model), so populating all ~4,100 flagged sub-provision ops costs a few dollars of OpenAI, not the
    Claude weekly limit. Same contract as the subagent: given a provision + instruction + payload, the
    model returns op_kind + VERBATIM span anchors into the provision; it never writes statutory text.
REASONING: locate-not-compute + llmkit (feedback: use llmkit for classification, not hand-rolled SDK).
    Structured outputs enforce the schema server-side; the cache (sha of provision+model) makes reruns
    free and the run auditable (prompt hash, tokens, model_version per op). Deterministic
    `ledd_apply.splice` holds the text and re-verifies anchors, so 0% fabrication + safe staleness.
ASSUMES: OPENAI_API_KEY in env; `provision`/`instruction`/`payload` are public-domain (never the
    current/oracle dump or register) — G1. Offline only; the recon runtime never imports this.
"""
from __future__ import annotations

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

from source.scrape import apply_prompt

MODEL = "gpt-4.1"   # best-tested OpenAI tier (0.909 vs engine); see docs/notes/llm_ledd_applicator.md model comparison
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "ledd_apply")


class OpLocation(ExtractionSchema):
    schema_name: ClassVar[str] = "lovhistorie_ledd_apply"
    schema_version: ClassVar[str] = "v1"
    op_kind: str = ""            # replace | insert_after | delete
    span_start_anchor: str = ""
    span_end_anchor: str = ""
    reasoning: str = ""


def locate(provision: str, instruction: str, payload: str, *, client=None, model: str = MODEL,
           cache: LLMCache = CACHE, reextract: bool = False) -> dict | None:
    """Return {op_kind, span_start_anchor, span_end_anchor} for one op, or None (-> stays flagged)."""
    if not provision or not instruction:
        return None
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    from llmkit.cache import text_hash
    _sep = "\x00"
    doc_id = "leddapply#" + text_hash(_sep.join([provision, instruction, payload or ""]))
    try:
        res = extract(doc_id=doc_id, text=provision,
                      system_prompt=apply_prompt.INSTRUCTIONS,
                      user_prompt=apply_prompt.user_message(provision, instruction, payload or ""),
                      schema=OpLocation, model=model, cache=cache, client=client, reextract=reextract,
                      use_structured_outputs=True, schema_in_cache_key=True, max_tokens=500)
    except Exception as e:
        print(f"  locate error: {str(e)[:80]}", file=sys.stderr)
        return None
    if not res.valid or res.parsed is None:
        return None
    p = res.parsed
    if p.op_kind not in ("replace", "insert_after", "delete") or not p.span_start_anchor.strip():
        return None
    return {"op_kind": p.op_kind, "span_start_anchor": p.span_start_anchor.strip(),
            "span_end_anchor": p.span_end_anchor.strip(), "reasoning": p.reasoning}
