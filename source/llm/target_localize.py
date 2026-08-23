"""LLM localizer for amended-law sections — a format-agnostic replacement for amend._SECTION.

INTENT: split an amending act into per-target-law sections WITHOUT a layout-specific regex.
    The model lists every amended-law mention (its verbatim `anchor` + the `law_cite` tokens);
    this module (a) LOCATES each anchor as a verbatim source position, (b) checks the cite is
    a substring of the located anchor (hallucination gate — the model cannot invent a law not
    named in real source text), (c) resolves the cite to a datokode deterministically, and (d)
    slices the act between consecutive located anchors. Same recall payoff as broadening the
    regex, but new act layouts need ZERO new code: the model adapts, the verifier stays fixed.
REASONING: this generalizes amend.py's payload pattern (locate-by-verbatim-anchor, flag-don't-
    fabricate) from the new-text payload to the TARGET NAMING. Determinism moves from PARSING
    (brittle, per-format) to VERIFYING (fixed: substring + datokode resolve). Recall stays high
    because (i) anchor location is whitespace-tolerant with a shortened-prefix fallback, (ii)
    resolution has two routes (date-phrase parse and bare datokode), (iii) anything unresolved
    is RETURNED as a flagged mention (the caller streams it to omnibus_unresolved) — never
    dropped silently, so the residual is measurable via register_gaps.
ASSUMES: OPENAI_API_KEY in env; `act_text` is the public-domain amending act (LTI XML text or
    gazette OCR), never the current/oracle text (G1). gazette.datokode is the deterministic
    date-phrase→datokode resolver (fails safe to None).
ANTI-GAMING: reads only the public act + the model's anchors/cites (cached). No answer-key read;
    target validity is a self-consistency check (cite ⊂ anchor ⊂ source, datokode parses), not a
    lookup against data/current. G1-safe, like source/scrape/lti_amendments.py.
"""
from __future__ import annotations

import hashlib
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
    from source.llm.schemas import TargetMentions
except ModuleNotFoundError:
    from schemas import TargetMentions  # type: ignore

from source.parse import gazette

PROMPT_DIR = Path(__file__).parent / "prompts"
MODEL = "gpt-4.1"
CACHE = LLMCache(_REPO / "data" / "llm_cache" / "target_mentions")

_WS = re.compile(r"\s+")


def _hh(*parts: str) -> str:
    """Deterministic short content hash for cache doc_ids. Builtin hash() is randomized per
    process (PYTHONHASHSEED), so using it in a doc_id defeats the on-disk LLM cache ACROSS runs
    — every fresh process re-paid the call. sha256 is stable, so the cache now hits run-to-run."""
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:8]


# A NEW target-law amendment block inside an omnibus act opens with a law citation immediately
# followed by an amendatory intro. This is the DETERMINISTIC block grid used to bound each
# localized section at the next block — even when the LLM mention list MISSED that law (a recall
# gap on many-law acts): without it, one law's section over-extends and swallows the FOLLOWING
# law's ops (grannegjerde's §5/§8 leaked into oreign in lov/2013-06-21-100, because the model
# didn't list grannegjerde). It generalizes lti_amendments._BLOCK_HEADER beyond the Bokmål
# "gjøres følgende endringer:" to the Nynorsk "skal det gjerast slike endringar:" and the direct
# single-op form ("... skal § 22 f oppheves"), with an optional leading item number ("2." / "II.").
# Source-signal only (matches the header, never the answer text); when NO block matches (a
# format the grid can't see) the old anchor-to-anchor slicing is kept, so recall never drops.
_NEXT_BLOCK = re.compile(
    r"(?:\b(?:\d{1,2}\.|[IVX]+\.)\s+)?"                                          # optional item no.
    r"(?:\bI\s+)?\blov\s+\d{1,2}\.?\s*[a-zæøå]+\.?\s*\d{4}(?:\s*nr\.?\s*\d+)?"   # law citation
    r"(?:\s+(?:um|om)\s+[^§]{0,90}?)?"                                           # optional "om <name>"
    r"\s+skal\s+(?:det\s+gj|gj[øo]res|§|f[øo]lg)", re.I)


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


