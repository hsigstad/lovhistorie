"""Build the PUBLIC law-identity register — the backbone list of Norwegian laws.

INTENT: emit `data/law_register.jsonl`, one entry per law IDENTITY (datokode, title,
    enactment date, type, whether we hold its enactment base, amendment count) attested
    in the public-domain gazette. This is the referential-integrity backbone the
    segmentation/`classification_qa` checks a law's identity and an amendment's target
    against. Nodes = acts we segmented (originals + amending acts) + every amendment
    TARGET (which surfaces repealed / unharvested laws by identity).
REASONING: a complete law universe turns "target unresolvable" from a coverage artifact
    into a real misattribution signal, and makes harvest coverage measurable. Sourced
    ONLY from public gazette data so the register is itself publishable.
ASSUMES: cached segmentation (`segment_issue`) for the act-index issues; zero live LLM.
ANTI-GAMING: DISTINCT from `source/eval/build_register.py` (the amendment-register
    ORACLE, current-dump-derived, eval-only). Per the 2026-08-23 oracle ruling this
    register may be read VALIDATION-SIDE only (coverage audit, target-resolution QA,
    flagging suspects) and MUST NOT drive a reconstruction decision — register flags,
    the gazette adjudicates. The NLOD current dump never populates an entry here; it is
    used only to AUDIT how much of the in-force universe we cover. Status/in-force is
    left 'unknown' pending the public NB-metadata acquisition step.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

from source.scrape.build_enactment import _act_index, TEXT_DIR
from source.llm import segment_issue

_REPO = Path(__file__).resolve().parents[2]
OUT = _REPO / "data" / "law_register.jsonl"
# Lovdata's PUBLIC in-force dataset (gjeldende-lover), extracted from the free, no-auth
# download https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2 (nightly).
# Used for IDENTITY + LIFECYCLE enrichment only (title, departement, legalArea, dateInForce)
# — this is the authoritative in-force law list. We DO NOT read `fulltext` (consolidated
# current text = answer key) or `lastChangedBy`/`lastChangeInForce` (amendment-reference =
# strong oracle); those stay eval-only. In-force only: Lovdata excludes repealed laws, so
# this completes the in-force universe but not the historical (repealed) tail.
GJELD = _REPO / "data" / "lovdata_gjeldende"


class _CacheOnly:
    """Segment from cache only — any live LLM call raises (zero-spend build)."""
    def __getattr__(self, k):
        raise RuntimeError("segmentation cache miss (live LLM blocked)")


def _title_from_amend(title: str) -> str:
    """Strip the 'om endr. i lov av <date> nr <n>' prefix to the law's own name hint."""
    t = re.sub(r"^\s*om\s+(endr(?:ing(?:er)?|\.)?|oppheving|opphevelse)\s+(i|av)\s+", "", title or "", flags=re.I)
    t = re.sub(r"^lov(?:en)?\s+(av\s+)?\d{1,2}\.?\s*\w+\s+\d{4}\s+nr\.?\s*\d+\s*", "", t, flags=re.I)
    return t.strip(" .,")


