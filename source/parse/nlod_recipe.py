"""Extract a law's amendment 'recipe' from the current NLOD consolidated text.

INTENT: the current gjeldende-lover text annotates every provision with its
amendment chain ("Endret ved lov 25 nov 2022 nr. 86 (i kraft ... iflg. res.
... nr. 2013)"). That gives the COMPLETE, dated list of amending acts to fetch
and replay - so an Option-1 full-history reconstruction (original enactment +
all amendments, all from public-domain Lovtidend) needs no historical snapshot.

REASONING: we only need the list of *acts*; their full "skal lyde" text is then
pulled from Lovtidend. The enacting act itself is the base (from Lovtidend at
the enactment date).

ASSUMES: annotations name acts as "<d> <mon> <yyyy> nr. <n>". We keep only *lov*
references and drop resolution/forskrift numbers (the "iflg. res. ... nr. XXXX"
inside the ikrafttredelse parenthetical), which is the capture-then-filter step.
"""
import re
import os

MONTHS = {"jan": 1, "feb": 2, "mars": 3, "apr": 4, "mai": 5, "juni": 6,
          "juli": 7, "aug": 8, "sep": 9, "sept": 9, "okt": 10, "nov": 11, "des": 12}

_REF = re.compile(r"(\d{1,2})\s+(\w+?)\.?\s+(\d{4})\s+nr\.?\s*(\d+)")


def _month(tok):
    tok = tok.lower().rstrip(".")
    return MONTHS.get(tok[:4]) or MONTHS.get(tok[:3])


def enactment(xml_path):
    """(year, month, day, nr) from the nl-YYYYMMDD-NNN filename."""
    m = re.match(r"nl-(\d{4})(\d{2})(\d{2})-(\d+)", os.path.basename(xml_path))
    return tuple(int(x) for x in m.groups()) if m else None


def amendments_of(xml_path):
    """Sorted, deduped list of (year, month, day, nr) amending *laws*.

    Drops references that sit in an "iflg. res." / "res." context (those are
    ikrafttredelsesresolusjoner / forskrifter, not amending laws).
    """
    t = open(xml_path, encoding="utf-8", errors="ignore").read()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t)
    refs = set()
    for m in _REF.finditer(t):
        d, mon, y, nr = m.groups()
        mm = _month(mon)
        if not mm:
            continue
        # filter: skip if the ~12 chars before this ref mention 'res.' (resolution)
        pre = t[max(0, m.start() - 14):m.start()].lower()
        if "res." in pre or "forskrift" in pre:
            continue
        refs.add((int(y), mm, int(d), int(nr)))
    return sorted(refs)


if __name__ == "__main__":
    import glob
    for f in sorted(glob.glob("nl/*.xml"))[:1] or ["nl-19970606-035.xml"]:
        print("enacted:", enactment(f))
        for a in amendments_of(f):
            print("  amending lov:", a)
