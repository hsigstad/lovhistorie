# Data on Dropbox — inventory & restore guide

The large/encumbered working data is **gitignored** (only public-domain bases, catalog
metadata, code and docs are in git). It lives on Dropbox so a fresh clone (e.g. on
**educloud**) can restore it. This doc is the source of truth for what's there and how to
pull it.

## Where
**`personal-dropbox:pipelines/lovhistorie/`** (rclone remote name may differ per machine;
on the research host the write remote is `personal-dropbox:`, read-only `personal-dropbox-ro:`).
Fallback location if ever re-uploaded there: `bi-dropbox:pipelines/lovhistorie/`.

## Inventory (as of 2026-08-12)

| archive | size | restores to | sha256 |
|---|---|---|---|
| `lovtidend_text.tar.gz` | 88M | `data/lovtidend_text/` | `ea234b8a6cc1fff9235d056dcf37ea150bdc44ad2b4e3785a075c0164462098a` |
| `lti.tar.gz` | 94M | `data/lti/` | `11d8cd7d464f18af3c70ac2ea9498bb044fa4ff980ef41e12524d7d40e47356b` |
| `current.tar.gz` | 8.6M | `data/current/` | `f15b2418cca1e5e5907f374d8d605ee316fde942b9874cab1356de45ac87e595` |
| `amendment_streams.tar.gz` | 17M | `data/` (loose files) | `41012abfb37feae0f2f3e229054a00f6cae8757243f2efb6a4397350cfd8432e` |
| `ground_truth_ENCUMBERED.tar.gz` | 1.1M | `data/ground_truth/` | `c94f0bd2de1712d5128d142a5183d4b5e4dc74ed56cbfd56aa0d77411e5dbcd0` |

**What each is:**
- **`lovtidend_text`** — the NB gazette harvest (1,033 issues / ~144k pages of ALTO OCR).
  The PRIMARY scraped data (~1 day of fetching, irreplaceable short of re-scraping via
  `source/scrape/harvest_lovtidend.py`).
- **`lti`** — Lovtidend Avd. I 2001–2024 clean XML dump (input; source of post-2001 bases
  + `amendments.jsonl.gz`). Re-obtainable from NB/Lovdata if lost.
- **`current`** — NLOD current consolidated text = the harness ANSWER KEY (`data/current/`).
- **`amendment_streams`** — `amendments.jsonl.gz` (LTI stream), `pre2001_amendments.jsonl.gz`
  + `amendment_blocks.jsonl.gz` (derived from the harvest — regenerable via
  `gazette.py --build` and `rederive_blocks.py`), and `lovtidend_index.json` (NB catalog census).
- **`ground_truth_ENCUMBERED`** — Lovdata Pro historical-version HTML. **EVAL-ONLY,
  encumbered — keep private, never place in a public repo or the published corpus.**

## Pull + restore (on educloud / a fresh clone)

```bash
git clone git@github.com:hsigstad/lovhistorie.git
cd lovhistorie && mkdir -p data _dl

# 1. Download the archives from Dropbox (rclone; adjust the remote name to yours).
#    Or use the Dropbox web/desktop client and drop the 5 *.tar.gz into ./_dl/
rclone copy personal-dropbox:pipelines/lovhistorie/ ./_dl/ --include '*.tar.gz' -P

# 2. Verify integrity (should print "OK" for all 5 — sha256 above).
sha256sum -c <<'SUMS'
ea234b8a6cc1fff9235d056dcf37ea150bdc44ad2b4e3785a075c0164462098a  _dl/lovtidend_text.tar.gz
11d8cd7d464f18af3c70ac2ea9498bb044fa4ff980ef41e12524d7d40e47356b  _dl/lti.tar.gz
f15b2418cca1e5e5907f374d8d605ee316fde942b9874cab1356de45ac87e595  _dl/current.tar.gz
41012abfb37feae0f2f3e229054a00f6cae8757243f2efb6a4397350cfd8432e  _dl/amendment_streams.tar.gz
c94f0bd2de1712d5128d142a5183d4b5e4dc74ed56cbfd56aa0d77411e5dbcd0  _dl/ground_truth_ENCUMBERED.tar.gz
SUMS

# 3. Restore (each archive already contains its top-level dir, except amendment_streams
#    which is loose files -> extract into data/).
for a in lovtidend_text lti current ground_truth_ENCUMBERED; do tar xzf _dl/$a.tar.gz -C data/; done
tar xzf _dl/amendment_streams.tar.gz -C data/

# 4. Sanity check: the gate should reproduce convergence ~0.344, guards green.
python -m source.eval.gate
```

(`ground_truth_ENCUMBERED.tar.gz` extracts to `data/ground_truth/`, which is gitignored —
keep it that way.)

## Re-backing-up (after producing new data)
- **From the sandbox** (no Dropbox write rights): tar new/changed data into
  `data/_backup/`, write an `inbox/to_dropbox/<name>.manifest.json` (see the
  2026-08-12 one for the format: `dest`, `files[]` with `path`+`sha256`, `log_file`,
  `log_entry`), and message the host session (`inbox/messages/sandbox-to-host_*.md`) to
  run `/backup`. The host drain uploads via rclone, verifies sha256, and appends the
  `log_entry` here.
- **From educloud** (if it has Dropbox write access): just
  `rclone copy data/_backup/ <remote>:pipelines/lovhistorie/ -P` and add a log line below.

## Upload log
- 2026-08-12: backed up lovhistorie working data (208M, 5 archives) to personal-dropbox:pipelines/lovhistorie/ — lovtidend_text.tar.gz (88M, the NB gazette harvest, 1033 issues/144k pages — PRIMARY scraped data), lti.tar.gz (94M, Lovtidend Avd.I 2001-2024 XML dump), current.tar.gz (8.6M, NLOD current answer key), amendment_streams.tar.gz (17M, amendments+pre2001+blocks+index), ground_truth_ENCUMBERED.tar.gz (1.1M, Lovdata Pro eval-only). Restore: tar xzf <archive> -C data/
