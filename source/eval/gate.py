"""THE completion gate — one function, one exit code, the whole `/goal` condition.

INTENT: `python -m source.eval.gate` exits 0 IFF (1) the reconstruction path provably
    never uses the final/current texts as input, AND (2) corpus convergence against the
    current text clears the threshold. Nothing here is a judgement call — the `/goal`
    evaluator model just runs this and reads the exit code.
REASONING: convergence alone is gameable (return the current text). So the gate first
    runs three mechanical anti-gaming guards; only if all pass does the convergence
    number count. Guards live HERE (harness side); the pipeline (source.parse.pipeline)
    is the scanned, isolated side. That split is the anti-gaming contract.
ASSUMES: the current NLOD dump (the ANSWER KEY, harness-only) is at $LOVHISTORIE_CURRENT_DIR
    as nl-<datokode>.xml. amendments.jsonl.gz present. Dev-set laws below have both.
GUARDS:
    G1 no-answer-key-import  — recon modules must not import source.eval or hardcode the
                               current dump; enforced by AST, not trust.
    G2 runs-isolated         — with the answer key physically absent, the current loader
                               fails yet reconstruct() still works → it doesn't need it.
    G3 base-integrity        — an amended provision's ENACTMENT base must differ from the
                               current text (else the base was seeded from the answer).
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

from source.parse import amendments, pipeline
from source.eval import metrics

ROOT = Path(__file__).resolve().parents[2]
# The current NLOD dump (harness answer key). Large + git-ignored; place it at
# data/current/ or point $LOVHISTORIE_CURRENT_DIR at it.
DEFAULT_CURRENT = str(ROOT / "data" / "current")

# --- the target ------------------------------------------------------------------
THRESHOLD = 0.97          # corpus convergence required to pass (fraction of provisions)
TAU = 0.98                # per-provision similarity counted as a match
# G3 (base-integrity) uses a SEPARATE, tighter threshold than TAU: real contamination
# (a base copied out of the answer key) normalizes to ~1.0, whereas an honestly barely-
# amended provision can sit just above TAU (e.g. vphl §5-10, one changed amount → 0.9974).
# ≥0.999 catches copies without punishing legitimate near-identity. (2026-08-10.)
G3_TAU = 0.999

# Dev-set laws: (target_law, datokode). NEVER put held-out/test laws here — the loop
# must not tune on the point-in-time test set. Expand with laws that have BOTH a row in
# amendments.jsonl.gz and a current nl-<datokode>.xml.
DEV_LAWS = [
    ("lov/1918-05-31-4", "1918-05-31-4"),      # avtaleloven
    ("lov/1959-10-23-3", "1959-10-23-3"),      # oreigningslova
    ("lov/1979-05-18-18", "1979-05-18-18"),    # foreldelsesloven
    ("lov/1982-12-17-86", "1982-12-17-86"),    # rettsgebyrloven
    ("lov/1986-06-20-35", "1986-06-20-35"),    # mesterbrevloven (enactment base built)
    ("lov/1988-05-13-27", "1988-05-13-27"),    # kjøpsloven
    ("lov/1997-06-13-44", "1997-06-13-44"),    # aksjeloven
    ("lov/2007-06-29-75", "2007-06-29-75"),    # verdipapirhandelloven
    ("lov/2009-06-19-103", "2009-06-19-103"),  # tjenesteloven
]

# The reconstruction path — the modules the input-isolation guard scans. If a new
# module joins the pipeline, add it here so the guard keeps covering the whole path.
RECON_MODULES = ["pipeline.py", "replay.py", "ledd.py", "amendments.py"]
_DUMP_LITERAL = re.compile(r"nl-\d{8}-\d+\.xml|LOVHISTORIE_CURRENT_DIR|current_provisions")


# --- answer key (harness only; read at CALL time so G2 can hide it) --------------
def _current_dir() -> Path:
    return Path(os.environ.get("LOVHISTORIE_CURRENT_DIR", DEFAULT_CURRENT))


def _fname(datokode: str) -> str:
    y, m, d, nr = datokode.split("-")
    return f"nl-{y}{m}{d}-{int(nr):03d}.xml"


def current_provisions(datokode: str):
    """{para: text} of the current text — ANSWER KEY, harness-only. None if absent.

    Parsed STRUCTURALLY, via the same data-name-keyed parser as the enactment base
    (build_enactment.parse_lovdata_xml), so base and answer are split IDENTICALLY. The
    old regex reader split on every in-body "§ N", inventing phantom provisions from
    cross-references (tjenesteloven: 33 vs 29 real) and truncating provisions mid-
    sentence — which understated convergence for every law. Symmetry is the point: a
    never-amended provision's base then equals its answer. (2026-08-10.)

    Note: this reads the answer key at CALL time (so G2 can hide it by removing the
    dir → f.exists() False → None) and only PARSES it; nothing here leaks into the
    reconstruction path (build_enactment is not a RECON_MODULE and is never imported
    by pipeline/replay/ledd/amendments)."""
    f = _current_dir() / _fname(datokode)
    if not f.exists():
        return None
    from source.scrape.build_enactment import parse_lovdata_xml
    return parse_lovdata_xml(f.read_text(encoding="utf-8", errors="ignore"))


# --- G1: the reconstruction path must not be able to see the answer key ----------
def guard_no_answer_key_import():
    """FAIL if any recon module imports the harness (source.eval) or hardcodes the
    current dump. AST for imports so a docstring mentioning 'current' can't false-fail."""
    offenders = []
    for name in RECON_MODULES:
        path = ROOT / "source" / "parse" / name
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            mod = None
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
            elif isinstance(node, ast.Import):
                mod = ",".join(a.name for a in node.names)
            if mod and re.search(r"\bsource\.eval\b", mod):
                offenders.append(f"{name}: imports harness `{mod}`")
        # hardcoded answer-key path / symbol anywhere in the source text
        for m in _DUMP_LITERAL.finditer(src):
            offenders.append(f"{name}: references answer key `{m.group(0)}`")
    return offenders


