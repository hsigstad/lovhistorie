"""Parse Norwegian endringslov (amendment) instructions and replay them.

INTENT: turn the amendment instructions found in Norsk Lovtidend text into
structured ops, then apply them to a base document to reconstruct point-in-time
statutory text. Pairs with source/scrape/nb_lovtidend.py (pre-2001 text) and the
current NLOD gjeldende-lover corpus (the base / endpoint).

REASONING: Norwegian endringslover re-state the FULL new wording of each amended
provision ("§ X skal lyde: <complete new text>"), so replay is a clean overwrite
rather than a fragile diff. This is why forward replay from a base reconstructs
exact historical text.

ASSUMES / KNOWN LIMITS (validated on Lovtidend 1991 Nr. 3 and the 1999-2000 NB
gazette OCR harvest):
- Whole-provision ops ("§ X skal lyde", "§ X oppheves") parse cleanly.
- OCR of gazette text is noisy: the ":" after "skal lyde" is frequently dropped
  and the new text is broken onto the next line; sub-references are word-split
  ("anne t punktum" for "annet punktum"); a leading digit of a § number is often
  read as a letter ("§l4" for "§14"). The regexes below tolerate these.
- The amending act cites OTHER laws by full date-citation as cross-references;
  those are handled upstream in gazette.split_bodies (act boundaries), so this
  module is still given the text of a SINGLE amendment block.
- SUB-PROVISION ops are the messy minority and need finer granularity, e.g.
  "§ 4 pkt. b oppheves" repeals a *point* inside §4, and "nytt pkt. a skal lyde"
  inserts a point. The `subunit` field captures the raw sub-reference; applying
  it precisely (ledd/punktum edits) is still TODO — see the note.
- Instruction styles NOT captured as structured set/repeal (they need bespoke
  handling and are rare): "endres § X ... slik:" textual micro-edits ("ordet
  «eller» går ut"); and § numbers so garbled OCR leaves no recoverable number
  ("§s—l", "§lO 4"). Such blocks still yield a best-effort headless op via the
  last-resort "skal lyde" fallback so they are not silently dropped.
"""
import re


def _norm_para(p):
    """Normalise a captured § reference: strip spaces, fix common OCR of the
    leading digit ('§l4' -> '§14'), and use ASCII hyphen for ranged numbers."""
    p = re.sub(r"\s+", "", p)
    p = re.sub(r"^§[lI](?=\d)", "§1", p)  # OCR: leading '1' read as 'l'/'I'
    p = p.replace("—", "-")
    return p


# OCR word-splits seen inside sub-references; rejoin so the subunit reads cleanly.
_OCR_SUBSPLITS = [
    (r"\banne\s+t\b", "annet"), (r"\bførs\s+te\b", "første"),
    (r"\btredj\s+e\b", "tredje"), (r"\bfjerd\s+e\b", "fjerde"),
    (r"\bfemt\s+e\b", "femte"),
]


def _norm_subunit(s):
    """Collapse whitespace in a sub-reference and repair common OCR word-splits.
    Never allowed to swallow the new text — callers pass only the pre-'skal lyde'
    span."""
    s = " ".join(s.split())
    for pat, rep in _OCR_SUBSPLITS:
        s = re.sub(pat, rep, s)
    return s


def _clean_newtext(t):
    """Normalise whitespace and strip stray OCR page separators ('/', '///')."""
    t = " ".join(t.split())
    t = re.sub(r"^\s*/+\s*", "", t)
    t = re.sub(r"\s*/+\s*$", "", t)
    return t.strip()


# A § reference, tolerating: leading-digit OCR ('§l4'), ranged numbers ('§ 9-8'),
# and a trailing provision letter ('§ 8 A', '§ 58 a') — but NOT the first letter
# of a following word (negative lookahead), so "§ 23 nr. 1" stays paragraf "§23".
_PARA_CORE = r"§\s*[lI]?\d+(?:\s*[-—]\s*\d+)?(?:\s*[A-Za-z](?![^\W\d_]))?"

# A 'skal lyde' new_text ends at the next §, the next 'Ny/Nytt/Nye §|kapittel',
# an ikrafttredelse clause ('Endring…', 'trer i kraft'), a repeal, a romertall
# section break on its own line, or end of block.
_TERM = (
    r"(?="
    r"§\s*[lI]?\d"
    r"|\n\s*(?:Ny|Nytt|Nye)\s+(?:§|kapittel|paragraf)"
    r"|Endring"                 # Endringene / Endringa / Endring … trer i kraft
    r"|trer\s+i\s+kraft"
    r"|oppheves"
    r"|\n\s*[IVX]{1,4}\.?\s*\n"  # 'II' / 'III' / 'IV' … romertall section break
    r"|$)"
)

