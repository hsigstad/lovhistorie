"""Structure a harvested Norsk Lovtidend issue into individual acts.

INTENT: turn the raw per-page OCR of one gazette issue (data/lovtidend_text/<id>.jsonl.gz)
    into a list of structured acts — each with its date, act number, class (original
    enactment / amendment / repeal / ikrafttredelse), the law it targets, and its body
    text. Amendment bodies then feed source.parse.endringslov.parse_amendments to yield
    the pre-2001 amendment stream that LTI (2001+) lacks; original-enactment bodies feed
    the provision splitter for enactment bases. This is the upstream act-boundary /
    header layer that endringslov.py assumes it is given.

REASONING: each issue opens with an "Innhold" (table of contents) that enumerates every
    act as "<Month> <day>. Lov nr. <n> om <endr./opph. av/…> <title> <pageno>". The TOC
    is a clean, machine-readable index of act number → date → class → target-law citation,
    far more reliable than heuristic body-boundary detection. We parse the TOC for the
    inventory, then slice each act's body by its "Lov nr. <n>" heading in the post-TOC
    pages.

ASSUMES: modern (~1949+) per-issue format with an Innhold TOC and "Lov nr. N" headings.
    Pre-1949 bound annuals differ and are handled later. Two-column OCR reflow scrambles
    the date line (e.g. body heading "15\ndes. Lov nr. 89"), so body-heading detection
    keys on "Lov nr. <n>" alone, not the date.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

# Norwegian month names (bokmål + nynorsk + gazette abbreviations) -> month number.
_MONTHS = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "mars": 3, "mar": 3,
    "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "november": 11, "nov": 11, "desember": 12, "des": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

# A law citation inside a title: "lov 21. november 1952 nr. 2" -> datokode. Tolerant of
# the frequent OCR "nr. 2om" (missing space before the following word).
_CITE = re.compile(
    rf"lov\s+(?:av\s+)?(\d{{1,2}})\.?\s*({_MONTH_RE})\w*\.?\s*(\d{{4}})\s*nr\.?\s*(\d+)",
    re.I,
)

# A TOC / body act heading: "<Month> <day>. Lov nr. <n>" (month & day order varies with
# reflow, so we also accept "<day>. <Month> ... Lov nr. <n>" — we only need the nr here).
_TOC_ENTRY = re.compile(
    rf"(?P<mon>{_MONTH_RE})\w*\.?\s*(?P<day>\d{{1,2}})\.\s*Lov\s+nr\.?\s*(?P<nr>\d+)\s*(?P<rest>.*)",
    re.I,
)


def datokode(citation: str) -> str | None:
    """'lov 21. november 1952 nr. 2 om …' -> '1952-11-21-2' (first citation). None if
    no parseable law citation is present."""
    m = _CITE.search(citation)
    if not m:
        return None
    day, mon, year, nr = m.groups()
    mm = _MONTHS.get(mon.lower())
    if not mm:
        return None
    return f"{year}-{mm:02d}-{int(day):02d}-{int(nr)}"


def classify(title_rest: str) -> str:
    """Class of a Lov act from the text after 'Lov nr. N': amend / repeal / original.
    (ikrafttredelse/delegering entries are TOC-only and filtered before this.)"""
    t = title_rest.lower()
    if re.search(r"\bom\s+opph(?:evelse|\.)", t) or re.match(r"\s*om\s+opph", t):
        return "repeal"
    if re.search(r"\bom\s+endr", t):  # "om endr." / "om endringer"
        return "amend"
    return "original"


def load_issue(path: str | Path) -> list[dict]:
    """Read a harvested issue cache into [{page, text}]."""
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def issue_year(pages: list[dict]) -> int | None:
    """The issue's year, from the cover line 'Nr. <n> - <YEAR>' on the first pages."""
    head = "\n".join(p["text"] for p in pages[:3])
    m = re.search(r"Nr\.\s*\d+\s*[-–]\s*(19\d\d|20\d\d)", head)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(18\d\d|19\d\d|20\d\d)\b", head)
    return int(m.group(1)) if m else None


