"""Build an INDEPENDENT 2005 point-in-time ground-truth set from the Lovdata-CD-2005 corpus.

INTENT: the point-in-time deliverable (evaluation.md check 2) needs held-out historical text that is
    NOT our own reconstruction and NOT the answer key. The Lovdata CD autumn-2005 edition — out of the
    15-year database-protection window, released by NB as NLOD 2.0 — is exactly that: Lovdata's OWN
    curated consolidation frozen at 2005, independent of our gazette+amendment replay. NB's fragmented
    NCC form is now available cleanly as the HF dataset `norkart/lovdata` (doc_type-labelled parquet).
    This module pulls the `lovdata_cd_norgeslover_2005` docs, splits them into per-law blocks on the CD's
    law header, and emits the 2005 consolidated text of the dev laws present in the selection.
REASONING: unlike sondreskarsten/law-history (a replay seeded from CURRENT text -> shows today's text at
    early dates -> useless as a 2005 oracle) and unlike encumbered Lovdata Pro, this is a genuinely
    independent public snapshot. It lets us put the FIRST real number on point-in-time accuracy.
SCOPE / STATUS (2026-08-25): the CD 'Norges Lover' is a CURATED SELECTION, so only 4 of 9 dev laws are
    in it: avtaleloven(1918), oreigningslova(1959), kjøpsloven(1988), aksjeloven(1997). foreldelses- and
    rettsgebyrloven are NOT in Norges Lover; vphl(2007)/tjeneste(2009) postdate the 2005 edition. The
    per-law block extraction is SOLID (validated: avtale/oreign score cleanly). The per-PROVISION
    segmenter below is a first cut that works for small laws but drops ~half of large-law provisions
    (empty bodies for a chunk of aksje/kjøp §s) — TODO: replace parse_provs with the pipeline's
    target_localize segmenter (which handles heading-vs-cross-reference on noisy prose) before trusting
    the aksje/kjøp point-in-time numbers.
ASSUMES: network access to HF (parquet download, ~248 MB) OR the cached parquet under DATA/ground_truth.
    Output is PUBLISHABLE (public-domain / NLOD 2.0), unlike Lovdata Pro — but kept local by default.
"""
from __future__ import annotations
import re, json, sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
OUT = _REPO / "data" / "ground_truth" / "2005"
PARQUET_URLS = [
    "https://huggingface.co/datasets/norkart/lovdata/resolve/refs%2Fconvert%2Fparquet/default/test/0000.parquet",
    "https://huggingface.co/datasets/norkart/lovdata/resolve/refs%2Fconvert%2Fparquet/default/test/0001.parquet",
]
# dev laws present in the 2005 'Norges Lover' selection: (enactment-year, name-substring, datokode)
DEV = [("1918", "Avtaleloven", "lov/1918-05-31-4"),
       ("1959", "Oreigningslova", "lov/1959-10-23-3"),
       ("1988", "Kjøpsloven", "lov/1988-05-13-27"),
       ("1997", "Aksjeloven", "lov/1997-06-13-44")]

# law-boundary header on the CD: '<year> <Name - abbrev.>' or '<year> <Lov om ...>' or '<year> <Xloven>'
HEADER = re.compile(
    r"(?<![.\d,])\b(1[89]\d\d|20\d\d)\s+("
    r"[A-ZÆØÅ][A-Za-zæøåÆØÅ .-]{2,45}?\s+-\s+[a-zæøå][a-zæøå.]{1,12}\."
    r"|Lov\s+(?:om|um)\s|Provisorisk|Millit\w+|Grunnlov"
    r"|[A-ZÆØÅ][A-Za-zæøåÆØÅ.-]{2,45}?(?:loven|lova|balken|traktaten|traktat|retten)\b)")
PROV = re.compile(r"§\s?(\d+)(?:-(\d+))?\s?([a-z])?\s?\.")


