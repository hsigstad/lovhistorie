"""LLM amendment APPLICATOR — localize-then-verify the span an op edits, then splice deterministically.

INTENT: the deterministic ledd engine can't apply a sub-provision op ("§ 21 annet ledd skal lyde:")
    to an OCR base that lacks (N) ledd markers — it returns None and the op is dropped (avtaleloven
    applies 0/6 sub-ops). But the op's NEW TEXT is given (clean LTI for post-2001 amendments); only
    the LOCATION of the span to replace/delete is unknown. So ask the LLM ONLY for that span (start +
    end anchor, verbatim), then deterministically splice: replace the located span with the op's
    new_text (or delete it for a repeal). The model never writes statutory text — it only points at a
    span — so there is no fabrication (edit = located source span → given new_text, both verbatim).
REASONING: this is localize-then-verify (as in target_localize/amend) applied to APPLICATION rather
    than extraction. Robust to unstructured OCR (the model reads "annet ledd" = 2nd paragraph from the
    prose, no markers needed). OFFLINE (base-prep / precompute), cached → runtime replay stays
    deterministic (rule 3). Anchors located whitespace-tolerantly; a not-found anchor returns None
    (flag-don't-fabricate → the op is left unapplied, exactly as today).
ASSUMES: OPENAI_API_KEY; `provision` is public-domain text (OCR base or a prior-amended state), never
    the current/answer text. `new_text` is the op's replacement (from the amendment, verbatim).
ANTI-GAMING: reads only the public provision + op + the model's span anchors (cached). G1-safe.
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

from pydantic import BaseModel

import re

from source.llm.target_localize import _build_norm, _norm

# Sub-unit ops (ledd/punktum/nr/bokstav) target only PART of a provision; a whole-provision "§ N skal
# lyde:" (no sub-unit) replaces everything and is exempt from the oversize-span guard below.
_SUBUNIT_INSTR = re.compile(r"\b(ledd|punktum|bokstav|nr\.?)\b", re.I)
MODEL = "gpt-4.1"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "apply_op")
PROMPT = """You apply ONE amendment instruction to ONE Norwegian statutory provision.

You are given the provision's current text and an instruction such as:
  "§ 21 annet ledd skal lyde:"      (replace the 2nd ledd)
  "§ 17 andre ledd andre og tredje punktum skal lyde:"  (replace those punktums)
  "§ 14 siste ledd oppheves"        (delete the last ledd)
  "§ 22 nr. 3 oppheves"             (delete item 3)

A LEDD is a numbered paragraph/clause; PUNKTUM a sentence; NR/BOKSTAV a list item. The text is OCR'd
running prose WITHOUT explicit numbers, so you must count ledd/punktum/etc. yourself from the prose.

TASK: identify the EXACT span of the provision that the instruction targets (the ledd/punktum/nr the
new text replaces, or that a repeal deletes). Return:
  - start_anchor: the first 4-8 words of that span, copied VERBATIM from the provision text.
  - end_anchor: the last 4-8 words of that span, copied VERBATIM from the provision text.
Both must be literal substrings of the provision so the span can be located. If you cannot confidently
identify the span, return empty strings (do NOT guess)."""


class OpSpan(ExtractionSchema):
    schema_name: ClassVar[str] = "lovhistorie_apply_span"
    schema_version: ClassVar[str] = "v1"
    start_anchor: str = ""
    end_anchor: str = ""


def _find(anchor: str, text: str, norm_text: str, offsets: list, start: int) -> int:
    a = _norm(anchor)
    if not a:
        return -1
    ns = 0
    for k, off in enumerate(offsets):
        if off >= start:
            ns = k
            break
    for cand in (a, " ".join(a.split()[:5]), " ".join(a.split()[:3])):
        j = norm_text.find(cand, ns)
        if j >= 0:
            return j
    return -1


def apply_op(provision: str, instruction: str, new_text: str, op_type: str, *,
             client=None, model: str = MODEL, cache: LLMCache = CACHE, reextract: bool = False,
             doc_id: str = "") -> str | None:
    """Return `provision` with the op's span replaced by `new_text` (or deleted for a repeal). None if
    the span can't be located (op left unapplied, flag-don't-fabricate)."""
    if not provision or not instruction:
        return None
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    try:
        res = extract(doc_id=f"applyop#{doc_id}#{hash((provision, instruction)) & 0xffffffff:x}",
                      text=provision, system_prompt=PROMPT,
                      user_prompt=f"INSTRUCTION: {instruction}\n\nPROVISION:\n{provision}",
                      schema=OpSpan, model=model, cache=cache, client=client, reextract=reextract,
                      use_structured_outputs=True, schema_in_cache_key=True, max_tokens=800)
    except Exception:
        return None
    if not res.valid or res.parsed is None:
        return None
    sa, ea = res.parsed.start_anchor.strip(), res.parsed.end_anchor.strip()
    if not sa or not ea:
        return None
    norm_text, offsets = _build_norm(provision)
    si = _find(sa, provision, norm_text, offsets, 0)
    ei = _find(ea, provision, norm_text, offsets, si if si >= 0 else 0)
    if si < 0 or ei < 0 or ei < si:
        return None
    span_start = offsets[si]
    span_end = offsets[min(ei + len(_norm(ea)) - 1, len(offsets) - 1)] + 1
    # span-sanity guard: a SUB-UNIT op (ledd/punktum/nr/bokstav) targets PART of the provision, not
    # almost all of it. An oversized span there means the LLM mis-located the boundary (caused §21
    # 0.99→0.26) — reject and leave the op unapplied (flag-don't-fabricate). A whole-provision "skal
    # lyde:" with no sub-unit legitimately replaces everything, so it is exempt.
    if _SUBUNIT_INSTR.search(instruction) and (span_end - span_start) > 0.75 * len(provision):
        return None
    repl = "" if op_type == "repeal" else (new_text or "")
    out = provision[:span_start] + repl + provision[span_end:]
    return " ".join(out.split())


if __name__ == "__main__":
    from source.parse import pipeline
    base = pipeline.enactment_base("lov/1918-05-31-4")
    r = apply_op(base.get("§21", ""), "§ 21 annet ledd skal lyde:", "NYTT ANNET LEDD.", "change")
    print(repr(r))
