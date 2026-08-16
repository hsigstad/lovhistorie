"""Ledd-level op engine — apply sub-provision amendments (the corpus majority).

INTENT: apply `§ X <ordinal> ledd skal lyde / nytt <ordinal> ledd skal lyde /
    <ordinal> ledd oppheves`, and `<ordinal> ledd <ordinal>/siste punktum skal lyde`,
    to a provision, deterministically, returning the rebuilt provision text — or
    None when it cannot resolve the address cleanly (so replay FLAGS it rather than
    fabricating; goal.md flag-don't-fabricate rule).
REASONING: the structured LTI enactment base (build_enactment.parse_lovdata_xml)
    serialises a provision as `title \n ledd1 \n ledd2 …` (one physical line per
    top-level ledd, title on line 0). We split on "\n", address the ledd BY POSITION
    (Norwegian ordinal → 1-based index), edit it, and re-serialise the other ledd
    unchanged. Two legacy fallbacks keep older bases working: a provision numbered
    inline `(1) … (2) …` (split on the markers) and a single unnumbered blob (whole
    text = ledd 1, so any multi-ledd address flags).
ASSUMES: the instruction carries a Norwegian ordinal ("andre", "syvende", "siste")
    + an action verb; new_text is the replacement/insert body (for skal-lyde / nytt).
    Bokstav/nr list items ("bokstav b", "nr. 7") ARE resolved once the base preserves
    their `a) b) c)` / `1. 2. 3.` markers (build_enactment injects them from the XML
    data-li-identifier attributes). We split the addressed ledd on those markers,
    validate the marker run is a clean consecutive sequence (else flag), and edit the
    addressed item — recursing for nested addresses ("ledd nr. 7 bokstav b",
    "ledd nr. 7 tredje punktum"). Multi-ledd range/pair inserts ("nytt tredje til
    sjette ledd skal lyde") split the new_text on its own (N) markers and insert.
    Anything that cannot be split cleanly returns None (flag), never a guessed blob.
"""
from __future__ import annotations

import re

ORDINALS = {
    "første": 1, "andre": 2, "annet": 2, "tredje": 3, "fjerde": 4, "femte": 5,
    "sjette": 6, "syvende": 7, "sjuende": 7, "åttende": 8, "niende": 9, "tiende": 10,
    "ellevte": 11, "tolvte": 12,
}
_LEDD = re.compile(r"\((\d+)\)\s*")          # inline ledd marker "(1) "
_NUM_MARK = re.compile(r"^\s*\((\d+)\)\s*")  # leading "(N) " on a ledd line

# list-item markers as flattened into a ledd line by build_enactment (identifier +
# space): nr points "1. " / "1) ", bokstav items "a) ". Matched only at a token
# boundary (start-of-string or after whitespace) and only when followed by whitespace,
# so an in-body "§ 2-2." or "artikkel 37" never reads as a marker.
_NR_MARK = re.compile(r"(?:(?<=\s)|^)(\d+)([.)])(?=\s)")
_BOK_MARK = re.compile(r"(?:(?<=\s)|^)([a-zæøå])(\))(?=\s)", re.I)
# a leading marker on an amendment's new_text body, dropped before re-inserting it
# (the marker is re-attached from the address, never doubled).
_LEAD_MARK = re.compile(r"^\s*(?:\(\d+\)|\d+[.)]|[a-zæøå]\))\s+", re.I)
# multi-ledd range/pair insert: "nytt tredje til sjette ledd" / "nytt tredje og fjerde ledd"
_RANGE = re.compile(r"ny(?:tt|e)?\s+(\w+)\s+(til|og)\s+(\w+)\s+ledd", re.I)


# ---------------------------------------------------------------------------
# addressing: pull the ledd/punktum ordinal + the action verb from an instruction
# ---------------------------------------------------------------------------
def _ordinal_before(instr, unit):
    """The ordinal (1-based) that qualifies `unit` ("ledd"/"punktum"), or None.
    Matches '<ordinal> <unit>' and 'siste <unit>' (-> sentinel -1 = last)."""
    if re.search(rf"\bsiste\s+{unit}\b", instr):
        return -1
    for word, n in ORDINALS.items():
        if re.search(rf"\b{word}\s+{unit}\b", instr):
            return n
    return None


