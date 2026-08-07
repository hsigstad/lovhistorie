"""Run the convergence proxy on a few laws — the no-ground-truth dev signal.

INTENT: measure the engine's honest reach today — of the provisions whose last
    amendment is a whole-provision op, how many does replay reconstruct to match
    the current text? — and count what the ledd engine still owes.
REASONING: convergence needs no Lovdata Pro; the pipeline (replay) uses ONLY the
    ops, the current text is loaded here in the harness role as the answer key
    (input-restriction rule). This is a proxy, not the success bar (see goal.md).
ASSUMES: current consolidated XML available as <CURRENT_DIR>/nl-<datokode>.xml
    (from the gjeldende-lover NLOD dump). Set CURRENT_DIR below.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from source.parse import amendments, replay
from source.eval import metrics

# gjeldende-lover extraction (NLOD current dump). Overridable via env for the harness.
CURRENT_DIR = Path(os.environ.get(
    "LOVHISTORIE_CURRENT_DIR",
    "/tmp/claude-1000/-workspace/abf882c9-8e7b-487d-ac08-83e1bb6afe47/scratchpad/nl"))


def _fname(datokode: str) -> str:
    """'1986-06-20-35' -> 'nl-19860620-035.xml' (gjeldende-lover naming)."""
    y, m, d, nr = datokode.split("-")
    return f"nl-{y}{m}{d}-{int(nr):03d}.xml"


def current_provisions(datokode: str):
    """{para: text} of the current text — ANSWER KEY, harness-only."""
    f = CURRENT_DIR / _fname(datokode)
    if not f.exists():
        return None
    t = re.sub(r"<[^>]+>", " ", f.read_text(encoding="utf-8", errors="ignore"))
    t = re.sub(r"\s+", " ", t)
    # body after the last title occurrence (skip the table of contents)
    titles = list(re.finditer(r"\[\w+loven\]|Lov om ", t))
    body = t[titles[-1].start():] if titles else t
    order = []
    seen = set()
    for m in re.finditer(r"§\s*(\d+(?:-\d+)?[a-z]?)", body):
        p = "§" + m.group(1)
        if p not in seen:
            seen.add(p)
            order.append(p)
    return metrics.provisions_ordered(body, order)


def run(target_law: str, datokode: str):
    ops = amendments.load_for(target_law)
    cur = current_provisions(datokode)
    if cur is None:
        return f"{datokode}: current text not found (set LOVHISTORIE_CURRENT_DIR)"
    recon, flags = replay.replay({}, ops)               # pipeline: ops only
    reach = replay.reconstructable(ops)                 # provisions engine handles today
    scored = [(p, metrics.similarity(recon.get(p, ""), cur.get(p, "")))
              for p in reach if p in cur]
    ok = sum(1 for _, s in scored if s >= 0.98)
    kinds = {}
    for o in ops:
        kinds[o["kind"]] = kinds.get(o["kind"], 0) + 1
    return (f"{datokode}: {len(ops)} ops {kinds} | engine reaches {len(reach)} provisions "
            f"(whole-provision ops) -> {ok}/{len(scored)} match current @0.98 | "
            f"flagged for ledd engine: {len(flags)}")


if __name__ == "__main__":
    for tl, dk in [("lov/1986-06-20-35", "1986-06-20-35"),   # mesterbrevloven
                   ("lov/1997-06-13-44", "1997-06-13-44")]:  # aksjeloven
        print(run(tl, dk))
