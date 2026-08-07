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
from pathlib import Path

from source.scrape import nb_lovtidend as nb
from source.eval import metrics  # provisions_ordered — cross-reference-safe splitter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "enactment"

# Known enactment locations (public metadata: where the original text sits in NB).
# datokode -> issue URN, first physical page, and a needle on the law's title line.
LOCATIONS = {
    "1986-06-20-35": {  # mesterbrevloven
        "urn": "URN:NBN:no-nb_digitidsskrift_2015102680007_013",
        "page": 23,
        "title_needle": "Lov om mesterbrev",
    },
}

_NEXT_LAW = re.compile(r"\n\d{1,2}\.\s+\w+\.\s+Lov nr\.\s*\d+")
_HEAD = re.compile(r"(?m)^\s*§\s*(\d+[a-z]?)\.")


def _law_text(urn: str, page: int, title_needle: str, span: int = 4) -> str:
    """Raw text of the law: from its title line to the next law's gazette heading."""
    txt = "\n".join(nb.page_text(urn, p) for p in range(page, page + span))
    start = re.search(re.escape(title_needle), txt)
    if not start:
        raise ValueError(f"title needle {title_needle!r} not found on p{page}+")
    after = txt[start.start():]
    nxt = _NEXT_LAW.search(after, 50)          # skip the law's own heading line
    return after[: nxt.start() if nxt else len(after)]


def parse_provisions(law_text: str) -> dict:
    """{'§N': text} from enactment text. Order = line-start '§ N.' headings (dedup);
    extraction via provisions_ordered so in-body '§ N' references don't split."""
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
        if t:
            out[p] = t
    return out


def build(datokode: str, loc: dict | None = None) -> dict:
    loc = loc or LOCATIONS[datokode]
    law = _law_text(loc["urn"], loc["page"], loc["title_needle"], loc.get("span", 4))
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
    provs = build(dk)
    print(f"{dk}: {len(provs)} provisions -> data/enactment/{dk}.json")
    for p, t in provs.items():
        print(f"  {p}: {t[:70]}")
