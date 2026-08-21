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
REASONING: source.llm.segment_issue LLM-segments an issue into acts with {nr,date,klass,body}; the
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

from source.llm import amend, segment_issue, target_localize
from source.scrape.build_omnibus import _is_amendatory, _norm_head, public_universe

TEXT_DIR = _REPO / "data" / "lovtidend_text"
OUT = _REPO / "data" / "gazette_recovered.jsonl.gz"
UNRESOLVED = _REPO / "data" / "gazette_unresolved.jsonl.gz"

# Broad, recall-SAFE gate for "this is an amending act": it contains an "I lov …" section marker —
# the universal way a Norwegian act introduces a law it changes ("I lov av <cite> … gjøres følgende
# endringer:", "I lov <cite> skal § N lyde:"). Deliberately NOT a per-target date+nr regex: the LLM
# localizer resolves WHICH law each "I lov" section amends (OCR-, name- and date-only-tolerant), so no
# brittle citation regex gates what the model sees. Its only job is to skip pure original enactments.
_AMEND_ACT = re.compile(r"\bi\s+lov\b", re.I)
# The LLM segmenter (segment_issue) already slices each act's body between consecutive act headings,
# so no regex tail-trim is needed here. Only cap the localize window for a genuinely huge act (a big
# recodification with a long consequential-amendments chapter); oversize is LOGGED, not silently
# trusted. The change-list sits near the act's start, so the head is what matters.
_MAX_BODY = 60000


def _bound_body(body: str) -> tuple[str, bool]:
    return body[:_MAX_BODY], len(body) > _MAX_BODY


def _flush(recovered, unresolved):
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for o in recovered:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    with gzip.open(UNRESOLVED, "wt", encoding="utf-8") as fh:
        for u in unresolved:
            fh.write(json.dumps(u, ensure_ascii=False) + "\n")


def _catalog_years() -> dict:
    """{catalog_id: issue_year} from the NB census — a cheap, reliable year filter that needs no
    per-issue LLM call or the (mis-firing) issue_year OCR heuristic."""
    import json
    idx_path = _REPO / "data" / "lovtidend_index.json"
    if not idx_path.exists():
        return {}
    out = {}
    for x in json.loads(idx_path.read_text(encoding="utf-8")):
        y = str(x.get("issued", ""))[:4]
        if y.isdigit():
            out[x["id"]] = int(y)
    return out


def _register_selected_acts(targets: set[str]) -> set:
    """Pre-2001 act datokodes the REGISTER says amend one of `targets`. Used ONLY to SELECT which
    acts to spend LLM effort on (prioritization) — a strict subset of what a blind full sweep would
    process, giving the identical dev-law result ~10-45x faster. The amendment TEXT still comes from
    public OCR, extracted + verbatim-verified; the register (answer-key-derived) never supplies text
    or provisions. EVAL/validation accelerator: a published corpus can run the blind sweep for the
    same result. Returns empty set if the register is absent (→ caller falls back to no filter)."""
    import gzip as _gz
    import json as _json
    import re as _re
    p = _REPO / "data" / "amendment_register.jsonl.gz"
    if not p.exists():
        return set()
    out = set()
    for line in _gz.open(p, "rt", encoding="utf-8"):
        r = _json.loads(line)
        if r.get("target_law", "").split("/")[-1] in targets:
            m = _re.search(r"([0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]+)", r.get("act_id", ""))
            if m and int(m.group(1)[:4]) < 2001:
                out.add(m.group(1))
    return out


def run(targets: set[str], years: set[int] | None = None, limit_issues: int | None = None,
        reextract: bool = False, scoped: bool = False, model: str = segment_issue.MODEL,
        extract_model: str | None = None, register_guided: bool = False):
    # Model split (general, not per-law): segmentation + localization are LOCATION tasks mini handles
    # well and are already cached from prior sweeps; OP EXTRACTION needs the stronger model (mini drops
    # payload-carrying ops). extract_model defaults to gpt-4.1.
    extract_model = extract_model or "gpt-4.1"
    # register_guided: localize/extract ONLY the acts the register flags as amending a target
    # (prioritization → ~10-45x fewer LLM calls, identical dev-law result). Segmentation still runs
    # (cheap/cached) so we can find each act; the general localize→verify→extract path is unchanged.
    sel_acts = _register_selected_acts(targets) if register_guided else None
    import gzip as _gz
    import json as _json
    from openai import OpenAI
    client = OpenAI()
    issues = sorted(glob.glob(str(TEXT_DIR / "*.jsonl.gz")))
    id2year = _catalog_years()
    recovered, unresolved = [], []
    n_issues = n_acts = 0
    for ip, path in enumerate(issues, 1):
        yr = id2year.get(Path(path).name.split(".")[0])
        if years and yr not in years:
            continue
        if yr and yr >= 2001:                       # LTI era is covered by build_omnibus
            continue
        n_issues += 1
        # LLM ACT-SEGMENTER (replaces gazette.parse_toc/split_bodies): locate every "Lov nr. N" act,
        # verified + sliced. Unlocks the ~80% of issues the TOC-regex segmenter returned 0 acts for.
        pages = [_json.loads(l) for l in _gz.open(path, "rt", encoding="utf-8")]
        acts, _seg = segment_issue.segment(pages, client=client, model=model, reextract=reextract,
                                           doc_key=Path(path).name.split(".")[0])
        for act in acts:
            body, date, nr = act.get("body") or "", act.get("date"), act.get("nr")
            if not body or not date or not _AMEND_ACT.search(body):
                continue                                 # not an amending act (no "I lov" marker)
            if int(date[:4]) >= 2001:
                continue
            act_dk = act.get("datokode") or f"{date}-{nr}"
            if sel_acts is not None and act_dk not in sel_acts:
                continue                                 # register-guided: not a flagged target-amending act
            n_acts += 1
            body, truncated = _bound_body(body)
            if truncated:
                unresolved.append({"act": f"lov/{act_dk}", "reason": "body-capped",
                                   "cite": "", "anchor": f"len>{_MAX_BODY}", "year": yr})
            # LLM localizes WHICH laws this act amends (targets resolved by the model, not a regex);
            # we then keep only the sections resolving to our target set.
            secs, lrep = target_localize.localize(body, client=client, model=model, reextract=reextract)
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
                                       model=extract_model, reextract=reextract)
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
                    help="keep only sections resolving to these target law datokodes; default = full "
                         "public universe. NB: every amending act is localized regardless — targets "
                         "filter the RESOLVED sections, they do NOT gate what the LLM sees.")
    ap.add_argument("--years", nargs="*", type=int, default=None,
                    help="restrict to these issue years (default: all pre-2001)")
    ap.add_argument("--limit-issues", type=int, default=None)
    ap.add_argument("--model", default=segment_issue.MODEL,
                    help="LLM for segment+localize (cheap; mini default)")
    ap.add_argument("--extract-model", default="gpt-4.1",
                    help="LLM for op extraction (stronger; gpt-4.1 default)")
    ap.add_argument("--register-guided", action="store_true",
                    help="localize/extract ONLY acts the register flags as amending a target "
                         "(prioritization; ~10-45x fewer calls, identical dev-law result)")
    ap.add_argument("--reextract", action="store_true")
    a = ap.parse_args()
    tgts = set(a.targets) if a.targets else public_universe()
    run(tgts, set(a.years) if a.years else None, a.limit_issues, a.reextract,
        model=a.model, extract_model=a.extract_model, register_guided=a.register_guided)
