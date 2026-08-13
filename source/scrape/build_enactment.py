"""Build a law's ENACTMENT base from Norsk Lovtidend and cache it to disk.

INTENT: one-time (offline) step — locate a law's original enactment in the NB
    Lovtidend gazette, OCR-extract it, split into {paragraf_id: text}, and write
    data/enactment/<datokode>.json. The reconstruction path then reads that cache
    (pipeline.enactment_base) with NO network and NO OCR at gate time — keeping
    reconstruction deterministic (hard rule 3) and the run reproducible.
REASONING: the gazette enactment text is PUBLIC DOMAIN and is a legitimate *input*
    (not the answer key) — so caching + committing it is fine and desirable. This is
    the analogue of the amendments parse: acquire the public source once, replay
    offline. Locating the exact issue/page is the fiddly part, so known locations are
    recorded in LOCATIONS; the search-based locator is the general path.
ASSUMES: provision headings sit at line start as "§ N." in the reflowed OCR (in-body
    "§ N" cross-references are mid-line and are filtered); a law runs from its title
    to the next "<day>. <month>. Lov nr. <n>" gazette heading.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from source.scrape import nb_lovtidend as nb
from source.eval import metrics  # provisions_ordered — cross-reference-safe splitter
from source.parse import amendments  # amended-provision set for the G3-compliance filter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "enactment"
LTI = ROOT / "data" / "lti"   # clean Lovtidend avd. I dump (one XML/act, 2001-2024)


def lti_path(datokode: str) -> Path:
    """datokode -> the clean LTI enactment XML (data/lti/<year>/nl-<datokode>.xml)."""
    y, m, d, nr = datokode.split("-")
    return LTI / y / f"nl-{y}{m}{d}-{int(nr):03d}.xml"


def build_post2001(datokode: str) -> dict:
    """Build a post-2001 law's enactment base from the clean LTI dump (no OCR)."""
    return build_from_lti(datokode, str(lti_path(datokode)))

# Known enactment locations (public metadata: where the original text sits in NB).
# datokode -> issue URN, first physical page, and a needle on the law's title line.
LOCATIONS = {
    "1986-06-20-35": {  # mesterbrevloven
        "urn": "URN:NBN:no-nb_digitidsskrift_2015102680007_013",
        "page": 23,
        "title_needle": "Lov om mesterbrev",
    },
    "1997-06-13-44": {  # aksjeloven (Lov 13. juni 1997 nr. 44 om aksjeselskaper)
        # Norsk Lovtidend Avd. I 1997 Nr. 14 (catalog id bc9cc206ad25f019010553993bc27c83)
        "urn": "URN:NBN:no-nb_digitidsskrift_2015111680005_003",
        "page": 52,
        "title_needle": "Lov om aksjeselskaper",
        "span": 75,  # law runs ~p52-125 (ch.21 markers seen through p125)
    },
    "1979-05-18-18": {  # foreldelsesloven (Lov 18. mai 1979 nr. 18 om foreldelse av fordringer)
        # Norsk Lovtidend Avd. I 1979 Nr. 15 (catalog id e75bd1fbf45e1ef8fc2d00fa8187ffa8).
        # Whole issue is this one act; headings are the period-less "§ N (tittel)" form.
        "urn": "URN:NBN:no-nb_digitidsskrift_2025070980003_015",
        "page": 4,
        "title_needle": "Lov om foreldelse av fordringer",
        "span": 13,  # pages 4-16 = the entire issue (single act, no next law)
    },
    "1959-10-23-3": {  # oreigningslova (Lov 23. okt. 1959 nr. 3 om oreigning av fast eigedom)
        # Norsk Lovtidend Avd. I 1959 Nr. 39 (catalog id c4051bf6c6c0d7aa9c15257a5b82fcf7).
        # Whole issue is this one act (single "Vi OLAV ... gjer kunnig" preamble).
        "urn": "URN:NBN:no-nb_digitidsskrift_2025110680050_016",
        "page": 8,
        "title_needle": "Lov om oreigning av fast eigedom",
        "span": 19,  # pages 8-26 = the entire issue (single act, no next law)
    },
    "1918-05-31-4": {  # avtaleloven (Lov 31. mai 1918 nr. 4 om avslutning av avtaler ...)
        # Norsk Lovtidend 1. Afdeling 1918 (pre-1949 BOUND ANNUAL, cid
        # 9e50e3a594ecedf23c3b0dccfd88ffab). Old layout: the next act ("31 mai Nr. 5")
        # shares the last page (604) with avtaleloven's tail, and its heading is NOT the
        # modern "<month> Lov nr. <n>" form _NEXT_LAW keys on, so we cut at end_needle
        # (the statsråd signature that closes the law) instead. Title wraps "Lov\nom ...",
        # so the needle omits the leading "Lov".
        "urn": "URN:NBN:no-nb_digitidsskrift_2015110481241_001",
        "page": 597,
        "title_needle": "om avslutning av avtaler",
        "span": 8,          # pages 597-604
        "end_needle": "Gunnar Knudsen.",   # statsrad signature ending §41's promulgation
    },
}

