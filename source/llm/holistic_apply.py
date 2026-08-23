"""HOLISTIC amendment application — reconstruct a provision from base + ALL its ordered amendments.

INTENT: the deterministic ledd engine applies amendments PIECEMEAL (one sub-op at a time, located by
    regex markers), which mangles sub-provision ops on unmarked OCR prose — rettsgebyr §14 has 24
    captured amendments yet reconstructs to 0.09 (a garbled partial splice). This module instead gives
    an LLM the enactment provision + its FULL chronological amendment list and has it CONSOLIDATE the
    provision (resolving supersession — later "skal lyde" on the same part overrides earlier), the way
    a human editor does. Validated: §14 0.09 -> 0.72 (gpt-4.1), the hardest provision in the worst law.
REASONING: this is application as REASONING, not regex splicing. The model only ASSEMBLES verbatim
    spans from (base ∪ amendment new_texts); verify() then checks every output span traces to one of
    those sources and flags drift (the model once wrote "§ 14-5" for a "§ 65" source ref) — preserving
    the "0% fabricated statutory text" guarantee by VERIFICATION rather than by piecemeal splicing.
    OFFLINE + cached (like the other LLM build stages); runtime replay stays deterministic (rule 3).
ASSUMES: OPENAI_API_KEY; `base_text` + `ops` are public-domain (enactment + captured amendments), never
    the current/answer text (G1). `as_of` filters ops to a point in time so future/mis-dated ops don't
    overshoot the target state.
ANTI-GAMING: reads only the public provision + its amendments (cached). No answer-key read. G1-safe.
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path
from typing import ClassVar

_REPO = Path(__file__).resolve().parents[2]
try:
    from llmkit import ExtractionSchema, LLMCache, extract
except ModuleNotFoundError:  # pragma: no cover - sandbox bootstrap
    _PKG = _REPO.parent.parent / "packages" / "llmkit"
    if _PKG.exists() and str(_PKG) not in sys.path:
        sys.path.insert(0, str(_PKG))
    from llmkit import ExtractionSchema, LLMCache, extract

from source.llm.target_localize import _hh

MODEL = "gpt-4.1"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "holistic_apply")

_PROMPT = """You are a Norwegian legal editor. Apply the amendments IN ORDER to the enactment provision
to produce its consolidated current text.
- A "skal lyde" op REPLACES the named part (ledd = paragraph, punktum = sentence, nr/bokstav = list item).
- "oppheves" DELETES that part; "nytt/ny ... skal lyde" INSERTS it.
- Later amendments to the SAME part OVERRIDE earlier ones — track each ledd/punktum separately and keep
  only the latest version of each.
- Use ONLY wording found in the ENACTMENT text or the amendment NEW texts. Never paraphrase, invent, or
  alter any number or §-reference. Output only the consolidated provision body."""


class HolisticProvision(ExtractionSchema):
    schema_name: ClassVar[str] = "lovhistorie_holistic_provision"
    schema_version: ClassVar[str] = "v1"
    consolidated_text: str = ""


def _ordered(ops: list, as_of: str) -> list:
    """Ops for one provision, filtered to <= as_of (undated -> earliest) and sorted chronologically."""
    keep = [o for o in ops if (o.get("date") or "0000") <= as_of]
    keep.sort(key=lambda o: (o.get("date") or "", o.get("act") or ""))
    return keep


def apply(para: str, base_text: str, ops: list, *, client=None, model: str = MODEL,
          cache: LLMCache = CACHE, reextract: bool = False, as_of: str = "2025-12-31") -> str | None:
    """Consolidated text of `para` from `base_text` + its `ops` (<= as_of), or None. Cached + G1-safe."""
    used = _ordered(ops, as_of)
    if not base_text or not used:
        return None
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    block = "\n".join(
        f"{i}. [{o.get('date')}] {o.get('instruction')}\n   NEW: {(o.get('new_text') or '')!r}"
        + (" (REPEAL)" if o.get("change_type") == "repeal" else "")
        for i, o in enumerate(used, 1))
    up = f"ENACTMENT {para}:\n{base_text}\n\nAMENDMENTS (chronological):\n{block}"
    try:
        res = extract(doc_id=f"holistic#{para}#{_hh(base_text, block)}", text=up, system_prompt=_PROMPT,
                      user_prompt=up, schema=HolisticProvision, model=model, cache=cache, client=client,
                      reextract=reextract, use_structured_outputs=True, schema_in_cache_key=True,
                      max_tokens=4000)
    except Exception:
        return None
    if not res.valid or res.parsed is None:
        return None
    out = (res.parsed.consolidated_text or "").strip()
    return out or None


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def verify(out: str, base_text: str, ops: list, as_of: str = "2025-12-31") -> float:
    """Fraction of output SENTENCES that trace (whitespace-normalized, >=0.75 longest-match) to the
    base or an amendment new_text. A low score flags drift (fabricated/altered spans) — the guardrail
    for the 0%-fabrication guarantee. 1.0 = every span is verbatim-sourced."""
    srcs = [_norm(base_text)] + [_norm(o.get("new_text") or "") for o in _ordered(ops, as_of)]
    sents = [x for x in re.split(r"(?<=[.:])\s+", out) if len(x.strip()) > 8]
    if not sents:
        return 0.0
    def traced(s):
        n = _norm(s)
        return any(difflib.SequenceMatcher(None, n, src).find_longest_match(
            0, len(n), 0, len(src)).size >= 0.75 * len(n) for src in srcs)
    return sum(traced(s) for s in sents) / len(sents)
