"""Attribute every convergence MISS to a cause — the measure-before-building diagnostic.

INTENT: `python -m source.eval.loss_breakdown` classifies each statutory current
    provision the pipeline fails to reproduce (below its per-source τ) into ONE cause
    bucket, so the next engine lift is chosen from data, not guessed. The buckets map
    1:1 onto docs/todo.md's levers (missing-amendment coverage / ledd engine / OCR /
    base-structural), and the totals say whether the 0.97 gate is even reachable on
    this dev set and which lever pays.
REASONING: the gate (source.eval.gate) computes per-provision similarity but throws the
    reason away. This module reuses the gate's EXACT scope + τ (annex-out-of-scope,
    per-source OCR τ) so its miss set is identical to the gate's, then adds attribution.
    It is harness-side (reads the answer key, like the gate) and never touches the recon
    path — no anti-gaming surface (it is not a RECON_MODULE).
ASSUMES: run from repo root with the current NLOD dump present (data/current or
    $LOVHISTORIE_CURRENT_DIR); same prerequisite as the gate. Read-only; writes a
    committed report to build/eval/loss_breakdown.md.

CAUSE BUCKETS (one per miss, priority order):
  base-missing        provision absent from recon AND no amendment op targets it → we
                      have no source text at all (OCR base-drop, or a renumber TARGET id,
                      or a provision only ever created by an uncaptured amendment).
  uncaptured-amdt     recon carries the provision (from the base / an old op) but NO op
                      in our stream targets it and the text differs a lot (sim < 0.85):
                      a real amendment we never resolved — name-cite / omnibus / blanket-
                      terminology. THE pre-2001 amendment-coverage lever.
  base-ocr-noise      no op targets it, recon == base, sim in [0.85, τ): pure OCR
                      fidelity gap on a never-amended provision (low ceiling — see lesson 4).
  engine-gap:ledd     an op targets it but the ledd/sub-provision engine could not apply
                      it (flagged) → the ledd-engine lever (risky; deprioritised).
  engine-gap:struct   flagged op that is a renumber / move / repeal-mismatch → structural
                      id-remap lever (~the hard `nåværende § X blir § Y` residual).
  applied-wrong       a whole-provision op WAS applied but the result is far off
                      (sim < 0.85): truncated block, wrong op text, OR a further
                      uncaptured amendment on top.
  applied-ocr-noise   op applied, result close (sim in [0.85, τ)): OCR noise in the
                      amendment/base text (minor).
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from source.eval import gate, metrics
from source.parse import amendments, pipeline
from source.eval.status import LAW_NAMES

ROOT = Path(__file__).resolve().parents[2]
REPORT_MD = ROOT / "build" / "eval" / "loss_breakdown.md"

# A "close but sub-τ" miss (OCR noise) vs a "genuinely different text" miss (a change we
# never applied). 0.85 is the elbow between the OCR-noise band (τ_OCR floor is 0.90, so
# real OCR misses cluster just under τ) and wholesale text differences. Diagnostic-only:
# it splits reporting buckets, it is NOT a scoring threshold and never enters the gate.
NEAR = 0.85

_RENUMBER = re.compile(
    r"\bn[aå]v[aæ]rende\b.*\bblir\b|\bblir\s+ny\s+§|\bblir\s+§|\bflytt|\bomnummerer",
    re.I,
)


def _renumberish(instr: str | None) -> bool:
    return bool(instr and _RENUMBER.search(instr))


def classify_law(law: str, dk: str):
    """Return (miss_records, n_statutory, tau) for one dev law.

    miss_record = (para, bucket, sim). Buckets defined in the module docstring; the
    per-source τ and annex scope match gate.convergence() exactly so the miss COUNT
    equals the gate's (total - matched) for this law."""
    cur = gate.current_provisions(dk)
    if cur is None:
        return None, None, None
    statutory = {p: t for p, t in cur.items()
                 if not gate._is_convention_annex(p)}
    tau = gate.TAU_OCR if pipeline.is_ocr_base(law) else gate.TAU

    base = pipeline.enactment_base(law)
    recon, flags = pipeline.reconstruct(law)
    ops = amendments.load_for(law)

    ops_by_para: dict[str, list] = defaultdict(list)
    for o in ops:
        if o["para"]:
            ops_by_para[o["para"]].append(o)
    flagged = {f["para"] for f in flags if f.get("para")}

    misses = []
    for p, truth in statutory.items():
        got = recon.get(p, "")
        sim = metrics.similarity(got, truth)
        if sim >= tau:
            continue
        ops_p = ops_by_para.get(p, [])
        in_base = p in base
        has_output = bool(got)

        if not has_output:
            # nothing reconstructed for this id
            if not ops_p:
                bucket = "base-missing"
            elif p in flagged and any(_renumberish(o["instruction"]) for o in ops_p):
                bucket = "engine-gap:struct"
            elif p in flagged and any(o["kind"] == "subprovision" for o in ops_p):
                bucket = "engine-gap:ledd"
            else:
                bucket = "base-missing"      # op exists but produced no text (e.g. repeal-mismatch)
        elif p in flagged:
            if any(_renumberish(o["instruction"]) for o in ops_p):
                bucket = "engine-gap:struct"
            else:
                bucket = "engine-gap:ledd"
        elif not ops_p:
            bucket = "uncaptured-amdt" if sim < NEAR else "base-ocr-noise"
        else:
            bucket = "applied-wrong" if sim < NEAR else "applied-ocr-noise"

        misses.append((p, bucket, sim))
    return misses, len(statutory), tau


