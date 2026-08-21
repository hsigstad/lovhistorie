"""Generate the public point-in-time BROWSER data + landing page.

INTENT: `python -m source.site.browser` writes the data behind the public site's
    interactive statute browser — one compact JSON per dev-set law plus an index —
    and renders build/site/index.html from source/site/browser_template.html. The
    page lets anyone scrub a Norwegian statute through time, see amendment redlines,
    and compare each reconstruction against the official current text.
REASONING: same discipline as status.py/examples.py — the data is GENERATED from the
    live pipeline (reconstruct at every amendment date), never hand-authored, so it
    can't drift from the code. Data is written per-law and fetched on demand by the
    page, so the initial load stays light and adding a law is just another file.
ASSUMES: run from the repo root with the current NLOD dump present (data/current or
    $LOVHISTORIE_CURRENT_DIR) — same prerequisite as the gate. Every text emitted is
    PUBLIC-DOMAIN (reconstruction + NLOD current); NO Lovdata-Pro ground-truth text is
    written, so the output is safe to publish.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from source.eval import gate, metrics
from source.parse import pipeline

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "build" / "site"
SITE_LAWS = SITE / "laws"
# The extracted law data lives OUTSIDE build/site because sitekit wipes build/site
# on every rebuild. It is generated once (expensively) and synced into the site after
# sitekit runs — so re-rendering the page template never re-reconstructs the laws.
CACHE = ROOT / "build" / "browser_data"
TEMPLATE = Path(__file__).parent / "browser_template.html"
STATUS_JSON = ROOT / "docs" / "reference" / "status.json"

LAW_NAMES = {
    "1918-05-31-4": "avtaleloven",
    "1959-10-23-3": "oreigningslova",
    "1979-05-18-18": "foreldelsesloven",
    "1982-12-17-86": "rettsgebyrloven",
    "1986-06-20-35": "mesterbrevloven",
    "1988-05-13-27": "kjøpsloven",
    "1997-06-13-44": "aksjeloven",
    "2007-06-29-75": "verdipapirhandelloven",
    "2009-06-19-103": "tjenesteloven",
}
_MND = ["", "januar", "februar", "mars", "april", "mai", "juni", "juli",
        "august", "september", "oktober", "november", "desember"]


def _clean(t: str) -> str:
    return (t or "").lstrip(". ").strip()


def _act_label(refid: str) -> str:
    m = re.match(r"lov/(\d{4})-(\d{2})-(\d{2})-(\d+)", refid or "")
    if m:
        y, mo, d, nr = m.groups()
        return f"Lov {int(d)}. {_MND[int(mo)]} {y} nr. {nr}"
    return refid or "amendment"


def _chapter(p: str) -> str:
    m = re.match(r"§\s*(\d+)", p)
    return m.group(1) if m else "?"


def _sortkey(prov: str):
    m = re.match(r"§\s*(\d+)-(\d+)", prov)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.match(r"§\s*(\d+)", prov)
    return (int(m.group(1)) if m else 999, 0)


def extract_law(dk: str) -> dict:
    """Reconstruct one law at every amendment date; return the compact per-provision
    version history (enactment baseline + each distinct state), fidelity vs the official
    current text, and the annotation-stripped official text where it differs."""
    law = "lov/" + dk
    cur = gate.current_provisions(dk)
    if cur is None:
        raise RuntimeError(f"no current text for {dk}")
    ops = pipeline.load_ops(law)
    op_index: dict = {}
    for o in ops:
        d, p = o.get("date"), o.get("para")
        if d and p:
            op_index.setdefault((d, p), []).append(o)
    dates = sorted({o["date"] for o in ops if o.get("date")})

    snaps = [(d, pipeline.reconstruct(law, d)[0]) for d in dates]
    latest = pipeline.reconstruct(law, None)[0]
    base0 = pipeline.reconstruct(law, dk[:10])[0]     # enactment baseline

    stat = [p for p in cur if not metrics.is_convention_annex(p)]
    provisions = []
    for p in stat:
        seq = []
        for d, provs in snaps:
            t = _clean(provs.get(p, ""))
            if not seq or seq[-1]["text"] != t:
                # src = the amending act(s) that produced this version, with the gazette
                # instruction + the Norsk Lovtidend text the pipeline replayed (the source
                # behind the diff). Empty for the enactment baseline.
                src = [{"act": _act_label(o.get("act")),
                        "ins": (o.get("instruction") or "").strip(),
                        "txt": _clean(o.get("new_text") or "")}
                       for o in op_index.get((d, p), [])]
                seq.append({"date": d, "text": t, "src": src})
        seq = [v for v in seq if v["text"]] or seq
        # prepend enactment baseline only for provisions present at enactment
        b = _clean(base0.get(p, ""))
        if b:
            if not seq or seq[0]["text"] != b:
                seq = [{"date": dk[:10], "text": b, "src": []}] + seq
            else:
                seq[0]["date"] = dk[:10]
        curtext = _clean(cur.get(p, ""))
        fid = metrics.similarity(_clean(latest.get(p, "")), curtext) if curtext else 0.0
        rec = {"prov": p, "chapter": _chapter(p), "fidelity": round(fid, 3), "versions": seq}
        if fid < 0.999:
            rec["official"] = _clean(metrics.strip_annotation(curtext))
        provisions.append(rec)
    provisions.sort(key=lambda r: _sortkey(r["prov"]))
    return {"law": LAW_NAMES.get(dk, dk), "datokode": dk,
            "enacted": dk[:10], "provisions": provisions}


def build_data() -> list:
    """Extract every dev-set law that has current text into the CACHE dir; write
    <dk>.json + index.json and return the index rows (skips laws with no current dump)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    index = []
    for _, dk in gate.DEV_LAWS:
        if gate.current_provisions(dk) is None:
            print(f"  skip {dk} (no current text)", file=sys.stderr)
            continue
        print(f"  extracting {LAW_NAMES.get(dk, dk)} ({dk}) ...", flush=True)
        data = extract_law(dk)
        (CACHE / f"{dk}.json").write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        provs = data["provisions"]
        index.append({
            "datokode": dk, "law": data["law"], "enacted": dk[:10],
            "n_provisions": len(provs),
            "n_amended": sum(1 for r in provs if len(r["versions"]) > 1),
            "n_hifi": sum(1 for r in provs if r["fidelity"] >= 0.98),
            "ocr": pipeline.is_ocr_base("lov/" + dk),
        })
    index.sort(key=lambda r: -r["n_provisions"])
    (CACHE / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index


def sync_to_site(index: list) -> None:
    """Copy the cached law JSONs into build/site/laws/ and render index.html. Run AFTER
    sitekit (which wipes build/site), so the browser landing overwrites sitekit's index."""
    import shutil
    SITE_LAWS.mkdir(parents=True, exist_ok=True)
    for f in CACHE.glob("*.json"):
        shutil.copy2(f, SITE_LAWS / f.name)
    (SITE / "index.html").write_text(render_page(index, _status_brief()), encoding="utf-8")


def _status_brief() -> dict:
    try:
        d = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
        return {"convergence": d.get("convergence"), "matched": d.get("matched"),
                "total": d.get("total"), "as_of": d.get("as_of"),
                "pit": (d.get("point_in_time_summary") or {}).get("similarity_mean")}
    except (OSError, ValueError):
        return {}


def render_page(index: list, status: dict) -> str:
    tpl = TEMPLATE.read_text(encoding="utf-8")
    n_laws = len(index)
    n_prov = sum(r["n_provisions"] for r in index)
    perf = ""
    if status.get("convergence"):
        perf = (f"{status['convergence'] * 100:.0f}% of provisions on the "
                f"{n_laws}-law development set reconstruct to today's official text")
    repl = {
        "__PERF__": perf,
        "__NLAWS__": str(n_laws),
        "__NPROV__": f"{n_prov:,}",
        "__ASOF__": status.get("as_of", ""),
        "__CONV__": f"{status['convergence'] * 100:.1f}%" if status.get("convergence") else "—",
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    return tpl


def main() -> int:
    import os
    # RENDER-ONLY: re-render index.html from already-extracted laws/ data (fast; for
    # iterating on the template without re-reconstructing every law).
    if os.environ.get("LOVHISTORIE_BROWSER_RENDER_ONLY"):
        idx = CACHE / "index.json"
        if not idx.exists():
            print("browser: render-only set but cached data missing — run a full build first.",
                  file=sys.stderr)
            return 1
        index = json.loads(idx.read_text(encoding="utf-8"))
    else:
        if gate.current_provisions(gate.DEV_LAWS[0][1]) is None:
            print("browser: no current-text data found — site data not generated.", file=sys.stderr)
            print("         place the NLOD dump at data/current/ or set $LOVHISTORIE_CURRENT_DIR.",
                  file=sys.stderr)
            return 1
        print("=== Building statute-browser data (all dev laws) ===", flush=True)
        index = build_data()
    sync_to_site(index)
    print(f"browser: wrote index.html + {len(index)} law files "
          f"({sum(r['n_provisions'] for r in index)} provisions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