# --- G2: prove reconstruct() works with the answer key physically removed --------
def guard_runs_isolated():
    """With the answer-key dir pointed at nothing: the current loader must return None
    (truly gone) AND reconstruct() must still produce provisions (doesn't need it)."""
    offenders = []
    saved = os.environ.get("LOVHISTORIE_CURRENT_DIR")
    os.environ["LOVHISTORIE_CURRENT_DIR"] = str(ROOT / "data" / "_no_answer_key_here")
    try:
        for law, dk in DEV_LAWS:
            if current_provisions(dk) is not None:
                offenders.append(f"{dk}: answer key still reachable under isolation")
            recon, _ = pipeline.reconstruct(law)
            if not isinstance(recon, dict):
                offenders.append(f"{law}: reconstruct() failed without answer key")
    finally:
        if saved is None:
            os.environ.pop("LOVHISTORIE_CURRENT_DIR", None)
        else:
            os.environ["LOVHISTORIE_CURRENT_DIR"] = saved
    return offenders


# --- G3: an amended provision's enactment base must differ from the current text --
def guard_base_integrity():
    """If enactment_base seeds an amended provision with text identical to the current
    version, the base was copied from the answer — contamination. FAIL those."""
    offenders = []
    for law, dk in DEV_LAWS:
        base = pipeline.enactment_base(law)
        if not base:
            continue  # empty base can't be contaminated (honest current state)
        cur = current_provisions(dk) or {}
        # For a snapshot base (booklet ajourført at base_as_of) a provision amended only
        # ON/BEFORE base_as_of is LEGITIMATELY identical to current — the snapshot bakes
        # that amendment in — so it is not contamination. Only amendments dated AFTER the
        # snapshot must leave base != current; those are the ones G3 polices. Pure
        # enactment bases have base_as_of None and check every amendment (unchanged).
        since = pipeline.base_as_of(law)
        amended = {op["para"] for op in amendments.load_for(law)
                   if op["kind"] in ("replace", "add", "subprovision") and op["para"]
                   and (not since or (op.get("date") or "") > since)}
        for para in amended:
            if para in base and para in cur and \
                    metrics.similarity(base[para], cur[para]) >= G3_TAU:
                offenders.append(f"{law} {para}: enactment base == current text")
    return offenders


# --- convergence: matched / ALL current provisions (denominator can't be shrunk) --
def convergence():
    matched = total = 0
    per_law = []
    for law, dk in DEV_LAWS:
        cur = current_provisions(dk)
        if cur is None:
            per_law.append((dk, None, None))
            continue
        recon, _ = pipeline.reconstruct(law)
        m = sum(1 for p, txt in cur.items()
                if metrics.similarity(recon.get(p, ""), txt) >= TAU)
        matched += m
        total += len(cur)
        per_law.append((dk, m, len(cur)))
    frac = matched / total if total else 0.0
    return frac, matched, total, per_law


def main():
    g1 = guard_no_answer_key_import()
    g2 = guard_runs_isolated()
    g3 = guard_base_integrity()
    frac, matched, total, per_law = convergence()

    print("=== lovhistorie completion gate ===")
    print(f"G1 no-answer-key-import : {'PASS' if not g1 else 'FAIL'}")
    for o in g1:
        print(f"   - {o}")
    print(f"G2 runs-isolated        : {'PASS' if not g2 else 'FAIL'}")
    for o in g2:
        print(f"   - {o}")
    print(f"G3 base-integrity       : {'PASS' if not g3 else 'FAIL'}")
    for o in g3:
        print(f"   - {o}")
    print(f"convergence             : {frac:.4f}  ({matched}/{total} provisions @ ≥{TAU})")
    for dk, m, t in per_law:
        print(f"   - {dk}: " + (f"{m}/{t}" if t else "current text NOT FOUND"))
    print(f"threshold               : {THRESHOLD}")

    guards_ok = not (g1 or g2 or g3)
    if not guards_ok:
        print("VERDICT: FAIL — anti-gaming guard tripped (this is a hard stop, not progress)")
        return 3
    if frac >= THRESHOLD:
        print("VERDICT: PASS")
        return 0
    print("VERDICT: FAIL — guards clean, convergence below threshold (keep working)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
