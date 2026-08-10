"""Bulk-harvest the digitised Norsk Lovtidend Avd. I corpus (1877-2000) as text.

INTENT: pull NB's public-domain ALTO OCR for every digitised Avd. I (Lover og
    sentrale forskrifter) issue/volume 1877-2000 into a local, resumable text cache
    (data/lovtidend_text/<catalog_id>.jsonl.gz, one JSON line {urn,page,text} per
    page). This is the owned, publishable source corpus the pipeline is built on:
    it supplies BOTH original enactment texts and the pre-2001 amendment (endringslov)
    stream (which LTI, 2001+, lacks). Downstream act-splitting/replay is separate.

REASONING: NB exposes ordered running text ONLY per-page (the ALTO endpoint); there
    is no bulk dump and no whole-issue text endpoint (verified 2026-08). So this is
    ~144k small requests — hence idempotent per-item caching, retry/backoff, and
    capped concurrency (NB/sandbox egress timed out at 8 concurrent; 6 is safe).

ASSUMES: data/lovtidend_index.json is the NB catalog census (list of items with
    id,title,issued,pageCount,isDigital,license). All Avd. I items are
    license=publicdomain. Holes (1891,1976,1980,1982,1984,1987-89) simply have no
    items and are skipped implicitly.

Run: python -m source.scrape.harvest_lovtidend            # harvest everything
     python -m source.scrape.harvest_lovtidend --years 1918,1959,1979,1983,1997
     python -m source.scrape.harvest_lovtidend --workers 6 --limit 5   # smoke test
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from source.scrape import nb_lovtidend as nb

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "data" / "lovtidend_index.json"
OUT = ROOT / "data" / "lovtidend_text"


def _year(row) -> int | None:
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", row.get("issued") or "")
    if m:
        return int(m.group(1))
    m = re.search(r"(1[89]\d\d|20\d\d)", row.get("title") or "")
    return int(m.group(1)) if m else None


def _is_avdi(title: str) -> bool:
    """True for Avd. I content (modern 'Avd. I' or old '1. Afdeling'); excludes
    Avd. II / 2den Afdeling and Register/index volumes."""
    if re.search(r"2den Afdeling|2\.?\s*Afdeling|Avd\. II", title):
        return False
    if re.search(r"[Rr]egister", title):
        return False
    if "Avd. I" in title:
        return True
    return bool(re.search(r"1\.?\s*(ste)?\s*[Aa]fdeling", title))


def worklist(years: set[int] | None = None) -> list[dict]:
    rows = json.loads(INDEX.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        if "lovtiden" not in (r.get("title") or "").lower():
            continue
        if not r.get("isDigital"):
            continue
        if not _is_avdi(r.get("title") or ""):
            continue
        y = _year(r)
        if not y or not (1877 <= y <= 2000):
            continue
        if years and y not in years:
            continue
        if not (r.get("pageCount") or 0):
            continue
        out.append({"id": r["id"], "year": y, "title": r["title"],
                    "pages": int(r["pageCount"])})
    # Newest-first: modern per-issue years are smaller + cleaner OCR (faster feedback,
    # less lost work on an interruption) and hold the modern dev-laws' amendments; the
    # giant pre-1948 bound annuals go last. Stable by id within a year.
    out.sort(key=lambda d: (-d["year"], d["id"]))
    return out


def _fetch_page(urn: str, p: int, retries: int = 4) -> str | None:
    """One page's reflowed OCR text, with exponential backoff. None on hard failure."""
    for attempt in range(retries):
        try:
            return nb.page_text(urn, p)
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(2 ** attempt)  # 1,2,4s
    return None


def _done(item: dict) -> bool:
    """An item is complete when its cache exists with pages == expected count."""
    f = OUT / f"{item['id']}.jsonl.gz"
    if not f.exists():
        return False
    try:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            return sum(1 for _ in fh) == item["pages"]
    except Exception:
        return False


