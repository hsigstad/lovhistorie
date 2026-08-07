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

import re

_ANCHOR = re.compile(r'<a name="_(\d+(?:-\d+)?[a-z]?)"\s*>', re.I)


def parse(html: str) -> dict[str, str]:
    """{paragraf_id: normalized-plaintext} for each provision anchor."""
    anchors = [(m.start(), m.group(1)) for m in _ANCHOR.finditer(html)]
    out: dict[str, str] = {}
    for i, (pos, pid) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(html)
        txt = re.sub(r"<[^>]+>", " ", html[pos:end])
        out.setdefault("§" + pid, " ".join(txt.split()))
    return out


def parse_file(path) -> dict[str, str]:
    return parse(open(path, encoding="utf-8", errors="ignore").read())


if __name__ == "__main__":
    import sys
    provs = parse_file(sys.argv[1])
    print(f"parsed {len(provs)} provisions; sample:")
    for p in list(provs)[:3]:
        print(f"  {p}: {provs[p][:90]}")
