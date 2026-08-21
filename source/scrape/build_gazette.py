"""Tier-1 pre-2001 recovery: localize-then-verify on the OCR gazette we ALREADY hold.

INTENT: the pre-2001 amendment tail is mostly a HARVEST gap, BUT the 1990s (and harvested 1980s)
    Lovtidend issues are on disk in data/lovtidend_text — and their secondary-target / flat-omnibus
    amendments are simply UNPARSED (register audit: 1990s only 45% captured though well-harvested;
    proof: the 1994 "retting"-style act naming "Lov 31. mai 1918 nr. 4 om avslutning av avtaler" in
    a flat numbered list sits in our OCR, uncaptured). This build runs the SAME localizer +
    verbatim-anchored op extractor as source/scrape/build_omnibus, but fed each amending act's OCR
    BODY (segmented by source/parse/gazette) instead of LTI XML — recovering those ops with NO new
    harvest. Writes to data/gazette_recovered.jsonl.gz (a SEPARATE stream, so it never collides with
    a concurrently-running LTI omnibus sweep).
REASONING: gazette.parse_issue already segments an issue into acts with {nr,date,klass,body}; the
    act datokode is f"{date}-{nr}". Feeding body → target_localize.localize is source-agnostic (it
    reads text), so the pre-2001 adapter is plumbing, not new logic. OCR noise is handled the same
    way as everywhere: unverifiable mentions/ops drop to a measured stream, never fabricate.
ASSUMES: OPENAI_API_KEY; data/lovtidend_text/*.jsonl.gz is the public-domain NB OCR. Targets default
    to the public recon universe (build_omnibus.public_universe) so recovered ops are scoped to laws
    we reconstruct; --years bounds a run to well-harvested slices.
ANTI-GAMING: reads only public OCR + cached model anchors; no data/current / register in the build
    path. G1-safe, like the LTI omnibus build and the existing gazette parser.
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
from source.scrape.build_omnibus import _cite_regex, _is_amendatory, _norm_head, public_universe

TEXT_DIR = _REPO / "data" / "lovtidend_text"
OUT = _REPO / "data" / "gazette_recovered.jsonl.gz"
UNRESOLVED = _REPO / "data" / "gazette_unresolved.jsonl.gz"

# an amending act's body cites at least one OTHER law by date+nr; original enactments rarely do.
_CITES_LAW = re.compile(r"\blov\b[^.\n]{0,40}\b\d{1,2}\.?\s*[a-zæøå]+\.?\s*\d{4}\s*nr\.?\s*\d+", re.I)
# OCR body segmentation is imperfect: ~10% of amending-act bodies are oversized because the
# split absorbed the issue tail (a following act's body bled in). Cap the localize window — an
# amending act's own change-list sits near its start, and the bled tail is where mis-attributed
# ops would come from. Oversize is LOGGED (measured), not silently trusted. A later refinement
# is boundary-aware chunking; for now the cap bounds both cost and cross-act bleed.
_MAX_BODY = 60000
_ANY_ACT_HEAD = re.compile(r"Lov\s+nr\.?\s*(\d+)\s*\n")


def _bound_body(body: str, nr: int) -> tuple[str, bool]:
    """Trim a body to THIS act only: cut at the next act heading 'Lov nr. <m>\\n' with m != nr
    (this act's own heading repeats as a running page header, so we must skip same-nr matches),
    else cap at _MAX_BODY. Returns (text, truncated)."""
    end = len(body)
    for m in _ANY_ACT_HEAD.finditer(body, 200):
        if int(m.group(1)) != nr:
            end = m.start()
            break
    truncated = end > _MAX_BODY
    return body[: min(end, _MAX_BODY)], truncated


def _flush(recovered, unresolved):
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for o in recovered:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    with gzip.open(UNRESOLVED, "wt", encoding="utf-8") as fh:
        for u in unresolved:
            fh.write(json.dumps(u, ensure_ascii=False) + "\n")


def run(targets: set[str], years: set[int] | None = None, limit_issues: int | None = None,
        reextract: bool = False, scoped: bool = False):
    from openai import OpenAI
    client = OpenAI()
    issues = sorted(glob.glob(str(TEXT_DIR / "*.jsonl.gz")))
    # scoped run: only localize act bodies that CITE a target law (public-signal prefilter) — bounds
    # a dev-law pre-2001 pass to a few dozen acts instead of every amending act in the OCR corpus.
    tcites = {dk: _cite_regex(dk) for dk in targets} if scoped else None
    recovered, unresolved = [], []
    n_issues = n_acts = 0
    for ip, path in enumerate(issues, 1):
        try:
            parsed = gazette.parse_issue(path)
        except Exception:
            continue
        yr = parsed.get("year")
        if years and yr not in years:
            continue
        if yr and yr >= 2001:                       # LTI era is covered by build_omnibus
            continue
        n_issues += 1
        for act in parsed["acts"]:
            body, date, nr = act.get("body") or "", act.get("date"), act.get("nr")
            if not body or not date or not _CITES_LAW.search(body):
                continue
            if tcites is not None and not any(rx.search(body) for rx in tcites.values()):
                continue                                 # scoped: body cites no target law
            act_dk = f"{date}-{nr}"
            n_acts += 1
            body, truncated = _bound_body(body, nr)
            if truncated:
                unresolved.append({"act": f"lov/{act_dk}", "reason": "body-capped",
                                   "cite": "", "anchor": f"len>{_MAX_BODY}", "year": yr})
            secs, lrep = target_localize.localize(body, client=client, reextract=reextract)
            for reason, anchor, cite in lrep.unresolved:
                unresolved.append({"act": f"lov/{act_dk}", "reason": reason, "cite": cite,
                                   "anchor": anchor[:80], "year": yr})
            wanted = []
            for dk, s in secs:
                if dk not in targets or dk == act_dk:
                    continue
                if not _is_amendatory(s):
                    unresolved.append({"act": f"lov/{act_dk}", "reason": "no-amendatory-cue",
                                       "cite": f"lov/{dk}", "anchor": _norm_head(s), "year": yr})
                    continue
                wanted.append((dk, s))
            if not wanted:
                continue
            ops, _ = amend.extract_ops(act_dk, body, client=client, sections=wanted,
                                       reextract=reextract)
            for o in ops:
                o["source"] = "gazette_recovered"
            recovered.extend(ops)
        if limit_issues and n_issues >= limit_issues:
            break
        if n_issues % 50 == 0:
            _flush(recovered, unresolved)
            print(f"  ... {n_issues} issues, {n_acts} amending acts, {len(recovered)} ops", flush=True)

    _flush(recovered, unresolved)
    laws = {o["target_law"] for o in recovered}
    acts = {o["act_refid"] for o in recovered}
    print(f"\ngazette Tier-1: {n_issues} issues / {n_acts} amending acts scanned")
    print(f"recovered {len(recovered)} ops | {len(acts)} acts x {len(laws)} target laws | "
          f"unresolved {len(unresolved)}")
    print(f"  -> {OUT.relative_to(_REPO)}\n  -> {UNRESOLVED.relative_to(_REPO)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="*", default=None,
                    help="restrict to these target law datokodes + prefilter act bodies to those "
                         "citing one (cheap dev-law pass); default = full public universe")
    ap.add_argument("--years", nargs="*", type=int, default=None,
                    help="restrict to these issue years (default: all pre-2001)")
    ap.add_argument("--limit-issues", type=int, default=None)
    ap.add_argument("--reextract", action="store_true")
    a = ap.parse_args()
    scoped = bool(a.targets)
    tgts = set(a.targets) if scoped else public_universe()
    run(tgts, set(a.years) if a.years else None, a.limit_issues, a.reextract, scoped=scoped)
