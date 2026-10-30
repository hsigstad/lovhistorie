# Segmentation handoff — giant Lovtidend volumes (for Eivind's Claude Code agent)

**Goal.** Help segment the remaining Tier-2 **giant** Lovtidend issues (bound annual volumes,
>600k chars). They hold ~8,889 `skal lyde` amendment markers — ~47% of all remaining amendment
coverage — and are the single biggest lever left on the corpus. This is embarrassingly parallel
across people/quotas: each issue (and each 80k-char chunk within it) is independent.

This doc is written so a Claude Code **agent** can follow it end to end. Henrik keeps the 30
densest giants (ranks 0–29); **your block is the rest** (see step 3). No overlap, so no conflicts.

---

## 0. Prereqs (one-time)

1. **Clone the repo** (you have this if you're reading the doc):
   `git clone git@github.com:hsigstad/lovhistorie.git && cd lovhistorie`
2. **Python env:** `pip install -r requirements.txt`
3. **Restore the OCR data from Dropbox** (it is gitignored for size — public-domain NB gazette OCR,
   NOT in the repo). From `bi-dropbox:pipelines/lovhistorie/` (or the share link Henrik sends):
   ```bash
   mkdir -p data
   tar xzf lovtidend_text.tar.gz -C data/     # -> data/lovtidend_text/  (REQUIRED: the OCR you segment)
   ```
   `current.tar.gz` / `lti.tar.gz` / `llm_cache.tar.gz` / `ground_truth_ENCUMBERED.tar.gz` are
   **NOT needed** for segmentation — they only matter for the full convergence gate
   (`source.eval.gate`), which you do not run. The pre-commit gates below need only
   `data/lovtidend_text` + the tracked `data/segments.jsonl`.
   > **CAVEAT — verify currency.** `lovtidend_text.tar.gz` is dated 2026-08-12. After restoring,
   > confirm it holds your assigned giants: `ls data/lovtidend_text | wc -l` should be ~1036, and
   > every iid printed in step 3 must exist as `data/lovtidend_text/<iid>.jsonl.gz`. If any are
   > missing, ping Henrik to refresh the bundle before starting.
4. **Install the commit gates** (git hooks are not cloned):
   `python -m source.eval.install_hooks`  — writes `.git/hooks/pre-commit` (runs
   `classification_qa --diff` then `segments_quality --diff`; blocks any degrading commit).

Read `CLAUDE.md` (the "Pipeline map") and `docs/notes/friday_segmentation_worklist.md` for context.
The canonical loop is: **`fold_append prepare` → one subagent per chunk → `fold_append fold` →
gates → commit**. Everything below is that loop, specialised to giants.

---

## 1. How one issue is segmented

- `python -m source.scrape.fold_append prepare --iids <iid> --outdir <dir>` writes the issue's
  frozen OCR to `<dir>/<iid>_<cidx>.txt` (giants auto-chunk at ~80k chars, 12k overlap) and an
  embedded per-chunk prompt into `<dir>/jobs.json`.
- One **subagent per chunk** reads its chunk text and returns a flat, gap-free, verbatim-anchored
  segment partition — the schema + rules are `source/scrape/segment_prompt.py` (`SCHEMA`,
  `PROMPT_TEMPLATE`). The agent LOCATES/CLASSIFIES (verbatim `start_anchor` + kind); it never
  rewrites text. Save each chunk's result as `<dir>/out/<iid>_<cidx>.json` = `{"segments":[...]}`.
- `python -m source.scrape.fold_append fold --results <results.json>` stitches the chunks
  (`fold_segmentation.stitch_chunks`), substring-verifies every anchor, tiles into char offsets,
  and REPLACES that iid's rows in `data/segments.jsonl` (untouched issues stay byte-identical).
- Anchor misses of 0–3 per giant (<1.5%) are normal. An issue with an **empty** chunk is
  auto-deferred (don't fold it until that chunk is re-run) — a missing chunk would leave a gap.

---

## 2. Driver scripts (write these to your own `scratchpad/`, not tracked)

Henrik's Friday drivers live in his local scratchpad (untracked, ephemeral by convention). Recreate
these three in your clone's `scratchpad/`:

**`scratchpad/prep_giants.py`** — rank giants, skip Henrik's top-30 + anything already segmented,
prep your next N into one dir each:
```python
#!/usr/bin/env python3
# Usage: python scratchpad/prep_giants.py <N> [start_k]   (one giant per scratchpad/seg_g{k}/ dir)
import json, subprocess, sys, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
START_K = int(sys.argv[2]) if len(sys.argv) > 2 else 0
pri = json.load(open(ROOT / "docs/notes/friday_issue_priority.json"))
have = set(json.loads(l).get("issue_id") for l in open(ROOT / "data/segments.jsonl"))
giants = [r for r in pri if r["giant"]]
giants.sort(key=lambda r: -r["skal_lyde"])
HENRIK = {r["iid"] for r in giants[:30]}              # ranks 0-29 are Henrik's
mine = [r for r in giants[30:] if r["iid"] not in have]   # YOUR block = ranks 30+, not yet done
batch = mine[:N]
if not batch:
    print("NO REMAINING GIANTS IN YOUR BLOCK", file=sys.stderr); sys.exit(2)
manifest = {}
for i, r in enumerate(batch):
    iid = r["iid"]; outdir = ROOT / f"scratchpad/seg_g{START_K + i}"
    if outdir.exists(): shutil.rmtree(outdir)
    (outdir / "out").mkdir(parents=True)
    subprocess.run([sys.executable, "-m", "source.scrape.fold_append", "prepare",
                    "--iids", iid, "--outdir", str(outdir)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    jobs = json.load(open(outdir / "jobs.json"))
    units = [{"iid": u["iid"], "cidx": u["cidx"], "cstart": u["cstart"], "cend": u["cend"],
              "promptfile": str(outdir / f"{u['iid']}_{u['cidx']}.prompt.txt"),
              "outfile": str(outdir / "out" / f"{u['iid']}_{u['cidx']}.json")} for u in jobs]
    for u, j in zip(units, jobs): Path(u["promptfile"]).write_text(j["prompt"])
    json.dump(units, open(outdir / "wf_units.json", "w"))
    manifest[str(outdir)] = {"iid": iid, "n": len(units), "markers": r["skal_lyde"]}
    print(f"seg_g{START_K+i}: {iid} skal={r['skal_lyde']} -> {len(units)} chunks", file=sys.stderr)
print(json.dumps([{"dir": d, "iid": m["iid"], "n": m["n"]} for d, m in manifest.items()]))
```

**`scratchpad/burn_workflow.js`** — one subagent per chunk; expands a compact `[{dir,iid,n}]` spec
(the stdout of prep_giants) so the paths follow the fixed prep convention:
```javascript
export const meta = {
  name: 'lovhistorie-giant-burn',
  description: 'Segment giant Lovtidend issues: one subagent per 80k chunk',
  phases: [{ title: 'Segment' }],
}
const spec = typeof args === 'string' ? JSON.parse(args) : args
const units = []
for (const g of spec) for (let c = 0; c < g.n; c++) units.push({
  iid: g.iid, cidx: c,
  promptfile: `${g.dir}/${g.iid}_${c}.prompt.txt`,
  outfile: `${g.dir}/out/${g.iid}_${c}.json`,
})
log(`Segmenting ${units.length} chunks across ${spec.length} giants`)
const results = await parallel(units.map(u => () =>
  agent(
    `You are segmenting one chunk of a Norsk Lovtidend issue.\n` +
    `STEP 1: Read the instruction file at ${u.promptfile}. It has the full rules and names the OCR text file.\n` +
    `STEP 2: Read that OCR text file and segment it EXACTLY per those rules — complete, gap-free, ordered; ` +
    `verbatim start_anchor for every segment; no segments for running headers or mid-sentence continuations.\n` +
    `STEP 3: Write ONLY {"segments":[...]} (strict JSON, no fences) to EXACTLY:\n  ${u.outfile}\n` +
    `STEP 4: Final message = the number of segments written.`,
    { label: `seg:${u.iid.slice(0,8)}/${u.cidx}`, phase: 'Segment' }
  ).then(t => ({ iid: u.iid, cidx: u.cidx, ok: true })).catch(e => ({ iid: u.iid, cidx: u.cidx, ok: false, note: String(e).slice(0,120) }))
))
return { total: units.length, good: results.filter(r => r.ok).length, results }
```

**`scratchpad/assemble_results.py`** — gather one dir's chunk outputs into a fold input (folds only
issues whose EVERY chunk is present):
```python
#!/usr/bin/env python3
# Usage: python scratchpad/assemble_results.py scratchpad/seg_gN   -> writes <dir>/results.json
import json, sys
from pathlib import Path
from collections import defaultdict
D = Path(sys.argv[1]); units = json.load(open(D / "wf_units.json"))
by = defaultdict(list)
for u in units: by[u["iid"]].append(u)
out = []
for iid, us in by.items():
    rows, ok = [], True
    for u in us:
        f = Path(u["outfile"])
        if not f.exists(): ok = False; break
        segs = json.loads(f.read_text()); segs = segs["segments"] if isinstance(segs, dict) else segs
        if not segs: ok = False; break
        rows.append({"iid": iid, "cidx": u["cidx"], "cstart": u["cstart"], "cend": u["cend"], "segments": segs})
    if ok: out.extend(rows)
    else: print(f"DEFER {iid}: incomplete", file=sys.stderr)
json.dump(out, open(D / "results.json", "w"), ensure_ascii=False)
print(f"assembled {len(out)} units -> {D/'results.json'}")
```

---

## 3. The loop (repeat until your block is done or your quota runs out)

```bash
# a) prep the next 5 giants from YOUR block (ranks 30+), one dir each; capture the compact spec:
python scratchpad/prep_giants.py 5 0        # prints [{dir,iid,n}, ...] on the last line

# b) run the Workflow with that spec as args (Claude Code: Workflow tool, scriptPath=burn_workflow.js,
#    args=<the printed JSON>). One subagent per chunk; ~115k tokens/chunk, so 5 giants ≈ a lot —
#    watch your usage. Outputs are durable on disk, so hitting your quota mid-run loses nothing:
#    just re-run prep (it recomputes what's missing) + the workflow.

# c) fold each COMPLETE giant, then gate + commit it (one commit per giant keeps diffs reviewable):
for d in scratchpad/seg_g0 scratchpad/seg_g1 ... ; do
  python scratchpad/assemble_results.py "$d"
  git pull --rebase                                   # stay current before touching segments.jsonl
  python -m source.scrape.fold_append fold --results "$d/results.json"
  git add data/segments.jsonl data/segments_meta.json
  git commit -m "segment: giant <iid> (<markers> markers) — Eivind"   # pre-commit hook runs both --diff gates
  git push
done
```

- **Commit per giant**, `git pull --rebase` before each fold. Henrik is not folding concurrently
  this week, so conflicts are unlikely — but segments.jsonl is one big file, so stay current.
- If a giant has a missing/empty chunk, `assemble_results` defers it — re-run that chunk and retry.

---

## 4. Caveats / coordination

- **Division of labour:** Henrik owns giants ranked **0–29** (30 densest; 2 folded, 6 partially
  done, rest to resume when his quota resets). **Your block = ranks 30+** (skipped automatically by
  the prep script). No overlap.
- **`data/segments.jsonl` is ~52 MB** and will grow — it is nearing GitHub's 100 MB hard limit.
  If a push is rejected for size, STOP and ping Henrik (we'll migrate it to git-LFS or external
  storage). Don't force anything.
- **Cost:** ~115k tokens per 80k chunk (dense OCR in, ~1,500-segment partition out). A single giant
  is 20–55 chunks. Pace to your weekly quota; the work is fully resumable.
- **G1 safety:** the subagent sees ONLY public-domain OCR (never the current dump / Lovdata oracle /
  register). The prompt enforces this; don't add other sources.
- Questions → Henrik (h.sigstad@gmail.com).
