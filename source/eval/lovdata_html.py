"""Parse a Lovdata Pro historical-version HTML export into provisions.

INTENT: turn a manually-saved Lovdata Pro "Historisk versjon" HTML (the gold
    standard for a past date) into {paragraf_id: text}, so the harness can score
    our reconstruction against it (docs/evaluation.md check 2).
REASONING: these exports mark every provision with an `<a name="_X-Y">` anchor,
    which is a far cleaner boundary than the visible "§ X-Y." heading; split on the
    anchors and strip tags.
ASSUMES: provision ids look like `X-Y` / `X-Ya` (chapter-section, e.g. aksjeloven
    §1-1) or plain `N` / `Na`. HTML is the preferred ground-truth format (vs PDF).
"""
from __future__ import annotations

import html as _html
import re

_ANCHOR = re.compile(r'<a name="_(\d+(?:-\d+)?[a-z]?)"\s*>', re.I)
_TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)
_TR = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
_TD = re.compile(r"<td\b.*?</td>", re.S | re.I)


def _is_footnote_table(tbl: str) -> bool:
    """True for a Lovdata FOOTNOTE table — the editorial cross-reference apparatus the
    export renders as a two-column table, every row `[footnote-index, note-text]` (e.g.
    `[1, "Se § 5, c."]`, `[4, "Jf. lov 10 juni 2005 nr. 51."]`). SEMANTIC test, not a
    font-size heuristic: every `<tr>` must have exactly two `<td>` and the first cell must
    be a BARE integer (the note index). A genuine statutory table (rate schedule, layout)
    fails this — its first cell is not a bare note-index — so its content is preserved."""
    rows = _TR.findall(tbl)
    if not rows:
        return False
    for r in rows:
        cells = _TD.findall(r)
        if len(cells) != 2:
            return False
        first = " ".join(re.sub(r"<[^>]+>", " ", cells[0]).split())
        if not re.fullmatch(r"\d{1,3}", first):
            return False
    return True


def parse(html: str) -> dict[str, str]:
    """{paragraf_id: normalized-plaintext} for each provision anchor.

    Footnote tables are dropped (see _is_footnote_table): the export appends the editorial
    cross-reference apparatus ("Se § X", "Jf. lov Y") as a two-column table, which is NOT
    statutory text and which neither the current-text reader (parse_lovdata_xml) nor the
    reconstruction carries — leaving it in inflated the GT provision and understated clean-law
    point-in-time (rate 0.564→0.782 aggregate on removal; maintainer sign-off 2026-08-14).
    Only footnote tables are removed; statutory tables are preserved."""
    anchors = [(m.start(), m.group(1)) for m in _ANCHOR.finditer(html)]
    out: dict[str, str] = {}
    for i, (pos, pid) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(html)
        # Decode HTML entities (the Aspose export uses &#xa0; etc.) BEFORE tag-strip, so
        # a non-breaking space becomes real whitespace rather than the literal token "xa0"
        # (x,a,0 are alphanumerics that normalize would otherwise keep as spurious text).
        seg = _html.unescape(html[pos:end])
        seg = _TABLE.sub(lambda m: " " if _is_footnote_table(m.group(0)) else m.group(0), seg)
        txt = " ".join(re.sub(r"<[^>]+>", " ", seg).split())
        # Align with the gate's current-text representation (parse_lovdata_xml), which
        # starts each provision at ". <title>" — i.e. the "§ N-M" heading number is NOT
        # part of the provision text. The Lovdata HTML export keeps it ("§ 1-2. …"), and
        # since metrics.normalize maps § -> space but keeps the digits, that heading would
        # inject spurious "1 2" tokens and deflate similarity vs a correct reconstruction.
        # Drop the leading heading number (+ any superscript footnote digits) so both
        # sides are scored on the provision BODY only. (2026-08-12.)
        txt = re.sub(r"^\s*§\s*" + re.escape(pid) + r"\s*\.?\s*\d{0,3}\s*", "", txt)
        out.setdefault("§" + pid, txt)
    return out


def parse_file(path) -> dict[str, str]:
    return parse(open(path, encoding="utf-8", errors="ignore").read())


if __name__ == "__main__":
    import sys
    provs = parse_file(sys.argv[1])
    print(f"parsed {len(provs)} provisions; sample:")
    for p in list(provs)[:3]:
        print(f"  {p}: {provs[p][:90]}")
