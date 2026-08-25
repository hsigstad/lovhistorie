"""LLM per-provision CLEAN-TEXT extraction from the Lovdata-CD-2005 corpus.

INTENT: the 2005 CD blocks interleave editorial apparatus (footnote reference digits, footnote
    DEFINITIONS "N Jfr. …", parallel-law refs "asal. §5-23", "Endret ved …" notes, CISG "Art N"
    annex) through the statutory text. A regex splitter mis-assigns bodies and leaves apparatus in
    (avtaleloven regressed to μ0.85). This module has an LLM return, per provision, the CLEAN statutory
    text (title + ledd) with the apparatus removed, then VERIFIES each provision traces (word-5-grams)
    to the source to bound fabrication. Piloted: small laws reach static-provision μ≈0.95 (vs 0.85 regex).
REASONING: OFFLINE + cached (llmkit LLMCache), so the extracted base is a REPRODUCIBLE build input, not a
    runtime call (rule 3). The trace check flags a provision the model paraphrased instead of copied.
ASSUMES: OPENAI_API_KEY; the CD block is public-domain (Lovdata CD out of 15-yr DB protection / NLOD 2.0),
    never the current/answer text. Large laws chunk on provision boundaries (never mid-provision).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
try:
    from llmkit import LLMCache
except ModuleNotFoundError:  # pragma: no cover
    _PKG = _REPO.parent.parent / "packages" / "llmkit"
    if _PKG.exists() and str(_PKG) not in sys.path:
        sys.path.insert(0, str(_PKG))
    from llmkit import LLMCache

from source.llm.target_localize import _hh

CACHE = LLMCache(_REPO / "data" / "llm_cache" / "extract_cd")
MODEL = "gpt-4.1"
_PROV = re.compile(r"§\s?\d")

_SYS = (
    "You extract CLEAN statutory text from a Norwegian law's 2005 consolidated form (OCR'd from the "
    "Lovdata CD). The source interleaves editorial apparatus that is NOT part of the law:\n"
    "- footnote reference digits rendered inline (e.g. 'forpliktelser2', '§12.1');\n"
    "- CROSS-REFERENCE footnote definitions ('1 Jfr. lov 13 juni 1997 nr. 44', 'se § 39');\n"
    "- parallel-law references ('asal. §5-23' = allmennaksjeloven);\n"
    "- 'Endret ved ...' / 'Jfr. tidligere ...' change-history notes.\n"
    "BUT KEEP in-force / ikrafttredelse footnotes and their markers (e.g. a trailing "
    "'1 Frå 1 juli 1960 iflg. res. 2 juni 1960.' or '1 I kraft 1 jan 1999') — the official "
    "consolidated text RETAINS these, so copy them verbatim as part of the provision.\n"
    "For EACH provision heading (§N or §N-M), return the provision's clean statutory text = its title "
    "plus all ledd/paragraphs, VERBATIM from the source but with the apparatus above removed. Do NOT "
    "paraphrase, translate, reorder, or invent — copy the statutory words exactly, only deleting "
    "apparatus. Keep ledd markers like '(1)'. Skip convention-annex articles ('Art 1', 'Art 61' — the "
    "CISG). Return JSON {\"provisions\":[{\"para\":\"§N\",\"text\":\"...\"}, ...]} in document order."
)


@dataclass
class ExtractReport:
    n: int = 0
    cached_chunks: int = 0
    trace_mean: float = 1.0
    low_trace: list = field(default_factory=list)   # provisions whose text did not trace (possible drift)


def _norm(t: str) -> str:
    return " ".join((t or "").split())


def _chunks(block: str, chunk_chars: int):
    """Split on provision-heading boundaries only (never mid-provision), accumulating up to chunk_chars."""
    cuts = [m.start() for m in _PROV.finditer(block)]
    if len(block) <= chunk_chars or len(cuts) < 2:
        return [block]
    out, start = [], 0
    for c in cuts:
        if c - start >= chunk_chars:
            out.append(block[start:c]); start = c
    out.append(block[start:])
    return out


def extract_law(dk: str, block: str, *, client=None, model: str = MODEL, cache: LLMCache = CACHE,
                reextract: bool = False, chunk_chars: int = 14000):
    """{para: clean_text} for one CD law block, LLM-extracted + cached + trace-verified."""
    if client is None:
        from openai import OpenAI
        client = OpenAI(timeout=240)
    provs, rep = {}, ExtractReport()
    for ci, ch in enumerate(_chunks(block, chunk_chars)):
        key = cache.key(f"cd#{dk}#{ci}#{model}", _hh(_SYS, ch), model)
        hit = cache.get(key) if not reextract else None
        if hit is not None:
            content = hit.extraction.get("content", ""); rep.cached_chunks += 1
        else:
            r = client.chat.completions.create(
                model=model, temperature=0, max_tokens=16000,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": _SYS}, {"role": "user", "content": ch}])
            content = r.choices[0].message.content or ""
            cache.put(key, {"content": content}, doc_id=f"cd#{dk}#{ci}", model=model)
        try:
            items = json.loads(content).get("provisions", [])
        except Exception:
            items = []
        for p in items:
            pid = "§" + re.sub(r"[^\d\-a-z]", "", (p.get("para") or "").lower().lstrip("§"))
            if pid and pid != "§" and pid not in provs and p.get("text"):
                provs[pid] = _norm(p["text"])
    # verify: fraction of each provision's word-5-grams present verbatim in the source (fabrication gauge)
    sw = _norm(block).lower().split()
    ngr = set(tuple(sw[i:i + 5]) for i in range(len(sw) - 4))
    traces = []
    for pid, t in provs.items():
        w = t.lower().split()
        g = [tuple(w[i:i + 5]) for i in range(len(w) - 4)]
        frac = (sum(x in ngr for x in g) / len(g)) if g else 1.0
        traces.append(frac)
        if frac < 0.6:
            rep.low_trace.append(pid)
    rep.n = len(provs)
    rep.trace_mean = sum(traces) / len(traces) if traces else 1.0
    return provs, rep
