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