def _clean(body: str) -> str:
    body = re.split(r"\s0\s+Endret ved", body)[0]
    body = re.split(r"\s0\s+Tilf[øo]yd ved", body)[0]
    body = re.sub(r"(?<=[a-zæøå.,)])\d{1,2}(?=\s|$)", "", body)
    return " ".join(body.split())


def parse_provs(block: str) -> dict:
    ms = list(PROV.finditer(block))
    d = {}
    for i, m in enumerate(ms):
        pid = "§" + m.group(1) + ("-" + m.group(2) if m.group(2) else "") + (m.group(3) or "")
        end = ms[i + 1].start() if i + 1 < len(ms) else len(block)
        body = _clean(block[m.end():end])
        if pid not in d or len(body) > len(d[pid]):
            d[pid] = body
    return d


def load_corpus(cache_dir: Path) -> str:
    """Concatenate the lovdata_cd_norgeslover_2005 docs (id-ordered) into the full 2005 law corpus."""
    import pandas as pd
    frames = []
    for i, url in enumerate(PARQUET_URLS):
        f = cache_dir / f"lovdata_cd_{i}.parquet"
        if not f.exists():
            import urllib.request
            urllib.request.urlretrieve(url, f)
        frames.append(pd.read_parquet(f))
    df = pd.concat(frames, ignore_index=True)
    laws = df[df.doc_type == "lovdata_cd_norgeslover_2005"].copy()
    laws["n"] = laws.id.str.extract(r"(\d+)").astype(int)
    return "\n".join(laws.sort_values("n").text.tolist())


# Laws whose per-provision parse is validated clean (gold≈today for unchanged §s -> trustworthy
# point-in-time score). kjøp/aksje are held back: their CD OCR interleaves CISG-annex articles /
# allmennaksjelov parallels / footnote definitions that the regex segmenter can't split cleanly yet
# (needs an LLM-assisted segmenter) — see docs/notes/lovdata_cd_2005.md.
TRUSTED = {"1918-05-31-4", "1959-10-23-3"}
GT_ROOT = _REPO / "data" / "ground_truth"


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    full = load_corpus(OUT)
    heads = [(m.start(), m.group(1), m.group(2).strip()) for m in HEADER.finditer(full)]
    index_rows = []
    for year, namesub, law in DEV:
        blk = None
        for i, (pos, y, name) in enumerate(heads):
            if y == year and namesub.lower() in name.lower():
                blk = full[pos:heads[i + 1][0]]
                break
        if not blk:
            print(f"{law}: block not found", flush=True)
            continue
        dk = law.split("/")[1]
        (OUT / f"{dk}.txt").write_text(blk, encoding="utf-8")
        # TRUSTED (small, clean) laws use the cached LLM CLEAN-TEXT extractor (piloted to static-μ≈0.95,
        # vs 0.85 regex); held-back large laws keep the regex parse until the large-law extractor lands.
        if dk in TRUSTED:
            from source.llm import extract_cd
            provs, rep = extract_cd.extract_law(dk, blk)
            note = f"LLM extract: trace μ={rep.trace_mean:.2f}, low-trace {len(rep.low_trace)}"
        else:
            provs = parse_provs(blk)
            note = "regex"
        json.dump(provs, open(OUT / f"{dk}.json", "w"), ensure_ascii=False)
        tag = "TRUSTED->eval" if dk in TRUSTED else "held back (parse-limited)"
        print(f"{law}: {len(blk)} chars, {len(provs)} provisions [{tag}; {note}]", flush=True)
        if dk in TRUSTED:
            # (a) eval ground-truth (source.eval.ground_truth reads <dk>/<date>.json + index.csv)
            (GT_ROOT / dk).mkdir(parents=True, exist_ok=True)
            json.dump(provs, open(GT_ROOT / dk / "2005-12-31.json", "w"), ensure_ascii=False)
            index_rows.append({"datokode": dk, "valid_from_date": "2005-12-31",
                               "filename": "2005-12-31.json", "source": "lovdata_cd_2005",
                               "era": year[:3] + "0s", "size_class": "", "amendment_intensity": ""})
            # (b) reconstruction base for the SEPARATE 2005-baseline pipeline (pipeline.reconstruct
            #     base="2005"): base_as_of=2005-12-31 so replay applies ONLY post-2005 amendments.
            B2005 = _REPO / "data" / "enactment_2005"
            B2005.mkdir(parents=True, exist_ok=True)
            json.dump({"provisions": provs, "base_as_of": "2005-12-31",
                       "source": {"lovdata_cd": "2005"}},
                      open(B2005 / f"{dk}.json", "w"), ensure_ascii=False)
    if index_rows:
        _update_index(index_rows)


