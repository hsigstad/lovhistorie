"""The reconstruction entrypoint — the ONLY thing the autonomous loop improves.

INTENT: expose one function, `reconstruct(target_law, as_of)`, that rebuilds a law's
    provisions from PUBLIC-DOMAIN inputs only — the enactment base (gazette) + the
    ordered Lovtidend amendment ops — and never from the current/final consolidated
    text. The eval gate (source/eval/gate.py) drives this toward convergence.
REASONING: keeping the whole reconstruction behind one import boundary lets the gate
    prove input-isolation mechanically: this module (and everything it imports) must
    NOT import the harness package `source.eval`, which is where the answer key lives.
    Break that and the gate's static guard fails — the anti-gaming contract in code.
ASSUMES: amendments.load_for gives ordered ops; replay applies them; enactment_base
    supplies the starting text. enactment_base is the current frontier of the work
    (see its docstring) — today it returns {} so convergence measures amendments
    alone; wiring the gazette base is the main lever to raise it.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

from source.parse import amendments, replay

_ENACTMENT = Path(__file__).resolve().parents[2] / "data" / "enactment"
_PARA = re.compile(r"§\s*(\d+(?:-\d+)?[a-z]?)")

# A provision-body HEADING at the start of a string: '§ 5-8 a.Opplysninger…' -> '§5-8a'.
# The suffix letter is frequently rendered/OCR'd with a space before it ('§ 5-8 a.'), which
# _PARA drops (it captures '§5-8'). The TRAILING PERIOD anchors the letter as a genuine
# suffix, so a following word or Norwegian preposition ('§ 5 i loven', '§ 27 første ledd' —
# no period) can never be mistaken for one. Digits, optional space+single letter, period.
_HEAD_ID = re.compile(r"§\s*(\d+(?:-\d+)?)\s*([a-z])?\.")


def _heading_id(s: str | None):
    """Canonical id from a period-anchored provision heading at the START of `s`, with any
    space before the suffix letter removed ('§ 5-8 a.' -> '§5-8a'). None if `s` does not
    open with such a heading. This is the ONLY place a spaced suffix is accepted — and only
    because the period makes it unambiguous."""
    if not s:
        return None
    m = _HEAD_ID.match(s.lstrip())
    return "§" + m.group(1) + (m.group(2) or "") if m else None


def _clean_para(s: str | None):
    """First '§ N' anywhere in `s` -> '§N'. For target fields that NAME the provision
    ('§ 1-9', '§ 6 n'). NOT for new_text bodies — their first § is often a cross-ref."""
    if not s:
        return None
    m = _PARA.search(s)
    return "§" + m.group(1) if m else None


def _leading_para(new_text: str | None):
    """'§ N' ONLY if new_text opens with its own heading ('§ 4.Vedtak…' -> '§4';
    '§ 5-8 a.…' -> '§5-8a'). Start-anchored so a body cross-reference ('Vedtak etter
    §§ 2, 3…') never matches. Prefers the period-anchored heading id (recovers a spaced
    letter suffix); falls back to the bare '§ N' form for headings without a period."""
    if not new_text:
        return None
    m = _PARA.match(new_text.lstrip())
    return _heading_id(new_text) or ("§" + m.group(1) if m else None)


def _op_para(d: dict):
    """Clean paragraf id: the fields that NAME the target first; new_text's own
    leading heading only as a last resort (never a mid-body §-reference)."""
    return (_clean_para(d.get("paragraph"))
            or _clean_para(d.get("target"))
            or _clean_para(d.get("instruction"))
            or _leading_para(d.get("new_text")))


# Split points: line-start provision headings '§ N.' (spaced suffix tolerated: '§ 5-8 a.').
_BLOCK = re.compile(r"(?m)(?=^\s*§\s*\d+(?:-\d+)?\s*[a-z]?\.)")


def _split_block(new_text: str):
    """A '§ X skal lyde' / 'Kapittel N skal lyde' new_text can carry SEVERAL
    provisions ('§ 1-1.…\\n§ 1-2.…'). Split on line-start '§ N.' headings into
    [(para, piece_with_heading)] so each provision is set from its own slice, not all
    dumped onto the first. Body cross-references ('… jf. § 2-2') are mid-line and
    never split. Returns [] if there is no leading heading."""
    pieces = []
    for part in _BLOCK.split(new_text):
        para = _heading_id(part)
        if para:
            pieces.append((para, part.strip()))
    return pieces


# Derived amendment stream re-parsed from the LTI acts (source.scrape.lti_amendments):
# recovers omnibus sections the external amendments stream dropped. A DERIVED public-domain
# jsonl.gz (NOT an LTI XML, NOT the answer key) — read here exactly like amendments.DATA;
# the LTI XMLs themselves are only ever touched by the offline build script (anti-gaming
# lesson #7). Absent → skipped.
_LTI_AMEND = amendments.DATA.parent / "lti_amendments.jsonl.gz"
# Derived LLM sub-provision op stream (source.llm.amend): the correctly-attributed +
# correctly-bounded ledd/punktum replace/insert ops the regex parser over-captures or
# mis-files. Boundaries-only (payloads are verbatim source slices), read exactly like the
# other derived streams; the ledd engine is idempotent (align) so overlap is safe. Absent → skipped.
_LLM_AMEND = amendments.DATA.parent / "llm_amendments.jsonl.gz"
# Derived omnibus-recovery stream (source.scrape.build_omnibus): secondary-target sections the
# external/LTI streams mono-collapsed onto an omnibus act's primary law, re-recovered via the
# format-agnostic LLM localizer + verbatim-anchored op extractor. Same schema; dedup below
# guards the boundary so an op present in another stream is not applied twice. Absent → skipped.
_OMNIBUS = amendments.DATA.parent / "omnibus_recovered.jsonl.gz"
# Derived pre-2001 gazette-OCR recovery (source.scrape.build_gazette): the same localize-then-verify
# path applied to amending-act bodies already on disk in data/lovtidend_text — recovers pre-2001
# secondary-target/flat-omnibus amendments the regex gazette parser missed, no new harvest. NB: the
# current-dump register undercounts these (many touch since-superseded text), so they help POINT-IN-
# TIME more than convergence-to-current. Absent → skipped.
_GAZETTE = amendments.DATA.parent / "gazette_recovered.jsonl.gz"


def load_ops(target_law: str):
    """Ordered ops for a law WITH change_type + clean para (richer than
    amendments.load_for). change_type ∈ {change, add, repeal, renumber, move,
    unknown}; renumber/move/unknown are left for replay to flag, not fabricate.
    Multi-provision new_text blocks are expanded to one op per provision.

    Merges the external amendment stream with the LTI-reparse stream (the omnibus
    sections the external stream dropped); dedup by (act, para, date, instruction) guards
    the boundary so a section present in both is not applied twice."""
    ops, seen = [], set()
    # NB: _OMNIBUS / _GAZETTE (LLM omnibus + pre-2001 gazette recovery) are DELIBERATELY NOT in
    # this tuple. Clean A/B (2026-08-21): merging them made the dev set WORSE (convergence 68.5→67.8,
    # −4 aksjeloven / −2 vphl) and left point-in-time flat (0.8794→0.8801). Cause: the op extractor
    # emits malformed STRUCTURAL ops (chapter/heading/renumber, e.g. "§kapittel3avsnittIVoverskrift")
    # that corrupt previously-correct provisions; and the real captured amendments don't help because
    # amendment CAPTURE is not the dev-set bottleneck (OCR base + ledd tail dominate — errors cluster,
    # lesson #6). Re-enable only when recovered ops are filtered to clean provision-grade ops AND the
    # A/B shows net-positive. The streams + register remain valid analysis/point-in-time tools.
    for path in (amendments.DATA, _LTI_AMEND, _LLM_AMEND):
        if not path.exists():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                if d.get("target_law") != target_law:
                    continue
                base = {
                    "change_type": d.get("change_type"),
                    "instruction": d.get("instruction"),
                    "date": d.get("date_in_force_resolved") or d.get("date_in_force"),
                    "act": d.get("act_refid"),
                }
                new = d.get("new_text")
                pieces = _split_block(new) if new and new.lstrip().startswith("§") else []
                if pieces:                    # whole-provision block: one op per §
                    for para, piece in pieces:
                        key = (base["act"], para, base["date"], base["instruction"])
                        if key in seen:
                            continue
                        seen.add(key)
                        ops.append({**base, "para": para, "new_text": piece})
                else:                         # sub-provision / repeal / structural
                    para = _op_para(d)
                    key = (base["act"], para, base["date"], base["instruction"])
                    if key in seen:
                        continue
                    seen.add(key)
                    ops.append({**base, "para": para, "new_text": new})
    ops.sort(key=lambda o: (o["date"] or "", o["act"] or ""))
    return ops


def enactment_base(target_law: str) -> dict:
    """{paragraf_id: text} of the law AS ORIGINALLY ENACTED, from the gazette.

    Reads the cached, public-domain enactment built OFFLINE by
    source.scrape.build_enactment (data/enactment/<datokode>.json). No network, no
    OCR, no current text at runtime — deterministic (hard rule 3).

    HARD RULE: the cache must come from Norsk Lovtidend, NEVER from the current
    consolidated text (the gate's base-integrity guard enforces this). Laws not yet
    built return {} — their never-amended provisions can't be reconstructed and
    score 0 against the current text, which is the honest state convergence exposes.
    """
    dk = target_law.split("/")[-1]
    f = _ENACTMENT / f"{dk}.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("provisions", {})


def is_ocr_base(target_law: str) -> bool:
    """True if the enactment base was OCR'd from a gazette/booklet (its `source` has no
    clean-LTI-XML `lti` key). OCR bases carry irreducible character noise, so the eval
    applies an OCR-calibrated τ to them (gate.TAU_OCR); clean LTI bases keep the strict
    τ. Objective + structural (the source provenance recorded at build time), so it can't
    be used to hand-pick which provisions get the looser bar."""
    dk = target_law.split("/")[-1]
    f = _ENACTMENT / f"{dk}.json"
    if not f.exists():
        return False
    src = json.loads(f.read_text(encoding="utf-8")).get("source", {})
    return "lti" not in src


def base_as_of(target_law: str) -> str | None:
    """The version boundary a SNAPSHOT base was captured at (booklet 'ajourført' date),
    or None for a pure enactment base. When set, the base already incorporates every
    amendment dated <= this, so reconstruction must replay ONLY later amendments."""
    dk = target_law.split("/")[-1]
    f = _ENACTMENT / f"{dk}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8")).get("base_as_of")


def reconstruct(target_law: str, as_of: str | None = None):
    """Rebuild {paragraf_id: text} for `target_law` as of `as_of` (or latest).

    Returns (provisions, flags). Inputs are enactment base + amendment ops ONLY.
    For a snapshot base (base_as_of set), amendments already baked into the snapshot
    (date <= base_as_of) are skipped so they are not double-applied; dates before the
    snapshot are not reconstructable from it and are the honest floor of its reach.
    """
    base = enactment_base(target_law)
    ops = load_ops(target_law)
    since = base_as_of(target_law)
    if since:
        ops = [o for o in ops if not o.get("date") or o["date"] >= since]
    provs, flags = replay.replay(base, ops, as_of=as_of)
    # blanket terminology reforms ("ordet «A» endres til «B»") — applied AFTER the per-provision
    # ops as a deterministic str.replace over provisions containing the term (source.parse.blanket).
    reforms = _load_reforms(target_law)
    if reforms:
        from source.parse import blanket
        blanket.apply_reforms(provs, reforms, as_of=as_of)
    return provs, flags


_BLANKET = amendments.DATA.parent / "blanket_amendments.jsonl.gz"


def _load_reforms(target_law: str):
    """Term-reform ops for a law, from the derived blanket stream (absent → none)."""
    if not _BLANKET.exists():
        return []
    out = []
    with gzip.open(_BLANKET, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("target_law") == target_law:
                out.append(d)
    return out
