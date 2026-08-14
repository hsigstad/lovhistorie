"""Re-parse LTI amending-act XMLs into a COMPLETE amendment stream (every target law).

INTENT: the external `amendments.jsonl.gz` stream drops many omnibus sections — a single
    act amends dozens of laws ("Lov om endringer i X og enkelte andre lover"), and only
    some laws' sections were captured (e.g. lov 2009-06-19-48 amends 34 laws; its vphl
    section, ~11 provisions, is absent). But the FULL act text is in `data/lti/`. This
    offline build re-parses each LTI act, extracts the ops for EVERY law it targets, and
    writes the sections MISSING from the external stream to `data/lti_amendments.jsonl.gz`
    (same schema) for pipeline.load_ops to merge — recovering post-2001 omnibus amendments
    from data we already hold, deterministically, no OCR.
REASONING: each `<section class="section">` is one target law's block: a header
    "I lov <cite> ... gjøres følgende endringer:" (→ target datokode) followed by
    instruction paragraphs (`<article class="defaultP">§ X ... skal lyde:</article>`) each
    trailed by the new-text content articles up to the next instruction. Structure-based
    extraction (not OCR regex): the instruction is the defaultP, the new text is the
    content between it and the next instruction.
ASSUMES / SCOPE: modern (2001+) LTI XML with `class="section"` blocks. Blocks are bounded by
    the amendment header "I lov <cite> ... gjøres følgende endringer:" OR the bare-title variant
    "Lov [av] <cite> om <name> ... gjøres følgende endringer:" (a consequential-amendments chapter
    uses both — see _BLOCK_HEADER). Op scope = whole-provision replace/add + sub-unit repeals;
    sub-provision replace/add is gated (see _parse_block). Blanket-terminology sections
    ("uttrykket «A» endres til «B» i følgende bestemmelser: …") and ikrafttredelse tails
    are SKIPPED (flag-don't-fabricate — recorded, not guessed). Emits only (act,target)
    sections NOT already present in the external stream, so the merge is purely additive
    (no duplicate ops).
ANTI-GAMING: this reads `data/lti/` (enactment+amendment SOURCE, public-domain — NOT the
    current consolidated text) and is an OFFLINE build script under source/scrape/, never a
    RECON module (per the LTI-naming caveat in docs/notes/lessons_and_pitfalls.md #7). It
    writes a DERIVED jsonl.gz that the recon path reads, exactly like the pre-2001 gazette
    parser and the block-override flow.
"""
from __future__ import annotations

import glob
import gzip
import json
import re
import sys
from pathlib import Path

from source.parse import gazette, inforce
from source.scrape.build_enactment import _xml_text

ROOT = Path(__file__).resolve().parents[2]
LTI = ROOT / "data" / "lti"
OUT = ROOT / "data" / "lti_amendments.jsonl.gz"

# The TRUE op-block boundary is the amendment header "I lov <cite> … gjøres følgende
# endringer:", NOT the <section> tag. One <section> (e.g. a new enactment's consequential-
# amendments chapter) can carry SEVERAL such headers, each starting a different target law's
# block; splitting on <section> mis-lumped them all under the first cite. So we scan the WHOLE
# act body for these headers and bound each block at the next header. `[^§]*?` keeps the header
# from swallowing the first op's '§' if a title is unusually long.
#
# The prefix is "I lov <cite>" for most blocks, but a consequential-amendments chapter listing
# many laws also uses the bare-title form "Lov [av] <cite> om <name> … gjøres følgende endringer:"
# for some items (e.g. lov 2019-03-15-6 introduces its nr. 44 aksjeloven block with "I lov …" but
# its nr. 45 allmennaksjeloven block with "Lov av …"). Missing the "Lov [av] …" form left the nr.
# 45 block unbounded, so ALL of allmennaksjeloven's ops (its §4-13/§5-10/§13-18 verdipapirsentral
# amendments) leaked into the preceding nr. 44 aksjeloven block — a mis-attribution, NOT an in-force
# problem. Accepting both prefixes fixes the boundary. Safe to broaden: the "gjøres følgende
# endringer:" anchor is the real guard, and `[^§]*?` cannot span a preceding block's ops (they
# contain §), so a bare preamble title line can't false-match a later law's "gjøres" header.
_BLOCK_HEADER = re.compile(
    r"(?:I\s+lov|Lov(?:\s+av)?)\s+(\d{1,2}\.?\s*[a-zæøå]+\.?\s*\d{4}\s*nr\.?\s*\d+)[^§]*?"
    r"gj[øo]res?\s+f[øo]lg\w*\s+endring\w*\s*:", re.I)
