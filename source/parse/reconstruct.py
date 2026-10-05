"""CLI: reconstruct a Norwegian statute as it read at a past date, from the corpus.

INTENT: a thin, answer-key-free command wrapper over `pipeline.reconstruct` so a
    collaborator can get the point-in-time text of a law without writing Python. Prints the
    §§ in order (optionally one § or JSON) and a summary of any FLAGGED ops (amendments the
    deterministic engine could not apply — left at last-known text, never fabricated).
REASONING: the handoff needs a runnable entrypoint; `reconstruct()` is otherwise a library
    call. This module only imports the runtime (`source.parse.pipeline`) — no eval / no
    answer key (G1-safe).
ASSUMES: `data/segments.jsonl` (the corpus, in git) + `data/lovtidend_text/` (the frozen NB
    OCR the segments point into — gitignored; restore `lovtidend_text.tar.gz` from Dropbox).

Examples:
    python -m source.parse.reconstruct 2007-06-29-75                 # latest text
    python -m source.parse.reconstruct lov/2007-06-29-75 --as-of 2010-01-01
    python -m source.parse.reconstruct 1997-06-13-44 --para §5-3
    python -m source.parse.reconstruct 2009-06-19-103 --json > out.json
    python -m source.parse.reconstruct --list                       # what's reconstructable
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from source.parse import pipeline


def _norm_law(law: str) -> str:
    """Accept '2007-06-29-75' or 'lov/2007-06-29-75'; return the 'lov/<dk>' form."""
    law = law.strip()
    return law if "/" in law else f"lov/{law}"


_PARA_SORT = re.compile(r"§?\s*(\d+)(?:-(\d+))?([a-zæøå])?", re.I)


def _para_key(p: str):
    """Natural sort key for a provision id like '§5', '§5-3', '§9a'."""
    m = _PARA_SORT.match(p)
    if not m:
        return (10**9, 0, "", p)
    main = int(m.group(1))
    sub = int(m.group(2)) if m.group(2) else 0
    suf = (m.group(3) or "").lower()
    return (main, sub, suf, p)


_DATOKODE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d+$")   # well-formed: YYYY-MM-DD-NN


def available_laws() -> list[str]:
    """Datokodes with a reconstructable enactment base: provision rows in the corpus
    segments, plus the committed dev-set enactment bases. Only WELL-FORMED datokodes are
    returned — a provision row's carried-forward `datokode` is sometimes an OCR-mangled
    heading ('11. nov. Nr. 1608'), which is not an addressable law."""
    dks = set()
    if pipeline._SEGMENTS.exists():
        for line in open(pipeline._SEGMENTS, encoding="utf-8"):
            r = json.loads(line)
            if r.get("klass") == "provision" and _DATOKODE.match(r.get("datokode") or ""):
                dks.add(r["datokode"])
    if pipeline._ENACTMENT.exists():
        for f in pipeline._ENACTMENT.glob("*.json"):
            if _DATOKODE.match(f.stem):
                dks.add(f.stem)
    return sorted(dks)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m source.parse.reconstruct",
        description="Reconstruct a Norwegian statute's point-in-time text from the corpus.")
    ap.add_argument("law", nargs="?", help="datokode, e.g. 2007-06-29-75 (or lov/2007-06-29-75)")
    ap.add_argument("--as-of", metavar="YYYY-MM-DD", default=None,
                    help="reconstruct the text as it read on this date (default: latest)")
    ap.add_argument("--base", choices=["enactment", "2005"], default="enactment",
                    help="base pipeline: from enactment (default) or the 2005 snapshot")
    ap.add_argument("--para", metavar="§X", default=None, help="print only this provision")
    ap.add_argument("--json", action="store_true", help="emit {para: text} as JSON")
    ap.add_argument("--list", action="store_true", help="list reconstructable datokodes and exit")
    args = ap.parse_args(argv)

    if args.list:
        laws = available_laws()
        print(f"{len(laws)} reconstructable datokodes (provision base present):")
        for dk in laws:
            print(f"  {dk}")
        return 0

    if not args.law:
        ap.error("a law datokode is required (or use --list)")

    law = _norm_law(args.law)
    provs, flags = pipeline.reconstruct(law, as_of=args.as_of, base=args.base)

    if not provs:
        print(f"No base found for {law} — not in the corpus/enactment set. "
              f"Run --list to see what's reconstructable, and ensure data/lovtidend_text/ "
              f"is restored (the segments point into it).", file=sys.stderr)
        return 2

    if args.para:
        want = args.para if args.para.startswith("§") else f"§{args.para}"
        if want not in provs:
            print(f"{want} not in {law} (have {len(provs)} §§). Try --json to see all keys.",
                  file=sys.stderr)
            return 2
        print(provs[want])
        return 0

    if args.json:
        json.dump(provs, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    asof = args.as_of or "latest"
    print(f"# {law}  (as of {asof}; {len(provs)} §§, {len(flags)} flagged ops)\n")
    for para in sorted(provs, key=_para_key):
        print(provs[para])
        print()
    if flags:
        print(f"--- {len(flags)} FLAGGED ops (not applied; provision left at last-known text) ---")
        shown = {}
        for f in flags:
            shown.setdefault(f.get("why", "?"), 0)
            shown[f["why"]] += 1
        for why, n in sorted(shown.items(), key=lambda kv: -kv[1]):
            print(f"  {why}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