CURRENT_DIR = _REPO / "data" / "current"


def _current_index() -> dict:
    """datokode -> {year, title, kort[]} from the NLOD current dump — the laws we can score.
    Used to resolve each CD 'Norges Lover' block to a datokode (and drop repealed laws absent
    from the dump, which are out of scope because there is no current text to score against)."""
    import glob
    out = {}
    for f in glob.glob(str(CURRENT_DIR / "*.xml")):
        t = open(f, encoding="utf-8", errors="replace").read(1200)
        md = re.search(r"Datokode</dt><dd[^>]*>LOV-([\d-]+)", t)
        if not md:
            continue
        mt = re.search(r"<title>(.*?)</title>", t)
        title = mt.group(1) if mt else ""
        dk = md.group(1)
        # korttittel is given in (parens) OR [brackets] depending on the law — capture both
        kort = [k.strip().lower() for k in re.findall(r"[\(\[]([a-zæøåA-ZÆØÅ. ]+)[\)\]]", title)]
        out[dk] = {"year": dk[:4], "title": title, "kort": kort}
    return out


def resolve_blocks(full: str | None = None) -> dict:
    """{datokode: block_text} for every CD 'Norges Lover' law present in the current dump.

    Match is by enactment year + korttittel (the title's parenthetical, e.g. '(aksjeloven)') or a
    title substring. Sub-400-char splits (spurious HEADER hits) are dropped; the first block per
    datokode wins. Repealed laws absent from the current dump stay unresolved (not scoreable)."""
    if full is None:
        full = load_corpus(OUT)
    heads = [(m.start(), m.group(1), m.group(2).strip()) for m in HEADER.finditer(full)]
    cur = _current_index()
    norm = lambda s: re.sub(r"[^a-zæøå]", "", s.lower())  # noqa: E731
    out = {}
    for i, (pos, y, nm) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(full)
        if end - pos < 400:
            continue
        base = norm(nm.split(" - ")[0])
        if not base:
            continue
        peers = [(dk, v) for dk, v in cur.items() if v["year"] == y]
        # 1. exact korttittel (disambiguates e.g. aksjeloven vs allmennaksjeloven); accept if unique
        hits = [dk for dk, v in peers if any(norm(k) == base for k in v["kort"])]
        # 2. fallback: exact normalised title (minus any "- abbrev") — for laws with no korttittel
        if not hits:
            hits = [dk for dk, v in peers if norm(v["title"].split(" - ")[0]) == base]
        # 3. fallback: unique title-substring, but only when exactly one peer contains it (guards the
        #    aksjeloven-in-allmennaksjeloven cross-match, which would give 2 hits -> rejected)
        if not hits:
            hits = [dk for dk, v in peers if base in norm(v["title"])]
        if len(hits) == 1:
            out.setdefault(hits[0], full[pos:end])
    return out


