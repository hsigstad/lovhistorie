"""Render worked reconstruction examples as a committed, site-readable page.

INTENT: `python -m source.eval.examples` writes docs/reference/examples.md — a handful of
    curated provisions shown three ways: (1) as originally ENACTED, (2) as our
    pipeline RECONSTRUCTS them by replaying every Norsk Lovtidend amendment, and
    (3) the OFFICIAL current NLOD text. The point of the page is to let a visitor
    SEE the output, not just read an aggregate convergence number: a provision whose
    enacted text is nearly disjoint from today's wording, that replay nonetheless
    lands back on exactly.
REASONING: like status.py, the numbers/text are GENERATED from the live pipeline so
    they can never drift from the code — never hand-typed statute text that rots. The
    showcase set is a fixed allowlist (curated for readability + length), but the three
    texts and the similarity are recomputed every run; if a curated provision ever
    stops reconstructing cleanly the page reports the lower score honestly rather than
    hiding it.
ASSUMES: run from the repo root with the current NLOD dump present (data/current or
    $LOVHISTORIE_CURRENT_DIR) — same prerequisite as the gate/status. Every text shown
    is PUBLIC-DOMAIN (enactment base, our reconstruction, NLOD current); NO Lovdata-Pro
    ground-truth text is ever rendered here, so the page is safe to publish.
"""
from __future__ import annotations

import sys
from pathlib import Path

from source.eval import metrics
from source.parse import pipeline

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_MD = ROOT / "docs" / "reference" / "examples.md"

# Curated showcase provisions. Each is a clean-base (2001+) law, so the displayed
# text is machine-readable rather than OCR'd, and each was substantively AMENDED after
# enactment (enacted text far from current) so the reconstruction demonstrably replays
# change rather than copying an unchanged provision. (datokode, law, provision, blurb).
SHOWCASE = [
    ("2007-06-29-75", "verdipapirhandelloven", "§7-15",
     "Enacted in 2007 as *Tillegg til prospekt* (supplement to a prospectus), this slot "
     "was rewritten from the ground up when chapter 7 was replaced *i sin helhet* in 2019 "
     "(after intervening amendments in 2012 and 2015). Its 2007 text and today's text are "
     "almost completely disjoint, yet replaying the three gazette amendments in order "
     "reconstructs today's wording exactly."),
    ("1997-06-13-44", "aksjeloven", "§16-2",
     "The rules on the winding-up board (*avviklingsstyre*) were restructured by the 2018 "
     "amendment (in force 2019): the enacted §16-2 elected a separate liquidation board; "
     "the current text instead vests winding-up in the existing board. Replay applies the "
     "amendment and lands on the current text."),
]


def _clean(t: str) -> str:
    """Trim the leading section-number residue ('. ' left by the heading split) for
    display only — it carries no statutory content and does not affect scoring (normalize()
    drops '§' and punctuation before comparison)."""
    return t.lstrip(". ").strip()


def collect() -> list[dict] | None:
    """Load the three texts + similarity for each showcase provision. None if the
    current dump is absent (same gate as status)."""
    from source.eval import gate
    out = []
    for dk, law, prov, blurb in SHOWCASE:
        cur = gate.current_provisions(dk)
        if cur is None:
            return None
        recon, _ = pipeline.reconstruct("lov/" + dk, None)
        base = pipeline.enactment_base("lov/" + dk)
        out.append({
            "datokode": dk, "law": law, "prov": prov, "blurb": blurb,
            "enacted": base.get(prov, ""),
            "reconstructed": recon.get(prov, ""),
            "current": cur.get(prov, ""),
            "sim_recon_cur": metrics.similarity(recon.get(prov, ""), cur.get(prov, "")),
            "sim_base_cur": metrics.similarity(base.get(prov, ""), cur.get(prov, "")),
        })
    return out


def render_md(items: list[dict]) -> str:
    blocks = []
    for it in items:
        rc = f"{it['sim_recon_cur'] * 100:.1f}%"
        bc = f"{it['sim_base_cur'] * 100:.1f}%"
        verdict = ("matches the current statutory text **exactly**"
                   if it["sim_recon_cur"] >= 0.999 else
                   f"matches the current statutory text at **{rc}** character-identity")
        blocks.append(f"""## {it['law']} {it['prov']}

{it['blurb']}

**Enacted text** (`{it['datokode']}`, the base the reconstruction starts from) — {bc}
similar to today's wording:

```
{_clean(it['enacted'])}
```

**Reconstructed** (enactment base + every Norsk Lovtidend amendment replayed to today,
*never shown the current text*):

```
{_clean(it['reconstructed'])}
```

**Official current text** (NLOD), for comparison:

```
{_clean(it['current'])}
```

The reconstruction {verdict}. The one visible difference — the trailing
*"Endret ved lover …"* provenance note in the official text — is Lovdata's **editorial
annotation**, not statute; the pipeline deliberately does not fabricate it, and the
similarity metric strips it from both sides before scoring.
""")
    body = "\n".join(blocks)
    return f"""<!-- GENERATED by `python -m source.eval.examples` — do not edit by hand. -->
# Worked examples

The [Performance](status.html) page reports *how often* the reconstruction lands back on
today's official statute text. This page shows *what that looks like* on individual
provisions: the same statute section as originally **enacted**, as our pipeline
**reconstructs** it by replaying every gazette amendment, and as the **official current**
text reads today.

These are deliberately provisions that were **substantially rewritten** after enactment —
the enacted text is nearly disjoint from today's wording — so the match is produced by the
amendment replay, not by a provision that never changed. Every text below is
**public-domain** (original enactment, our reconstruction, and the NLOD current text); no
Lovdata-Pro validation text appears here.

{body}## Refresh these examples

```
python -m source.eval.examples     # recompute the three texts from the local data, rewrite this page
```

Requires the current NLOD dump locally (`data/current/` or `$LOVHISTORIE_CURRENT_DIR`).
`bash build.sh deploy` runs this automatically when the data is present, so the published
page always shows the current reconstruction output.
"""


def main() -> int:
    items = collect()
    if not items:
        print("examples: no current-text data found — page left unchanged.", file=sys.stderr)
        print("          place the NLOD dump at data/current/ or set "
              "$LOVHISTORIE_CURRENT_DIR.", file=sys.stderr)
        return 1
    EXAMPLES_MD.write_text(render_md(items), encoding="utf-8")
    lo = min(it["sim_recon_cur"] for it in items)
    print(f"examples: wrote {EXAMPLES_MD.name} ({len(items)} provisions, "
          f"min sim(recon,current) {lo * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
