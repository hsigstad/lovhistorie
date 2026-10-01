"""LLM body-locator (line-numbered, table-of-contents-aware).

INTENT: given an issue's OCR text and a target law (nr + title), return the (start, end) char offsets
    of that law's ENACTMENT body — the primary locator for build_enactment.build_from_index, replacing
    the brittle regex body-location. Validated to be >= regex with 0 regressions and to rescue
    mislocated laws (e.g. a regex 0.00 -> 0.67) on the dev + scale samples.
REASONING: localisation via LINE NUMBERS, not text anchors — the model reads the whole issue (numbered
    "N|line") and returns the body's start/end line, told to IGNORE the table-of-contents entry (title +
    page number) and return the real body. Line numbers are robust to slice and verify; an earlier
    anchor-based variant underperformed regex (fragile re-location). The deterministic _NEXT_LAW end is
    preferred for precision when found; the model's end_line is the fallback (older bound-volume layouts
    where _NEXT_LAW is absent).
ASSUMES: OPENAI_API_KEY; `full` is public-domain NB OCR (never current/answer text) — G1-safe. Issues
    larger than _CAP chars return None (caller falls back to regex); gpt-4.1's large context fits normal
    issues, but the multi-megabyte Register+acts bound volumes are left to a future chunked pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
try:
    from llmkit import LLMCache, extract
except ModuleNotFoundError:  # pragma: no cover
    _PKG = _REPO.parent.parent / "packages" / "llmkit"
    if _PKG.exists() and str(_PKG) not in sys.path:
        sys.path.insert(0, str(_PKG))
    from llmkit import LLMCache, extract

from pydantic import BaseModel

MODEL = "gpt-4.1"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "locate_body")
_CAP = 600000   # chars; above this fall back to regex (giant Register+acts bound volumes)

_SYS = (
    "You are given the full OCR text of a Norwegian Lovtidend gazette issue, each line numbered "
    "\"N|text\". The issue opens with a table of contents / register (acts listed with page numbers), "
    "then the acts themselves.\n"
    "Find the ENACTMENT BODY of the law titled \"{title}\" (Lov nr. {nr}): its heading followed by its "
    "provisions (§ 1, § 2, ...).\n"
    "Return found=true, start_line = the law's heading line (just before § 1), end_line = the last line "
    "of THIS law before the next act begins.\n"
    "IGNORE the table-of-contents / register listing for this law (title followed by a page number, among "
    "other listed acts) — that is NOT the body. If the body is absent, found=false."
)


class _Span(BaseModel):
    found: bool = False
    start_line: int = 0
    end_line: int = 0


def locate(full: str, nr: str, title: str, *, client=None, model: str = MODEL, cache: LLMCache = CACHE):
    """(start, end) char offsets of law <nr>/<title>'s enactment body in `full`, or None.
    `end` is the model's end_line offset; the caller may prefer a deterministic _NEXT_LAW end."""
    if not title or len(full) > _CAP:
        return None
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    lines = full.split("\n")
    numtext = "\n".join(f"{i}|{ln}" for i, ln in enumerate(lines))
    try:
        res = extract(doc_id=f"locbody#{nr}#{title[:40]}#{len(full)}", text=numtext,
                      system_prompt=_SYS.format(title=title, nr=nr), user_prompt=numtext,
                      schema=_Span, model=model, cache=cache, client=client,
                      use_structured_outputs=True, max_tokens=200)
    except Exception:
        return None
    p = res.parsed
    if not p or not p.found or p.end_line <= p.start_line or p.start_line >= len(lines):
        return None
    # line index -> char offset (prefix sums over lines joined by "\n")
    off = [0]
    for ln in lines:
        off.append(off[-1] + len(ln) + 1)
    start = off[p.start_line]
    end = min(off[min(p.end_line + 1, len(lines))], len(full))
    return (start, end) if end > start else None
