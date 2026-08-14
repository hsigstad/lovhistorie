"""LLM boundaries-only base segmentation — wires llmkit to lovhistorie.

INTENT: for OCR-base laws where the regex heading parser is fragile, an LLM locates each
    provision heading (line number) and we slice the source DETERMINISTICALLY. The model
    emits only line numbers + ids, never text, so every provision string is a verbatim
    source slice (the substring guarantee => 0% content fabrication). Validated end-to-end
    (docs/done.md 2026-08-14): avtaleloven convergence 30->33/45, aksjeloven-2001 booklet
    192 vs 153, both 100% source-faithful.
REASONING: extraction is cached + audited via llmkit (LLMCache + Pydantic + structured
    outputs), so the segmented base is a REPRODUCIBLE build input, not a gate-time call.
    Deterministic invariant-repair (monotonic, dedup) + a substring assertion turn a
    mislocated boundary into a flag, never a corrupted or fabricated provision.
ASSUMES: OPENAI_API_KEY in env; `source_text` is the law's public-domain OCR (NEVER the
    current/oracle text — gate guard G1). Line-label mode (needs line-structured text);
    anchor mode for line-break-poor sources is a follow-up (docs/todo.md).
ANTI-GAMING: reads only the caller's public-domain OCR; the cache holds that OCR + the
    model's line-number output, never the answer key. G1-safe.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
try:
    from llmkit import LLMCache, extract
except ModuleNotFoundError:  # pragma: no cover - env bootstrap (sandbox: llmkit not installed)
    _PKG = _REPO.parent.parent / "packages" / "llmkit"
    if _PKG.exists() and str(_PKG) not in sys.path:
        sys.path.insert(0, str(_PKG))
    from llmkit import LLMCache, extract

try:
    from source.llm.schemas import BaseSegmentation
except ModuleNotFoundError:  # when run with source/llm on sys.path
    from schemas import BaseSegmentation  # type: ignore

import re

PROMPT_DIR = Path(__file__).parent / "prompts"
MODEL = "gpt-4.1"                       # strong structural model; beats gpt-4o-mini here
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "base_segment")
_HEAD_STRIP = re.compile(r"^\s*[§S]?\s*\d+\s*(?:[-–—]\s*\d+)?\s*[a-z]?\s*[.)]?\s*", re.I)


def _system_prompt() -> str:
    return (PROMPT_DIR / "segment_base_system.txt").read_text(encoding="utf-8")


@dataclass
class SegmentReport:
    n_found: int = 0                 # raw provisions the model returned
    n_kept: int = 0                  # after invariant-repair
    dropped: list = field(default_factory=list)   # (paragraf, line) dropped as non-monotonic/dup
    substring_ok: int = 0            # provisions whose sliced text IS a verbatim source slice
    substring_total: int = 0
    id_mismatch: list = field(default_factory=list)  # slice heading != labelled id (flag)
    valid: bool = True               # llmkit schema validation passed
    cached: bool = False


def _norm_id(p: str) -> str:
    p = p.strip().replace(" ", "")
    if not p.startswith("§"):
        p = "§" + p.lstrip("§S")
    return p


def _repair(provisions):
    """Deterministic invariant-repair: sort by line, drop non-monotonic + duplicate-id
    boundaries (flag-don't-fabricate). Returns (kept, dropped)."""
    kept, seen, last, dropped = [], set(), 0, []
    for b in sorted(provisions, key=lambda x: x.heading_line):
        pid = _norm_id(b.paragraf)
        if b.heading_line <= last or pid in seen or not pid.strip("§"):
            dropped.append((pid, b.heading_line))
            continue
        kept.append((pid, b.heading_line))
        seen.add(pid)
        last = b.heading_line
    return kept, dropped


def segment_base(datokode: str, source_text: str, *, client=None, model: str = MODEL,
                 cache: LLMCache = CACHE, reextract: bool = False):
    """{paragraf_id: text} for one statute's OCR, by LLM boundary location + deterministic
    slicing. Returns (provisions, SegmentReport). Every provision text is a verbatim slice
    of `source_text`; the report records repairs, the substring check, and id mismatches."""
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    lines = source_text.split("\n")
    numbered = "\n".join(f"{i + 1:4d}| {ln}" for i, ln in enumerate(lines))

    res = extract(
        doc_id=datokode, text=numbered,
        system_prompt=_system_prompt(), user_prompt=numbered,
        schema=BaseSegmentation, model=model, cache=cache, client=client,
        reextract=reextract, use_structured_outputs=True, schema_in_cache_key=True,
        max_tokens=16000,
    )
    rep = SegmentReport(valid=res.valid, cached=res.cached)
    if not res.valid or res.parsed is None:
        return {}, rep
    kept, dropped = _repair(res.parsed.provisions)
    rep.n_found = len(res.parsed.provisions)
    rep.n_kept = len(kept)
    rep.dropped = dropped

    provs, src = {}, " ".join(source_text.split())
    for i, (pid, line) in enumerate(kept):
        s = line - 1
        e = (kept[i + 1][1] - 1) if i + 1 < len(kept) else len(lines)
        block = "\n".join(lines[s:e])
        body = " ".join(_HEAD_STRIP.sub("", block).split())
        provs[pid] = body
        if body:
            rep.substring_total += 1
            if " ".join(body.split()) in src:
                rep.substring_ok += 1
        # heading-matches-number cross-check: the slice's first line should carry this id
        head = lines[s]
        num = pid.lstrip("§").rstrip("abcdefghijklmnopqrstuvwxyz")
        if num and re.sub(r"\s", "", num) not in re.sub(r"\s", "", head):
            rep.id_mismatch.append(pid)
    return provs, rep


if __name__ == "__main__":  # quick manual check on a cached OCR file
    import json
    dk, path = sys.argv[1], sys.argv[2]
    provs, rep = segment_base(dk, Path(path).read_text(encoding="utf-8"))
    print(f"{dk}: {rep.n_found} found -> {rep.n_kept} kept (dropped {len(rep.dropped)}); "
          f"substring {rep.substring_ok}/{rep.substring_total}; id_mismatch {len(rep.id_mismatch)}; "
          f"cached={rep.cached}")
    print(json.dumps({p: t[:60] for p, t in list(provs.items())[:5]}, ensure_ascii=False, indent=1))