def _ordinal(instr):
    return _ordinal_before(instr, "ledd")


def _action(instr):
    # insert must be tested before replace: "nytt <ord> ledd skal lyde" is an insert
    if re.search(r"\b(?:nytt|ny|nye|nytt)\b", instr) and "skal lyde" in instr:
        return "insert"
    if "oppheves" in instr:
        return "repeal"
    if "skal lyde" in instr:
        return "replace"
    return None


# ---------------------------------------------------------------------------
# provision <-> (title, [ledd]) model
# ---------------------------------------------------------------------------
def split_ledd(text):
    """Legacy public helper: split a '(1) … (2) …' provision into [(n, ledd_text)];
    [] if there are no inline markers. Kept for backward compatibility."""
    parts = _LEDD.split(text)
    if len(parts) < 3:
        return []
    out = []
    for i in range(1, len(parts) - 1, 2):
        out.append((int(parts[i]), parts[i + 1].strip()))
    return out


def _parse(text):
    """Return (title, ledd_list, mode). ledd_list is 1-based by POSITION.
    mode: 'nl' structured newline base | 'num' inline (n) markers | 'blob' single."""
    if "\n" in text:
        parts = text.split("\n")
        return parts[0], parts[1:], "nl"
    segs = _LEDD.split(text)
    if len(segs) >= 3:                       # inline "(1) … (2) …"
        title = segs[0].strip()
        ledd = [segs[i + 1].strip() for i in range(1, len(segs) - 1, 2)]
        return title, ledd, "num"
    return "", [text], "blob"                # single unnumbered blob


def _renumber(ledd):
    """After insert/repeal, rewrite leading '(N)' markers to match new positions
    (only ledd that already carry a marker — unnumbered ledd are left untouched)."""
    out = []
    for i, t in enumerate(ledd, start=1):
        m = _NUM_MARK.match(t)
        out.append(f"({i}) " + t[m.end():] if m else t)
    return out


def _serialize(title, ledd, mode):
    if mode == "nl":
        return "\n".join([title] + ledd)
    # 'num': re-attach inline "(i)" markers by position (they were the split
    # delimiters, so they are not part of the stored ledd bodies).
    body = " ".join(f"({i}) {t}" for i, t in enumerate(ledd, start=1))
    return (title + " " + body).strip() if title else body


# ---------------------------------------------------------------------------
# conservative punktum (sentence) splitting within one ledd
# ---------------------------------------------------------------------------
# Do NOT treat these as sentence ends: common Norwegian legal abbreviations and a
# bare "§ 5." reference. If a ledd cannot be split unambiguously we return None.
_ABBR = re.compile(
    r"(?:jf|jfr|kfr|nr|mv|m\.v|pkt|f\.eks|bl\.a|osv|ca|evt|flg|jftr|§\s*\d+[a-z]?)$",
    re.I)


