"""Canonical agent prompt + schema for the offline ledd-APPLICATOR subagent (sibling of
segment_prompt.py).

INTENT: version-control the applicator prompt + its structured-output schema, because this wording
    IS the reproducible bootstrap for `data/applications.jsonl` — the model reads a provision + an
    amendment instruction + the new-text payload and LOCATES the span the edit applies to, emitting
    only VERBATIM ANCHORS into the provision, never statutory text.
REASONING: locate-not-compute. Deterministic code (source/parse/ledd_apply.splice) re-resolves the
    anchors against the current provision and splices the payload in, so 0% fabrication is automatic
    and a changed base degrades to flag-don't-fabricate. Validated 2026-10-12
    (docs/notes/llm_ledd_applicator.md): vs the deterministic ledd engine on clean bases 10/12 exact /
    0.977 mean; first real OCR law (helsepersonelloven) 35/37 applied, net-positive.
ASSUMES: the subagent sees ONLY the public provision + the amendment (both public-domain), never the
    current/oracle dump or the register (G1). The case file is written by the offline populator from
    public bases + ops.
"""
from __future__ import annotations

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "op_kind": {"type": "string", "enum": ["replace", "insert_after", "delete"],
                    "description": "replace a span with the payload; insert payload after an anchor; or delete a span"},
        "span_start_anchor": {"type": "string",
            "description": "VERBATIM first ~8 words of the span in the PROVISION (exact substring). For insert_after: the text to insert right after."},
        "span_end_anchor": {"type": "string",
            "description": "VERBATIM last ~8 words of the span in the PROVISION (the span ends right after these). Omit for insert_after."},
        "reasoning": {"type": "string", "description": "one short sentence: which ledd/punktum/part you located and why"},
    },
    "required": ["op_kind", "span_start_anchor"],
}


def build_prompt(case_path: str) -> str:
    """Subagent prompt for one application case FILE ({provision, instruction, payload})."""
    return (f"Read this JSON file with the Read tool:\n{case_path}\n"
            f'It has three fields: "provision", "instruction", "payload".\n\n' + INSTRUCTIONS
            + "\n\nReturn ONLY the JSON object.")


def user_message(provision: str, instruction: str, payload: str) -> str:
    """Inline user message for the llmkit (OpenAI) path — same task, text given directly."""
    return f"INSTRUCTION: {instruction}\n\nPAYLOAD (new text, for context only — do NOT echo it):\n{payload}\n\nPROVISION:\n{provision}"


# Delivery-agnostic task body, shared by the subagent prompt (build_prompt) and the llmkit system
# prompt (ledd_apply_llm). Describes the three named inputs + exactly what to return.
INSTRUCTIONS = """You apply ONE Norwegian statutory amendment to a provision, by LOCATING the span it edits — you NEVER write statutory text yourself. You are given three inputs:
- "provision": the current text of the § (OCR'd; ledd = paragraphs; may have no explicit numbering).
- "instruction": the amendment instruction, e.g. "§ 24-2 andre ledd skal lyde:" or "§ 10-13 første punktum skal lyde:" or "§ X skal lyde:".
- "payload": the NEW text the amendment supplies (context only; deterministic code splices it in — NOT your job).

Decide WHERE in "provision" the edit applies, and return ONLY verbatim anchors into "provision":
- Parse the instruction's address: a whole § ("§ X skal lyde") replaces the ENTIRE provision; "andre/annet ledd" = the 2nd paragraph; "første/andre … punktum" = the Nth sentence of the addressed ledd; "bokstav a/b" = that lettered item; "nr. N" = that numbered item; "nytt … ledd/punktum/bokstav" = an INSERT (nothing replaced).
- Ordinals: første=1, annet/andre=2, tredje=3, fjerde=4, femte=5, sjette=6, syvende/sjuende=7, ...
- Count ledd as the natural paragraphs of the provision text, reading through OCR noise.

Return:
- op_kind: "replace" (… skal lyde on existing text), "insert_after" (nytt/ny … — the payload is NEW, nothing is removed), or "delete" (… oppheves).
- span_start_anchor: the VERBATIM first ~8 words of the located span in "provision" (copy exactly, OCR quirks and all). For a whole-§ replace, the first ~8 words of the whole provision. For insert_after, the ~8 words AFTER WHICH the new text goes (e.g. the end of the preceding ledd).
- span_end_anchor: the VERBATIM last ~8 words of the located span (the span ends right after these). For a whole-§ replace, the last ~8 words of the provision. Leave empty for insert_after.
- reasoning: one short sentence.

Anchors MUST be exact substrings of "provision" — they are located by searching. If you cannot confidently locate the span, give your best anchors anyway (deterministic verification rejects a bad anchor)."""

# Back-compat alias (the subagent workflow referenced PROMPT_TEMPLATE via build_prompt only).
PROMPT_TEMPLATE = INSTRUCTIONS
