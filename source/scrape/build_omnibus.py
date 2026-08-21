"""Recover omnibus secondary-target amendments the external/LTI streams dropped.

INTENT: the external `amendments.jsonl.gz` and the section-regex LTI re-parse both mono-collapse
    many omnibus acts onto their PRIMARY law, so laws that are only a SECONDARY target inside a
    "mv."/"m.m."/"retting av feil" act lose those amendments (register audit: 24% of all amendment
    edges are mis-targeted this way, worst for old small codes — avtaleloven 4/17). This offline
    build re-recovers them from the PUBLIC act text: source/llm/target_localize localizes every
    amended-law section (format-agnostic, verified), then source/llm/amend.extract_ops pulls the
    ops per section (verbatim-anchored payloads). Writes the sections MISSING for the requested
    target laws to data/omnibus_recovered.jsonl.gz (same schema as lti_amendments → pipeline
    load_ops merges + dedups) and every unresolvable mention to data/omnibus_unresolved.jsonl.gz
    (recall loss is MEASURED, never silent).
REASONING: candidate acts are discovered by PUBLIC signal only — an act's own text citing a target
    law's date+nr — never from the register (answer key). Resolution + op extraction are the
    localize-then-verify path (no format-specific parsing). This supersedes broadening the _SECTION
    regex: new layouts need no new code.
ASSUMES: OPENAI_API_KEY in env; data/lti/*/nl-*.xml is the public amending-act corpus. Targets
    default to the old/small codes the register flags as most under-captured; pass --targets for
    others, --limit-acts to bound a run (cached + resumable).
ANTI-GAMING: reads only public act text + the model's anchors (cached); no data/current / register
    read in the build path. G1-safe, like source/scrape/lti_amendments.py.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.llm import amend, target_localize
from source.parse import gazette

LTI_DIR = _REPO / "data" / "lti"
OUT = _REPO / "data" / "omnibus_recovered.jsonl.gz"
UNRESOLVED = _REPO / "data" / "omnibus_unresolved.jsonl.gz"

# old/small codes the register flags as most under-captured (mis-targeted-heavy)
SPOTLIGHT = [
    "1918-05-31-4", "1988-05-13-27", "1979-05-18-18", "1939-02-17-1",
    "1980-02-08-2", "1965-06-18-6", "1969-06-13-26",
]

_ENT = {"&#248;": "ø", "&#230;": "æ", "&#229;": "å", "&#216;": "Ø", "&#198;": "Æ", "&#197;": "Å"}
# month-number -> all spellings gazette accepts (full + abbrev), for the candidate cite regex
_NUM2MON: dict[int, list[str]] = {}
for _name, _n in gazette._MONTHS.items():
    _NUM2MON.setdefault(_n, []).append(re.escape(_name))


def plain_text(xml_path: str) -> str:
    t = re.sub(r"<[^>]+>", " ", Path(xml_path).read_text(encoding="utf-8"))
    for k, v in _ENT.items():
        t = t.replace(k, v)
    return t


def _cite_regex(dk: str) -> re.Pattern:
    """Tolerant matcher for a datokode's citation in act prose: '31. mai 1918 nr. 4'."""
    y, m, d, n = dk.split("-")
    mons = "|".join(_NUM2MON.get(int(m), []))
    return re.compile(rf"\b0?{int(d)}\.?\s*(?:{mons})[a-zæøå]*\.?\s*{y}\s*nr\.?\s*{int(n)}\b", re.I)


def candidate_acts(targets: list[str]) -> dict[str, list[str]]:
    """{act_path: [target dks it cites]} — PUBLIC-signal discovery: the act's own text names the
    target law's date+nr. No register / answer-key consulted."""
    regexes = {dk: _cite_regex(dk) for dk in targets}
    hits: dict[str, list[str]] = {}
    for p in sorted(glob.glob(str(LTI_DIR / "*" / "nl-*.xml"))):
        txt = None
        for dk, rx in regexes.items():
            # cheap substring pre-gate on year+nr before the full regex
            if txt is None:
                txt = plain_text(p)
            if rx.search(txt):
                hits.setdefault(p, []).append(dk)
    return hits


# A section only counts as an AMENDMENT if it carries an amendatory verb — this drops
# applicative cross-references ("Lov av … § 2-1 GJELDER FOR …" makes another law apply; it is
# not a change to it) that the localizer otherwise picks up as a target mention. Public-source
# guard (no register/answer-key). Recall-safe: real amendment sections state the operation.
# Key on `\blyde\b` (not "skal lyde" adjacent — the provision sits BETWEEN, e.g. "skal § 21 nr. 3
# tredje punktum lyde:") plus the other amendatory verbs. "lyde" is amendment-specific, so this is
# recall-safe; applicative cross-refs ("… § 2-1 gjelder for …") carry none of these cues.
_AMENDATORY = re.compile(
    r"\blyde\b|opphev|oppheva|tilføy|tilf&#248;y|gj[øo]res\s+følgende|skal\s+det\s+hete|"
    r"\bendr(?:es|et|a|ing)|ny(?:tt|e)?\s+(?:§|ledd|kapittel|paragraf|punktum)|skal\s+betegnes|"
    r"ny\s+§|skal\s+utgå|tilføyes|oppheves", re.I)


