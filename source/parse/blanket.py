"""Blanket terminology-reform parser — the pre-2001/omnibus lever the ledd path is NOT.

INTENT: capture reforms that rename a term across a law without a per-provision "§X skal
    lyde" op — "(I følgende bestemmelser skal) ordet/uttrykket «A» endres til «B»", "endres
    «A» til «B»", "«A» erstattes med «B»". These modernizations (e.g. skifteretten→tingretten,
    an agency rename) leave many provisions stuck at their old wording (loss_breakdown's
    uncaptured/mis-attributed tail; avtaleloven §38 class).
REASONING: the term pair sits in «guillemets» — a RELIABLE delimiter, so a regex is the right
    tool (not a fragile judgment). We deliberately DROP the fragile "§§ 10 første ledd, 19 …"
    scope list: term A is specific, so applying A→B to every provision of the target law that
    CONTAINS A reproduces the listed scope without parsing it. The op is attributed to its
    target-law block via the same `I lov <cite>` split as the amendment extractor.
ASSUMES: LTI act text (tags stripped). Application is a deterministic str.replace of a
    source-specified term — every character still traces to a public-domain source (the base,
    or B from the reform act), so no fabrication.
"""
from __future__ import annotations

import re

# term-pair forms, all delimited by «»: "ordet/uttrykket «A» endres til «B»",
# "endres «A» til «B»", "«A» erstattes med «B»". Case-insensitive on the connective words.
_FORMS = [
    re.compile(r"(?:ordet|uttrykket|uttrykkene|betegnelsen)\s+«([^»]+)»\s+endres?\s+til\s+«([^»]+)»", re.I),
    re.compile(r"\bendres?\s+«([^»]+)»\s+til\s+«([^»]+)»", re.I),
    re.compile(r"«([^»]+)»\s+erstattes?\s+med\s+«([^»]+)»", re.I),
]


def extract_reforms(act_datokode: str, act_text: str):
    """[{target_law, term_old, term_new, change_type, date_*}] — one law-level term-reform op
    per (target-law block × term pair). Applied in pipeline.reconstruct as a str.replace over
    the law's provisions that contain term_old. Deduped on (target_law, old, new)."""
    from source.llm import target_localize        # format-agnostic per-law section localizer
    y, m, d = act_datokode[:4], act_datokode[5:7], act_datokode[8:10]
    act_date = f"{y}-{m}-{d}"
    from source.parse import inforce
    resolved = inforce.resolved_date(act_datokode) or act_date
    out, seen = [], set()
    sections, _ = target_localize.localize(act_text)
    for target_dk, sec in sections:
        for rx in _FORMS:
            for mm in rx.finditer(sec):
                old, new = mm.group(1).strip(), mm.group(2).strip()
                # skip § cross-reference renumbers ("«§ 54» til «§ 70»") — those are structural
                # id-remaps, not terminology; handled by the renumber/align path, not here.
                if old.startswith("§") or not old or old == new:
                    continue
                key = (target_dk, old, new)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "act_refid": f"lov/{act_datokode}",
                    "target_law": f"lov/{target_dk}",
                    "term_old": old, "term_new": new,
                    "change_type": "term_replace",
                    "date_in_force_resolved": resolved, "date_in_force": act_date,
                    "source": "blanket_reform",
                })
    return out


def apply_reforms(provisions: dict, reforms: list, as_of: str | None = None):
    """Apply term-reform ops to {para: text} in date order (those in force by `as_of`).
    A str.replace of a source-specified term; a term not present in a provision is a no-op."""
    for r in sorted(reforms, key=lambda x: x.get("date_in_force_resolved") or ""):
        d = r.get("date_in_force_resolved") or r.get("date_in_force")
        if as_of and d and d > as_of:
            continue
        old, new = r["term_old"], r["term_new"]
        for p, t in provisions.items():
            if old in t:
                provisions[p] = t.replace(old, new)
    return provisions
