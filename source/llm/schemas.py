"""Pydantic schemas for lovhistorie LLM extraction (llmkit ExtractionSchema).

INTENT: define the boundaries-only structural-segmentation schema — the model returns
    provision LOCATIONS (line numbers) and ids, NEVER statutory text — so deterministic
    slicing yields verbatim source slices (the substring guarantee; see docs/thinking.md).
REASONING: emitting coordinates + labels (not content) makes content fabrication
    structurally impossible; the residual failure is a mislocated boundary, which is
    bounded and self-detecting. Schema stays permissive; invariants are repair+flags in
    segment.py, not hard rejections (one bad boundary must not discard the extraction).
ASSUMES: OPENAI_API_KEY in env; llmkit importable (pip-installed, or the workspace
    packages dir added below). Source text is public-domain OCR (never the current/oracle
    text — gate guard G1).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, field_validator

# llmkit lives in the workspace packages dir; add it when not pip-installed (sandbox).
try:
    from llmkit import ExtractionSchema
except ModuleNotFoundError:  # pragma: no cover - env bootstrap
    _PKG = Path(__file__).resolve().parents[3] / "packages" / "llmkit"
    if _PKG.exists() and str(_PKG) not in sys.path:
        sys.path.insert(0, str(_PKG))
    from llmkit import ExtractionSchema


class ProvisionBoundary(BaseModel):
    """One provision heading located in the source: its normalized id and the 1-based
    line number where its heading sits. NO text — the body is sliced deterministically."""
    paragraf: str        # normalized id: "§1", "§38a", "§2-11a"
    heading_line: int     # 1-based line of the "§ N" heading in the numbered source

    @field_validator("paragraf")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        return v.strip()


class BaseSegmentation(ExtractionSchema):
    """The full boundary list for one statute's OCR text. Invariants (monotonic,
    non-overlapping, coverage, heading-matches-number) are applied as REPAIR + flags in
    source/llm/segment.py, not as hard schema rejections — a single bad boundary should be
    dropped/flagged, not discard the whole extraction."""
    schema_name: ClassVar[str] = "lovhistorie_base_segment"
    schema_version: ClassVar[str] = "v1"
    provisions: list[ProvisionBoundary] = []


class AmendOp(BaseModel):
    """One amendment instruction, located not quoted: which law + provision + sub-unit it
    changes, the op type, and (for replace/insert) the FIRST and LAST few tokens of the new
    statutory text VERBATIM — locating anchors that source/llm/amend.py finds + slices, so the
    payload is a verbatim source span with a correct boundary (not the regex over-capture)."""
    target_law_cite: str            # "13. juni 1997 nr. 44" or a datokode
    target_paragraf: str            # "§21-15"
    subunit: str = ""               # "annet ledd annet punktum" / "" for whole-provision
    op_type: str                    # replace | insert | repeal | renumber
    payload_head: str = ""          # first ~6 tokens of the new text, VERBATIM ("" if none)
    payload_tail: str = ""          # last ~6 tokens of the new text, VERBATIM




class AmendmentOps(ExtractionSchema):
    """Ops for ONE target law's section (the wrapper splits the act on `I lov <cite>` first, so
    each call is scoped to a single law → correct attribution + higher op recall). No
    target_law_cite here — the caller sets it from the section header."""
    schema_name: ClassVar[str] = "lovhistorie_amend_section"
    schema_version: ClassVar[str] = "v1"
    ops: list[AmendOp] = []


class TargetMention(BaseModel):
    """One place an amending act names a law it changes — located, not quoted. `anchor` is a
    verbatim source slice starting at 'I lov'/'Lov av'/its numbered prefix; `law_cite` is the
    date+nr identifying tokens, verified to lie WITHIN the located anchor. The section that
    amends this law runs from this anchor to the next one — so segmentation is model-localized
    but every boundary is a verbatim source position, and the target is resolved + catalog-checked
    deterministically (source/llm/target_localize.py). Replaces the brittle _SECTION regex."""
    anchor: str                      # verbatim first ~6-12 words of the mention
    law_cite: str                    # "31. mai 1918 nr. 4" — must be a substring of `anchor`


class TargetMentions(ExtractionSchema):
    """Every amended-law mention in one act, in source order. High-recall by design: the model
    lists all mentions regardless of layout; the verifier drops only the unverifiable (to a
    measured stream), so recall loss is visible, never silent."""
    schema_name: ClassVar[str] = "lovhistorie_target_mentions"
    schema_version: ClassVar[str] = "v1"
    mentions: list[TargetMention] = []
