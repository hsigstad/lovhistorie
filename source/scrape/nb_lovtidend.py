"""Fetch pre-2001 Norsk Lovtidend text from Nasjonalbiblioteket (NB).

INTENT: get machine-readable statutory / amendment text for the pre-2001 window
that the free Lovdata dumps and the 2001-floor reconstructions (Sondre repo,
norgeslover.no) cannot supply. See docs/notes/statutory_law_versioning.md.

REASONING: NB has digitized Norsk Lovtidend and, unlike the in-copyright
*Norges Lover* book, serves it as PUBLIC DOMAIN (license=publicdomain,
viewability=ALL, accessAllowedFrom=EVERYWHERE) with per-page OCR as ALTO XML.
So we pull NB's own OCR (ABBYY FineReader) rather than OCR'ing scans ourselves,
and the whole thing is fetchable without login / Norwegian-IP / Feide.

ASSUMES: the "Avd. I. Lover og sentrale forskrifter" items are the content
volumes (the "register ..." items are indexes). Two-column print layout, so
text is reflowed by ALTO block coordinates (HPOS split at page mid).

Validated end-to-end on Lovtidend 1991 Nr. 3
(URN:NBN:no-nb_digitidsskrift_2015102680006_003).
"""
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

CATALOG = "https://api.nb.no/catalog/v1"
ALTO = CATALOG + "/metadata/{urn}/altos/{urn}_{p:04d}"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vague-lovtidend"})
    return urllib.request.urlopen(req, timeout=60).read()


def find_content_volumes(query="Norsk lovtidend Lover og sentrale forskrifter", size=50):
    """Return [(year, catalog_id, title)] for Avd. I *content* volumes.

    ASSUMES title contains 'Lover og sentrale' (excludes 'register ...' indexes).
    """
    import json
    d = json.loads(_get(f"{CATALOG}/items?q={urllib.parse.quote(query)}&size={size}"))
    rows = []
    for it in d.get("_embedded", {}).get("items", []):
        md = it.get("metadata", {})
        title = md.get("title", "")
        if "Lover og sentrale" not in title:
            continue
        year = str(md.get("originInfo", {}).get("issued") or md.get("year") or "")
        rows.append((year, it.get("id", ""), title))
    return sorted(rows)


def resolve_urn(catalog_id):
    """Catalog id (hash) -> URN:NBN digitidsskrift id used by the ALTO endpoint."""
    import json
    d = json.loads(_get(f"{CATALOG}/items/{catalog_id}"))

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                if isinstance(v, str) and v.startswith("URN:NBN"):
                    return v
                r = walk(v)
                if r:
                    return r
        if isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None

    return walk(d)


def n_pages(urn):
    import json
    m = json.loads(_get(f"{CATALOG}/iiif/{urn}/manifest"))
    return len(m["sequences"][0]["canvases"])


def _is(tag, name):
    return tag.tag.endswith(name)


def page_text(urn, p, two_col=True):
    """OCR text of one page, reflowed by column when two_col.

    REASONING: naive ALTO line order interleaves the two print columns; we sort
    TextBlocks into left/right columns by HPOS relative to page width, then each
    column top-to-bottom by VPOS.
    """
    root = ET.fromstring(_get(ALTO.format(urn=urn, p=p)))
    page = next((e for e in root.iter() if _is(e, "Page")), None)
    pw = float(page.get("WIDTH")) if page is not None and page.get("WIDTH") else None
    blocks = []
    for tb in root.iter():
        if not _is(tb, "TextBlock"):
            continue
        lines = []
        for tl in tb:
            if not _is(tl, "TextLine"):
                continue
            words = [s.get("CONTENT") for s in tl if _is(s, "String") and s.get("CONTENT")]
            if words:
                lines.append(" ".join(words))
        if lines:
            blocks.append((float(tb.get("HPOS", 0)), float(tb.get("VPOS", 0)), "\n".join(lines)))
    if two_col and pw:
        mid = pw / 2
        ordered = sorted([b for b in blocks if b[0] < mid], key=lambda b: b[1]) + \
                  sorted([b for b in blocks if b[0] >= mid], key=lambda b: b[1])
    else:
        ordered = sorted(blocks, key=lambda b: (b[1], b[0]))
    return "\n".join(b[2] for b in ordered)


def issue_text(urn, pages=None):
    pages = pages or n_pages(urn)
    return "\n".join(page_text(urn, p) for p in range(1, pages + 1))


def search(query, size=20):
    """NB full-text search over digitized periodicals (validated: locates a law
    in the right year's Lovtidend). Returns [(year, catalog_id, title)].

    REASONING: NB's catalog q= runs full-text over the OCR for periodicals, so a
    law title finds the Lovtidend volume that contains it - this solves the
    "which issue/page holds this act" location step without a separate index.
    """
    import json
    q = urllib.parse.quote(f'"{query}"')
    d = json.loads(_get(f"{CATALOG}/items?q={q}&size={size}&filter=mediatype:Tidsskrift"))
    out = []
    for it in d.get("_embedded", {}).get("items", []):
        md = it.get("metadata", {})
        title = md.get("title", "")
        year = str(md.get("originInfo", {}).get("issued") or md.get("year") or "")
        out.append((year, it.get("id", ""), title))
    return out


def find_page(urn, needle, require=None, pages=None):
    """First physical page whose text contains `needle` (and matches optional
    `require` regex). Returns (page_no, text) or (None, None).
    """
    import re
    pages = pages or n_pages(urn)
    for p in range(1, pages + 1):
        try:
            t = page_text(urn, p)
        except Exception:
            continue
        if needle in t and (require is None or re.search(require, t)):
            return p, t
    return None, None


if __name__ == "__main__":
    urn = "URN:NBN:no-nb_digitidsskrift_2015102680006_003"  # Lovtidend 1991 Nr. 3
    print(page_text(urn, 8)[:600])
