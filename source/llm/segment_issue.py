"""LLM act-segmenter for a Norsk Lovtidend issue — replaces the TOC-dependent regex segmenter.

INTENT: split one issue's OCR into its constituent acts {nr, date, title, body} WITHOUT relying on
    an "Innhold" TOC or a single "Lov nr. N\\n" heading format. `gazette.parse_issue` (regex) returns
    0 acts for 833/1033 harvested issues (80%, ~127k pages) because most issues lack the "Innhold"
    header and render headings as "Lov nr. 3." (period) not "Lov nr. 3\\n" — locking the pre-2001
    amendments (incl. avtaleloven §36) out of recovery. This uses the project's localize-then-verify
    pattern: the model LOCATES each act's "Lov nr. N" heading (verbatim anchor + nr + date + title);
    the deterministic layer verifies the anchor is a real source slice, reads the nr, resolves the
    datokode from the act's OWN date, and slices bodies between consecutive located headings.
REASONING: segmentation is a LOCALISATION task (where does each act start?), exactly what the anchor
    pattern handles — the model never emits body text, only headings it can point to, so a mislocated
    or invented heading is dropped (flag-don't-fabricate), never fabricated. Act dates come from the
    heading region, so the datokode needs no separate (mis-firing) issue-year heuristic.
ASSUMES: OPENAI_API_KEY; `pages` is the public-domain NB OCR (data/lovtidend_text/<id>.jsonl.gz),
    never the current/answer text (G1). Large issues are chunked with overlap so no heading is missed
    at a boundary; headings are deduped by located position.
ANTI-GAMING: reads only public OCR + the model's heading anchors (cached). G1-safe, like segment.py.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
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

from source.llm.target_localize import _build_norm, _locate, _norm
from source.parse import gazette

PROMPT_DIR = Path(__file__).parent / "prompts"
MODEL = "gpt-4.1-mini"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "issue_acts")

_CHUNK = 18000        # chars per LLM window (issues run to ~200 pages)
_OVERLAP = 1500       # carry-over so an act heading at a boundary is seen whole


class ActHeading(BaseModel):
    """One act's opening heading, LOCATED not quoted. `anchor` is the verbatim run of ~6-12 words at
    the 'Lov nr. N …' heading (a source slice we re-find); `nr` is the act number; `date` is the act's
    own date as written ('4. mars 1983', '' if absent); `title` a short label."""
    anchor: str
    nr: int
    date: str = ""
    title: str = ""


class IssueActs(ExtractionSchema):
    schema_name: ClassVar[str] = "lovhistorie_issue_acts"
    schema_version: ClassVar[str] = "v1"
    acts: list[ActHeading] = []


@dataclass
class SegReport:
    n_headings: int = 0
    located: int = 0
    dropped: list = field(default_factory=list)   # (reason, anchor, nr)
    cached_all: bool = True


def _chunks(text: str):
    i = 0
    while i < len(text):
        yield i, text[i:i + _CHUNK]
        if i + _CHUNK >= len(text):
            break
        i += _CHUNK - _OVERLAP


def _system_prompt() -> str:
    return (PROMPT_DIR / "segment_issue_system.txt").read_text(encoding="utf-8")


def segment(pages, *, client=None, model: str = MODEL, cache: LLMCache = CACHE,
            reextract: bool = False):
    """[{nr, date, klass, target, title, body}] — one per located act, in source order. Mirrors the
    dict shape of gazette.parse_issue()['acts'] so build_gazette can use it as a drop-in."""
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    full = "\n".join(p.get("text", "") for p in pages)
    rep = SegReport()
    norm_text, offsets = _build_norm(full)

    located = {}   # orig_pos -> (nr, date, title)
    for ci, (base, chunk) in enumerate(_chunks(full)):
        try:
            res = extract(
                doc_id=f"issueacts#{len(full)}#{ci}#{hash(chunk) & 0xffffffff:x}", text=chunk,
                system_prompt=_system_prompt(), user_prompt=chunk, schema=IssueActs,
                model=model, cache=cache, client=client, reextract=reextract,
                use_structured_outputs=True, schema_in_cache_key=True, max_tokens=8000,
            )
        except Exception as e:
            rep.dropped.append((f"extract-error:{type(e).__name__}", "", -1))
            rep.cached_all = False
            continue
        rep.cached_all = rep.cached_all and res.cached
        if not res.valid or res.parsed is None:
            rep.cached_all = False
            continue
        for h in res.parsed.acts:
            rep.n_headings += 1
            anchor = (h.anchor or "").strip()
            if not anchor or _norm("Lov nr") not in _norm(anchor):   # must be a real act heading
                rep.dropped.append(("not-act-heading", anchor[:50], h.nr))
                continue
            pos = _locate(anchor, full, norm_text, offsets, 0)
            if pos < 0:
                rep.dropped.append(("anchor-not-found", anchor[:50], h.nr))
                continue
            located.setdefault(pos, (h.nr, h.date.strip(), h.title.strip()))

    # An act's "Lov nr. N" repeats as a running page header; the model may anchor a later repeat as a
    # second heading, splitting the body. Keep only the FIRST position per nr (acts are nr-ascending).
    first_pos = {}
    for pos in sorted(located):
        nr = located[pos][0]
        first_pos.setdefault(nr, pos)
    located = {pos: located[pos] for pos in first_pos.values()}

    starts = sorted(located)
    acts = []
    for i, pos in enumerate(starts):
        nr, date, title = located[pos]
        end = starts[i + 1] if i + 1 < len(starts) else len(full)
        body = full[pos:end]
        # datokode from the act's OWN date + nr (no issue-year heuristic); klass/target from the body
        dk = gazette.datokode(f"lov {date} nr. {nr}") if date else None
        yyyy_mm_dd = dk[: len("YYYY-MM-DD")] if dk else None
        rest = body[:400]
        klass = gazette.classify(rest)
        acts.append({
            "nr": nr,
            "date": yyyy_mm_dd,
            "datokode": dk,
            "klass": klass,
            "target": gazette.datokode(rest) if klass in ("amend", "repeal") else None,
            "title": title or " ".join(rest.split())[:120],
            "body": body,
        })
        rep.located += 1
    return acts, rep


if __name__ == "__main__":
    import gzip, json
    path = sys.argv[1]
    pages = [json.loads(l) for l in gzip.open(path, "rt", encoding="utf-8")]
    acts, rep = segment(pages)
    print(f"{Path(path).name}: {rep.located} acts located "
          f"({rep.n_headings} headings, {len(rep.dropped)} dropped, cached_all={rep.cached_all})")
    for a in acts[:20]:
        print(f"  nr {a['nr']:>3} {a['date'] or '????-??-??'} [{a['klass']}] len={len(a['body']):>6}  {a['title'][:45]}")
