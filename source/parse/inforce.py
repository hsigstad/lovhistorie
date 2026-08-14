"""Resolve the TRUE entry-into-force date of an amending act (point-in-time deliverable).

INTENT: replace the act-DATE approximation used for `date_in_force_resolved` with the real
    ikrafttredelse date, so point-in-time reconstruction (`replay(as_of=t)`) applies each
    amendment only from the date it ACTUALLY took effect, not the date the act was passed.
    The act date is a lower bound; a deferred act can enter force months or years later, so
    scoring a past state against the act date shows amendments too early.
REASONING: LTI carries in-force info in two public-domain, offline places:
    (1) the amending act's own `<dd class="dateInForce">` — a concrete ISO date for the acts
        in force on a fixed day, OR "Kongen bestemmer/fastsetter" (deferred: the King sets
        the date later by resolution);
    (2) for deferred acts, the triggering ikrafttredelsesresolusjon — an `sf-` forskrift
        titled "(Delt) ikraftsetting av lov <cite> ..." whose own `<dd class="dateInForce">`
        is the concrete date and whose title cites the triggered act.
    Resolution: concrete act date if present; else the EARLIEST triggering resolution date
    (a "delt ikraftsetting" brings the first provisions into force — act-level grain for now);
    else None (deferred + no trigger found → flag-don't-fabricate; the caller keeps the
    act-date fallback so nothing regresses).
ASSUMES / SCOPE: modern LTI XML (2001+, `class="dateInForce"`). Act-level resolution only —
    per-provision partial scope ("§§ X trer i kraft straks, resten senere") is a documented
    follow-up (docs/todo.md). Pre-2001 gazette acts are out of scope (no LTI in-force field,
    no modern trigger resolutions) and keep their existing date.
ANTI-GAMING: reads ONLY `data/lti/` (public-domain enactment+amendment SOURCE), never the
    consolidated current text (`data/current/`) or the Lovdata-Pro oracle. This is an OFFLINE
    build input, exactly like build_enactment / lti_amendments — resolving a date sharpens
    WHEN an amendment applies, it does not import any answer key (lesson #7). The derived
    cache `data/inforce.jsonl.gz` is git-ignored and rebuildable.
"""
from __future__ import annotations

import glob
import gzip
import json
import re
import sys
from pathlib import Path

from source.parse import gazette

ROOT = Path(__file__).resolve().parents[2]
LTI = ROOT / "data" / "lti"
CACHE = ROOT / "data" / "inforce.jsonl.gz"

# a leading ISO date inside a <dd class="dateInForce"> value ("2021-02-01", "2008-05-09")
_ISO = re.compile(r"(\d{4}-\d{2}-\d{2})")
_DATE_IN_FORCE = re.compile(
    r'<dd class="dateInForce">\s*([^<]*?)\s*</dd>', re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
# an in-force resolution's title: "(Delt/Gradvis) Ikraftsetting/Ikraftsetjing/Iverksetting
# av lov[a] <cite> ...". The <cite> is left for gazette.datokode to parse off the tail.
_INFORCE_TITLE = re.compile(
    r"(?:delt|gradvis|endelig|endeleg)?\s*"
    r"(?:ikraftset\w+|iverkset\w+)\s+av\s+lova?\s+(.*)", re.I)


def _dd_in_force(raw: str) -> str | None:
    """Concrete ISO in-force date from an act/resolution XML, or None if deferred
    ('Kongen bestemmer/fastsetter') or absent."""
    m = _DATE_IN_FORCE.search(raw)
    if not m:
        return None
    iso = _ISO.match(m.group(1))
    return iso.group(1) if iso else None


def _act_datokode(path: Path) -> str:
    """'nl-20190315-006.xml' -> '2019-03-15-6'."""
    dk = path.stem.replace("nl-", "")
    return f"{dk[:4]}-{dk[4:6]}-{dk[6:8]}-{int(dk[8:].lstrip('-') or 0)}"


def build() -> dict:
    """Scan data/lti/ and write the in-force cache (one row per amending act). Returns the
    resolved-date map. Rebuild after a new LTI harvest."""
    # (2) trigger index: triggered-act datokode -> [concrete resolution dates]
    triggers: dict[str, list[str]] = {}
    for p in sorted(glob.glob(str(LTI / "*" / "sf-*.xml"))):
        raw = Path(p).read_text(encoding="utf-8", errors="ignore")
        tm = _TITLE.search(raw)
        if not tm:
            continue
        im = _INFORCE_TITLE.search(re.sub(r"<[^>]+>", " ", tm.group(1)))
        if not im:
            continue
        target = gazette.datokode("lov " + im.group(1))
        date = _dd_in_force(raw)
        if target and date:
            triggers.setdefault(target, []).append(date)

    # (1) each amending act's own in-force field, then resolve
    rows = []
    for p in sorted(glob.glob(str(LTI / "*" / "nl-*.xml"))):
        path = Path(p)
        dk = _act_datokode(path)
        own = _dd_in_force(path.read_text(encoding="utf-8", errors="ignore"))
        trig = sorted(triggers.get(dk, []))
        if own:
            resolved, status = own, "concrete"
        elif trig:
            resolved, status = trig[0], "triggered"
        else:
            resolved, status = None, "deferred_untriggered"
        rows.append({"datokode": dk, "own_date": own, "trigger_dates": trig,
                     "resolved": resolved, "status": status})

    with gzip.open(CACHE, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_res = sum(1 for r in rows if r["resolved"])
    n_trig = sum(1 for r in rows if r["status"] == "triggered")
    print(f"built {CACHE.relative_to(ROOT)}: {len(rows)} acts, {n_res} resolved "
          f"({n_trig} via trigger resolution), {len(triggers)} triggered-act keys")
    return {r["datokode"]: r["resolved"] for r in rows}


_MAP: dict[str, str | None] | None = None


def _load() -> dict[str, str | None]:
    """The resolved-date map, from the cache (built on first use if absent)."""
    global _MAP
    if _MAP is None:
        if not CACHE.exists():
            return build()
        _MAP = {}
        with gzip.open(CACHE, "rt", encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                _MAP[d["datokode"]] = d["resolved"]
    return _MAP


def resolved_date(datokode: str) -> str | None:
    """True in-force ISO date for an amending act, or None if unresolved (caller keeps its
    own act-date fallback — flag-don't-fabricate)."""
    return _load().get(datokode)


if __name__ == "__main__":
    m = build()
    if "--stats" in sys.argv:
        from collections import Counter
        with gzip.open(CACHE, "rt", encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh]
        c = Counter(r["status"] for r in rows)
        print("status:", dict(c))
        later = sum(1 for r in rows if r["resolved"] and r["own_date"] is None)
        moved = sum(1 for r in rows
                    if r["resolved"] and r["resolved"] != r["datokode"][:10]
                    and r["resolved"] > r["datokode"][:10])
        print(f"deferred acts resolved via trigger: {later}")
        print(f"acts whose in-force date is LATER than passage date: {moved}")
