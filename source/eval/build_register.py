"""Build the amendment REGISTER — Lovdata's own provenance of which act amended which
provision of which law — from the NLOD current dump (`data/current/`).

INTENT: a machine-readable index of amendment edges `(amending_act -> target_law, provision,
    change_type)` as recorded by Lovdata in the consolidated text's `changesToParent`
    annotations ("Endret/Tilføyd/Opphevet ved lov <cite> (ikr. … iflg. res. …)"). This is
    the ORACLE view of the amendment graph: it says, per still-in-force provision, exactly
    which acts touched it. Two uses: (1) VALIDATION ground truth for reconstruction capture
    — `register_gaps` diffs our parsed streams against it and reports missed amending acts
    per law (e.g. avtaleloven captures 4 of 17 acts); (2) a QA target-resolution table that
    tells us WHICH omnibus acts still need their secondary-law sections recovered from the
    public act text.

ANTI-GAMING (lessons_and_pitfalls #7): this READS `data/current/` — the consolidated answer
    key — so it lives under source/eval/ and is EVAL-ONLY. The register MUST NOT be read by
    any reconstruction / base-build / target-resolution path: resolving an omnibus act's
    targets from this file would be reading the answer key. The legitimate fix path re-parses
    targets from the public ACT text in `data/lti/` (see source/scrape/lti_amendments.py);
    the register only tells us where to look and scores the result. The OUTPUT is derived
    solely from public-domain NLOD text, so it is itself publishable, but it is gitignored
    with the rest of `data/current`-derived material and travels as an eval artifact.

SCOPE / LIMITS: `changesToParent` records history only for text CURRENTLY in force — a
    provision added then repealed loses its trail, and fully-repealed laws are absent. So the
    register is a FLOOR on amendment counts, not the complete history. Multi-act blocks
    ("Endret ved lover A, B, C (ikr. … )") bind the trailing ikr/res clause to the LAST act
    only; earlier acts in the block get null in-force (they had their own, at their own time).

STRUCTURE: each `<article class="changesToParent">` sits inside the `legalArticle` / `legalP`
    / `section` it annotates; the nearest enclosing `data-lovdata-URL="NL/lov/<id>/<prov>"`
    gives (target_law, provision). The block text carries the verb, one or more
    `<a href="lov/<id>">` amending acts, and an optional `(ikr. <date> iflg. res. <cite>)`
    tail whose `href="forskrift/<id>"` is the source_ref.
"""
from __future__ import annotations

import glob
import gzip
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
CURRENT_DIR = HERE / "data" / "current"
OUT_JSONL = HERE / "data" / "amendment_register.jsonl.gz"
OUT_INDEX = HERE / "data" / "register_index.json"

_VERB = {
    "endret": "change", "endra": "change", "endres": "change",
    "tilføyd": "add", "tilføyd": "add", "nytt": "add", "ny": "add",
    "opphevet": "repeal", "oppheva": "repeal",
}
_ACT_HREF = re.compile(r'href="lov/([0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]+)"')
_RES_HREF = re.compile(r'href="forskrift/([0-9]{4}-[0-9]{2}-[0-9]+)"')
_LOVDATA_URL = re.compile(r'data-lovdata-URL="NL/lov/([0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]+)(?:/([^"]+))?"')
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S)
_BLOCK = re.compile(r'<article class="changesToParent">(.*?)</article>', re.S)
_IKR = re.compile(r"ikr\.?\s*([0-9]{1,2}\.?\s*\w+\.?\s*[0-9]{4}[^)]*)", re.I)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def _law_id_from_name(path: str) -> str | None:
    m = re.search(r"nl-(\d{4})(\d{2})(\d{2})-0*(\d+)", Path(path).name)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"


def _verb_of(block_text: str) -> str:
    w = block_text.strip().split()
    for tok in w[:3]:
        v = _VERB.get(tok.lower().strip(".,:"))
        if v:
            return v
    return "change"


