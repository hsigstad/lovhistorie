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
    windows: int = 0
    trace_mean: float = 1.0
    low_trace: list = field(default_factory=list)   # provisions whose text did not trace (possible drift)
    title_only: list = field(default_factory=list)  # provisions the CD carries as a TOC heading only (no body)


def _norm(t: str) -> str:
    return " ".join((t or "").split())


def _windows(block: str, size: int, overlap: int):
    """OVERLAPPING fixed-char windows over the block, as (offset, text).

    The CD OCR interleaves footnote apparatus INSIDE each provision (the same '§N-M.' token
    recurs as a footnote marker, and footnotes embed cross-references), so there is no reliable
    deterministic heading boundary to cut on — splitting on every '§' lands cuts mid-provision
    and the model silently drops the run after a bad start (observed: a window beginning on a
    '§3-1 første ledd' apparatus line returned 1 provision for a 15 k-char chunk). Overlapping
    windows instead guarantee every provision appears WHOLE in at least one window; extract_law
    then keeps the best-tracing copy across windows, so a garbled copy from a bad window start
    loses to the clean copy from its neighbour."""
    if len(block) <= size:
        return [(0, block)]
    out, start, n = [], 0, len(block)
    step = max(1, size - overlap)
    while True:
        out.append((start, block[start:start + size]))
        if start + size >= n:
            break
        start += step
    return out


def _trace_frac(text: str, ngr: set) -> float:
    """Fraction of `text`'s word-5-grams present verbatim in the source n-gram set."""
    w = text.lower().split()
    g = [tuple(w[i:i + 5]) for i in range(len(w) - 4)]
    return (sum(x in ngr for x in g) / len(g)) if g else 1.0


def extract_law(dk: str, block: str, *, client=None, model: str = MODEL, cache: LLMCache = CACHE,
                reextract: bool = False, chunk_chars: int = 10000, overlap: int = 5000):
    """{para: clean_text} for one CD law block, LLM-extracted + cached + trace-verified.

    Windows overlap (see `_windows`); when the same provision is returned by more than one
    window the copy with the higher source-trace wins (ties broken by length), so a window that
    began mid-provision cannot poison a provision another window carried cleanly."""
    if client is None:
        from openai import OpenAI
        client = OpenAI(timeout=240)
    # source 5-gram index up front — the merge keeps the best-tracing copy of each provision.
    sw = _norm(block).lower().split()
    ngr = set(tuple(sw[i:i + 5]) for i in range(len(sw) - 4))
    rep = ExtractReport()
    best: dict = {}   # pid -> (trace, text)
    windows = _windows(block, chunk_chars, overlap)
    for off, ch in windows:
        key = cache.key(f"cd#{dk}#w{off}#{model}", _hh(_SYS, ch), model)
        hit = cache.get(key) if not reextract else None
        if hit is not None:
            content = hit.extraction.get("content", ""); rep.cached_chunks += 1
        else:
            r = client.chat.completions.create(
                model=model, temperature=0, max_tokens=16000,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": _SYS}, {"role": "user", "content": ch}])
            content = r.choices[0].message.content or ""
            cache.put(key, {"content": content}, doc_id=f"cd#{dk}#w{off}", model=model)
        try:
            items = json.loads(content).get("provisions", [])
        except Exception:
            items = []
        for p in items:
            pid = "§" + re.sub(r"[^\d\-a-z]", "", (p.get("para") or "").lower().lstrip("§"))
            txt = _norm(p.get("text") or "")
            if not pid or pid == "§" or not txt:
                continue
            tr = _trace_frac(txt, ngr)
            cur = best.get(pid)
            if cur is None or tr > cur[0] or (tr == cur[0] and len(txt) > len(cur[1])):
                best[pid] = (tr, txt)
    provs = {pid: t for pid, (tr, t) in best.items()}
    traces = [tr for tr, _ in best.values()]
    rep.low_trace = [pid for pid, (tr, _) in best.items() if tr < 0.6]
    # Completeness guard: the NCC/norkart 2005 CD carries some provisions as a TOC HEADING only
    # (e.g. "§3. Avtale og handelsbruk." with the body dropped by NCC's training-chunk processing).
    # trace_mean does NOT catch this (the title is faithful text) — so flag title-only captures so a
    # body-incomplete gold is never silently promoted to a trustworthy oracle. Heuristic: strip the
    # "§N." prefix; if what remains is a short capitalised title with no ledd marker, it is body-less.
    rep.title_only = [pid for pid, t in provs.items() if _is_title_only(t)]
    rep.n = len(provs)
    rep.windows = len(windows)
    rep.trace_mean = sum(traces) / len(traces) if traces else 1.0
    return provs, rep


_TITLE_PFX = re.compile(r"^§\s*\d+[a-z]?\s*\.\s*")


def _is_title_only(text: str) -> bool:
    body = _TITLE_PFX.sub("", text).strip()
    # a real provision body carries a ledd marker "(1)" or runs long; a TOC heading is a short phrase
    return "(1)" not in body and "(2)" not in body and len(body) < 55