# Month names (bokmål/nynorsk + gazette abbreviations) as they appear in gazette
# act headings. Used to recognise a "<day.> <month> Lov nr. <n>" act heading.
_MONTHS_RE = r"(?:jan|feb|mars?|apr|mai|juni?|juli?|aug|sept?|okt|nov|des)\w*"

# The start of the NEXT act. The two-column OCR reflow scrambles the date line, so a
# true act boundary reads either "<day>. <month> Lov nr. <n>" or, month-before-day,
# "<month> Lov nr. <n>\n<day>", often with periods dropped. What un-ambiguously marks
# a NEW act (versus the running page header "<day>. <month> Lov nr. <n>" that repeats on
# every page of the CURRENT act) is that the act heading is immediately followed by the
# new law's title line "Lov om …" / "Lov um …". Requiring that following title line is
# what keeps this from matching the running header and truncating the law at page 2.
_NEXT_LAW = re.compile(
    r"(?m)^\s*(?:\d{1,2}\.?\s*)?" + _MONTHS_RE + r"\.?\s*Lov nr\.?\s*\d+\s*"
    r"(?:\n\s*\d{1,2}\s*)?"          # optional stray day line from column reflow
    r"\n\s*Lov\s+(?:om|um)\b",
    re.I,
)
# Provision heading at line start: "§ N." or the chapter-section form "§ N-M." (with an
# optional trailing letter, e.g. "§ 3-8a."). In-body "§ N" cross-references are mid-line
# and so are not matched. Older layouts (e.g. foreldelsesloven 1979) print the heading as
# "§ N (kort tittel)" with NO period, so a "(" immediately after the number also opens a
# heading. Requiring a "." or "(" right after the number still rejects in-body references
# like "§ 292 første ledd skal lyde:" (letter follows) even when they wrap to line start.
_HEAD = re.compile(r"(?m)^\s*§\s*(\d+(?:-\d+)?[a-z]?)\s*(?:\.|\()")


def _law_text(urn: str, page: int, title_needle: str, span: int = 4,
              end_needle: str | None = None) -> str:
    """Raw text of the law: from its title line to the next law's gazette heading.

    `end_needle` (optional): a literal string that closes the law, used for pre-1949
    bound-annual layouts where the next act's heading is NOT the modern
    "<month> Lov nr. <n>" form _NEXT_LAW keys on (so the running boundary can't be
    found automatically) and the next act shares the last page with this law's tail.
    """
    txt = "\n".join(nb.page_text(urn, p) for p in range(page, page + span))
    start = re.search(re.escape(title_needle), txt)
    if not start:
        raise ValueError(f"title needle {title_needle!r} not found on p{page}+")
    after = txt[start.start():]
    if end_needle:
        e = after.find(end_needle, 50)         # skip the law's own heading line
        if e >= 0:
            return after[: e + len(end_needle)]
    nxt = _NEXT_LAW.search(after, 50)          # skip the law's own heading line
    return after[: nxt.start() if nxt else len(after)]