# "§ X <subunit> skal lyde[:] <new text>" — colon optional, newline before text
# tolerated. subunit stays on the same line as the instruction (no newline, no §).
_SET = re.compile(
    r"(" + _PARA_CORE + r")([^\n:§]*?)skal\s+lyde\s*:?\s*\n?\s*(.+?)" + _TERM, re.S)

# Inverted phrasing "… skal § X <subunit> lyde[:] <new text>" (the OCR reflow can
# break the subunit across a line, so newlines are allowed up to 'lyde').
_SET_INV = re.compile(
    r"skal\s+(" + _PARA_CORE + r")([^:§]*?)\s+lyde\b\s*:?\s*\n?\s*(.+?)" + _TERM,
    re.S)

# "Nytt/Ny/Nye kapittel <id> skal lyde[:] <new text>" — a whole new chapter; its
# body naturally contains §s, so it terminates only at ikrafttredelse/romertall.
_NEWCHAP = re.compile(
    r"(?:Nytt|Ny|Nye)\s+kapittel\s+([^\n:§]*?)\s*skal\s+lyde\s*:?\s*\n?\s*(.+?)"
    r"(?=Endring|trer\s+i\s+kraft|\n\s*[IVX]{1,4}\.?\s*\n|$)", re.I | re.S)

_REPEAL = re.compile(r"(" + _PARA_CORE + r")([^\n:§]*?)oppheves")

# Whole-LAW repeal: "Lov <date> nr. N … oppheves" (no § — the entire act is lifted).
_WHOLELAW = re.compile(
    r"\bLov\s+\d{1,2}\.\s*\w+.*?\bnr\.?\s*\d+.*?\boppheves\b", re.S | re.I)

# Last-resort headless "… skal lyde[:] <new text>": catches instructions whose
# unit reference is not a recoverable § (romertall sections, "overgangsregel …",
# or § numbers destroyed by OCR). Used only when nothing else matched.
_ANY_SET = re.compile(r"([^\n]*?)\bskal\s+lyde\b\s*:?\s*\n?\s*(.+?)" + _TERM, re.S)


def parse_amendments(text):
    """Yield dicts: {paragraf, subunit, action, new_text}.

    action is 'set' (skal lyde / new provision / new chapter) or 'repeal'
    (oppheves). `subunit` holds any sub-reference the instruction targeted (e.g.
    'nytt pkt. a', 'annet ledd'), empty for whole-provision ops. `paragraf` is
    '' for whole-law repeals and for headless/unrecoverable-§ fallbacks.
    """
    text = re.sub(r"[ \t]+", " ", text)
    ops = []
    for m in _SET.finditer(text):
        nt = _clean_newtext(m.group(3))
        if nt:
            ops.append({"paragraf": _norm_para(m.group(1)),
                        "subunit": _norm_subunit(m.group(2)),
                        "action": "set", "new_text": nt})
    for m in _SET_INV.finditer(text):
        nt = _clean_newtext(m.group(3))
        if nt:
            ops.append({"paragraf": _norm_para(m.group(1)),
                        "subunit": _norm_subunit(m.group(2)),
                        "action": "set", "new_text": nt})
    for m in _NEWCHAP.finditer(text):
        nt = _clean_newtext(m.group(2))
        if not nt:
            continue
        pm = re.search(_PARA_CORE, m.group(2))
        ops.append({"paragraf": _norm_para(pm.group(0)) if pm else "",
                    "subunit": _norm_subunit("kapittel " + m.group(1)),
                    "action": "set", "new_text": nt})
    for m in _REPEAL.finditer(text):
        ops.append({"paragraf": _norm_para(m.group(1)),
                    "subunit": _norm_subunit(m.group(2)),
                    "action": "repeal", "new_text": None})
    if not ops and _WHOLELAW.search(text):
        ops.append({"paragraf": "", "subunit": "hele loven",
                    "action": "repeal", "new_text": None})
    if not ops:
        m = _ANY_SET.search(text)
        if m:
            nt = _clean_newtext(m.group(2))
            if nt:
                pm = re.search(_PARA_CORE, m.group(1))
                ops.append({"paragraf": _norm_para(pm.group(0)) if pm else "",
                            "subunit": _norm_subunit(m.group(1))[:120],
                            "action": "set", "new_text": nt})
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