def build_corpus(min_completeness: float = 0.85, limit: int | None = None):
    """Extract the 2005 point-in-time gold for EVERY resolvable CD 'Norges Lover' law via extract_cd,
    gate each on full-body completeness, and emit gold + a manifest (data/ground_truth/2005/corpus_manifest.csv).

    Laws whose gold is >= min_completeness complete are wired into the point-in-time eval (index.csv);
    the rest are flagged (the NCC 2005 CD drops bodies for some large laws — see docs/notes/lovdata_cd_2005.md).
    Completeness = fraction of current statutory provisions with a full (non-title-only) gold body.
    RESUMABLE: extract_cd is llmkit-cached, so a re-run after an interrupt is ~free."""
    import csv
    from source.llm import extract_cd
    from source.eval import gate, metrics
    OUT.mkdir(parents=True, exist_ok=True)
    items = list(resolve_blocks().items())
    if limit:
        items = items[:limit]
    manifest, index_rows = [], []
    for n, (dk, blk) in enumerate(items, 1):
        provs, rep = extract_cd.extract_law(dk, blk)
        try:
            cur = gate.current_provisions(dk)
        except Exception:
            cur = None
        if cur:
            order = [p for p in cur if not metrics.is_convention_annex(p)]
            full_body = [p for p in order if p in provs and not extract_cd._is_title_only(provs[p])]
            completeness = len(full_body) / len(order) if order else 0.0
            denom = len(order)
        else:                                            # no current text: fall back to intrinsic
            completeness = 1 - len(rep.title_only) / (rep.n or 1)
            denom = rep.n
        trusted = completeness >= min_completeness and rep.n >= 5
        json.dump(provs, open(OUT / f"{dk}.json", "w"), ensure_ascii=False)
        if trusted:
            (GT_ROOT / dk).mkdir(parents=True, exist_ok=True)
            json.dump(provs, open(GT_ROOT / dk / "2005-12-31.json", "w"), ensure_ascii=False)
            index_rows.append({"datokode": dk, "valid_from_date": "2005-12-31",
                               "filename": "2005-12-31.json", "source": "lovdata_cd_2005",
                               "era": dk[:3] + "0s", "size_class": "", "amendment_intensity": ""})
        manifest.append({"datokode": dk, "n": rep.n, "denom": denom,
                         "completeness": round(completeness, 3), "title_only": len(rep.title_only),
                         "low_trace": len(rep.low_trace), "trusted": int(trusted)})
        print(f"[{n}/{len(items)}] {dk}: n={rep.n} complete={completeness:.0%} "
              f"title_only={len(rep.title_only)} low_trace={len(rep.low_trace)} "
              f"{'TRUSTED' if trusted else 'flag'}", flush=True)
    with open(OUT / "corpus_manifest.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["datokode", "n", "denom", "completeness",
                                           "title_only", "low_trace", "trusted"])
        w.writeheader(); w.writerows(manifest)
    if index_rows:
        _update_index(index_rows)
    nt = sum(m["trusted"] for m in manifest)
    print(f"\nCORPUS: {len(manifest)} CD laws extracted; {nt} >= {min_completeness:.0%} complete "
          f"-> wired into the point-in-time eval. Manifest: {OUT / 'corpus_manifest.csv'}", flush=True)
    return manifest


def _update_index(rows):
    """Merge our rows into data/ground_truth/index.csv (add lovdata_cd_2005 rows; keep existing)."""
    import csv
    idx = GT_ROOT / "index.csv"
    cols = ["datokode", "valid_from_date", "filename", "source", "era", "size_class", "amendment_intensity"]
    existing = []
    if idx.exists():
        existing = [r for r in csv.DictReader(open(idx, encoding="utf-8"))
                    if r.get("source") != "lovdata_cd_2005"]
    with open(idx, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in existing + rows:
            w.writerow({c: r.get(c, "") for c in cols})
    print(f"index.csv: {len(rows)} lovdata_cd_2005 rows wired into the point-in-time eval", flush=True)


if __name__ == "__main__":
    import sys as _sys
    if "--corpus" in _sys.argv:
        build_corpus()
    else:
        build()
