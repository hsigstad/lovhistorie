"""Ledd-level op engine — apply sub-provision amendments (55% of the corpus).

INTENT: apply `§ X <ordinal> ledd skal lyde / nytt <ordinal> ledd skal lyde /
    <ordinal> ledd oppheves` etc. to a provision, deterministically, returning the
    rebuilt provision text — or None when it cannot handle the case (so replay
    FLAGS it rather than fabricating; goal.md rule).
REASONING: many modern provisions number their ledd `(1) … (2) …`; we split on
    that, edit the addressed ledd, and re-serialise. Unnumbered-ledd provisions
    (older laws, where ledd are separate paragraphs) need paragraph-preserving
    extraction — not handled yet → returns None (flag).
ASSUMES: instruction text carries a Norwegian ordinal ("andre", "fjerde", …) + an
    action verb; new_text is the replacement ledd (for skal-lyde / nytt).
"""
from __future__ import annotations

import re

ORDINALS = {
    "første": 1, "andre": 2, "annet": 2, "tredje": 3, "fjerde": 4, "femte": 5,
    "sjette": 6, "syvende": 7, "sjuende": 7, "åttende": 8, "niende": 9, "tiende": 10,
}
_LEDD = re.compile(r"\((\d+)\)\s*")


def _ordinal(instr):
    for word, n in ORDINALS.items():
        if re.search(rf"\b{word}\s+ledd\b", instr):
            return n
    return None


def _action(instr):
    if re.search(r"\bnytt\b|\bny\b|\bnye\b", instr) and "skal lyde" in instr:
        return "insert"
    if "oppheves" in instr:
        return "repeal"
    if "skal lyde" in instr:
        return "replace"
    return None


def split_ledd(text):
    """Split a provision into [(n, ledd_text)] on '(1) (2) …'; [] if unnumbered."""
    parts = _LEDD.split(text)
    if len(parts) < 3:          # no '(n)' markers -> unnumbered, cannot handle here
        return []
    out = []
    # parts = [pre, '1', body1, '2', body2, ...]
    for i in range(1, len(parts) - 1, 2):
        out.append((int(parts[i]), parts[i + 1].strip()))
    return out


def _serialize(ledd):
    return " ".join(f"({n}) {t}" for n, t in ledd)


def apply(provision_text, instruction, new_text):
    """Return rebuilt provision text, or None if the case isn't handled (-> flag).

    Handles ledd-level replace / insert / repeal on '(n)'-numbered provisions.
    Punktum/bokstav-level and unnumbered-ledd provisions return None.
    """
    instr = instruction or ""
    if re.search(r"\bpunktum\b|\bbokstav\b|\bnr\.\b", instr):
        return None                          # deeper granularity — not yet
    n = _ordinal(instr)
    act = _action(instr)
    if not n or not act:
        return None
    ledd = split_ledd(provision_text)
    if not ledd:                             # unnumbered ledd — needs paragraph parse
        return None
    d = dict(ledd)
    if act == "replace":
        if n not in d or not new_text:
            return None
        d[n] = " ".join(new_text.split())
    elif act == "insert":
        if not new_text:
            return None
        shifted = {(k + 1 if k >= n else k): v for k, v in d.items()}
        shifted[n] = " ".join(new_text.split())
        d = shifted
    elif act == "repeal":
        if n not in d:
            return None
        d = {(k - 1 if k > n else k): v for k, v in d.items() if k != n}
    return _serialize(sorted(d.items()))
