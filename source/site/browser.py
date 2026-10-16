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
from source.parse import pipeline, replay as _replay, ledd_apply, blanket

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

_TITLES: dict | None = None


def _title(dk: str) -> str:
    """Short law title from the public register (lazy-loaded). Falls back to the datokode."""
    global _TITLES
    if _TITLES is None:
        from source import consume
        _TITLES = consume._titles()
    return _TITLES.get(dk) or dk


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


def _reconstruct_series(law: str, dk: str, dates: list):
    """ONE replay pass -> ([(date, provs)], latest, base0), matching pipeline.reconstruct(law, d) at
    each amendment date. A sub-provision op only touches its own provision and the op stream is
    date-sorted, so a single date-ordered pass reproduces every snapshot (validated: vphl 0/60 mismatch)
    instead of one full reconstruct per date (~15x fewer). GUARDED: if the single-pass result disagrees
    with pipeline.reconstruct at the latest + a sampled mid date (e.g. a law with undated ops out of
    list order), fall back to the exact per-date path for that law — correctness over speed."""
    base = pipeline.enactment_base(law)
    ops = pipeline.load_ops(law)
    fb = ledd_apply.make_fallback(law)
    reforms = pipeline._load_reforms(law)

    def _snap(doc, d):
        p = dict(doc)
        if reforms:
            blanket.apply_reforms(p, reforms, as_of=d)
        return p

    doc, flags, snaps, prev = dict(base), [], {}, None
    for op in ops:
        d = op.get("date")
        if d and prev is not None and d != prev:
            snaps[prev] = _snap(doc, prev)
        if "change_type" in op:
            _replay._apply_change_type(doc, op, flags, fb)
        else:
            _replay._apply_kind(doc, op, flags)
        if d:
            prev = d
    if prev is not None:
        snaps[prev] = _snap(doc, prev)
    latest = _snap(doc, None)

    guard = [(None, latest)]
    if dates:
        md = dates[len(dates) // 2]
        guard.append((md, snaps.get(md)))
    for gd, got in guard:
        ref = pipeline.reconstruct(law, gd)[0]
        if got is None or any(got.get(p, "") != ref.get(p, "") for p in set(got) | set(ref)):
            snaps = {d: pipeline.reconstruct(law, d)[0] for d in dates}   # exact fallback
            latest = pipeline.reconstruct(law, None)[0]
            break
    series = [(d, snaps[d]) for d in dates if d in snaps]
    base0 = snaps.get(dk[:10]) or pipeline.reconstruct(law, dk[:10])[0]
    return series, latest, base0


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

    snaps, latest, base0 = _reconstruct_series(law, dk, dates)

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
    fids = [r["fidelity"] for r in provisions]
    law_fid = round(sum(fids) / len(fids), 3) if fids else 0.0
    return {"law": LAW_NAMES.get(dk) or _title(dk), "datokode": dk, "enacted": dk[:10],
            "fidelity": law_fid, "provisions": provisions}


def _law_universe() -> list[str]:
    """Datokodes to publish: ALL reconstructable laws with a current-dump answer key (dev-set first
    for stable ordering), so the browser shows the honest state across every law we hold — not just
    the 9 dev laws. Falls back to the dev set if the corpus enumeration is unavailable."""
    try:
        from source.eval.convergence_corpus import reconstructable_scoreable
        laws = [l.split("/")[-1] for l in reconstructable_scoreable()]
    except Exception:
        laws = []
    dev = [dk for _, dk in gate.DEV_LAWS]
    seen, out = set(), []
    for dk in dev + sorted(laws):
        if dk not in seen:
            seen.add(dk)
            out.append(dk)
    return out


def build_data(laws: list[str] | None = None) -> list:
    """Extract every reconstructable+scoreable law into the CACHE dir; write <dk>.json + index.json
    and return the index rows (skips laws with no current dump). `laws` overrides the universe."""
    CACHE.mkdir(parents=True, exist_ok=True)
    laws = laws if laws is not None else _law_universe()
    index = []
    for i, dk in enumerate(laws):
        if gate.current_provisions(dk) is None:
            continue
        try:
            data = extract_law(dk)
        except Exception as e:                      # one bad law must not sink the whole build
            print(f"  ERR {dk}: {str(e)[:80]}", file=sys.stderr)
            continue
        (CACHE / f"{dk}.json").write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        provs = data["provisions"]
        index.append({
            "datokode": dk, "law": data["law"], "enacted": dk[:10],
            "fidelity": data["fidelity"],
            "n_provisions": len(provs),
            "n_amended": sum(1 for r in provs if len(r["versions"]) > 1),
            "n_hifi": sum(1 for r in provs if r["fidelity"] >= 0.98),
            "ocr": pipeline.is_ocr_base("lov/" + dk),
        })
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(laws)} ({len(index)} written)", flush=True)
    index.sort(key=lambda r: (-r["fidelity"], -r["n_provisions"]))
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
                "distribution": d.get("distribution") or {},
                "pit": (d.get("point_in_time_summary") or {}).get("similarity_mean")}
    except (OSError, ValueError):
        return {}