# Deterministic OCR post-correction (docs/goal.md rule 3: OCR post-correction is allowed
# with sign-off IF deterministic — 2026-08-12). Non-Norwegian diacritics never
# occur in Norwegian statutory text, so every ö/ä/ü/ï/ë is an OCR misread of its base
# letter — most damagingly o->ö, which the scorer's normalize() strips to a SPACE and so
# splits common words (generalforsamlingen -> "generalf rsamlingen"). Fold them back.
# (Verified held-out: aksjeloven point-in-time 2001 +2 @>=0.98 / +5 @>=0.90, nothing drops.)
_OCR_DIACRITICS = str.maketrans("öÖäÄüÜïÏëË", "oOaAuUiIeE")


def _ocr_postcorrect(text: str) -> str:
    return text.translate(_OCR_DIACRITICS)


# OCR of chapter-section headings often mangles the "§N-M." token — the hyphen picks up
# stray spaces or becomes an en/em-dash/tilde and the trailing period drops or turns to
# noise: "§ 1 —3", "§3— 4", "§ 3-8 a". Canonicalise any "§ N <dash> M [letter]" back to
# "§N-M[letter]. " so the line-anchored _HEAD and provisions_ordered can segment §N-M laws
# whose scan garbled the hyphen (e.g. dense paperback særtrykk). Single-§ laws have no N-M
# form so they never match and are untouched. The letter suffix must be IMMEDIATE (no space)
# so "§ 2-11 første" is not mis-read as suffix "f"; the trailing "\s*\.?" absorbs an existing
# period so an already-clean "§3-8." is not doubled. LINE-ANCHORED ((?m)^): a real heading
# opens its line, whereas an in-body cross-reference ("jf. § 2-11 …") is mid-line — so this
# repairs headings without canonicalising cross-refs into phantom provisions. (An unanchored
# version regressed the already-clean antiqua gazette bases by exactly that; verified.)
_GARBLED_SECT = re.compile(r"(?m)^(\s*)§\s*(\d+)\s*[-–—~]\s*(\d+)([a-z])?\s*\.?")


def _repair_headings(text: str) -> str:
    return _GARBLED_SECT.sub(
        lambda m: f"{m.group(1)}§{m.group(2)}-{m.group(3)}{m.group(4) or ''}. ", text)


def parse_provisions(law_text: str, repair_headings: bool = False) -> dict:
    """{'§N': text} from enactment text. Order = line-start '§ N.' headings (dedup);
    extraction via provisions_ordered so in-body '§ N' references don't split.

    `repair_headings` canonicalises OCR-garbled '§ N —M' section headings first — needed
    for dense paperback særtrykk (booklets), but LEFT OFF for the gazette bases, whose
    antiqua headings are already clean and which a repair only perturbs (verified: it
    regressed aksjeloven 149→146). So the gazette build path keeps the default False and
    only build_booklet opts in."""
    if repair_headings:
        law_text = _repair_headings(law_text)
    order, seen = [], set()
    for m in _HEAD.finditer(law_text):
        p = "§" + m.group(1)
        if p not in seen:
            seen.add(p)
            order.append(p)
    provs = metrics.provisions_ordered(law_text, order)
    # drop the leading heading period, collapse whitespace, drop empties
    out = {}
    for p, t in provs.items():
        t = re.sub(r"^\s*\.\s*", "", t)
        t = " ".join(t.split())
        t = _ocr_postcorrect(t)
        if t:
            out[p] = t
    return out


_XML_TAG = re.compile(r"<[^>]+>")
_XML_WS = re.compile(r"[ \t\r\f\v]+")
# A bokstav/nr list item: `<li data-li-identifier="a)" …>` / `data-li-identifier="1."`.
# Its marker ("a)", "b)", "1.", "1)") lives in the attribute, NOT the text, so a plain
# tag-strip drops it and concatenates the items marker-less. We inject the marker
# (identifier + surrounding spaces) at each item's start so the flattened ledd carries
# `… a) item-a b) item-b …`, which the ledd engine can then split and address. This is
# symmetric: the gate parses the answer key with this SAME function, so both sides gain
# the markers identically (score-neutral for never-amended provisions).
_LI_MARK = re.compile(r'<li\b[^>]*\bdata-li-identifier="([^"]*)"[^>]*>')


