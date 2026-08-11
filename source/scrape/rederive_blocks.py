"""Re-derive FULL (untruncated) amendment-block text from the LTI amending-act XMLs.

INTENT: the upstream Lovtidend parse writes data/amendments.jsonl.gz with `new_text`
    hard-truncated at 4000 chars. For big whole-chapter / whole-part replacements
    ("Kapittel N skal lyde:", "Etter kapittel 10 skal del 4 til 6 lyde:") that cut
    loses the block's TAIL provisions, so pipeline.load_ops._split_block never sees
    them and reconstruct() drops ~dozens of provisions per law (vphl: ~90-114). This
    OFFLINE script re-opens each truncated op's amending act in the clean LTI dump,
    extracts the FULL replacement block in the SAME serialisation the upstream parser
    used, and writes overrides to data/amendment_blocks.jsonl.gz. The reconstruction
    path then reads only that derived DATA file (source.parse.amendments) — it never
    touches nl-*.xml, keeping the eval gate's G1 static guard clean.
REASONING: an amending act embeds each instruction's replacement content as a run of
    `<article class="futureLegalArticle" data-name="§X-Y">` blocks (not-yet-in-force
    markup) right after the `<article class="defaultP">…skal lyde:</article>`
    instruction, with `<span class="futuretitle">` avsnitt/chapter subtitles between
    them. We serialise those § articles as `§ X-Y.<title>\n<ledd1>\n<ledd2> …`, one
    provision per line-start `§ N.` heading — exactly what _split_block expects.
ANTI-FABRICATION: an override is ACCEPTED only when its first 4000 chars reproduce the
    op's truncated new_text EXACTLY (the truncation is a pure prefix cut, so a faithful
    re-derivation must match it byte-for-byte). Any op whose act XML is missing (e.g.
    act year > 2024, outside LTI's 2001-2024 range), whose instruction can't be located,
    or whose serialisation prefix does not match is SKIPPED and left truncated — never
    guessed.
ASSUMES: act_refid like 'lov/2019-06-21-41' maps to data/lti/2019/nl-20190621-041.xml
    (build_enactment.lti_path). Truncated rows are exactly len(new_text)==4000.
"""
from __future__ import annotations

import gzip
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LTI = ROOT / "data" / "lti"
AMEND = ROOT / "data" / "amendments.jsonl.gz"
OUT = ROOT / "data" / "amendment_blocks.jsonl.gz"

TRUNC_LEN = 4000  # the upstream hard cap; rows with exactly this length are truncated

_ACT_RE = re.compile(r"^(?:lov|forskrift)/(\d{4})-(\d{2})-(\d{2})-(\d+)$")

# Elements that end a replacement block or a single provision within it. A new
# instruction is a `defaultP`; a new law-section is a `<section>` / roman `<h>` header;
# provision boundaries inside the block are the next future article or the next
# `futuretitle` avsnitt/chapter subtitle.
_DELIM = re.compile(
    r'<article class="futureLegalArticle"[^>]*>|<span class="futuretitle"'
    r'|<h[1-6][ >]|</?section[ >]|<article class="defaultP"')
_DEFAULTP = re.compile(r'<article class="defaultP"[^>]*>(.*?)</article>', re.S)
_FUTURE_ART = re.compile(r'<article class="futureLegalArticle"[^>]*>')
_SECTION = re.compile(r"<section[ >]")

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\n\f\v]+")


def _flatten(fragment: str) -> str:
    """Fragment -> plain text, EXACTLY as the upstream amendment parser serialised it.

    Text NODES (the pieces between tags) are each entity-decoded, internal ordinary-
    whitespace-collapsed and EDGE-STRIPPED, then concatenated with NO separator — so a
    space that sits against a tag boundary disappears (`foretaket: <ul><li>er` ->
    `foretaket:er`) and list items run straight together (`instrumenter,` + `utførelse`
    -> `instrumenter,utførelse`). Entities become their real chars and are KEPT (`&#xa0;`
    -> the nbsp char, not a space). Bokstav/nr list markers (data-li-identifier) are
    DROPPED. Non-breaking spaces are NOT collapsed. This matches the upstream stream (and
    the non-truncated head of every block, which the prefix-match check verifies).
    NB: deliberately different from build_enactment._xml_text (which injects list markers,
    maps nbsp->space, and pads tag boundaries) — that would break byte-for-byte match."""
    out = []
    for node in _TAG.split(fragment):
        node = _WS.sub(" ", html.unescape(node)).strip()
        if node:
            out.append(node)
    return "".join(out)


def lti_path(act_refid: str) -> Path | None:
    """act_refid ('lov/2019-06-21-41') -> data/lti/<year>/nl-<datokode>.xml, or None if
    the ref is unparseable, the year is outside LTI's 2001-2024 coverage, or the file
    is absent."""
    m = _ACT_RE.match(act_refid or "")
    if not m:
        return None
    y, mo, d, nr = m.groups()
    if not (2001 <= int(y) <= 2024):
        return None
    p = LTI / y / f"nl-{y}{mo}{d}-{int(nr):03d}.xml"
    return p if p.exists() else None