def _fn_to_datokode(name: str) -> str | None:
    m = re.match(r"nl-(\d{4})(\d{2})(\d{2})-(\d+)", name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{int(m.group(4))}" if m else None


def _dd(html: str, cls: str) -> str | None:
    """First <dd class="cls"> inner text, tags stripped (Lovdata key-info list)."""
    m = re.search(rf'<dd class="{cls}">(.*?)</dd>', html, re.S)
    if not m:
        return None
    t = re.sub(r"<[^>]+>", " ", m.group(1))
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def load_gjeldende() -> dict[str, dict]:
    """Identity+lifecycle metadata for every in-force law, from the PUBLIC Lovdata
    `gjeldende-lover` download. IDENTITY FIELDS ONLY — never fulltext / change-refs."""
    out: dict[str, dict] = {}
    if not GJELD.exists():
        return out
    for p in GJELD.glob("nl-*.xml"):
        dk = _fn_to_datokode(p.name)
        if not dk:
            continue
        html = p.read_text(encoding="utf-8", errors="ignore")
        tm = re.search(r"<title>(.*?)</title>", html, re.S)
        out[dk] = {
            "title": re.sub(r"\s+", " ", tm.group(1)).strip() if tm else None,
            "departement": _dd(html, "ministry"),
            "legal_area": _dd(html, "legalArea"),
            "date_in_force": _dd(html, "dateInForce"),
        }
    return out


def collect_acts():
    idx = _act_index()
    issues, seen = [], set()
    for _, e in idx.items():
        iid = e["issue_id"]
        if iid not in seen:
            seen.add(iid); issues.append(iid)
    acts = []
    for iid in issues:
        f = TEXT_DIR / f"{iid}.jsonl.gz"
        if not f.exists():
            continue
        try:
            pages = [json.loads(l) for l in gzip.open(f, "rt", encoding="utf-8")]
            iss, _ = segment_issue.segment(pages, doc_key=iid, client=_CacheOnly())
        except Exception:
            continue
        for a in iss:
            a["_iid"] = iid
            acts.append(a)
    return acts


def build():
    acts = collect_acts()
    reg: dict[str, dict] = {}

    def ensure(dk, enact_date=None):
        if dk not in reg:
            reg[dk] = {
                "datokode": dk,
                "title": None,
                "enactment_date": enact_date or ("-".join(dk.split("-")[:3]) if dk else None),
                "type": "unknown",       # original | amending | repeal | unknown
                "status": "unknown",     # in_force (present in Lovdata gjeldende) | unknown
                "harvested": False,      # do we hold its enactment base?
                "amend_count": 0,        # amendments in our corpus targeting it
                "departement": None,
                "legal_area": None,
                "provenance": set(),
            }
        return reg[dk]

    for a in acts:
        dk = a.get("datokode")
        klass = a.get("klass")
        if dk:
            e = ensure(dk)
            e["provenance"].add("gazette_act")
            if klass in ("amend", "repeal"):
                if e["type"] == "unknown":
                    e["type"] = "amending"
            else:
                e["type"] = "original"
                e["harvested"] = True
                e["provenance"].add("gazette_original")
                if not e["title"]:
                    e["title"] = (a.get("title") or "").strip()[:120] or None
        # the TARGET law identity (may be a law we have not harvested)
        tgt = a.get("target")
        if tgt and klass in ("amend", "repeal"):
            te = ensure(tgt)
            te["provenance"].add("amendment_target")
            te["amend_count"] += 1
            if not te["title"]:
                hint = _title_from_amend(a.get("title") or "")
                if hint:
                    te["title"] = hint[:120]

    # Enrich / extend with the public Lovdata in-force set (identity+lifecycle only).
    gj = load_gjeldende()
    for dk, meta in gj.items():
        e = ensure(dk, meta.get("date_in_force"))
        e["status"] = "in_force"
        e["provenance"].add("lovdata_gjeldende")
        if e["type"] == "unknown":
            e["type"] = "original"      # a gjeldende entry is a standalone law
        if meta.get("title"):
            e["title"] = meta["title"][:160]
        if meta.get("departement"):
            e["departement"] = meta["departement"]
        if meta.get("legal_area"):
            e["legal_area"] = meta["legal_area"]
        if meta.get("date_in_force"):
            e["enactment_date"] = e["enactment_date"] or meta["date_in_force"]

    for e in reg.values():
        e["provenance"] = sorted(e["provenance"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for dk in sorted(reg):
            fh.write(json.dumps(reg[dk], ensure_ascii=False) + "\n")
    return reg


if __name__ == "__main__":
    reg = build()
    print(f"wrote {len(reg)} law identities -> {OUT.relative_to(_REPO)}")
