"""Score reconstruct(law, date) against Eivind Hammersmark's Lovdata-HIST labour-law versions.

INTENT: an independent, DATED point-in-time validation — Eivind (UiO) shared the official Lovdata HIST
    consolidated text of ~31 labour laws at every 1 Jan 1990-2026 (613 `exact` snapshots). This scores our
    reconstruction against them section-by-section, mirroring his own benchmark so we can reproduce/extend
    it as the corpus improves. It is the labour-law counterpart of status._point_in_time (which only covers
    the 9 dev laws) and pit_corpus (the 2005-CD oracle).
REASONING: the gold is Lovdata-Pro LICENSED (do-not-redistribute) — so it lives ONLY under the gitignored
    data/ground_truth/_eivind_hist/ and this CODE reads it if present, emitting nothing if absent (exactly
    like the other eval entrypoints degrade without their encumbered inputs). No gold text is written to any
    tracked file; only aggregate scores (build/eval/, gitignored) + printed summary.
ASSUMES: data/ground_truth/_eivind_hist/{snapshot_table.csv, laws/<slug>/hist_lov_<id>-<YYYYMMDD>.md}
    present locally (rclone copy from bi-dropbox-ro:Lovdata_HIST_labour_laws). Only `exact` rows are GT.
    A law with no enactment base (consume.has_base false) is skipped — reconstruction would be partial.
"""
from __future__ import annotations
import csv
import re
import statistics
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from source.parse import pipeline                 # noqa: E402
from source.eval import gate, metrics             # noqa: E402

HIST = _REPO / "data" / "ground_truth" / "_eivind_hist"
OUT = _REPO / "build" / "eval" / "hist_labour_scores.csv"
_HEAD = re.compile(r"^###\s+§\s*([0-9]+[A-Za-z]?(?:-[0-9]+[A-Za-z]?)?)\.?\s*(.*)$")


def _parse_md(path: Path) -> dict:
    """{canon §id: 'title body'} from a hist_lov_*.md (drop YAML front matter; sections are '### § N. ...')."""
    txt = path.read_text(encoding="utf-8")
    if txt.startswith("---"):                      # strip YAML front matter
        txt = txt.split("---", 2)[-1]
    out, cur, buf = {}, None, []
    for line in txt.splitlines():
        m = _HEAD.match(line)
        if m:
            if cur:
                out[cur] = " ".join(buf).strip()
            cur = pipeline._canon_para("§" + m.group(1))
            buf = [m.group(2)]                      # the provision title after "§N."
        elif cur is not None:
            if line.startswith("#"):                # a new chapter/heading ends the provision
                out[cur] = " ".join(buf).strip(); cur = None; buf = []
            else:
                buf.append(line)
    if cur:
        out[cur] = " ".join(buf).strip()
    return {k: v for k, v in out.items() if v}


def _norm(t: str) -> str:
    return " ".join((t or "").split())


def report(write: bool = True):
    if not (HIST / "snapshot_table.csv").exists():
        print("hist_labour: no Lovdata-HIST gold at data/ground_truth/_eivind_hist/ — skipping.")
        return []
    rows = [r for r in csv.DictReader(open(HIST / "snapshot_table.csv", encoding="utf-8"))
            if r["status"] == "exact"]
    per, all_sims = [], []
    from collections import defaultdict
    bylaw = defaultdict(list)
    for r in rows:
        bylaw[r["lovdata_id"]].append(r)
    for law, lrows in sorted(bylaw.items()):
        dk = law.split("/")[1]
        if not pipeline.enactment_base(law):        # no base -> reconstruction would be partial; skip
            continue
        ocr = pipeline.is_ocr_base(law)
        tau = gate.TAU_OCR if ocr else gate.TAU
        law_sims = []
        for r in sorted(lrows, key=lambda q: q["snapshot"]):
            md = HIST / r["md_path"]
            if not md.exists():
                continue
            gold = _parse_md(md)
            if len(gold) < 3:
                continue
            try:
                recon = pipeline.reconstruct(law, r["snapshot"])[0]
            except Exception:
                continue
            sims = [metrics.similarity(_norm(recon.get(p, "")), _norm(gold[p])) for p in gold]
            if not sims:
                continue
            m = statistics.mean(sims)
            per.append({"datokode": dk, "ocr_base": int(ocr), "date": r["snapshot"],
                        "n_sections": len(sims), "mean": round(m, 3),
                        "ge_098": round(sum(s >= 0.98 for s in sims) / len(sims), 3),
                        "ge_090": round(sum(s >= 0.90 for s in sims) / len(sims), 3)})
            law_sims += sims
            all_sims += sims
        if law_sims:
            dates = [p["date"] for p in per if p["datokode"] == dk]
            print(f"  {dk:16} {len(dates):2d} dates  mean={statistics.mean(law_sims):.3f}  "
                  f">=0.98 {sum(s>=0.98 for s in law_sims)/len(law_sims):.0%}  (OCR={ocr})")
    if write and per:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(per[0].keys()))
            w.writeheader(); w.writerows(per)
    if all_sims:
        print(f"\nAGGREGATE over {len({p['datokode'] for p in per})} reconstructable labour laws, "
              f"{len(per)} law-years, {len(all_sims):,} sections:")
        print(f"  mean={statistics.mean(all_sims):.3f}  >=0.98 {sum(s>=0.98 for s in all_sims)/len(all_sims):.1%}  "
              f">=0.90 {sum(s>=0.90 for s in all_sims)/len(all_sims):.1%}")
        print(f"  (Eivind's own run: 49% >=0.98, 59% >=0.90 across 349 law-years)")
    return per


if __name__ == "__main__":
    report()