def _split_punktum(body):
    """Split a ledd body into sentences on '. ' boundaries, keeping the period,
    but never after a known abbreviation. Returns the list of punktum."""
    out, start = [], 0
    for m in re.finditer(r"\.\s+", body):
        head = body[start:m.start()]
        # skip boundary if the token just before the '.' is an abbreviation
        last = re.search(r"(\S+)$", head)
        if last and _ABBR.search(last.group(1) + "."):
            continue
        # skip if what follows does not look like a sentence start (lowercase word)
        nxt = body[m.end():m.end() + 1]
        if nxt and nxt.islower():
            continue
        out.append(body[start:m.end()].strip())
        start = m.end()
    tail = body[start:].strip()
    if tail:
        out.append(tail)
    return out


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------
def apply(provision_text, instruction, new_text):
    """Return rebuilt provision text, or None if the address can't be resolved
    cleanly (-> replay flags it). None-means-flag contract; do not fabricate."""
    instr = instruction or ""
    has_punktum = bool(re.search(r"\bpunktum\b", instr))
    has_bokstav = bool(re.search(r"\bbokstav\b", instr))
    has_nr = bool(re.search(r"\bnr\.?\b", instr))

    n = _ordinal(instr)
    act = _action(instr)

    title, ledd, mode = _parse(provision_text)

    # An unstructured blob (no ledd boundaries knowable) cannot be addressed at
    # ledd/punktum granularity without risking dropping the rest of the provision
    # -> flag (do not fabricate). Structured (nl) and inline-numbered (num) bases
    # have real boundaries and are handled below.
    if mode == "blob":
        return None

    # -- multi-ledd range/pair insert ("nytt tredje til sjette ledd skal lyde") --
    # detected before the single-ledd path (whose "sjette ledd" ordinal would misfire).
    if "skal lyde" in instr and not has_nr and not has_bokstav and _RANGE.search(instr):
        return _apply_multiledd(title, ledd, mode, instr, new_text)

    # -- bokstav/nr sub-list items (now that the base preserves their markers) ----
    if has_bokstav or has_nr:
        return _apply_sublist(title, ledd, mode, n, instr, act, new_text)

    if not act:
        return None

    # -- punktum-within-ledd (no bokstav/nr) ------------------------------------
    if has_punktum:
        return _apply_punktum(title, ledd, mode, n, instr, act, new_text)

    # -- pure ledd --------------------------------------------------------------
    # resolve ledd position
    if n is None:
        if act == "insert":
            n = len(ledd) + 1            # "nytt ledd" with no ordinal -> append
        elif len(ledd) == 1:
            n = 1                        # single-ledd provision, unambiguous
        else:
            return None                  # ambiguous which ledd
    if n == -1:                          # "siste ledd"
        n = len(ledd) if act != "insert" else len(ledd) + 1

    if act == "replace":
        if not new_text:                 # empty new_text is a parse artifact -> flag
            return None
        from source.parse import align
        tgt = align.target_ledd(ledd, new_text, ordinal=n)
        if tgt["already_applied"]:
            return provision_text        # IDEMPOTENCY: already applied -> SKIP (no double-apply)
        # ADDRESS the ledd by CONTENT first (align), then the ordinal. Content-first is what
        # makes the ordinal's version-dependence harmless: a "syvende ledd" op whose provision
        # now has 3 ledds (an earlier repeal shortened it) is out of ordinal range, but its new
        # wording still matches the right ledd. Only if the content match is ambiguous do we use
        # the ordinal, which must then be in range; else flag (never guess).
        if tgt["matched"] and tgt["index"] is not None:
            idx = tgt["index"]
        elif 1 <= n <= len(ledd):
            idx = n - 1
        else:
            return None                  # neither a confident content match nor a valid ordinal
        ledd = list(ledd)
        old = ledd[idx]
        pm = _NUM_MARK.match(old)
        keep = pm.group(0) if (pm and not _NUM_MARK.match(new_text)) else ""
        ledd[idx] = keep + " ".join(new_text.split())
        return _serialize(title, ledd, mode)

    if act == "insert":
        if not new_text or not (1 <= n <= len(ledd) + 1):
            return None
        # IDEMPOTENCY (align): if a ledd already equals the inserted text, the insert is
        # already applied (whole-provision rebuild baked it in) -> no-op, don't duplicate it.
        from source.parse import align
        if align.target_ledd(ledd, new_text)["already_applied"]:
            return provision_text        # already inserted -> SKIP
        ledd = list(ledd)
        ledd.insert(n - 1, " ".join(new_text.split()))
        return _serialize(title, _renumber(ledd), mode)

    if act == "repeal":
        if not (1 <= n <= len(ledd)):
            return None
        ledd = [t for i, t in enumerate(ledd, start=1) if i != n]
        return _serialize(title, _renumber(ledd), mode)

    return None


# ---------------------------------------------------------------------------
# bokstav / nr sub-list addressing (recursive within one ledd body)
# ---------------------------------------------------------------------------
def _address_path(instr):
    """Sub-ledd address AFTER the ledd level, in the order the tokens appear:
    a list of (level, key) with level ∈ {nr, bokstav, punktum}. Empty -> whole ledd."""
    toks = []
    for m in re.finditer(r"\bnr\.?\s*(\d+)", instr):
        toks.append((m.start(), "nr", int(m.group(1))))
    for m in re.finditer(r"\bbokstav\s+([a-zæøå])\b", instr, re.I):
        toks.append((m.start(), "bokstav", m.group(1).lower()))
    if re.search(r"\bsiste\s+punktum\b", instr):
        toks.append((re.search(r"\bsiste\s+punktum\b", instr).start(), "punktum", -1))
    for word, k in ORDINALS.items():
        for m in re.finditer(rf"\b{word}\s+punktum\b", instr):
            toks.append((m.start(), "punktum", k))
    toks.sort()
    return [(lvl, key) for _, lvl, key in toks]