# Levers each bucket feeds (for the roll-up), and whether it is a SAFE deterministic lift.
LEVER = {
    "base-missing":       ("base-structural (OCR base-drops + renumber targets)", "safe-ish"),
    "uncaptured-amdt":    ("MISSING-AMENDMENT coverage (name / omnibus / blanket)", "safe"),
    "applied-wrong":      ("MISSING-AMENDMENT / block-truncation / wrong-op", "mixed"),
    "engine-gap:ledd":    ("ledd/sub-provision engine", "risky"),
    "engine-gap:struct":  ("structural id-remap (renumber / move)", "risky"),
    "base-ocr-noise":     ("OCR fidelity (never-amended)", "low ceiling"),
    "applied-ocr-noise":  ("OCR fidelity (amended body)", "low ceiling"),
}
BUCKET_ORDER = ["uncaptured-amdt", "applied-wrong", "base-missing",
                "engine-gap:ledd", "engine-gap:struct",
                "base-ocr-noise", "applied-ocr-noise"]


def collect():
    per_law = {}
    total_stat = 0
    corpus = Counter()
    examples = defaultdict(list)
    for law, dk in gate.DEV_LAWS:
        misses, n_stat, tau = classify_law(law, dk)
        if misses is None:
            per_law[dk] = None
            continue
        c = Counter(b for _, b, _ in misses)
        per_law[dk] = {"n_stat": n_stat, "n_miss": len(misses), "tau": tau, "buckets": c}
        total_stat += n_stat
        corpus.update(c)
        for p, b, sim in sorted(misses, key=lambda x: x[2]):
            if len(examples[b]) < 12:
                examples[b].append(f"{LAW_NAMES.get(dk, dk)} {p} ({sim:.2f})")
    return per_law, total_stat, corpus, examples


def render(per_law, total_stat, corpus, examples) -> str:
    total_miss = sum(corpus.values())
    matched = total_stat - total_miss
    lines = []
    lines.append("<!-- GENERATED by `python -m source.eval.loss_breakdown` — do not edit by hand. -->")
    lines.append("# Loss breakdown — why each convergence miss fails\n")
    lines.append(f"Dev set: **{matched}/{total_stat}** statutory provisions converge "
                 f"(per-source τ); **{total_miss}** miss. Gate threshold 0.97 needs "
                 f"~{round(0.97 * total_stat) - matched} more.\n")
    lines.append("## Misses by cause (corpus)\n")
    lines.append("| cause | n | share of misses | lever | class |")
    lines.append("|---|---:|---:|---|---|")
    for b in BUCKET_ORDER:
        n = corpus.get(b, 0)
        if not n:
            continue
        lever, cls = LEVER[b]
        lines.append(f"| `{b}` | {n} | {n / total_miss * 100:.0f}% | {lever} | {cls} |")
    lines.append(f"| **total** | **{total_miss}** | 100% | | |\n")

    # Lever roll-up: what a fully-solved lever would add, as a ceiling.
    roll = Counter()
    for b, n in corpus.items():
        roll[LEVER[b][0]] += n
    lines.append("## If a lever were fully solved (upper-bound gain)\n")
    lines.append("| lever | provisions | convergence if solved |")
    lines.append("|---|---:|---:|")
    for lever, n in roll.most_common():
        conv = (matched + n) / total_stat
        lines.append(f"| {lever} | +{n} | {conv:.3f} |")
    lines.append("")

    lines.append("## Per-law\n")
    hdr = ["law", "conv", "miss"] + BUCKET_ORDER
    lines.append("| " + " | ".join(hdr) + " |")
    lines.append("|" + "|".join(["---"] + ["---:"] * (len(hdr) - 1)) + "|")
    for dk, d in per_law.items():
        name = LAW_NAMES.get(dk, dk)
        if d is None:
            lines.append(f"| {name} | current absent | | " + " | ".join([""] * len(BUCKET_ORDER)) + " |")
            continue
        conv = (d["n_stat"] - d["n_miss"]) / d["n_stat"]
        row = [f"{name} `@{d['tau']}`", f"{conv:.2f}", str(d["n_miss"])]
        row += [str(d["buckets"].get(b, "") or "") for b in BUCKET_ORDER]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## Example provisions (lowest similarity first)\n")
    for b in BUCKET_ORDER:
        if not examples.get(b):
            continue
        lines.append(f"**`{b}`** — {LEVER[b][0]}")
        lines.append("  \n".join("  - " + e for e in examples[b]))
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    per_law, total_stat, corpus, examples = collect()
    if not total_stat:
        print("loss_breakdown: no current-text data found — place the NLOD dump at "
              "data/current/ or set $LOVHISTORIE_CURRENT_DIR.", file=sys.stderr)
        return 1
    md = render(per_law, total_stat, corpus, examples)
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(md + "\n", encoding="utf-8")
    # Terminal summary
    total_miss = sum(corpus.values())
    matched = total_stat - total_miss
    print(f"=== loss breakdown: {matched}/{total_stat} converge, {total_miss} miss ===")
    for b in BUCKET_ORDER:
        n = corpus.get(b, 0)
        if n:
            print(f"  {b:<20} {n:>4}  ({n / total_miss * 100:4.0f}%)  {LEVER[b][0]}")
    print(f"wrote {REPORT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
