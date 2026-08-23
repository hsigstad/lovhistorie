"""Offline pre-apply pass: bake sub-provision amendments the ledd engine drops, via the LLM applicator.

INTENT: the deterministic ledd engine can't apply sub-provision ops to OCR bases lacking (N) ledd
    markers, so those amendments are dropped (avtaleloven applies 0/6 sub-ops; §17's punktum op is
    dropped though its provision is one edit from converging). This pass replays each law with
    source.llm.apply_op as the ledd fallback (localize the op's span with the LLM, splice the op's
    verbatim new_text, span-guarded), and writes the provisions that CHANGED as whole-provision ops to
    data/applied_ops.jsonl.gz — which pipeline.load_ops reads so runtime replay applies them
    DETERMINISTICALLY (via the '§ N.' heading path). Runtime uses no LLM (rule 3); this is base-prep.
REASONING: only emit provisions where the LLM applicator changed the deterministic result — so it is
    strictly additive over the current reconstruction, and each emitted op is a verified splice (no
    fabrication). Dated at the provision's last op so it applies last (final state).
ASSUMES: OPENAI_API_KEY; reads only public streams + enactment bases (never the current/answer text).
ANTI-GAMING: G1-safe — apply_op reads the public provision + op + its own span anchors (cached).
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.llm import apply_op
from source.parse import pipeline, replay

OUT = _REPO / "data" / "applied_ops.jsonl.gz"
DEV = ["lov/1918-05-31-4", "lov/1959-10-23-3", "lov/1979-05-18-18", "lov/1982-12-17-86",
       "lov/1986-06-20-35", "lov/1988-05-13-27", "lov/1997-06-13-44", "lov/2007-06-29-75",
       "lov/2009-06-19-103"]


def _corroboration_filter(law: str, ops: list) -> tuple[list, int]:
    """Drop ops the applicator must NOT force-apply because our own localize-then-verify pipeline
    CONTRADICTS their attribution. For any amending act our omnibus/gazette localizer processed for
    this law (found >=1 provision), we trust OUR verified provision-list for that act: an op naming a
    provision our localization of the SAME act did not find is a mis-attribution the external stream
    made (rettsgebyrloven §11 was mis-filed onto oreign §11 — skjønnsloven/rettsgebyr content; the
    ledd engine harmlessly dropped it, but the applicator would force it onto oreign §11 and corrupt a
    converging provision). This is source-only (our localizer vs the external stream, never the answer
    key) and scoped to the APPLICATOR: the deterministic runtime path is untouched, so no recall risk.
    """
    import gzip as _gz
    import json as _json
    our_acts, our_pairs = set(), set()          # acts we localized; (act, para) we verified
    for fn in ("omnibus_recovered.jsonl.gz", "gazette_recovered.jsonl.gz"):
        p = _REPO / "data" / fn
        if not p.exists():
            continue
        with _gz.open(p, "rt", encoding="utf-8") as fh:
            for line in fh:
                d = _json.loads(line)
                if d.get("target_law") != law:
                    continue
                act = d.get("act_refid")
                para = (d.get("paragraph") or "").replace(" ", "")
                if act:
                    our_acts.add(act)
                    if para:
                        our_pairs.add((act, para))
    kept, dropped = [], 0
    for o in ops:
        act, para = o.get("act"), o.get("para")
        if act in our_acts and para and (act, para) not in our_pairs:
            dropped += 1                          # our verified localization of this act omits `para`
            continue
        kept.append(o)
    return kept, dropped


def run(laws, model=apply_op.MODEL, reextract=False):
    from openai import OpenAI
    client = OpenAI()
    rows = []
    for law in laws:
        base = pipeline.enactment_base(law)
        ops = pipeline.load_ops(law, include_applied=False)
        if not base or not ops:
            print(f"{law}: no base/ops, skip", flush=True)
            continue
        ops, n_dropped = _corroboration_filter(law, ops)
        if n_dropped:
            print(f"{law}: corroboration-filter dropped {n_dropped} localizer-contradicted ops",
                  flush=True)

        def fb(prov, instr, new, ct, _law=law):
            return apply_op.apply_op(prov, instr, new, ct, client=client, model=model,
                                     reextract=reextract, doc_id=f"{_law}:{instr[:24]}")

        # Per-provision gate: only KEEP an LLM-applied result for a provision whose base has NO (N)
        # ledd markers — there the deterministic ledd engine structurally cannot work, so the LLM is
        # the only option and is strictly additive. Where the base HAS markers, trust the deterministic
        # engine (the LLM's errors on those regressed aksje/vphl). General, no per-law cherry-picking.
        import re as _re
        unmarked = {p for p, t in base.items() if not _re.search(r"\(\s*[12]\s*\)", t)}
        det, _ = replay.replay(dict(base), ops)
        llm, _ = replay.replay(dict(base), ops, ledd_fallback=fb)
        # last op date per provision (for ordering the applied whole-provision op last)
        lastdate = {}
        for o in ops:
            p, dt = o.get("para"), o.get("date")
            if p and dt and dt > lastdate.get(p, ""):
                lastdate[p] = dt
        n = 0
        for p, txt in llm.items():
            if txt and txt != det.get(p, "") and p in lastdate and p in unmarked:
                rows.append({
                    "act_refid": "applied", "target_law": law, "paragraph": p,
                    "change_type": "change", "instruction": f"§ {p.lstrip('§')} skal lyde:",
                    "new_text": f"§ {p.lstrip('§')}. {txt}", "date_in_force": lastdate[p],
                    "source": "applied",
                })
                n += 1
        print(f"{law}: {n} provisions pre-applied", flush=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(rows)} pre-applied ops -> {OUT.relative_to(_REPO)}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--laws", nargs="*", default=DEV)
    ap.add_argument("--model", default=apply_op.MODEL)
    ap.add_argument("--reextract", action="store_true")
    a = ap.parse_args()
    run(a.laws, model=a.model, reextract=a.reextract)