# an instruction paragraph (defaultP that states an op, not the header/plain prose)
_DEFP = re.compile(r'<article class="defaultP"[^>]*>(.*?)</article>', re.S)
_IS_INSTR = re.compile(
    r"^(?:§|Ny\s+§|Nytt?\s|Nye\s|N[åa]v[æa]rende|Overskrift)", re.I)
_HAS_VERB = re.compile(r"\b(?:skal\s+lyde|oppheves|skal\s+endres)\b", re.I)
_PARA = re.compile(r"§\s*(\d+(?:-\d+)?\s*[a-z]?)")
_SUBUNIT = re.compile(r"\b(?:ledd|punktum|bokstav|nr\.?)\b", re.I)


def _para_id(instr: str) -> str | None:
    m = _PARA.search(instr)
    return "§" + m.group(1).replace(" ", "") if m else None


def _change_type(instr: str) -> str:
    if re.search(r"\boppheves\b", instr, re.I):
        return "repeal"
    if re.match(r"^\s*(?:Ny\s+§|Nytt?\s|Nye\s)", instr, re.I):
        return "add"
    return "change"


def _parse_block(block_html: str, whole_only: bool = True):
    """Yield (instruction, new_text, change_type) ops for ONE target-law block (already
    bounded to its own '§ … skal lyde' ops — the caller slices between amendment headers).
    Structure-based: instruction = a defaultP op line; new_text = the content articles up
    to the next instruction (whole-provision ops get their '§ N.' heading re-attached so
    the replay §-body branch applies them; sub-provision ops keep the raw replacement body)."""
    marks = []
    for m in _DEFP.finditer(block_html):
        txt = _xml_text(m.group(1))
        if _IS_INSTR.match(txt) and _HAS_VERB.search(txt):
            marks.append((m.start(), m.end(), txt))
    ops = []
    for i, (s, e, instr) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(block_html)
        content = _xml_text(block_html[e:end])
        para = _para_id(instr)
        ct = _change_type(instr)
        # SCOPE (shipped default): WHOLE-PROVISION replace/add + SUB-UNIT REPEALS.
        # - Whole-provision replace/add: self-contained (new text is the entire provision body),
        #   so re-attaching its '§ N.' heading makes a clean overwrite via replay's §-body branch.
        # - Sub-unit repeals ("§ X annet ledd oppheves"): SAFE to include — replay routes them
        #   through ledd.apply, which FLAGS-AND-LEAVES-INTACT if the address doesn't resolve
        #   (never deletes the whole §; see the 2026-08-13 over-deletion fix). Net +6 on the dev
        #   set (kjøpsloven §7/§17/§32/§35/§45/§67), ZERO τ-regression.
        # Sub-provision REPLACE/ADD ("… skal lyde:" on a ledd/punktum/nr) stay gated off
        # (`whole_only`): they gave +6 but −6 on the dev set — DOUBLE-APPLICATION when a
        # whole-provision rebuild and an in-force sub-op touch the same § and the ledd engine is
        # not idempotent (§21-15 1.000→0.729, §5-27, §16-9). NB: the −6 that used to hit aksjeloven
        # was a BLOCK-HEADER LEAK (allmennaksjeloven ops mis-attributed via a "Lov av …" header),
        # now fixed in _BLOCK_HEADER; and the residual −3 are in-force acts (confirmed triggered),
        # so the blocker is the ledd engine, NOT in-force dates. `whole_only=False` re-measures.
        is_subunit_repeal = ct == "repeal" and para and bool(_SUBUNIT.search(instr))
        if ct in ("change", "add") and para and not _SUBUNIT.search(instr) and content:
            num = para.lstrip("§")
            ops.append((instr, f"§ {num}. {content}".strip(), ct))
        elif is_subunit_repeal:
            ops.append((instr, None, "repeal"))
        elif not whole_only and para and (content or ct == "repeal"):
            ops.append((instr, (content or None) if ct != "repeal" else None, ct))
    return ops