def _is_amendatory(section_text: str) -> bool:
    return bool(_AMENDATORY.search(section_text))


def public_universe() -> set[str]:
    """The laws we already track, as datokodes — the union of target_law across the existing
    PUBLIC-derived amendment streams + enactment bases. G1-safe: never reads data/current. Used as
    the full-sweep target set so recovered ops are scoped to laws the pipeline reconstructs."""
    import glob
    uni = set()
    for s in ("amendments.jsonl.gz", "lti_amendments.jsonl.gz", "llm_amendments.jsonl.gz"):
        p = _REPO / "data" / s
        if not p.exists():
            continue
        for line in gzip.open(p, "rt", encoding="utf-8"):
            tl = json.loads(line).get("target_law") or ""
            if tl.startswith("lov/"):
                uni.add(tl.split("/", 1)[1])
    for f in glob.glob(str(_REPO / "data" / "enactment" / "*.json")):
        uni.add(Path(f).stem)
    return uni


def _norm_head(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()[:80]


def _act_dk(path: str) -> str | None:
    m = re.search(r"nl-(\d{4})(\d{2})(\d{2})-0*(\d+)", Path(path).name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}" if m else None


def _flush(recovered, unresolved):
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for o in recovered:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    with gzip.open(UNRESOLVED, "wt", encoding="utf-8") as fh:
        for u in unresolved:
            fh.write(json.dumps(u, ensure_ascii=False) + "\n")


def run(targets: list[str], limit_acts: int | None = None, reextract: bool = False,
        all_acts: bool = False):
    tset = set(targets)
    if all_acts:                       # full sweep: every act; candidate discovery is moot
        paths = sorted(glob.glob(str(LTI_DIR / "*" / "nl-*.xml")))
        print(f"FULL SWEEP: targets={len(tset)}  acts={len(paths)}", flush=True)
    else:
        cands = candidate_acts(targets)
        paths = sorted(cands)
        print(f"targets={len(tset)}  candidate acts (public-signal)={len(cands)}", flush=True)
    if limit_acts:
        paths = paths[:limit_acts]
    from openai import OpenAI
    client = OpenAI()
    recovered, unresolved = [], []
    for i, p in enumerate(paths, 1):
        act_dk = _act_dk(p)
        txt = plain_text(p)
        secs, lrep = target_localize.localize(txt, client=client, reextract=reextract)
        for reason, anchor, cite in lrep.unresolved:
            unresolved.append({"act": f"lov/{act_dk}", "reason": reason, "cite": cite,
                               "anchor": anchor[:80]})
        wanted = []
        for dk, s in secs:
            if dk not in tset:
                continue
            if not _is_amendatory(s):        # applicative cross-ref, not a change — log + skip
                unresolved.append({"act": f"lov/{act_dk}", "reason": "no-amendatory-cue",
                                   "cite": f"lov/{dk}", "anchor": _norm_head(s)})
                continue
            wanted.append((dk, s))
        if not wanted:
            continue
        ops, arep = amend.extract_ops(act_dk, txt, client=client, sections=wanted,
                                      reextract=reextract)
        for o in ops:
            o["source"] = "omnibus_recovered"
        recovered.extend(ops)
        print(f"  [{i}/{len(paths)}] {act_dk}: {len(wanted)} wanted sections -> {len(ops)} ops "
              f"(mentions {lrep.n_mentions}, unresolved {len(lrep.unresolved)}, cached={lrep.cached})",
              flush=True)
        if all_acts and i % 200 == 0:            # checkpoint so a long sweep survives a crash
            _flush(recovered, unresolved)
            print(f"  ... checkpoint at act {i}: {len(recovered)} ops so far", flush=True)

    _flush(recovered, unresolved)
    laws = {o["target_law"] for o in recovered}
    acts = {o["act_refid"] for o in recovered}
    print(f"\nrecovered {len(recovered)} ops | {len(acts)} acts x {len(laws)} target laws")
    print(f"unresolved mentions logged: {len(unresolved)}")
    print(f"  -> {OUT.relative_to(_REPO)}\n  -> {UNRESOLVED.relative_to(_REPO)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="*", default=SPOTLIGHT,
                    help="target law datokodes (default: register-flagged old codes)")
    ap.add_argument("--all", action="store_true",
                    help="full sweep: every act, targets = public recon universe (744 laws)")
    ap.add_argument("--limit-acts", type=int, default=None)
    ap.add_argument("--reextract", action="store_true")
    a = ap.parse_args()
    targets = sorted(public_universe()) if a.all else a.targets
    run(targets, a.limit_acts, a.reextract, all_acts=a.all)