def _resume_from(item: dict):
    """(next_page, existing_lines) for page-level resume. Reads a partial
    <id>.part.jsonl (plain, append-per-line) and returns the first unfetched page,
    dropping any trailing half-written/corrupt line from a mid-write kill."""
    part = OUT / f"{item['id']}.part.jsonl"
    if not part.exists():
        return 1, []
    good = []
    for line in part.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            good.append(json.loads(line))
        except Exception:
            break  # trailing corrupt line -> stop; resume from here
    # rewrite the cleaned partial so the corrupt tail is gone
    with part.open("w", encoding="utf-8") as fh:
        for r in good:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(good) + 1, good


def harvest_item(item: dict) -> dict:
    """Resolve URN, fetch pages, write <id>.jsonl.gz. Idempotent AND page-resumable:
    a run killed mid-item resumes from the last fetched page, not from scratch (the
    pre-1948 bound annuals are ~1000-1500 pp, so per-item restart would waste hours)."""
    if _done(item):
        return {**item, "status": "cached", "chars": 0, "failed": 0}
    urn = nb.resolve_urn(item["id"])
    if not urn:
        return {**item, "status": "no-urn", "chars": 0, "failed": item["pages"]}
    part = OUT / f"{item['id']}.part.jsonl"
    start, existing = _resume_from(item)
    chars = sum(len(r.get("text", "")) for r in existing)
    failed = 0
    with part.open("a", encoding="utf-8") as fh:
        for p in range(start, item["pages"] + 1):
            txt = _fetch_page(urn, p)
            if txt is None:
                failed += 1
                txt = ""
            chars += len(txt)
            fh.write(json.dumps({"urn": urn, "page": p, "text": txt},
                                ensure_ascii=False) + "\n")
            fh.flush()
    # complete: compress .part -> .jsonl.gz atomically, drop the partial
    tmp = OUT / f"{item['id']}.jsonl.gz.tmp"
    with part.open("r", encoding="utf-8") as src, gzip.open(tmp, "wt", encoding="utf-8") as dst:
        dst.write(src.read())
    tmp.rename(OUT / f"{item['id']}.jsonl.gz")
    part.unlink(missing_ok=True)
    return {**item, "status": "ok", "urn": urn, "chars": chars, "failed": failed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6,
                    help="concurrent items (NB egress timed out at 8; 6 is safe)")
    ap.add_argument("--years", type=str, default=None,
                    help="comma-separated years to restrict to (default: all)")
    ap.add_argument("--limit", type=int, default=None, help="cap #items (smoke test)")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    years = {int(y) for y in args.years.split(",")} if args.years else None
    items = worklist(years)
    if args.limit:
        items = items[: args.limit]

    total_pages = sum(i["pages"] for i in items)
    pending = [i for i in items if not _done(i)]
    done_pages = total_pages - sum(i["pages"] for i in pending)
    print(f"[harvest] {len(items)} items, {total_pages} pages total; "
          f"{len(pending)} items / {total_pages - done_pages} pages to fetch "
          f"({len(items) - len(pending)} items already cached)", flush=True)

    prog = OUT / "_progress.txt"
    manifest = OUT / "_manifest.jsonl"
    t0 = time.time()
    got_pages = done_pages
    n_ok = n_fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(harvest_item, it): it for it in pending}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            got_pages += r["pages"]
            n_ok += 1 if r["status"] in ("ok", "cached") else 0
            n_fail += r.get("failed", 0)
            with manifest.open("a", encoding="utf-8") as mh:
                mh.write(json.dumps(r, ensure_ascii=False) + "\n")
            rate = (got_pages - done_pages) / max(1e-9, time.time() - t0)
            eta_h = (total_pages - got_pages) / max(1e-9, rate) / 3600
            line = (f"[{i}/{len(pending)}] {r['year']} {r['id'][:8]} "
                    f"{r['status']} pages={r['pages']} failed={r.get('failed',0)} "
                    f"| {got_pages}/{total_pages} pp  {rate:.1f} pp/s  ETA {eta_h:.1f}h")
            print(line, flush=True)
            prog.write_text(line + "\n", encoding="utf-8")
    dt = (time.time() - t0) / 3600
    print(f"[harvest] done: {n_ok} items ok, {n_fail} page-failures, "
          f"{got_pages} pages in {dt:.1f}h", flush=True)


if __name__ == "__main__":
    sys.exit(main())