def _split_acts_with_ikr(block_html: str):
    """Yield (act_id, source_ref | None, in_force_raw | None). The optional (ikr…iflg.res…)
    parenthetical binds to the act href immediately preceding it; a res href inside it is the
    source_ref for that act."""
    # Segment on top-level parentheticals so each ikr clause stays with its preceding act.
    out = []
    # find act hrefs and parenthetical spans in order
    tokens = []  # (pos, kind, payload)
    for m in _ACT_HREF.finditer(block_html):
        tokens.append((m.start(), "act", m.group(1)))
    for m in re.finditer(r"\(([^()]*(?:ikr|iflg|res)[^()]*)\)", block_html, re.I):
        tokens.append((m.start(), "paren", m.group(0)))
    tokens.sort()
    pending = []
    for _, kind, payload in tokens:
        if kind == "act":
            pending.append(payload)
        else:  # paren binds to the last act seen
            if not pending:
                continue
            act = pending[-1]
            res = _RES_HREF.search(payload)
            ikr = _IKR.search(payload)
            out.append((act, res.group(1) if res else None,
                        _text(ikr.group(1)) if ikr else None))
            # earlier pending acts (before this paren) get emitted with no ikr
            for a in pending[:-1]:
                out.append((a, None, None))
            pending = []
    for a in pending:  # trailing acts with no paren
        out.append((a, None, None))
    # de-dup preserving first (act may repeat if href appears twice)
    seen, dedup = set(), []
    for a, r, i in out:
        if a in seen:
            continue
        seen.add(a)
        dedup.append((a, r, i))
    return dedup


def _title_map() -> dict[str, str]:
    m = {}
    for f in glob.glob(str(CURRENT_DIR / "*.xml")):
        lid = _law_id_from_name(f)
        if not lid:
            continue
        try:
            head = open(f, encoding="utf-8").read(4000)
        except OSError:
            continue
        t = _TITLE.search(head)
        if t:
            m[lid] = _text(t.group(1))
    return m


def build():
    titles = _title_map()
    rows = []
    for f in sorted(glob.glob(str(CURRENT_DIR / "*.xml"))):
        target_law = _law_id_from_name(f)
        if not target_law:
            continue
        html = open(f, encoding="utf-8").read()
        # positions of every provision anchor, to locate the enclosing provision of a block
        anchors = [(m.start(), m.group(1), m.group(2)) for m in _LOVDATA_URL.finditer(html)]
        for bm in _BLOCK.finditer(html):
            block_html = bm.group(1)
            btxt = _text(block_html)
            verb = _verb_of(btxt)
            # nearest preceding provision anchor whose law == target_law
            prov = None
            for pos, lid, p in reversed(anchors):
                if pos < bm.start() and lid == target_law:
                    prov = p
                    break
            for act, source_ref, in_force in _split_acts_with_ikr(block_html):
                if act == target_law:
                    continue  # self-reference / enactment note
                rows.append({
                    "act_id": f"lov/{act}",
                    "act_title": titles.get(act),
                    "act_date": act,                     # datokode == passage date
                    "target_law": f"lov/{target_law}",
                    "target_law_title": titles.get(target_law),
                    "provision": prov,                   # None => whole-law / chapter level
                    "change_type": verb,
                    "verb_raw": btxt[:40],
                    "in_force": in_force,
                    "source_ref": f"forskrift/{source_ref}" if source_ref else None,
                    "provenance": "nlod-current",
                })
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT_JSONL, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # act-level index: act -> {title, affected_laws, n_ops, first/last target date}
    idx: dict[str, dict] = {}
    for r in rows:
        a = r["act_id"]
        e = idx.setdefault(a, {"act_title": r["act_title"], "affected_laws": {}, "n_ops": 0})
        e["n_ops"] += 1
        e["affected_laws"].setdefault(r["target_law"], 0)
        e["affected_laws"][r["target_law"]] += 1
    index_out = {
        a: {"act_title": e["act_title"],
            "n_laws": len(e["affected_laws"]),
            "n_ops": e["n_ops"],
            "affected_laws": sorted(e["affected_laws"])}
        for a, e in idx.items()
    }
    OUT_INDEX.write_text(json.dumps(index_out, ensure_ascii=False, indent=1), encoding="utf-8")

    multi = sum(1 for e in index_out.values() if e["n_laws"] > 1)
    print(f"register: {len(rows)} edges | {len(index_out)} amending acts "
          f"({multi} multi-law) | {len({r['target_law'] for r in rows})} target laws")
    print(f"  -> {OUT_JSONL.relative_to(HERE)}")
    print(f"  -> {OUT_INDEX.relative_to(HERE)}")


if __name__ == "__main__":
    build()