def _split_marked(body, lvl):
    """Split a ledd/item body into (lead_text, [[label, sep, text], …]) on nr/bokstav
    markers. Returns None if there are no markers or the marker run is not a clean
    consecutive sequence (1,2,3… / a,b,c…) — the anti-fabrication guard: if we cannot
    be sure the split is the real list, we refuse rather than edit the wrong span."""
    mre = _NR_MARK if lvl == "nr" else _BOK_MARK
    ms = list(mre.finditer(body))
    if not ms:
        return None
    lead = body[:ms[0].start()].strip()
    items = []
    for i, m in enumerate(ms):
        e = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        items.append([m.group(1), m.group(2), body[m.end():e].strip()])
    # sequence must be consecutive from 1 / 'a'
    if lvl == "nr":
        try:
            nums = [int(it[0]) for it in items]
        except ValueError:
            return None
        if nums != list(range(1, len(nums) + 1)):
            return None
    else:
        labs = [it[0].lower() for it in items]
        if labs != [chr(ord("a") + i) for i in range(len(labs))]:
            return None
    return lead, items


def _join_marked(lead, items):
    parts = [lead] if lead else []
    for lab, sep, txt in items:
        parts.append(f"{lab}{sep} {txt}")
    return " ".join(parts).strip()


def _relabel(items, lvl):
    for i, it in enumerate(items):
        it[0] = str(i + 1) if lvl == "nr" else chr(ord("a") + i)


def _find_idx(items, lvl, key):
    for i, it in enumerate(items):
        if lvl == "nr" and int(it[0]) == key:
            return i
        if lvl == "bokstav" and it[0].lower() == key:
            return i
    return None


def _edit_body(body, path, act, new):
    """Recursively descend `path` into a ledd body and apply `act`. Returns the rebuilt
    body, or None on any ambiguity (bad split, missing target, out-of-range index)."""
    lvl, key = path[0]
    rest = path[1:]

    if lvl in ("nr", "bokstav"):
        split = _split_marked(body, lvl)
        if not split:
            return None
        lead, items = split
        idx = _find_idx(items, lvl, key)
        if rest:                                    # descend into the addressed item
            if idx is None:
                return None
            sub = _edit_body(items[idx][2], rest, act, new)
            if sub is None:
                return None
            items[idx][2] = sub
            return _join_marked(lead, items)
        if act == "replace":
            if idx is None:
                return None
            items[idx][2] = _LEAD_MARK.sub("", " ".join((new or "").split()))
            return _join_marked(lead, items)
        if act == "insert":
            sep = ")" if lvl == "bokstav" else "."
            lab = key if lvl == "bokstav" else str(key)
            pos = (ord(key) - ord("a")) if lvl == "bokstav" else (key - 1)
            pos = min(max(pos, 0), len(items))
            items.insert(pos, [lab, sep, _LEAD_MARK.sub("", " ".join((new or "").split()))])
            _relabel(items, lvl)
            return _join_marked(lead, items)
        if act == "repeal":
            if idx is None:
                return None
            items.pop(idx)
            _relabel(items, lvl)
            return _join_marked(lead, items)
        return None

    if lvl == "punktum":
        puncts = _split_punktum(body)
        if not puncts:
            return None
        p = len(puncts) if key == -1 else key
        if rest:
            if not (1 <= p <= len(puncts)):
                return None
            sub = _edit_body(puncts[p - 1], rest, act, new)
            if sub is None:
                return None
            puncts[p - 1] = sub
            return " ".join(puncts)
        if act == "replace":
            if not (1 <= p <= len(puncts)):
                return None
            puncts[p - 1] = " ".join((new or "").split())
            return " ".join(puncts)
        if act == "insert":
            if not (1 <= p <= len(puncts) + 1):
                return None
            puncts.insert(p - 1, " ".join((new or "").split()))
            return " ".join(puncts)
        return None

    return None


