"""LLM amendment op-extraction — wires llmkit to lovhistorie (boundaries-only).

INTENT: parse an amending act into structured ops, with payloads located by verbatim
    head/tail ANCHORS and sliced from the source — so a sub-provision op's new text has a
    CORRECT boundary (the regex parser over-captures, e.g. a punktum op with a 1168-char
    payload; docs/done.md 2026-08-14). The model emits only citations, ids, sub-addresses,
    op types and short locating quotes — never the full statutory text — so every payload is
    a verbatim source slice (substring guarantee); a not-found anchor FLAGS, never fabricates.
REASONING: this is the amendment-side analogue of source/llm/segment.py. Anchors (not line
    numbers) because act text is often line-poor (flattened LTI XML); find() with a monotonic
    cursor resolves repeated anchors to the next occurrence and enforces order. Validated in
    prototype: 96% of payloads located + source-sliced on the 0-newline LTI text.
ASSUMES: OPENAI_API_KEY in env; `act_text` is the public-domain amending act (LTI XML text or
    gazette OCR), never the current/oracle text (G1). Emits ops in the amendment-stream schema
    (source/parse/amendments), so pipeline.load_ops / replay consume them unchanged.
ANTI-GAMING: reads only the public-domain amending act; the cache holds that text + the model's
    anchors/labels, never the answer key. G1-safe.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
try:
    from llmkit import LLMCache, extract
except ModuleNotFoundError:  # pragma: no cover - sandbox bootstrap
    _PKG = _REPO.parent.parent / "packages" / "llmkit"
    if _PKG.exists() and str(_PKG) not in sys.path:
        sys.path.insert(0, str(_PKG))
    from llmkit import LLMCache, extract

try:
    from source.llm.schemas import AmendmentExtraction
except ModuleNotFoundError:
    from schemas import AmendmentExtraction  # type: ignore

from source.parse import gazette

PROMPT_DIR = Path(__file__).parent / "prompts"
MODEL = "gpt-4.1"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "amend_ops")

_CHANGE = {"replace": "change", "insert": "add", "repeal": "repeal", "renumber": "renumber"}


def _system_prompt() -> str:
    return (PROMPT_DIR / "amend_ops_system.txt").read_text(encoding="utf-8")


def _resolve(cite: str) -> str | None:
    """A block's target-law cite -> datokode (the model may return either form)."""
    cite = cite.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d+-\d+", cite):
        return cite
    return gazette.datokode("lov " + cite)


def _instruction(para: str, subunit: str, op_type: str) -> str:
    """Rebuild the instruction string the ledd engine parses (ordinal + action verb)."""
    num = para.lstrip("§")
    sub = f" {subunit}".rstrip()
    verb = "oppheves" if op_type == "repeal" else "skal lyde:"
    return f"§ {num}{sub} {verb}".strip()


@dataclass
class AmendReport:
    n_ops: int = 0
    payload_ops: int = 0            # replace/insert ops that carry a payload
    substring_ok: int = 0          # payloads located AND verified as source slices
    flagged: list = field(default_factory=list)   # (para, why) anchor not found
    valid: bool = True
    cached: bool = False


def extract_ops(act_datokode: str, act_text: str, *, client=None, model: str = MODEL,
                cache: LLMCache = CACHE, reextract: bool = False):
    """Ops for one amending act, in the amendment-stream schema. Returns (ops, AmendReport).
    Each replace/insert op's `new_text` is a verbatim source slice located by anchors; ops
    whose anchor can't be found exactly are FLAGGED and dropped (no fabrication)."""
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    res = extract(
        doc_id=act_datokode, text=act_text,
        system_prompt=_system_prompt(), user_prompt=act_text,
        schema=AmendmentExtraction, model=model, cache=cache, client=client,
        reextract=reextract, use_structured_outputs=True, schema_in_cache_key=True,
        max_tokens=8000,
    )
    rep = AmendReport(valid=res.valid, cached=res.cached)
    if not res.valid or res.parsed is None:
        return [], rep

    ops, cursor = [], 0
    for block in res.parsed.blocks:
        dk = _resolve(block.target_law_cite)
        if not dk:
            continue
        for op in block.ops:
            rep.n_ops += 1
            new_text = None
            if op.op_type in ("replace", "insert"):
                rep.payload_ops += 1
                h, t = op.payload_head.strip(), op.payload_tail.strip()
                hi = act_text.find(h, cursor) if h else -1
                ti = act_text.find(t, hi) if (t and hi >= 0) else -1
                if hi >= 0 and ti >= 0:
                    new_text = " ".join(act_text[hi:ti + len(t)].split())
                    cursor = ti + len(t)
                    rep.substring_ok += 1
                else:
                    rep.flagged.append((op.target_paragraf, "anchor-not-found"))
                    continue                     # flag-don't-fabricate: drop the op
            para = "§" + op.target_paragraf.lstrip("§").replace(" ", "")
            ops.append({
                "act_refid": f"lov/{act_datokode}",
                "target_law": f"lov/{dk}",
                "target": op.subunit or para,
                "paragraph": para,
                "change_type": _CHANGE.get(op.op_type, "unknown"),
                "instruction": _instruction(para, op.subunit, op.op_type),
                "new_text": new_text,
                "source": "llm_amend_ops",
            })
    return ops, rep


if __name__ == "__main__":
    import json
    dk = sys.argv[1]
    path = sys.argv[2]
    ops, rep = extract_ops(dk, Path(path).read_text(encoding="utf-8"))
    print(f"{dk}: {rep.n_ops} ops; payloads {rep.substring_ok}/{rep.payload_ops} source-verified; "
          f"flagged {len(rep.flagged)}; cached={rep.cached}")
    for o in ops[:6]:
        print(f"  {o['target_law']} {o['paragraph']} [{o['change_type']}] "
              f"new_text_len={len(o['new_text'] or '')}  instr={o['instruction'][:50]!r}")