def _xml_text(fragment: str) -> str:
    """Strip tags from an XML/HTML fragment -> plain text, whitespace collapsed
    (but NEWLINES are NOT introduced here; the caller inserts ledd boundaries).
    Bokstav/nr list markers (data-li-identifier) are injected as text first."""
    s = _LI_MARK.sub(lambda m: " " + m.group(1) + " ", fragment)
    s = _XML_TAG.sub(" ", s)
    s = (s.replace("&#160;", " ").replace("&nbsp;", " ")
           .replace("&amp;", "&").replace("&#38;", "&"))
    return _XML_WS.sub(" ", s).strip()


def parse_lovdata_xml(raw: str) -> dict:
    """{'§X-Y': text} from a clean Lovdata LTI enactment XML, PRESERVING sub-provision
    structure so the ledd engine can address ledd by position.

    Each provision is a `<article class="legalArticle" data-name="§X" id="P">` block;
    its top-level ledd are the DIRECT-child `<article class="legalP|numberedLegalP"
    id="P-ledd-N" | "P-nummer-N">` elements (nested list-item ledd carry longer ids
    with `-punkt-` and are excluded). We serialise a provision as
        `<title-after-§N> \n ledd1 \n ledd2 …`
    — one line per top-level ledd, the heading's title on line 0. Bokstav/nr list
    items inside a ledd are flattened into that ledd's line (their markers live in
    XML attributes, not text — exactly as the gate's current-text reader sees them),
    so a never-amended provision's base text still matches the current text; the
    similarity metric normalises whitespace away, so the newlines are score-neutral.

    Keys come from `data-name` (the authoritative §-id), NOT from scanning the body
    for `§ N`, so in-body cross-references never spawn phantom provisions."""
    provs = {}
    bounds = [(m.start(), m.group(0)) for m in re.finditer(
        r'<article class="(?:future)?[lL]egalArticle"[^>]*>', raw)]
    for i, (pos, tag) in enumerate(bounds):
        if "futureLegalArticle" in tag:          # not-yet-in-force text: skip
            continue
        dn = re.search(r'data-name="([^"]+)"', tag)
        idm = re.search(r'id="([^"]+)"', tag)
        if not dn or not idm:                    # unnamed article -> can't key it
            continue
        key = "§" + dn.group(1).lstrip("§").replace(" ", "")
        pid = idm.group(1)
        end = bounds[i + 1][0] if i + 1 < len(bounds) else len(raw)
        block = raw[pos:end]

        # title: the article header, minus its own "§ N" value span
        hm = re.search(r"<h[1-6][^>]*ArticleHeader\"[^>]*>(.*?)</h[1-6]>", block, re.S)
        title = ""
        if hm:
            title = _xml_text(hm.group(1))
            title = re.sub(r"^§\s*" + re.escape(key.lstrip("§")) + r"\b", "", title).strip()

        # top-level ledd = direct-child legalP/numberedLegalP with id == pid-ledd/nummer-N
        ledd_open = re.compile(
            r'<article class="(?:legalP|numberedLegalP)"[^>]*id="'
            + re.escape(pid) + r'-(?:ledd|nummer)-\d+"[^>]*>')
        opens = [m.start() for m in ledd_open.finditer(block)]
        if opens:
            ledd = []
            for j, s in enumerate(opens):
                e = opens[j + 1] if j + 1 < len(opens) else len(block)
                txt = _xml_text(block[s:e])
                if txt:
                    ledd.append(txt)
            provs[key] = "\n".join([title] + ledd)
        else:                                    # no structured ledd: whole body text
            body = _xml_text(block)
            body = re.sub(r"^§\s*" + re.escape(key.lstrip("§")) + r"\b", "", body).strip()
            provs[key] = body
    return provs


def build_from_lti(datokode: str, xml_path: str) -> dict:
    """Build a post-2001 enactment base from the clean Lovtidend LTI dump (one XML per
    promulgated act, keyed nl-<datokode>.xml). No network, no OCR, no locating, and
    NO reading of the current dump: the base asserts the honest LTI enactment text and
    nothing else. (A prior version filtered provisions using the answer key to dodge a
    G3 false-positive on barely-amended §5-10 — reverted; that G3 over-strictness is an
    eval-harness issue for the maintainer, not something the base build may use the key to hide.)"""
    raw = Path(xml_path).read_text(encoding="utf-8", errors="ignore")
    provs = parse_lovdata_xml(raw)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{datokode}.json").write_text(json.dumps({
        "datokode": datokode, "source": {"lti": Path(xml_path).name}, "provisions": provs,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return provs