def _apply_sublist(title, ledd, mode, n, instr, act, new_text):
    """Edit a bokstav/nr (possibly nested with punktum) list item inside one ledd."""
    if not act:
        return None
    # combined "… og nytt nr. 6 skal lyde" replaces AND inserts in one op with a fused
    # new_text: not a single clean edit -> flag rather than mis-split.
    if re.search(r"\bog\s+ny(?:tt|e)?\b", instr):
        return None
    if n is None:                                   # no ledd ordinal
        if len(ledd) == 1:
            n = 1                                   # single ledd -> unambiguous
        else:
            return None
    if n == -1:
        n = len(ledd)
    if not (1 <= n <= len(ledd)):
        return None
    path = _address_path(instr)
    if not path:
        return None
    if act in ("replace", "insert") and not new_text:
        return None

    target = ledd[n - 1]
    pm = _NUM_MARK.match(target)
    prefix = pm.group(0) if pm else ""
    body = target[pm.end():] if pm else target
    result = _edit_body(body, path, act, new_text)
    if result is None:
        return None
    new_ledd = list(ledd)
    new_ledd[n - 1] = prefix + result
    return _serialize(title, new_ledd, mode)


def _apply_multiledd(title, ledd, mode, instr, new_text):
    """Insert a run of new ledd ("nytt tredje til sjette ledd skal lyde"). The new_text
    must carry its own (N) markers and split into EXACTLY the stated count of ledd —
    else flag (never dump the blob into one ledd)."""
    m = _RANGE.search(instr)
    if not m:
        return None
    first = ORDINALS.get(m.group(1).lower())
    last = ORDINALS.get(m.group(3).lower())
    if not first or not last or last < first:
        return None
    count = last - first + 1
    segs = _LEDD.split(new_text or "")
    if len(segs) < 3 or segs[0].strip():            # must start with a (N) marker
        return None
    nums = [int(segs[i]) for i in range(1, len(segs) - 1, 2)]
    pieces = [" ".join(segs[i + 1].split()) for i in range(1, len(segs) - 1, 2)]
    if len(pieces) != count or nums != list(range(first, last + 1)):
        return None
    pos = first - 1
    if not (0 <= pos <= len(ledd)):
        return None
    out = list(ledd)
    for k, txt in enumerate(pieces):
        out.insert(pos + k, f"({first + k}) {txt}")
    return _serialize(title, _renumber(out), mode)


def _apply_punktum(title, ledd, mode, n, instr, act, new_text):
    """Edit a punktum (sentence) inside one ledd. Conservative: flag on any
    ambiguity in resolving the ledd, the sentence split, or the punktum index."""
    # need an unambiguous ledd
    if n is None:
        if len(ledd) == 1:
            n = 1
        else:
            return None
    if n == -1:
        n = len(ledd)
    if not (1 <= n <= len(ledd)):
        return None

    p = _ordinal_before(instr, "punktum")
    if p is None:
        return None                      # couldn't read the punktum ordinal
    if not new_text:
        return None                      # empty replacement -> parse artifact -> flag

    target = ledd[n - 1]
    pm = _NUM_MARK.match(target)
    prefix = pm.group(0) if pm else ""
    body = target[pm.end():] if pm else target
    puncts = _split_punktum(body)
    if len(puncts) < 2:
        return None                      # can't split reliably -> flag

    # the amendment text for a punktum sometimes repeats the ledd's own "(N)"
    # marker; drop it so we don't emit a doubled "(N) (N)" (the marker is re-added
    # once via `prefix`).
    new = re.sub(r"^\s*\(\d+\)\s*", "", " ".join(new_text.split()))

    idx = len(puncts) if p == -1 else p   # 'siste' -> last

    if act == "replace":
        if not (1 <= idx <= len(puncts)):
            return None
        puncts = list(puncts)
        puncts[idx - 1] = new
        new_ledd = list(ledd)
        new_ledd[n - 1] = prefix + " ".join(puncts)
        return _serialize(title, new_ledd, mode)

    if act == "insert":
        if not (1 <= idx <= len(puncts) + 1):
            return None
        puncts = list(puncts)
        puncts.insert(idx - 1, new)
        new_ledd = list(ledd)
        new_ledd[n - 1] = prefix + " ".join(puncts)
        return _serialize(title, new_ledd, mode)

    # punktum repeal is rare; flag rather than risk a wrong sentence removal
    return None
