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
        provs = parse_provs(blk)
        json.dump(provs, open(OUT / f"{dk}.json", "w"), ensure_ascii=False)
        tag = "TRUSTED->eval" if dk in TRUSTED else "held back (parse-limited)"
        print(f"{law}: {len(blk)} chars, {len(provs)} provisions [{tag}]", flush=True)
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
    build()