def _locate(anchor: str, text: str, norm_text: str, offsets: list[int], start: int) -> int:
    """First index (in ORIGINAL text) at/after `start` where `anchor` occurs, matched on
    whitespace-normalized text so OCR reflow / spacing differences don't defeat it. Falls back
    to a shortened distinctive prefix of the anchor. -1 if not found."""
    a = _norm(anchor)
    if not a:
        return -1
    # map a normalized-space cursor from the original `start`
    ns = _norm_cursor(offsets, start)
    for cand in (a, " ".join(a.split()[:6]), " ".join(a.split()[:4])):
        j = norm_text.find(cand, ns)
        if j >= 0:
            return offsets[j]
    return -1


def _build_norm(text: str):
    """Return (norm_text, offsets) where offsets[k] is the index in `text` of the k-th char of
    norm_text — so a match position in norm_text maps back to an original-text index."""
    out, offs = [], []
    prev_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            offs.append(i)
            prev_space = True
        else:
            out.append(ch)
            offs.append(i)
            prev_space = False
    norm = "".join(out).strip()
    # account for the leading strip: recompute offs aligned to the stripped string
    s = "".join(out)
    lead = len(s) - len(s.lstrip())
    return norm, offs[lead:lead + len(norm)]


def _norm_cursor(offsets: list[int], orig_start: int) -> int:
    """Smallest normalized index whose original offset is >= orig_start."""
    lo, hi = 0, len(offsets)
    while lo < hi:
        mid = (lo + hi) // 2
        if offsets[mid] < orig_start:
            lo = mid + 1
        else:
            hi = mid
    return lo


@dataclass
class LocalizeReport:
    n_mentions: int = 0
    resolved: int = 0
    unresolved: list = field(default_factory=list)   # (reason, anchor, law_cite)
    cached: bool = False
    valid: bool = True


def localize(act_text: str, *, client=None, model: str = MODEL, cache: LLMCache = CACHE,
             reextract: bool = False):
    """(sections, report) where sections = [(target_datokode, section_text)], one per located +
    resolved mention, sliced between consecutive anchors in source order. Unresolvable mentions
    are recorded in report.unresolved (NOT dropped from view) so recall loss is measurable."""
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    rep = LocalizeReport()
    try:
        res = extract(
            doc_id=f"mentions#{len(act_text)}#{_hh(act_text)}", text=act_text,
            system_prompt=(PROMPT_DIR / "target_localize_system.txt").read_text(encoding="utf-8"),
            user_prompt=act_text, schema=TargetMentions, model=model, cache=cache, client=client,
            reextract=reextract, use_structured_outputs=True, schema_in_cache_key=True,
            max_tokens=16000,   # covers the ~5 outlier acts with 60-269 mentions (p99 is 27)
        )
    except Exception as e:
        rep.valid = False
        rep.unresolved.append((f"extract-error:{type(e).__name__}", "", ""))
        return [], rep
    rep.cached = res.cached
    if not res.valid or res.parsed is None:
        rep.valid = False
        return [], rep

    norm_text, offsets = _build_norm(act_text)
    located = []                                  # (orig_pos, datokode)
    cursor = 0
    for men in res.parsed.mentions:
        rep.n_mentions += 1
        anchor, cite = men.anchor.strip(), men.law_cite.strip()
        # (b) hallucination gate: cite must lie within the anchor the model quoted
        if cite and _norm(cite) not in _norm(anchor):
            rep.unresolved.append(("cite-not-in-anchor", anchor, cite))
            continue
        # (a) locate the anchor as a verbatim source position (whitespace-tolerant)
        pos = _locate(anchor, act_text, norm_text, offsets, cursor)
        if pos < 0:
            rep.unresolved.append(("anchor-not-found", anchor, cite))
            continue
        # (c) resolve datokode: date+nr phrase route, bare-datokode route, then the date-only route
        # (nr-less 'lov av <date>' cites in old acts, matched to a tracked law by enactment date)
        dk = (gazette.datokode("lov " + cite) or _bare_datokode(cite)
              or gazette.datokode("lov " + anchor) or _date_only_datokode(anchor))
        if not dk:
            rep.unresolved.append(("cite-unresolved", anchor, cite))
            continue
        located.append((pos, dk))
        cursor = pos + 1

    located.sort()
    # deterministic block grid: bound each section at the end of the block CONTAINING its anchor,
    # so a missed mention can't let a section swallow the next law's ops (see _NEXT_BLOCK). bisect
    # the anchor into the grid; end at the next block boundary. No block info -> keep anchor-to-anchor.
    import bisect
    grid = sorted(m.start() for m in _NEXT_BLOCK.finditer(act_text))
    sections = []
    for i, (pos, dk) in enumerate(located):
        end = located[i + 1][0] if i + 1 < len(located) else len(act_text)
        if grid:
            bi = bisect.bisect_right(grid, pos) - 1        # block whose header starts at/<= anchor
            if bi + 1 < len(grid) and grid[bi + 1] < end:  # next block boundary bounds this section
                end = grid[bi + 1]
        sections.append((dk, act_text[pos:end]))
        rep.resolved += 1
    return sections, rep