def parse_toc(pages: list[dict], year: int | None) -> list[dict]:
    """Parse the Innhold TOC into act records. Each: {nr, date, klass, target, title}.
    Only 'Lov nr.' acts (skips Forskrift/Ikrafttr./Deleg. lines). date is YYYY-MM-DD."""
    # The TOC lives between "Innhold" and the first act body; scan the first ~8 pages.
    toc_text = "\n".join(p["text"] for p in pages[:8])
    start = toc_text.find("Innhold")
    if start >= 0:
        toc_text = toc_text[start:]
    acts = {}
    for m in _TOC_ENTRY.finditer(toc_text):
        nr = int(m.group("nr"))
        rest = m.group("rest")
        klass = classify(rest)
        mm = _MONTHS.get(m.group("mon").lower())
        day = int(m.group("day"))
        date = f"{year}-{mm:02d}-{day:02d}" if (year and mm) else None
        rec = {
            "nr": nr,
            "date": date,
            "klass": klass,
            "target": datokode(rest) if klass in ("amend", "repeal") else None,
            "title": " ".join(rest.split())[:200],
        }
        acts.setdefault(nr, rec)  # first (TOC) occurrence wins
    return [acts[k] for k in sorted(acts)]


# A BODY act heading (not a TOC/cover line): "Lov nr. <n>" followed immediately by a
# newline (reflowed running-page header). TOC entries read "Lov nr. 87 om endr. …"
# (word, not newline) and the cover spine reads "Lov nr. 86 - 103" (dash) — both are
# excluded by requiring only whitespace between the number and the line break.
_BODY_HEAD = re.compile(r"Lov\s+nr\.?\s*(\d+)\s*\n")


def split_bodies(pages: list[dict], toc: list[dict]) -> dict[int, str]:
    """Map act nr -> body text, disjoint and in nr order.

    Acts appear in the body in ascending nr order, and each act's body repeats its
    "Lov nr. <n>" heading as a running page header. Walking nrs ascending and taking,
    for each, the FIRST body heading that comes AFTER the previous act's chosen
    position keeps bodies disjoint and correctly ordered — and skips both the front
    matter (TOC/cover, excluded by _BODY_HEAD) and later running-header repeats that
    the old "last occurrence" rule used to grab (which leaked one act's tail into the
    next). Returns {} when no body headings can be located."""
    full = "\n".join(p["text"] for p in pages)
    by_nr: dict[int, list[int]] = {}
    for m in _BODY_HEAD.finditer(full):
        by_nr.setdefault(int(m.group(1)), []).append(m.start())
    if not by_nr:
        return {}
    chosen: list[tuple[int, int]] = []
    prev = -1
    for nr in sorted({a["nr"] for a in toc}):
        after = [p for p in by_nr.get(nr, []) if p > prev]
        if not after:
            continue
        pos = min(after)
        chosen.append((nr, pos))
        prev = pos
    bodies = {}
    for i, (nr, pos) in enumerate(chosen):
        end = chosen[i + 1][1] if i + 1 < len(chosen) else len(full)
        bodies[nr] = full[pos:end]
    return bodies


def parse_issue(path: str | Path) -> dict:
    """Full structure of one issue: {year, acts:[{nr,date,klass,target,title,body}]}."""
    pages = load_issue(path)
    year = issue_year(pages)
    toc = parse_toc(pages, year)
    bodies = split_bodies(pages, toc)
    for a in toc:
        a["body"] = bodies.get(a["nr"], "")
    return {"year": year, "path": str(path), "acts": toc}


def check_boundaries(pages: list[dict], toc: list[dict]) -> tuple[bool, str]:
    """Verify body slicing is clean for one issue: (a) chosen body start positions are
    strictly increasing in nr order and (b) no act's body contains the NEXT act's
    body heading ('Lov nr. <next>\\n') as its own content. Returns (ok, message)."""
    full = "\n".join(p["text"] for p in pages)
    bodies = split_bodies(pages, toc)
    present = [a["nr"] for a in sorted(toc, key=lambda a: a["nr"]) if a["nr"] in bodies]
    starts = [full.index(bodies[nr]) for nr in present]
    inc = all(starts[i] < starts[i + 1] for i in range(len(starts) - 1))
    bleed = []
    for i, nr in enumerate(present[:-1]):
        nxt = present[i + 1]
        # the next act's OWN body heading must not appear inside this act's body
        if re.search(rf"Lov\s+nr\.?\s*{nxt}\s*\n", bodies[nr]):
            bleed.append((nr, nxt))
    ok = inc and not bleed
    msg = f"increasing={inc} bleed={bleed if bleed else 'none'} (n={len(present)})"
    return ok, msg


def _instruction(op: dict) -> str:
    """Reconstruct an instruction string from a parsed op so amendments.classify()
    can type it (replace / subprovision / repeal / add / other)."""
    para = op["paragraf"] or ""
    sub = op["subunit"] or ""
    tail = "oppheves" if op["action"] == "repeal" else "skal lyde"
    return " ".join(f"{para} {sub} {tail}".split())


