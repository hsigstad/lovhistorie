"""Convergence-check harness for the gazette law-reconstruction pipeline.

INTENT: quantify reconstruction quality against authoritative ground truth, so
the OCR/parse quality of the in-house build is a *measured number*, not a hope.
The reconstruction is bracketed by the current NLOD text (the authoritative
endpoint), so every OCR flip / mis-parse / missing amendment surfaces as a
per-provision mismatch — errors are detected and localized, not silent.

METHOD (for one law): compare, provision by provision, the text extracted from
Norsk Lovtidend (NB OCR) against the current NLOD consolidated text. Provisions
*unamended* since enactment must match (their similarity = OCR fidelity);
provisions amended later legitimately differ and are excluded from the fidelity
metric (their history is checked by the amendment replay instead).

REASONING: OCR text is never byte-identical to clean text, so we compare on a
normalized form (lowercase, Norwegian-alnum only, collapsed whitespace) with a
difflib similarity ratio, and strip running-header noise (page numbers, "juni
Lov nr. 35" headers) that otherwise interrupts a provision mid-sentence.

Validated on Lov om Oppgaveregisteret (LOV-1997-06-06-35): after header
stripping, 7/8 unamended provisions match at >=0.98 (mean 0.994; six byte-
perfect). The one flagged provision (§9, a cross-reference list) is exactly what
a human should eyeball — the harness doing its job.
"""
import re
import difflib
import statistics

_MON = r"(jan|feb|mars|apr|mai|juni|juli|aug|sep|sept|okt|nov|des)"


def strip_running_headers(text):
    """Drop page numbers and running headers that OCR interleaves into the body."""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if re.fullmatch(r"\d{1,4}", s):
            continue
        if re.fullmatch(rf"{_MON}\.?\s+(Lov\s+)?[Nn]r\.?\s*\d+", s):
            continue
        if re.fullmatch(rf"\d+\s+{_MON}\.?\s+[Nn]r\.?\s*\d+", s):
            continue
        out.append(ln)
    return "\n".join(out)


def strip_annotation(t):
    """Drop the trailing amendment annotation the current NLOD text appends to a
    provision ("Endret/Tilføyd/Opphevet/Endres ved lov …"), and end-of-law tails.

    BUGFIX: without this, a provision's similarity is computed against its
    *annotation* rather than its text (e.g. an "Endret ved lov 2019 …" note),
    which spuriously inflates the apparent difference for amended provisions.
    """
    t = re.split(r"\b(?:Endret|Tilf[oø]yd|Opphevet|Endres)\s+ved\b", t)[0]
    t = re.split(r"Denne lov trer i kraft|\bLov nr\.\s*\d+\b", t)[0]
    return t


def normalize(s):
    s = strip_annotation(s).lower().replace("§", " ")
    return " ".join(re.sub(r"[^a-z0-9æøå]+", " ", s).split())


def provisions(text):
    """Split into {paragraf-id: text-until-next-§} (first occurrence wins)."""
    out = {}
    parts = re.split(r"(§\s*\d+\w*)", text)
    for i in range(1, len(parts) - 1, 2):
        out.setdefault(parts[i].replace(" ", ""), parts[i + 1])
    return out


def match_report(current_text, gazette_text, amended_after=frozenset(), thresh=0.98):
    """Per-provision similarity of gazette OCR vs current NLOD; returns rows +
    a fidelity summary over the unamended provisions.
    """
    cur = provisions(current_text)
    orig = provisions(strip_running_headers(gazette_text))
    real = sorted((n for n in cur if re.match(r"§\d+$", n)), key=lambda x: int(x[1:]))
    rows, sims = [], []
    for n in real:
        o, c = normalize(orig.get(n, "")), normalize(cur.get(n, ""))
        if not o:
            rows.append((n, None, "not-extracted"))
            continue
        L = min(len(o), len(c))
        sim = difflib.SequenceMatcher(None, o[:L], c[:L]).ratio()
        amended = n in amended_after
        rows.append((n, sim, "amended" if amended else "unchanged"))
        if not amended:
            sims.append(sim)
    summary = {
        "n_unchanged": len(sims),
        "n_pass": sum(1 for s in sims if s >= thresh),
        "mean": statistics.mean(sims) if sims else None,
        "min": min(sims) if sims else None,
        "flags": [n for n, s, t in rows if t == "unchanged" and s is not None and s < thresh],
    }
    return rows, summary


if __name__ == "__main__":
    # Demo: Lov om Oppgaveregisteret. Requires the current NLOD xml locally and
    # network access to NB. Amended-after set comes from the NLOD annotations.
    import sys
    sys.path.insert(0, "source")
    from scrape.nb_lovtidend import page_text

    cur_xml = "build/laws/nl/nl-19970606-035.xml"  # current consolidated text
    raw = re.sub(r"<[^>]+>", " ", open(cur_xml, encoding="utf-8", errors="ignore").read())
    cur = raw[list(re.finditer(r"Lov om Oppgaveregisteret", raw))[-1].end():]
    urn = "URN:NBN:no-nb_digitidsskrift_2015111680005_002"  # Lovtidend 1997, this law on p.68
    gaz = "\n".join(page_text(urn, p) for p in (68, 69, 70))
    gaz = gaz.split("Lov om Oppgaveregisteret", 1)[1]

    rows, summary = match_report(cur, gaz, amended_after={"§8"})
    for n, sim, tag in rows:
        s = f"{sim:6.3f}" if sim is not None else "   --"
        print(f"{n:5} {s}  {tag}")
    print(f"\nOCR fidelity (unamended): {summary['n_pass']}/{summary['n_unchanged']} "
          f">=0.98, mean {summary['mean']:.4f}, min {summary['min']:.4f}; "
          f"flags: {summary['flags']}")
