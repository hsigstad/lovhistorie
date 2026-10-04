"""Canonical agent prompt + output schema for subagent issue-segmentation (the ONE
segmentation step; decisions.md 2026-10-04).

INTENT: version-control the subagent prompt + its structured-output schema, because this
    prompt IS the bootstrap for `segments.jsonl` — its exact wording is a reproducibility-
    critical artifact, not an incidental string buried in a run script.
REASONING: the CONTRACT is ordered-starts, gap-free by construction — the subagent returns an
    ORDERED list of segment STARTS covering the whole issue top to bottom; each segment runs
    from its start to the NEXT segment's start, so gaps/overlaps are impossible. The agent
    decides boundaries + kinds (what it reads well); the deterministic layer tiles by
    consecutive starts, carves page furniture out as `noise`, substring-verifies, flags. This
    is the locate-vs-compute split: agent LOCATES/CLASSIFIES (verbatim pointers, never rewrites
    text, never a base-dependent decision, never anchors furniture); code COMPUTES (resolve,
    tile, parse address, decide insert-vs-replace vs base, order by in-force, apply).
ASSUMES: the subagent sees ONLY the public-domain OCR of one issue (never the current dump /
    oracle / register) — answer-free by construction (gate guard G1). `acts` passed to
    build_prompt is public gazette-index metadata, not an answer key.
"""
from __future__ import annotations

# JSON Schema for the Workflow agent() call (forces structured output).
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "segments": {
            "type": "array",
            "description": "ordered, top-to-bottom; each runs to the NEXT segment's start (gap-free)",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": [
                        "front_matter",      # masthead + table of contents (everything before the first act body)
                        "enactment_heading", # "Lov nr N / Lov om …" + preamble, up to the first §
                        "provision",         # one § of an enacted law
                        "amend_scope",       # "I lov/forskrift … gjøres følgende endringer:" (sets the target)
                        "amend_op",          # one amendment operation
                        "repeal",            # a standalone repealing act body
                        "ikrafttredelse",    # a commencement notice ("Ikrafttr. av lov …")
                        "in_force",          # an act's OWN "Loven trer i kraft …" clause
                        "forskrift",         # a regulation (forskrift/resolusjon) body
                        "signature",         # promulgation / signature block
                        "other"]},           # anything genuinely unclassifiable (flagged downstream)
                    "start_anchor": {"type": "string",
                        "description": "VERBATIM first ~8 words where THIS segment begins (exact OCR substring)"},
                    "datokode": {"type": "string", "description": "YYYY-MM-DD-nr of the act this belongs to (from the index)"},
                    "para": {"type": "string", "description": "provision only: normalized id, e.g. §1, §5a, §2-11"},
                    "target_cite": {"type": "string", "description": "amend_scope/amend_op: the law/forskrift being changed, verbatim"},
                    "instrument": {"type": "string", "enum": ["lov", "forskrift"], "description": "amend_scope: what the target is"},
                    "op_kind": {"type": "string",
                        "enum": ["set_text", "repeal", "renumber", "word_replace", "insert"],
                        "description": "amend_op: coarse, inferable from the instruction TEXT only"},
                    "from": {"type": "string", "description": "renumber/word_replace: verbatim source id-range or token"},
                    "to": {"type": "string", "description": "renumber/word_replace: verbatim target id-range or token"},
                    "position": {"type": "string", "description": "insert: verbatim position phrase, e.g. 'før de fire eksisterende'"},
                },
                "required": ["kind", "start_anchor"],
            },
        },
    },
    "required": ["segments"],
}


def build_prompt(path: str, acts: list[dict]) -> str:
    """System+task prompt for one issue. `acts` = the public index's (datokode, title, klass)
    for this issue — the acts whose bodies must appear, given as a checklist (NOT an answer key:
    it is public gazette metadata)."""
    checklist = "\n".join(f"  - {a['datokode']} ({a.get('klass')}): \"{a.get('title')}\"" for a in acts)
    return f"""You are segmenting one issue of *Norsk Lovtidend* (the Norwegian official gazette), OCR'd from a public-domain scan. Your ONLY input is this text file:

{path}

Read it with the Read tool. Do NOT read any other file or use any other source. Work solely from that text.

## What the issue looks like
It opens with a masthead and a TABLE OF CONTENTS (acts listed with page numbers), then the ACTS THEMSELVES — each introduced by a heading like "7. juli Lov nr. 68 / Lov om …". Running headers/page numbers ("2000 / 1682 / 7. juli Lov nr. 69") are interleaved into the text — IGNORE them, do not emit segments for them (deterministic code removes them).

## Acts expected in this issue (public gazette index — their bodies must all appear)
{checklist}

## Your task — a COMPLETE, GAP-FREE, ORDERED partition
Return an ORDERED list of segment STARTS that covers the ENTIRE issue from the very first character to the end. Each segment runs from its `start_anchor` to the NEXT segment's start, so THERE MUST BE NO GAP: every region of text — the front matter, each law heading, each individual § , each amendment operation, each commencement clause, any regulation or signature block — begins a new segment. The first segment starts at the very top of the file.

For each segment give `start_anchor` = the VERBATIM first ~8 words where it begins (an exact OCR substring; I locate it by searching, so copy it character-for-character, OCR quirks and all), plus:
- `front_matter` — the masthead + table of contents block (usually one segment at the top).
- `enactment_heading` then one `provision` per § — for an enacted law ("Lov om <subject>"). Set `datokode`; on each provision set `para` (normalized "§1", "§5a" — the OCR often mangles the § glyph, e.g. "S 2."/"5 3." are §2/§3; use the sequence).
- `amend_scope` — the "I lov/forskrift … gjøres følgende endringer:" line; set `target_cite` (verbatim) and `instrument` (lov|forskrift). Omnibus acts have several.
- `amend_op` — ONE per amendment instruction. Set `op_kind` from the TEXT only: `set_text` ("… skal lyde:"), `repeal` ("… oppheves"), `renumber` ("Nåværende … blir …" — also set verbatim `from`/`to`), `word_replace` ("erstattes/endres … med/til" — set verbatim `from`/`to`), `insert` (explicit "ny/nytt/skytes inn/inntas" — set `position` if stated). Do NOT decide whether a bare "skal lyde" replaces or inserts — that is `set_text`; downstream decides against the base.
- `in_force` — an act's own "Loven trer i kraft …" clause (its own segment, so it is not swallowed into the preceding op).
- `ikrafttredelse` — a standalone commencement notice for another act.
- `repeal` / `forskrift` / `signature` / `other` as they occur.

## Hard rules
1. Anchors are VERBATIM substrings — copy, never paraphrase/fix-OCR/translate. Unfound anchors are dropped.
2. COVER EVERYTHING — no gaps. If you are unsure what a region is, give it a segment with kind `other` rather than skipping it.
3. Do NOT segment inside a provision or an op's payload (no sub-§ breakdown, no articles inside an inserted chapter) — that structure is parsed later against the base. One segment per § and per op.
4. Do NOT emit segments for running headers / page numbers.

Return ONLY the JSON object (a `segments` array) as your final message — no prose, no code fences."""