# PD standalone-law booklets (særtrykk) at NB — the recovery route for laws whose
# annual Lovtidend Avd. I volume is in NB's digitisation gap (kjøpsloven 1988,
# rettsgebyrloven 1982). These are NOT enactment texts: each is a dated MID-LIFE
# snapshot ("Ajourført med endringer, senest …") that already incorporates the law's
# early amendments — so `base_as_of` records the version boundary the booklet prints,
# and reconstruction replays only amendments dated >= base_as_of (pipeline), while G3
# only checks post-base amendments for contamination (gate). Public-domain, EVERYWHERE
# access, mediatype books; text is public-domain by statute (åndsverkloven §14) anyway.
BOOKLETS = {
    "1988-05-13-27": {  # kjøpsloven — NB digibok 2012050708164 (1993 særtrykk, "med endringer")
        "urn": "URN:NBN:no-nb_digibok_2012050708164",
        "page": 5, "span": 26, "title_needle": "Lov om kjøp.",
        "base_as_of": "1993-01-01",  # ajourført senest 03.07.1992 nr. 93 fra 01.01.1993
    },
    "1982-12-17-86": {  # rettsgebyrloven — NB digibok 2012083008131 (1992 særtrykk)
        "urn": "URN:NBN:no-nb_digibok_2012083008131",
        "page": 3, "span": 12, "title_needle": "Lov om rettsgebyr.",
        "base_as_of": "1992-08-01",  # ajourført senest 15.05.1992 nr. 46 fra 01.08.1992
    },
}


def _resilient_pages(urn: str, page: int, span: int) -> str:
    """Join OCR text for pages [page, page+span). Tolerates the blank cover/back pages
    a booklet manifest counts but that have no ALTO layer (NB returns 500) — those are
    skipped, not fatal, so a build never aborts on a trailing non-content page."""
    out = []
    for p in range(page, page + span):
        for i in range(4):
            try:
                out.append(nb.page_text(urn, p))
                break
            except Exception:
                if i == 3:
                    out.append("")   # unfetchable cover/blank tail page — skip
                else:
                    time.sleep(1.2 * (i + 1))
    return "\n".join(out)


def build_booklet(datokode: str, loc: dict | None = None) -> dict:
    """Build a SNAPSHOT base from a PD standalone-law booklet (see BOOKLETS). Writes
    the same enactment JSON plus `base_as_of` (the booklet's ajourført version boundary)
    so the recon path replays only post-snapshot amendments and G3 only checks those."""
    loc = loc or BOOKLETS[datokode]
    txt = _resilient_pages(loc["urn"], loc["page"], loc["span"])
    start = re.search(re.escape(loc["title_needle"]), txt)
    if not start:
        raise ValueError(f"title needle {loc['title_needle']!r} not found in booklet")
    provs = parse_provisions(txt[start.start():], repair_headings=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{datokode}.json").write_text(json.dumps({
        "datokode": datokode,
        "source": {"urn": loc["urn"], "page": loc["page"], "booklet": True},
        "base_as_of": loc["base_as_of"],
        "provisions": provs,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return provs


def build(datokode: str, loc: dict | None = None) -> dict:
    loc = loc or LOCATIONS[datokode]
    law = _law_text(loc["urn"], loc["page"], loc["title_needle"], loc.get("span", 4),
                    loc.get("end_needle"))
    provs = parse_provisions(law)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{datokode}.json"
    out.write_text(json.dumps({
        "datokode": datokode,
        "source": {k: loc[k] for k in ("urn", "page")},
        "provisions": provs,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return provs


if __name__ == "__main__":
    dk = sys.argv[1] if len(sys.argv) > 1 else "1986-06-20-35"
    provs = build_booklet(dk) if dk in BOOKLETS else build(dk)
    tag = " (booklet snapshot)" if dk in BOOKLETS else ""
    print(f"{dk}: {len(provs)} provisions -> data/enactment/{dk}.json{tag}")
    for p, t in provs.items():
        print(f"  {p}: {t[:70]}")
