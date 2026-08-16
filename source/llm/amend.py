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
    from source.llm.schemas import AmendmentOps
except ModuleNotFoundError:
    from schemas import AmendmentOps  # type: ignore

from source.parse import gazette

PROMPT_DIR = Path(__file__).parent / "prompts"
MODEL = "gpt-4.1"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "amend_ops")

_CHANGE = {"replace": "change", "insert": "add", "repeal": "repeal", "renumber": "renumber"}
# Each target-law section starts at "I lov <cite>". Splitting here (not on the "gjøres
# følgende endringer:" header, which many acts omit for the direct "I lov X skal § Y lyde:"
# form) gives CORRECT per-law attribution — the regex block parser over-runs and mis-files
# ops from one law onto another (finansforetaksloven §21-15 → vphl §21-15; docs/done.md).
_SECTION = re.compile(r"\bI\s+lov\s+(\d{1,2}\.?\s*[a-zæøå]+\.?\s*\d{4}\s*nr\.?\s*\d+)", re.I)


def _system_prompt() -> str:
    return (PROMPT_DIR / "amend_section_system.txt").read_text(encoding="utf-8")


def _split_sections(act_text: str):
    """[(target_datokode, section_text)] — one per 'I lov <cite>' target-law section."""
    heads = [(m.start(), gazette.datokode("lov " + m.group(1)))
             for m in _SECTION.finditer(act_text)]
    out = []
    for i, (pos, dk) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(act_text)
        if dk:
            out.append((dk, act_text[pos:end]))
    return out




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
                cache: LLMCache = CACHE, reextract: bool = False, only_targets=None):
    """Ops for one amending act, in the amendment-stream schema. Returns (ops, AmendReport).
    Splits the act on `I lov <cite>` and runs ONE call per target-law section (correct
    attribution + recall). `only_targets` (a set of datokodes) restricts the LLM to those
    laws' sections — a big saving on omnibus acts amending laws we do not score. Each
    replace/insert op's `new_text` is a verbatim source slice located by anchors WITHIN its
    section; a not-found anchor FLAGS + drops the op."""
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    # entry-into-force date for op ordering + point-in-time (act date, resolved via inforce)
    y, m, d = act_datokode[:4], act_datokode[5:7], act_datokode[8:10]
    act_date = f"{y}-{m}-{d}"
    from source.parse import inforce
    resolved = inforce.resolved_date(act_datokode) or act_date
    rep = AmendReport()
    ops = []
    for target_dk, sec in _split_sections(act_text):
        if only_targets is not None and target_dk not in only_targets:
            continue                                 # skip laws we don't score
        try:
            res = extract(
                doc_id=f"{act_datokode}#{target_dk}", text=sec,
                system_prompt=_system_prompt(), user_prompt=sec,
                schema=AmendmentOps, model=model, cache=cache, client=client,
                reextract=reextract, use_structured_outputs=True, schema_in_cache_key=True,
                max_tokens=16000,
            )
        except Exception as e:                       # one section must not kill the run
            rep.valid = False
            rep.flagged.append((f"lov/{target_dk}", f"extract-error:{type(e).__name__}"))
            continue
        rep.cached = rep.cached or res.cached
        if not res.valid or res.parsed is None:
            rep.valid = False
            continue
        cursor = 0                                # anchors resolved within THIS section
        for op in res.parsed.ops:
            rep.n_ops += 1
            new_text = None
            if op.op_type in ("replace", "insert"):
                rep.payload_ops += 1
                h, t = op.payload_head.strip(), op.payload_tail.strip()
                hi = sec.find(h, cursor) if h else -1
                ti = sec.find(t, hi) if (t and hi >= 0) else -1
                if hi >= 0 and ti >= 0:
                    new_text = " ".join(sec[hi:ti + len(t)].split())
                    cursor = ti + len(t)
                    rep.substring_ok += 1
                else:
                    rep.flagged.append((op.target_paragraf, "anchor-not-found"))
                    continue                     # flag-don't-fabricate: drop the op
            para = "§" + op.target_paragraf.lstrip("§").replace(" ", "")
            ops.append({
                "act_refid": f"lov/{act_datokode}",
                "target_law": f"lov/{target_dk}",
                "target": op.subunit or para,
                "paragraph": para,
                "change_type": _CHANGE.get(op.op_type, "unknown"),
                "instruction": _instruction(para, op.subunit, op.op_type),
                "new_text": new_text,
                "date_in_force_resolved": resolved,
                "date_in_force": act_date,
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
