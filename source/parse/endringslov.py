"""Parse Norwegian endringslov (amendment) instructions and replay them.

INTENT: turn the amendment instructions found in Norsk Lovtidend text into
structured ops, then apply them to a base document to reconstruct point-in-time
statutory text. Pairs with source/scrape/nb_lovtidend.py (pre-2001 text) and the
current NLOD gjeldende-lover corpus (the base / endpoint).

REASONING: Norwegian endringslover re-state the FULL new wording of each amended
provision ("§ X skal lyde: <complete new text>"), so replay is a clean overwrite
rather than a fragile diff. This is why forward replay from a base reconstructs
exact historical text.

ASSUMES / KNOWN LIMITS (validated on Lovtidend 1991 Nr. 3):
- Whole-provision ops ("§ X skal lyde", "§ X oppheves") parse cleanly.
- SUB-PROVISION ops are the messy minority and need finer granularity, e.g.
  "§ 4 pkt. b oppheves" repeals a *point* inside §4, and "nytt pkt. a skal lyde"
  inserts a point. The `subunit` field captures the raw sub-reference; applying
  it precisely (ledd/punktum edits) is still TODO — see the note.
- Full-document structuring upstream (instrument boundaries, running-header
  dedup) is a separate, rougher step; this module assumes it is given the text
  of a single amendment block.
"""
import re

_SET = re.compile(
    r"(§\s*\d+\w*)([^\n:]*?)skal lyde:\s*(.+?)"
    r"(?=(§\s*\d+\w*)|trer i kraft|Endringene|oppheves|$)",
    re.S,
)
_REPEAL = re.compile(r"(§\s*\d+\w*)([^\n]*?)oppheves")


def parse_amendments(text):
    """Yield dicts: {paragraf, subunit, action, new_text}.

    action is 'set' (skal lyde) or 'repeal' (oppheves). `subunit` holds any
    sub-reference the instruction targeted (e.g. 'nytt pkt. a', 'annet ledd'),
    empty for whole-provision ops.
    """
    text = re.sub(r"[ \t]+", " ", text)
    ops = []
    for m in _SET.finditer(text):
        ops.append({
            "paragraf": m.group(1).replace(" ", ""),
            "subunit": " ".join(m.group(2).split()),
            "action": "set",
            "new_text": " ".join(m.group(3).split()),
        })
    for m in _REPEAL.finditer(text):
        ops.append({
            "paragraf": m.group(1).replace(" ", ""),
            "subunit": " ".join(m.group(2).split()),
            "action": "repeal",
            "new_text": None,
        })
    return ops


def apply_amendments(base, ops):
    """Apply parsed ops to a base document (dict paragraf -> text).

    NOTE: only whole-provision ops (empty subunit) are applied structurally here;
    ops carrying a `subunit` are returned in `deferred` rather than applied
    destructively, because sub-provision editing needs ledd/punktum granularity
    not yet implemented. This avoids the failure mode where "§4 pkt.b oppheves"
    wrongly deletes all of §4.
    """
    doc = dict(base)
    deferred = []
    for op in ops:
        if op["subunit"]:
            deferred.append(op)
            continue
        if op["action"] == "set":
            doc[op["paragraf"]] = op["new_text"]
        elif op["action"] == "repeal":
            doc.pop(op["paragraf"], None)
    return doc, deferred


if __name__ == "__main__":
    # Real block extracted from NB Lovtidend 1991 Nr. 3 (studentopptak reglement).
    block = (
        "§ 4 Søknadsfrister nytt pkt. a skal lyde:\n"
        "Som hovedregel settes søknadsfristen for alle høgskoler og alle "
        "studieretninger til 15. april for opptak til høstsemesteret.\n"
        "§ 4 pkt. b oppheves.\n"
        "Endringene trer i kraft straks."
    )
    ops = parse_amendments(block)
    for o in ops:
        print(o["paragraf"], o["action"], "| subunit:", repr(o["subunit"]),
              "| ->", (o["new_text"][:60] + "...") if o["new_text"] else "")
    doc, deferred = apply_amendments({"§4": "(tidligere ordlyd)"}, ops)
    print("applied whole-provision ops; deferred sub-provision ops:", len(deferred))
