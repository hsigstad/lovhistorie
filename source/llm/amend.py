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

from source.llm.target_localize import _build_norm, _norm


def _nfind(norm_sec, offs, anchor, ncur):
    """Whitespace-tolerant locate of `anchor` in the section at/after normalized cursor `ncur`.
    Returns (raw_start, raw_end, new_ncur) or None. OCR-robust: the model cleans OCR spacing so its
    verbatim anchors don't byte-match the raw text (§36/§38 'skal lyde' payloads were dropped this
    way); matching on whitespace-normalized text tolerates that, while the returned slice is still the
    RAW source (no fabrication). Character-level OCR errors in the anchor still fail safe (drop)."""
    a = _norm(anchor)
    if not a:
        return None
    j = norm_sec.find(a, ncur)
    if j < 0:
        return None
    return offs[j], offs[j + len(a) - 1] + 1, j + len(a)


def _nfind_tail_end(norm_sec, offs, anchor, ncur):
    """Locate the END (raw index) of a payload TAIL anchor, tolerant to OCR damage in its LEADING
    words. Only the tail's END bounds the span, so try the full anchor first, then progressively
    DROP leading words (keep the suffix), taking the longest suffix that matches at/after `ncur`.
    Returns (raw_end, norm_ncur) or None. This recovers whole-provision payloads whose tail contains
    an OCR-garbled word the model silently cleaned (avtaleloven §36 'kontraktsrettslig sedvane.' —
    the OCR mangles 'kontraktsrettslig' so the full tail never byte-matches, but 'sedvane.' does)."""
    words = _norm(anchor).split()
    for i in range(len(words)):
        cand = " ".join(words[i:])
        if len(cand) < 8:            # too short to be safe -> stop (flag-don't-fabricate)
            break
        j = norm_sec.find(cand, ncur)
        if j >= 0:
            return offs[j + len(cand) - 1] + 1, j + len(cand)
    return None

PROMPT_DIR = Path(__file__).parent / "prompts"
MODEL = "gpt-4.1"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "amend_ops")

_CHANGE = {"replace": "change", "insert": "add", "repeal": "repeal", "renumber": "renumber"}


def _system_prompt() -> str:
    return (PROMPT_DIR / "amend_section_system.txt").read_text(encoding="utf-8")


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
                cache: LLMCache = CACHE, reextract: bool = False, only_targets=None,
                sections=None):
    """Ops for one amending act, in the amendment-stream schema. Returns (ops, AmendReport).
    Splits the act on `I lov <cite>` and runs ONE call per target-law section (correct
    attribution + recall). `only_targets` (a set of datokodes) restricts the LLM to those
    laws' sections — a big saving on omnibus acts amending laws we do not score. Each
    replace/insert op's `new_text` is a verbatim source slice located by anchors WITHIN its
    section; a not-found anchor FLAGS + drops the op.

    `sections` (optional) = a pre-computed [(target_datokode, section_text)] list, e.g. from
    source/llm/target_localize.localize — the format-agnostic localizer that replaced the old
    brittle `I lov <cite>` section regex (it recovers omnibus layouts the regex missed: flat
    correction lists, Nynorsk block headers, etc.). When omitted, this falls back to running that
    same localizer on `act_text` (no regex splitter remains)."""
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    if sections is None:                              # localize-then-verify replaces the _SECTION regex
        from source.llm import target_localize
        sections, _ = target_localize.localize(act_text, client=client, model=model,
                                               reextract=reextract)
    # entry-into-force date for op ordering + point-in-time (act date, resolved via inforce)
    y, m, d = act_datokode[:4], act_datokode[5:7], act_datokode[8:10]
    act_date = f"{y}-{m}-{d}"
    from source.parse import inforce
    resolved = inforce.resolved_date(act_datokode) or act_date
    rep = AmendReport()
    ops = []
    for item in sections:
        target_dk, sec = item[0], item[1]
        # optional 3rd element = a focus hint (the target law's cite): used when `sec` is a WHOLE
        # multi-law act (whole-act extraction) so the model extracts ONLY this law's ops and does not
        # mis-attribute another law's inline ops (the whole-act mis-attribution that regressed aksje/
        # foreld). For a single-law section (2-tuple) there's no hint and the prompt is unchanged.
        focus = item[2] if len(item) > 2 else None
        if only_targets is not None and target_dk not in only_targets:
            continue                                 # skip laws we don't score
        up = (f"Extract ONLY the amendments this act makes to the law introduced as:\n"
              f"«{focus}»\nThis act amends several laws — IGNORE amendments to every other law.\n\n{sec}"
              if focus else sec)
        try:
            res = extract(
                doc_id=f"{act_datokode}#{target_dk}#{'F' if focus else ''}", text=sec,
                system_prompt=_system_prompt(), user_prompt=up,
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
        norm_sec, offs = _build_norm(sec)         # whitespace-normalized view for OCR-robust anchoring
        cursor = 0                                # normalized cursor: anchors resolved within THIS section
        for op in res.parsed.ops:
            rep.n_ops += 1
            new_text = None
            if op.op_type in ("replace", "insert"):
                rep.payload_ops += 1
                h, t = op.payload_head.strip(), op.payload_tail.strip()
                rh = _nfind(norm_sec, offs, h, cursor) if h else None
                # Search the tail from the head's START, not its end: the model sometimes returns a
                # payload_head that already spans most/all of the payload, so the tail (a suffix)
                # lies INSIDE the head span and a search after head-end silently fails
                # (anchor-not-found dropped a valid §17 punktum op on avtaleloven). Anchoring the
                # tail from the head's start and taking the later end covers head-contains-tail,
                # tail-after-head, and head==tail alike.
                h_start = rh[2] - len(_norm(h)) if rh else 0     # normalized start of the head match
                rt = _nfind(norm_sec, offs, t, h_start) if (t and rh) else None
                # tail exact-match failed (OCR damage in the tail's leading words) -> locate its END
                # by longest matching suffix, so an OCR-garbled word mid-tail can't drop the whole op.
                tail = None
                if rh and t:
                    tail = (rt[1], rt[2]) if rt else _nfind_tail_end(norm_sec, offs, t, h_start)
                if rh and tail is not None:
                    tail_end, tail_ncur = tail
                    new_text = " ".join(sec[rh[0]:max(rh[1], tail_end)].split())
                    cursor = max(rh[2], tail_ncur)
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