def _serialize_block(frag: str) -> str:
    """Serialise a replacement-block fragment into `§ X-Y.<title>\\n<ledd> …` text, one
    provision per line-start `§ N.` heading — the exact shape _split_block splits on."""
    arts = list(_FUTURE_ART.finditer(frag))
    delims = sorted(m.start() for m in _DELIM.finditer(frag))
    out = []
    for m in arts:
        pos, tag = m.start(), m.group(0)
        dn = re.search(r'data-name="([^"]+)"', tag)
        idm = re.search(r'id="([^"]+)"', tag)
        if not dn or not idm:
            continue
        num = dn.group(1).lstrip("§").replace(" ", "")
        pid = idm.group(1)
        nxt = [x for x in delims if x > pos]
        b = frag[pos:(min(nxt) if nxt else len(frag))]
        # title = the article header's <span class="legalArticleTitle"> content
        tm = re.search(r'legalArticleTitle"[^>]*>(.*?)</span>', b, re.S)
        title = _flatten(tm.group(1)) if tm else ""
        # top-level ledd = direct-child legalP/numberedLegalP with id == pid-ledd/nummer-N
        lo = re.compile(
            r'<article class="(?:legalP|numberedLegalP)"[^>]*id="'
            + re.escape(pid) + r'-(?:ledd|nummer)-\d+"[^>]*>')
        opens = [x.start() for x in lo.finditer(b)]
        ledd = []
        for j, s in enumerate(opens):
            e = opens[j + 1] if j + 1 < len(opens) else len(b)
            t = _flatten(b[s:e])
            if t:
                ledd.append(t)
        piece = "§ " + num + "." + title
        for l in ledd:
            piece += "\n" + l
        out.append(piece)
    return "\n".join(out)


def _candidate_blocks(raw: str, instruction: str):
    """All replacement-block fragments whose instruction defaultP text == `instruction`.
    A block runs from the instruction's end to the next instruction (defaultP) or the
    next law-section (<section>), whichever comes first."""
    instr = (instruction or "").strip()
    frags = []
    for m in _DEFAULTP.finditer(raw):
        if _flatten(m.group(1)) != instr:
            continue
        st = m.end()
        e1 = raw.find('<article class="defaultP"', st)
        sm = _SECTION.search(raw, st)
        e1 = e1 if e1 >= 0 else len(raw)
        e2 = sm.start() if sm else len(raw)
        frags.append(raw[st:min(e1, e2)])
    return frags


def rederive(verbose: bool = True):
    derived, skipped = [], []
    # cache raw XML per act to avoid re-reading a big file for its several ops
    raw_cache: dict[str, str | None] = {}
    with gzip.open(AMEND, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            nt = d.get("new_text") or ""
            if len(nt) != TRUNC_LEN:
                continue
            act = d.get("act_refid")
            tgt = d.get("target_law")
            instr = d.get("instruction")
            key = (act, tgt, instr)
            path = lti_path(act)
            if path is None:
                skipped.append((key, "no LTI xml (missing / act year >2024 / not lov)"))
                continue
            if act not in raw_cache:
                raw_cache[act] = path.read_text(encoding="utf-8", errors="ignore")
            raw = raw_cache[act]
            fulls = [_serialize_block(f) for f in _candidate_blocks(raw, instr)]
            # ACCEPT only a block whose 4000-char prefix reproduces the truncated text
            match = next((f for f in fulls if f[:TRUNC_LEN] == nt), None)
            if match is None:
                why = ("instruction not found in xml" if not fulls
                       else "no candidate block prefix matched truncated text")
                skipped.append((key, why))
                continue
            derived.append({
                "act_refid": act, "target_law": tgt, "instruction": instr,
                "new_text": match,
            })

    # dedup by (act, target_law, instruction) — keep first (all candidates identical)
    seen, uniq = set(), []
    for r in derived:
        k = (r["act_refid"], r["target_law"], r["instruction"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for r in uniq:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    if verbose:
        print(f"re-derived {len(uniq)} blocks -> {OUT.relative_to(ROOT)}")
        by_law: dict[str, int] = {}
        for r in uniq:
            by_law[r["target_law"]] = by_law.get(r["target_law"], 0) + 1
        for law, n in sorted(by_law.items(), key=lambda kv: -kv[1]):
            print(f"   {n:4d}  {law}")
        print(f"skipped {len(skipped)} truncated ops:")
        # group skip reasons
        reasons: dict[str, int] = {}
        acts_over_2024 = set()
        for (act, tgt, instr), why in skipped:
            reasons[why] = reasons.get(why, 0) + 1
            m = _ACT_RE.match(act or "")
            if m and int(m.group(1)) > 2024:
                acts_over_2024.add(act)
        for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"   {n:4d}  {why}")
        if acts_over_2024:
            print("   act years >2024 (un-derivable, LTI ends 2024): "
                  + ", ".join(sorted(acts_over_2024)))
    return uniq, skipped


if __name__ == "__main__":
    rederive(verbose="-q" not in sys.argv)