def _change_type(op: dict) -> str:
    """Best-effort ENDR / OPPH / NY mapping for the amendment stream."""
    if op["action"] == "repeal":
        return "OPPH"
    if (op["subunit"] or "").lower().startswith("kapittel"):
        return "NY"
    return "ENDR"


def build_amendment_ops(paths) -> list[dict]:
    """Run gazette + endringslov over cached issues and emit the pre-2001 amendment
    stream as dicts matching data/amendments.jsonl.gz's schema (so it can later merge
    with the 2001+ LTI stream). One dict per provision op of every amendment/repeal
    act whose target law resolved to a datokode. Acts whose target is cited only by
    name (e.g. 'offentlighetsloven') carry no datokode and are skipped here."""
    from source.parse import endringslov

    out = []
    for path in paths:
        iss = parse_issue(path)
        for a in iss["acts"]:
            if a["klass"] not in ("amend", "repeal") or not a["target"] or not a["body"]:
                continue
            # act_refid: synthesised datokode of the AMENDING act (date + nr).
            act_refid = f"lov/{a['date']}-{a['nr']}" if a["date"] else f"lov/?-{a['nr']}"
            for op in endringslov.parse_amendments(a["body"]):
                out.append({
                    "act_refid": act_refid,
                    "act_title": a["title"],
                    "target_law": f"lov/{a['target']}",
                    "target": op["subunit"] or op["paragraf"] or None,
                    "paragraph": op["paragraf"] or None,
                    "change_type": _change_type(op),
                    "instruction": _instruction(op),
                    "new_text": op["new_text"],
                    # NB: the act date is a first approximation of entry-into-force; the
                    # true ikrafttredelse is often a later date stated in the act body
                    # ("trer i kraft 1. januar 2001") and is not resolved here yet.
                    "date_in_force_resolved": a["date"],
                    "date_published": a["date"],
                    "source": "nb_lovtidend_pre2001",
                })
    return out


if __name__ == "__main__":
    import glob
    import gzip as _gzip
    import sys
    from source.parse import endringslov

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_build = "--build" in sys.argv
    data_dir = Path(__file__).resolve().parents[2] / "data"
    files = sorted(glob.glob(str(data_dir / "lovtidend_text" / "*.jsonl.gz")))
    if args:
        files = [f for f in files if args[0] in f]

    if do_build:
        from source.parse import amendments
        ops = build_amendment_ops(files)
        out_path = data_dir / "pre2001_amendments.jsonl.gz"
        with _gzip.open(out_path, "wt", encoding="utf-8") as fh:
            for op in ops:
                fh.write(json.dumps(op, ensure_ascii=False) + "\n")
        laws = {o["target_law"] for o in ops}
        kinds = {}
        for o in ops:
            _, kind = amendments.classify(o["instruction"])
            kinds[kind] = kinds.get(kind, 0) + 1
        print(f"wrote {len(ops)} ops -> {out_path}")
        print(f"distinct target laws: {len(laws)}")
        print("amendments.classify() types:",
              ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
        print("\nsample ops:")
        for o in ops[:4]:
            print(f"  {o['target_law']} | {o['instruction']!r} | "
                  f"{(o['new_text'] or '')[:100]!r}")
        sys.exit(0)

    tot_acts = tot_amend = tot_target = tot_ops = tot_body = 0
    all_clean = True
    for f in files:
        iss = parse_issue(f)
        acts = iss["acts"]
        amend = [a for a in acts if a["klass"] in ("amend", "repeal")]
        tgt = [a for a in amend if a["target"]]
        withbody = [a for a in acts if a["body"]]
        ops = 0
        for a in amend:
            ops += len(endringslov.parse_amendments(a["body"])) if a["body"] else 0
        clean, msg = check_boundaries(load_issue(f), acts)
        all_clean = all_clean and clean
        print(f"{Path(f).name[:12]} yr={iss['year']} acts={len(acts):3d} "
              f"amend={len(amend):3d} target-resolved={len(tgt):3d} "
              f"bodies={len(withbody):3d} ops={ops:4d}  boundaries[{msg}]")
        tot_acts += len(acts); tot_amend += len(amend); tot_target += len(tgt)
        tot_ops += ops; tot_body += len(withbody)
    print(f"\nTOTAL acts={tot_acts} amend={tot_amend} target-resolved={tot_target} "
          f"bodies={tot_body} ops={tot_ops}  all-boundaries-clean={all_clean}")
