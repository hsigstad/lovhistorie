"""Load the manually-downloaded Lovdata Pro ground-truth set (docs/reference/ground_truth.md).

INTENT: give the harness a uniform view of the held-out gold-standard versions —
    per (law, date) the raw historical text — without ever mixing it into the
    published corpus.
REASONING: read a small manifest (index.csv) + one text file per version, so the
    set is human-maintainable and the harness stays decoupled from how files were
    saved.
ASSUMES: files live under data/ground_truth/<datokode>/<YYYY-MM-DD>.txt with a
    manifest data/ground_truth/index.csv (datokode, valid_from_date, filename, ...).
    This tree is git-ignored (eval-only, never redistributed).
"""
from __future__ import annotations

import csv
from pathlib import Path

GT_ROOT = Path(__file__).resolve().parents[2] / "data" / "ground_truth"


def load_index(root: Path = GT_ROOT):
    """Return [{datokode, valid_from_date, filename, ...}] from index.csv (or [])."""
    idx = root / "index.csv"
    if not idx.exists():
        return []
    with idx.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _json_provisions(path):
    """A pre-parsed {para: text} dict written by a builder (e.g. build_gt_lovdata_cd) — used when
    the source needs segmentation the naive .txt §-split can't do cleanly (cross-refs/footnotes)."""
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_version(datokode: str, date: str, root: Path = GT_ROOT):
    """{paragraf_id: text} for one historical version, or None if not present.
    Parses .html (Lovdata Pro export) via lovdata_html; .json as a pre-parsed dict; .txt as § splits."""
    from source.eval import lovdata_html

    d = root / datokode
    for ext, parser in ((".html", lovdata_html.parse_file), (".json", _json_provisions),
                        (".txt", _txt_provisions)):
        p = d / f"{date}{ext}"
        if p.exists():
            return parser(p)
    return None


def _txt_provisions(path):
    import re
    t = " ".join(open(path, encoding="utf-8", errors="ignore").read().split())
    out, parts = {}, re.split(r"(§\s*\d+(?:-\d+)?[a-z]?)", t)
    for i in range(1, len(parts) - 1, 2):
        out.setdefault(parts[i].replace(" ", ""), parts[i + 1].strip())
    return out


def versions_for(datokode: str, root: Path = GT_ROOT):
    """[(date, {para: text})] for a law, from the manifest; skips missing files."""
    out = []
    for row in load_index(root):
        if row.get("datokode") != datokode:
            continue
        d = row.get("valid_from_date", "")
        provs = load_version(datokode, d, root)
        if provs:
            out.append((d, provs))
    return sorted(out)


def coverage(root: Path = GT_ROOT):
    """(n_laws, n_versions) parseable on disk — a quick readiness check."""
    rows = load_index(root)
    have = [r for r in rows if load_version(r["datokode"], r.get("valid_from_date", ""), root)]
    return len({r["datokode"] for r in have}), len(have)
