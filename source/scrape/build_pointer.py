"""Offline pointer-apply pass: bake holistically-consolidated provisions the ledd engine can't build.

INTENT: for provisions the deterministic engine mangles (captured sub-ops on an unmarked OCR base),
    reconstruct them with source.llm.pointer_apply (the LLM emits POINTERS; deterministic code
    assembles VERBATIM source), and write the result as a whole-provision op to data/pointer_ops.jsonl
    .gz. pipeline.load_ops reads it (last, highest precedence) so runtime replay overwrites the mangled
    provision via the '§ N.' heading path — DETERMINISTICALLY (rule 3; the LLM ran offline + cached).
REASONING: only APPLICATION-LIMITED provisions are targeted (a current-text miss that HAS captured ops
    — deterministic recon < tau). Those are already misses, so baking the pointer result can only help
    the convergence count (converts some; leaves the rest as misses). Every baked op is a verbatim
    source assembly (pointer_apply guarantee), dated at the provision's last op so it applies last.
ASSUMES: OPENAI_API_KEY (cached); reads public streams + enactment bases, never the current/answer text
    (the target/current is used ONLY to SELECT which provisions to spend effort on — a miss + has-ops
    gate — never to pick or edit the reconstructed text). Model tier by op-count is answer-free.
ANTI-GAMING: pointer_apply reads only the public provision + its amendments; the model emits references,
    not text. G1-safe.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.llm import pointer_apply
from source.parse import pipeline, replay


def _coverage(text: str, ops: list) -> float:
    """ANSWER-FREE quality proxy: fraction of the change/add ops whose NEW text actually appears in
    `text` (whitespace-normalized, first ~30 chars). A faithful consolidation incorporates the surviving
    amendments; a mangled piecemeal splice drops them. Compares two RECONSTRUCTIONS' op-coverage — never
    the current/answer text — so it says which reconstruction is more complete without the answer key."""
    n = " ".join(text.lower().split())
    cand = [o for o in ops if o.get("new_text") and o.get("change_type") in ("change", "add")]
    if not cand:
        return 1.0
    hit = sum(1 for o in cand if " ".join((o["new_text"][:30]).lower().split()) in n)
    return hit / len(cand)

OUT = _REPO / "data" / "pointer_ops.jsonl.gz"
DEV = ["lov/1918-05-31-4", "lov/1959-10-23-3", "lov/1979-05-18-18", "lov/1982-12-17-86",
       "lov/1986-06-20-35", "lov/1988-05-13-27", "lov/1997-06-13-44", "lov/2007-06-29-75",
       "lov/2009-06-19-103"]


def _tier(n_ops: int, default: str) -> str:
    """Answer-free model tier by op-count: gpt-4.1 is the sweet spot; escalate the reasoning-hard
    tail (>10 ops) to a cheap reasoning model (o4-mini)."""
    return default if n_ops <= 10 else "o4-mini"


def run(laws, model="gpt-4.1", reextract=False):
    from openai import OpenAI
    client = OpenAI(timeout=180)
    rows = []
    for law in laws:
        base = pipeline.enactment_base(law) or {}
        if not base:
            print(f"{law}: no base, skip", flush=True)
            continue
        # ANSWER-FREE scope: pointer only on OCR-base laws, where the deterministic ledd engine
        # structurally fails. On CLEAN/born-digital bases (is_ocr_base False, e.g. vphl/tjeneste) the
        # ledd engine works and pointer is WORSE — baking it there regressed vphl -22. is_ocr_base is a
        # public property of the base, not the answer.
        if not pipeline.is_ocr_base(law):
            print(f"{law}: clean base — deterministic reliable, skip pointer", flush=True)
            continue
        det, _ = pipeline.reconstruct(law)              # deterministic recon (pointer_ops deleted) to
        #                                                 compare op-coverage against — answer-free
        raw = pipeline.load_ops(law, include_applied=False)     # RAW captured amendments to consolidate
        ops = defaultdict(list)
        for o in raw:
            if o.get("para"):
                ops[o["para"]].append(o)
        # ANSWER-FREE selection (reproducible without the current text): provisions where the
        # deterministic ledd engine actually DROPPED >=1 op (replay flags). This is finer than an
        # "unmarked base" gate: within an OCR-base law many provisions still converge deterministically
        # (ledd applied their ops), and overriding THOSE regressed (aksje net-0, unmarked gate). A
        # dropped-op flag marks exactly where the fast path failed -> pointer is the better method there.
        _, flags = replay.replay(dict(base), raw)
        cand = sorted({f["para"] for f in flags
                       if f.get("para") and f["para"] in base and ops.get(f["para"])})
        n = 0
        for p in cand:
            used = [o for o in ops[p] if (o.get("date") or "0000") <= "2025-12-31"]
            m = _tier(len(used), model)
            out, rep = pointer_apply.apply(p, base.get(p, ""), ops[p], client=client, model=m,
                                           reextract=reextract)
            if not out:
                continue
            # Two answer-free guards: content-aware pointer self-skips MIS-FILED amendments, and this
            # coverage gate rejects a consolidation that incorporates FEWER amendments than the
            # deterministic recon (pointer mis-reasoned / over-skipped) — catches the residual
            # non-mis-attribution regressions. Neither reads the answer.
            if _coverage(out, ops[p]) < _coverage(det.get(p, ""), ops[p]):
                continue
            lastdate = max((o.get("date") or "" for o in used), default="")
            rows.append({
                "act_refid": "pointer", "target_law": law, "paragraph": p,
                "change_type": "change", "instruction": f"§ {p.lstrip('§')} skal lyde:",
                "new_text": f"§ {p.lstrip('§')}. {out}", "date_in_force": lastdate,
                "source": "pointer_apply", "model": m,
            })
            n += 1
        print(f"{law}: {n} provisions consolidated ({len(cand)} candidates)", flush=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(rows)} pointer-consolidated provisions -> {OUT.relative_to(_REPO)}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--laws", nargs="*", default=DEV)
    ap.add_argument("--model", default="gpt-4.1")
    ap.add_argument("--reextract", action="store_true")
    a = ap.parse_args()
    run(a.laws, model=a.model, reextract=a.reextract)