def parse_act(xml_path: Path, whole_only: bool = True):
    """All amendment rows an LTI act carries, one per (target law × op). `date_in_force` is
    the act (passage) date — a lower bound; `date_in_force_resolved` is the TRUE ikrafttredelse
    date from `source.parse.inforce` (the act's own dateInForce, or the triggering resolution
    for deferred acts), falling back to the act date when unresolved (flag-don't-fabricate)."""
    raw = xml_path.read_text(encoding="utf-8", errors="ignore")
    dk = xml_path.stem.replace("nl-", "")
    y, m, d, nr = dk[:4], dk[4:6], dk[6:8], int(dk[8:].lstrip("-") or 0)
    act_dk = f"{y}-{m}-{d}-{nr}"
    act_date = f"{y}-{m}-{d}"
    resolved = inforce.resolved_date(act_dk) or act_date
    rows = []
    heads = [(hm.start(), hm.end(), gazette.datokode("lov " + hm.group(1)))
             for hm in _BLOCK_HEADER.finditer(raw)]
    for i, (hs, he, target_dk) in enumerate(heads):
        if not target_dk:
            continue
        block_end = heads[i + 1][0] if i + 1 < len(heads) else len(raw)
        for instr, new_text, ct in _parse_block(raw[he:block_end], whole_only):
            rows.append({
                "act_refid": f"lov/{act_dk}",
                "target_law": f"lov/{target_dk}",
                "target": None,
                "paragraph": None,
                "change_type": ct,
                "instruction": instr,
                "new_text": new_text,
                "date_in_force_resolved": resolved,
                "date_in_force": act_date,
                "source": "lti_act_reparse",
            })
    return rows


def _existing_pairs(data_path: Path):
    """(act_refid, target_law) pairs already present in the external stream — so we emit
    ONLY the sections it dropped (purely additive, no duplicate ops)."""
    seen = set()
    with gzip.open(data_path, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            seen.add((d.get("act_refid"), d.get("target_law")))
    return seen


def build(act_datokoder=None, only_missing=True):
    """Parse LTI acts and write the missing (act,target) sections to OUT. `act_datokoder`
    limits to specific acts (fast measurement); None = every act in data/lti/."""
    from source.parse import amendments
    existing = _existing_pairs(amendments.DATA) if only_missing else set()
    # Refresh the in-force index on a FULL rebuild so `date_in_force_resolved` can't go stale
    # after a new LTI harvest (the lazy cache only builds when ABSENT, not when out of date).
    # Per-act measurement runs (act_datokoder set) reuse the cache — 19s is not worth paying.
    if act_datokoder is None:
        inforce.build()
    if act_datokoder:
        files = []
        for a in act_datokoder:
            y, m, d, nr = a.split("-")
            f = LTI / y / f"nl-{y}{m}{d}-{int(nr):03d}.xml"
            if f.exists():
                files.append(f)
    else:
        files = [Path(p) for p in sorted(glob.glob(str(LTI / "*" / "nl-*.xml")))]
    n_rows = kept = 0
    with gzip.open(OUT, "wt", encoding="utf-8") as out:
        for f in files:
            for row in parse_act(f):
                n_rows += 1
                if only_missing and (row["act_refid"], row["target_law"]) in existing:
                    continue
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                kept += 1
    print(f"parsed {len(files)} acts -> {n_rows} ops; kept {kept} in missing sections -> "
          f"{OUT.relative_to(ROOT)}")
    return kept


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    build(act_datokoder=args or None, only_missing="--all-sections" not in sys.argv)