_BARE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})-(\d+)\b")


def _bare_datokode(cite: str):
    m = _BARE.search(cite)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}" if m else None


# Date-only citation fallback. OLD amending acts cite the target by DATE + NAME without the "nr."
# ("I lov av 23. oktober 1959 om oreigning …"), which the nr-anchored gazette.datokode cannot resolve
# — the dominant reason pre-2001 amendments were dropped (probe 2026-08-23: oreign captured ~0/41).
# Resolve such a cite by matching its DATE against the laws we TRACK (enactment bases + the public
# amendment streams' target laws): if exactly ONE tracked law was enacted on that date, use it.
# Source-only (public act date vs our tracked universe, never the answer key) and conservative (a date
# with >1 tracked law is left unresolved, not guessed). Only tracked laws matter — an amendment to an
# untracked law is out of scope anyway.
_LAW_DATES = None
_DATE_RX = re.compile(r"\b0?(\d{1,2})\.?\s*([a-zæøå]{3,})\.?\s*(\d{4})\b", re.I)


def _tracked_law_dates():
    global _LAW_DATES
    if _LAW_DATES is not None:
        return _LAW_DATES
    import glob
    import gzip as _gz
    import json as _json
    data = _REPO / "data"
    m: dict[str, set] = {}
    for f in glob.glob(str(data / "enactment" / "*.json")):
        dk = Path(f).name.split(".")[0]
        if re.match(r"\d{4}-\d{2}-\d{2}-\d+$", dk):
            m.setdefault(dk[:10], set()).add(dk)
    for s in ("amendments.jsonl.gz", "lti_amendments.jsonl.gz", "llm_amendments.jsonl.gz"):
        p = data / s
        if not p.exists():
            continue
        for line in _gz.open(p, "rt", encoding="utf-8"):
            tl = (_json.loads(line).get("target_law") or "")
            dk = tl.split("/", 1)[1] if tl.startswith("lov/") else ""
            if re.match(r"\d{4}-\d{2}-\d{2}-\d+$", dk):
                m.setdefault(dk[:10], set()).add(dk)
    _LAW_DATES = m
    return m


def _date_only_datokode(text: str):
    """A tracked law's full datokode from a nr-less 'DD. month YYYY' date in `text`, iff that date
    maps to exactly one tracked law. None if no date, no tracked match, or an ambiguous date."""
    for mt in _DATE_RX.finditer(text):
        d, mon, y = mt.group(1), mt.group(2).lower(), mt.group(3)
        num = gazette._MONTHS.get(mon)
        if not num:                                   # OCR-tolerant prefix match
            num = next((n for name, n in gazette._MONTHS.items() if name[:3] == mon[:3]), None)
        if not num:
            continue
        hits = _tracked_law_dates().get(f"{y}-{int(num):02d}-{int(d):02d}")
        if hits and len(hits) == 1:
            return next(iter(hits))
    return None


if __name__ == "__main__":
    dk = sys.argv[1] if len(sys.argv) > 2 else "?"
    path = sys.argv[-1]
    secs, rep = localize(Path(path).read_text(encoding="utf-8"))
    print(f"{dk}: {rep.n_mentions} mentions; {rep.resolved} resolved sections; "
          f"unresolved {len(rep.unresolved)}; cached={rep.cached}")
    from collections import Counter
    for reason, cnt in Counter(r for r, *_ in rep.unresolved).most_common():
        print(f"   unresolved[{reason}]: {cnt}")
    for d, s in secs[:12]:
        print(f"   -> lov/{d}: {_norm(s)[:70]!r}")