def _dist_bar_html(dist: dict) -> str:
    """Stacked horizontal bar of the per-provision similarity distribution, graded green→amber→red
    to match the per-provision fidelity dots (good ≥0.98, warn ≥0.90, bad <0.90). Server-rendered
    (no JS), theme-aware via CSS vars. Empty string when no distribution is present."""
    bands = (dist or {}).get("bands")
    n = (dist or {}).get("n")
    if not bands or not n:
        return ""
    labels = ["= 1.000", "0.98–1.0", "0.95–0.98", "0.90–0.95", "0.80–0.90", "0.50–0.80", "< 0.50"]
    segs, leg = [], []
    for i, (b, lab) in enumerate(zip(bands, labels), 1):
        pct = b["count"] / n * 100
        segs.append(f'<span class="d-b{i}" style="width:{pct:.2f}%" '
                    f'title="{lab}: {b["count"]} ({pct:.0f}%)"></span>')
        leg.append(f'<span><i class="d-b{i}"></i>{lab} <b>{b["count"]}</b></span>')
    return (f'<figure class="distfig"><div class="distbar" role="img" '
            f'aria-label="character-similarity distribution of {n} provisions">'
            f'{"".join(segs)}</div><figcaption class="distlegend">{"".join(leg)}</figcaption></figure>')


_BANDS = [("=1.000", lambda f: f >= 0.9995), ("0.98–1.0", lambda f: 0.98 <= f < 0.9995),
          ("0.95–0.98", lambda f: 0.95 <= f < 0.98), ("0.90–0.95", lambda f: 0.90 <= f < 0.95),
          ("0.80–0.90", lambda f: 0.80 <= f < 0.90), ("0.50–0.80", lambda f: 0.50 <= f < 0.80),
          ("<0.50", lambda f: f < 0.50)]


def _corpus_dist() -> dict:
    """Per-provision char-similarity distribution over EVERY built law (reads CACHE/<dk>.json), so the
    landing bar reflects the whole corpus, not the dev-set gate. Empty if no law data on disk yet."""
    fids = []
    for f in CACHE.glob("*.json"):
        if f.name == "index.json" or f.name == "meta.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fids += [p["fidelity"] for p in data.get("provisions", [])]
    if not fids:
        return {}
    n = len(fids)
    bands = [{"label": lab, "count": sum(1 for f in fids if test(f))} for lab, test in _BANDS]
    return {"n": n, "bands": bands,
            "cum": {"0.90": sum(1 for f in fids if f >= 0.90),
                    "0.98": sum(1 for f in fids if f >= 0.98)}}


def render_page(index: list, status: dict) -> str:
    tpl = TEMPLATE.read_text(encoding="utf-8")
    n_laws = len(index)
    n_prov = sum(r["n_provisions"] for r in index)
    fids = sorted(r.get("fidelity", 0) for r in index)
    median = fids[len(fids) // 2] if fids else 0.0
    n90 = sum(1 for f in fids if f >= 0.90)
    devn = len(gate.DEV_LAWS)
    # Corpus-honest headline (breadth + median), NOT the dev-set gate (which stays labelled below).
    perf = (f"Across the {n_laws} statutes we can check against today's official text, the median law "
            f"reconstructs to {median * 100:.0f}% of the current wording, and {n90} match it to within "
            f"90%. Quality varies by law — the picker and the per-section fidelity badge show exactly "
            f"where each one lands")
    dist = _corpus_dist() or (status.get("distribution") or {})
    dist_txt = ""
    if dist.get("cum") and dist.get("n"):
        n = dist["n"]
        cum = dist["cum"]
        tail = next((b["count"] for b in dist["bands"] if b["label"].startswith("<0.50")), 0)
        dist_txt = (f"Across all {n:,} provisions in these {n_laws} statutes, {cum['0.90']} "
                    f"({cum['0.90'] / n * 100:.0f}%) reconstruct to within 90% character-identity and "
                    f"{cum['0.98']} to within 98%; most of the gap is near-misses (an OCR character, an "
                    f"editorial note), with the genuine failures a {tail}-provision tail below 50%. A "
                    f"strict per-provision convergence of __CONV__ is the internal gate on the "
                    f"{devn}-law development set (as of __ASOF__).")
    repl = {
        "__PERF__": perf,
        "__DIST__": dist_txt,
        "__DISTBAR__": _dist_bar_html(dist),
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
        print("=== Building statute-browser data (all reconstructable+scoreable laws) ===", flush=True)
        index = build_data()
    sync_to_site(index)
    print(f"browser: wrote index.html + {len(index)} law files "
          f"({sum(r['n_provisions'] for r in index)} provisions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
