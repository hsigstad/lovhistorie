# Statutory law texts over time (gjeldende rett)

Can we reconstruct the exact text of Norwegian statutes as they read at past
dates (e.g. what a clause said in 2001-2005, before later amendments)? This
note records what is available, what is reconstructable, and the verified
limits. Separate from the Lovdata *court decision* corpus (a separate case-law project).

## Proof-of-concept validated (2026-08)

The fully-open pipeline was prototyped end-to-end on real data (sandbox):

- **Fetch**: NB Norsk Lovtidend is public-domain / open-everywhere, so the
  sandbox pulls it directly (no browser, no Feide). Content volumes are the
  "Avd. I. Lover og sentrale forskrifter" items (vs "register" = index);
  resolve a catalog id -> URN, then the IIIF manifest lists pages.
- **Text (no OCR on our side)**: each page has an ALTO-XML OCR at
  `https://api.nb.no/catalog/v1/metadata/{URN}/altos/{URN}_{page:04d}`
  (ABBYY FineReader). Parse `<String CONTENT>` -> clean text (oe/aa preserved).
- **Extract**: on a real pre-2001 issue (Lovtidend 1991 Nr. 3,
  `URN:...digitidsskrift_2015102680006_003`, 32 pp) the endringslov structure
  is present and findable: `§ X ... skal lyde:` + new text, `§ X oppheves`,
  `trer i kraft ...`.
- **Replay**: a small parser turns `§ X skal lyde: <text>` / `oppheves` into
  structured ops and applies them to a base document keyed by paragraf; real
  current NLOD law files load as the base (folketrygdloven -> 70 §-anchors).

Code committed to `source/` (runnable, live-validated):
- `source/scrape/nb_lovtidend.py` - find content volumes, resolve URN, IIIF page
  count, and **column-aware ALTO text** (reflow by TextBlock HPOS/VPOS). The
  reflow fixes the two-column interleaving (a cut-off § now flows continuously).
- `source/parse/endringslov.py` - parse `skal lyde` / `oppheves` into structured
  ops and replay onto a base. Whole-provision ops apply cleanly; ops carrying a
  sub-reference (e.g. `§4 pkt. b`) are captured with a `subunit` and **deferred,
  not applied**, so a sub-point repeal never wrongly deletes the whole §.

Remaining engineering (surfaced, not yet done) before a full reconstruction:
1. **Sub-provision (ledd/punktum) granularity** - apply the deferred `subunit`
   ops precisely, not just whole-§ replace (the known "messy minority").
2. **Full-document structuring** - instrument-boundary detection and
   **running-header dedup** (a naive `Nr.` split over-segments because page
   headers repeat the promulgation number); needed to assemble a whole
   instrument cleanly rather than a single amendment block.
3. **Law location** - to target a *named* current law, find its issue/page via
   the yearly register (index) volumes or NB full-text search.

Status: every pipeline *stage* is validated on real pre-2001 NB data; a complete
verified reconstruction of one specific current NLOD law is the next milestone
(needs 1-3 above).

## Quality — measured, not assumed

The main risk of an in-house build is quality (OCR of numbers, sub-provision
parsing), not access. The reconstruction is bracketed by the authoritative
current NLOD text, so quality is *measurable*: replay/extract must converge to
current, provision by provision, and any error surfaces as a localized mismatch.
Harness: `source/analysis/reconstruction_qa.py`.

First measured result (Lov om Oppgaveregisteret, LOV-1997-06-06-35; NB OCR of the
original 1997 text vs current NLOD, per provision):

- Only §8 was amended after 1997 (2019 law) — it correctly shows as different.
- Of the 8 unamended provisions: **7/8 match at >=0.98 similarity, mean 0.9942**;
  six are byte-perfect (1.000), §3 = 0.994.
- §1 initially scored 0.505 purely from a **running-header** OCR-layout artifact
  ("1087 / juni Lov nr. 35" spliced mid-sentence); deterministic header-stripping
  fixed it to 1.000 — confirming the residual is layout, not OCR *accuracy*.
- §9 (a cross-reference list) flagged at 0.960 — exactly the kind of provision a
  human should eyeball; the harness doing its job.

Takeaway: on real pre-2001 gazette OCR the fidelity is ~99%+ and the residual is
localizable/fixable (running-header dedup + a few flagged provisions), with a
built-in per-provision QA number. Older/fraktur laws will score lower and need
more review; use the current-text endpoint (and Lovdata Pro spot-checks) as the
oracle to quantify per law before relying on it.

## Option 1: build from enactment (the self-contained route)

To track a law's history you need a *correct base at the start of your sample* -
seeding with current text reproduces the silent-baseline flaw at whatever year
the sample starts. Two ways to get that base:
1. **Original enactment + every amendment, replayed forward** - correct at every
   date, no snapshot dependency.
2. **A consolidated snapshot at the sample start** + replay forward - lighter on
   amendments, but needs a snapshot we do not have (Lovdata Pro / printed).

Because we hold **no** historical snapshot, **Option 1 is the self-contained
route**: it uses one public-domain source (Lovtidend) we already reach, and
constructs the base from the enactment instead of obtaining a gated snapshot.
Which provisions the base actually governs: those *not* amended in-sample (whole
sample) and any provision *before* its first in-sample amendment; provisions
amended in-sample self-correct from their first full-text restatement.

**Feasibility confirmed end-to-end on a real law (Lov om Oppgaveregisteret,
LOV-1997-06-06-35):**
- *Recipe* from current NLOD annotations (`source/parse/nlod_recipe.py`): enacted
  1997-06-06 nr 35, exactly **one** amending law (2019-06-21 nr 32) after the
  capture-then-filter drops the res./forskrift numbers.
- *Locate* via NB full-text search (`nb_lovtidend.search`): the law title returns
  the 1997 Lovtidend Avd. I volume (and Stortingsforhandlinger = forarbeider).
- *Fetch original* (`nb_lovtidend.find_page` + ALTO): pulled the original 1997
  §§ text from NB (public-domain), e.g. the full original § 1 Formål / § 2
  Organisasjon wording.
- *Validate*: the NB-OCR original § 1 is **verbatim-identical** to the current
  NLOD § 1 (§ 1 was never amended), confirming OCR + extraction are accurate.

So Option 1 works with only the accessible public-domain sources. Coverage/caveats:
NB Lovtidend covers **1877+** (pre-1877 originals - Grunnlov 1814, Norske Lov
1687, a few early-1800s - need another source, but are a tiny set); current-NLOD
annotations give the amendment list for *surviving* provisions (fully-repealed
ones need the endringslov "Endrer lov/..." back-references for total
completeness); pre-2001 amendments need locate+OCR while 2001+ are already
machine-readable, so the OCR burden is just the pre-2001 slice.

**The gate is enactment >= 1877, not the decade - old laws are traceable but
harder** (verified on skjønnsprosessloven, LOV-1917-06-01-1, which NB holds):
- *Orthography drift breaks title location*: the 1917 text spells it
  "ekspropriationssaker" / "Love" / "Afdeling"; a modern-title full-text search
  missed the 1917 volume, the period spelling found it. Locate old laws by
  period spelling or by date (year + law nr via the register), not modern title.
- *Much more history*: skjønnsprosessloven has ~49 amending laws over a century
  (vs Oppgaveregisteret's 1) - more fetch/OCR/parse, though the pre-2001 slice
  is still bounded and the recipe lists it.
- *Renumbering/restructuring* over decades makes cross-version provision matching
  harder. OCR itself is fine from ~1900 (antiqua); only pre-~1880s fraktur is rough.

Remaining to a *fully replayed* single law: fetch + parse each amendment's
"skal lyde" text and run the replay to check final == current NLOD (needs the
robust ledd-level endringslov parser). The enacting-act base and the locate step
are done.

## Sources in hand

Local data archive (`data/laws/`):

- `gjeldende-lover.tar.bz2` (5.8 MB) - current consolidated statutes, 756 laws,
  one XML per law keyed `nl-YYYYMMDD-NNN`. Each provision carries its full
  amendment chain inline: "Endret ved lov 25 nov 2022 nr. 86 (i kraft 25 nov
  2022 iflg. res. ...)". So per provision we have the list of amending laws and
  their entry-into-force (ikrafttredelse) dates, not just promulgation dates.
- `gjeldende-sentrale-forskrifter.tar.bz2` (20 MB) - current central
  regulations, same structure.
- `lovtidend-avd1-2001-2024.tar.bz2` (65 MB) + `lovtidend-avd1-2025.tar.bz2`
  (2.6 MB) - Norsk Lovtidend avd. I, one XML per promulgated act
  (`lti/YYYY/nl-...` and `sf-...`). This is the amendment (delta) stream.
- `alle_lovdata.zip` (191 MB) - the same Lovtidend delta stream by year
  (`alle_lovdata/lovtindend-avdeling1/YYYY/`), lover + forskrifter. Not
  historical consolidated versions.

Key fact verified in the data: Norwegian amendment laws (endringslover)
**re-state the full new wording** of every provision they touch ("§ X skal
lyde: <complete new text>"), not a word-level diff. Checked on
`lov 2022-11-25-86`: 42 provisions, all full restatements, 1 repeal, 2 new
sections, 0 word-level edits. Word-level edits ("ordet A erstattes med B")
exist but are a minority.

## What this makes reconstructable

Because every post-2001 change is a full-text restatement with a dated
ikrafttredelse, the text in force on any date from 2001 on can be reconstructed
by replaying amendments in in-force-date order onto a base. The delta stream
covers **2001 onward only**; laws enacted before 2001 have their original text
and pre-2001 amendments outside this window.

## Off-the-shelf: sondreskarsten/norwegian-laws

`github.com/sondreskarsten/norwegian-laws` (Sondre Skarsten; MIT code, NLOD 2.0
data; source = free Lovdata public API) already builds this. The `law-history`
branch is one Markdown file per law (`lover/lov-YYYY-MM-DD-NN.md`,
`forskrifter/...`) with **16,993 backdated git commits**, each commit dated to
the real ikrafttredelse. `git log -p -- lover/lov-1997-02-28-19.md` gives
per-clause diffs over time; checking out any date gives the consolidated text
as it read then. Coverage: 5,880 documents, ~39,090 dated amendments. **Central
regulations (forskrifter) are versioned exactly like laws, not just laws** -
the `law-history` branch carries ~5,122 `forskrifter/forskrift-*.md` files
alongside the lover, each with the same backdated per-amendment diffs, and the
zip's `historie/` mirrors this (5,123 forskrift changelog files). Auto-updates
daily; even carries future-dated commits for passed-but-not-yet-in-force laws
(e.g. a 2028 valglov change).

### Our copy: the source zip (data preserved) vs a full mirror

A copy of `norwegian-laws-main.zip` (47 MB) is in the local data
archive. It is a GitHub source-zip of the **main
branch only** (no `.git`, no `law-history` branch), but it does contain the
reconstruction data in flat form: `historie/*.md` = per-provision dated
amendment wordings ("YYYY-MM-DD - lov/... / § X skal lyde: <full new text>")
for 5,542 lover + 5,123 forskrifter, back to the 2001 floor (e.g. aksjeloven
earliest 2001-12-21), plus current `lover/`/`forskrifter/` and the loader/
publisher code. So the point-in-time amendment text is already backed up.

What the zip does NOT give versus a full mirror/bundle: the pre-assembled git
`law-history` branch (so `git checkout <date>` yields the whole consolidated
law as of that date; from the zip you assemble per-date text yourself from
`historie/` + current text, same silent-baseline caveat); and updatability (the
zip is a one-time snapshot, a mirror stays current). A mirror/bundle backup
could be produced if we want those; otherwise the zip suffices for data preservation.

Sondre also maintains `tidybrreg` (R interface to Brønnøysund/Enhetsregisteret)
and `stortingsverv-parser`.

### Verified capability and limits (checked Aug 2026)

- **History floor is 2001-01-01, not earlier.** Oldest commit is
  "Grunnlinje: 5880 gjeldende lover" dated 2001-01-01. Commits by decade:
  2000s 2,695 / 2010s 6,542 / 2020s 7,756; nothing before 2000. This matches
  the hard boundary: the machine-readable Lovtidend delta stream starts 2001.
- **Point-in-time text is genuine, not current text stamped with old dates.**
  For the folketrygdloven trygdeavgift nedre grense, the reconstruction shows a
  correct annual series: 2003 = 23 000, 2004 -> 29 600, 2010 = 39 600, ...,
  2026 = 99 650, each set at the right ikrafttredelse.
- **But the 2001 baseline is a placeholder = current text.** The same
  provision reads 99 650 (the 2026 value) at the 2001-01-01 baseline commit,
  then jumps to 23 000 at its first real post-2001 amendment. So the
  `Grunnlinje` commit dumps current consolidated text dated 2001, and the
  dated amendment stream overwrites each provision forward from its first
  post-2001 restatement.
- **Consequence / trap.** For any provision, the text shown between 2001-01-01
  and its *first* post-2001 amendment equals current text and may be wrong.
  The error is **silent** (plausible modern wording, not a gap). Densely
  amended provisions (annual thresholds, frequently touched sections) are
  reliable back to ~2001-2002; rarely amended provisions can be wrong across a
  long early window. For any 2001-2005 analysis, confirm the target provision
  had an amendment at or before the date of interest before trusting the text.

## Pre-2001 and the clean fix

True point-in-time text before ~2001 (and a correct 2001 base for
rarely-amended provisions) is not derivable from the free/delta sources. To
close it:

- **Lovdata Pro / Lovdata API.** Lovdata keeps historical consolidated versions
  of laws back to **1 Jan 1998** (paragraphs since 1999). The free public API
  (`api.lovdata.no`, NLOD 2.0) serves **current text only**; historical
  versions are Pro-gated. Confirmed: a folketrygdloven historical URL returns
  "ikke tilgjengelig paa Lovdatas aapne sider ... krever abonnement" (the
  Grunnlov is a public exception). The paid API has the endpoints
  (`/documentHistory` = version list per document; `/baseHistory` = documents
  changed in a date range; `/structuredRules/get` = fetch a document), behind
  an API account. **Option to consider asking Lovdata for** (not a firm ask):
  a **consolidated snapshot "gjeldende lover per 1.1.2001"** and/or **historical
  versions back to 1998** - either removes both the 2001 floor and the
  baseline-placeholder trap. Could fold into the pending Lovdata agreement or
  raise with marked@lovdata.no.
- **Free pre-2001 route via Nasjonalbiblioteket (2026-08).**
  The pre-2001 gap is closable without Lovdata Pro, at the cost of OCR:
  - *Base anchors*: NB-digitized printed **Norges Lover** editions - full
    consolidated snapshots at each print year. The main *Norges Lover 1687-YYYY*
    compilation is **comprehensive** (all laws of general practical
    significance), not a subset - the small subsets are the sector "lovsamling
    for X" editions (and probably what the
    `nb.no/.../URN:NBN:no-nb_digibok_2023030748057` link is). **The 1687-2001
    edition (updated Jan 2002, ISBN 9788205298941) is effectively the 2001
    snapshot itself** - OCR the book, strip the small Jan-2002 tail, done. NB has
    the series digitized (confirmed 1685-1991/1992, 1687-2006/2007, 1687-2014);
    in-copyright volumes are access-restricted (Norwegian IP / library / Feide
    access). Use a base **at or before 2001** since replay is
    forward-only; the 2006 edition is after 2001 and less useful as a base.
  - *Delta stream*: **`norgeslover.no/lovtidend-arkiv.php`** - scanned-PDF
    archive of **Norsk Lovtidend 1877-2016** (avd. I laws + central regs, avd.
    II local; 1,524 issues), digitized by NB. This is the pre-2001 amendment
    stream the Sondre repo and the API dumps lack. Caveats: scanned PDFs (need
    OCR + endringslov parsing), some gap years (1888, 1976, 1978, ...).
  - *Recipe*: printed edition as base at year Y + Lovtidend deltas rolled
    forward = pre-2001 point-in-time text for the covered laws. Labor-heavy
    (OCR) but free; an alternative to Lovdata Pro historical versions.
  - *Do we scan it ourselves?* Probably not by hand - NB has digitized nearly
    all Norwegian books, so the 2001 edition is likely already scanned. BUT I
    could not confirm it in NB's public catalog (ISBN 9788205298941 -> 0 hits;
    adjacent editions 1991/2006/2014/2017 surface, 2001-2003 do not). And it is
    in-copyright: not freely downloadable - read via Norwegian-IP/library, bulk
    OCR-text via NB research/DH-lab or a request (a Norwegian university library can facilitate).
    Either way the book is ~3,000 pages of dense two-column legal text, so
    producing clean machine-readable statute text is a real OCR project, not a
    quick step. Effort ladder, easiest first: (1) Lovdata Pro "per 1.1.2001"
    (clean structured data, skips the book); (2) ask NB / a university library for the digitized
    edition + text access; (3) 1992 digitized base + roll forward with
    Lovtidend 1992-2001 (adds ~9 yrs of scanned-Lovtidend OCR); (4) self-scan a
    physical copy (fallback; one book but 3,000 dense pages). Self-scanning is
    the fallback, not the plan.
- **`norgeslover.no/lover`** - free unofficial portal ("Ikke offisiell kilde",
  data "fra Lovdata, Stortinget, Regjeringen") with a per-law `Historisk
  visning` (client-side "as-of-date" timeline modal). **Checked (2026-08): same
  2001 floor as the Sondre repo, not a free route to Lovdata's 1998+ historical
  versions.** Folketrygdloven's embedded timeline has 256 version dates whose
  structure is identical to Sondre's - earliest is the 1997-05-01 ikrafttredelse
  marker, then it jumps to a **2001-01-01 baseline** and all real versions are
  2001+, with future-dated versions (2026-10, 2027-01) for not-yet-in-force
  changes. So it is the same 2001+ reconstruction (very likely the same current-
  text-as-baseline behaviour), just with a browsable UI. No shortcut for pre-2001.
- Related repos: `HNygard/norsk-lovtidend` (Lovtidend copy + scripts, delta
  stream), `pere/lovdata-gjeldende-lover` (Codeberg; diff-friendly current
  laws, git history only from 2025-11), `NationalLibraryOfNorway/`
  `lovdata-public-conversion-script`.

## Licensing / ownership (decision-driver)

If we need a dataset we **own and can freely reuse/publish**, that argues against
the Lovdata Pro route and for the open route, even at higher effort:

- **Lovdata Pro "per 1.1.2001" / historical versions** would come under Lovdata's
  commercial licence + database right - the deliverable likely carries reuse
  restrictions (can't freely publish/share the reconstructed corpus or reuse
  across future projects). Convenient but encumbered.
- **Open route is fully ownable.** Norwegian **statutory text is public domain**
  (aandsverkloven sec. 14 exempts laws, regulations, court decisions, official
  acts). **Norsk Lovtidend** is the official gazette = public domain. Lovdata's
  **free** current dumps are **NLOD 2.0** (reuse incl. redistribution allowed).
  A reconstruction from *(NLOD current text + public-domain Lovtidend)* is a
  dataset we own outright.
- **Do NOT source from the *Norges Lover* book.** The law text inside is public
  domain, but the NB scan is access-restricted (Feide reading licence, images
  via IIIF, no OCR text exposed) and the *edition* carries editorial copyright -
  bulk extraction is a terms problem and drags in encumbered editorial material.
  Source base + deltas from the **public-domain Norsk Lovtidend** instead (NB
  periodical / norgeslover.no front-end) - same information, clean provenance.
- **NB access flag CONFIRMED (2026-08).** Norsk Lovtidend on NB is
  `license: publicdomain`, `viewability: ALL`, `accessAllowedFrom: EVERYWHERE`
  (vs the *Norges Lover* book: `copyrighted`, viewability `NONE`, Feide-only).
  ~27,391 issues back to the 1870s. So the gazette is open to anyone, no login /
  no Norwegian-IP gate - **the sandbox can fetch it directly**; no browser
  control needed for this source. Sample pre-2001 issue URN:
  `URN:NBN:no-nb_digitidsskrift_2015111681020_001` (1974). IIIF manifest per
  item for page images.
- **OCR may be largely unnecessary.** The item `actions` array is
  `["download","text"]` - NB exposes OCR/text for these public-domain issues
  (the restricted book had only `jp2` images). So the pipeline likely starts
  from NB's machine-readable text (to clean up), not raw scans; exact text
  endpoint TBD (IIIF annotations / DH-lab text service) at build time.
- **Revised division of labour**: because the source is open-everywhere, the
  sandbox can prototype fetch + text-extract + endringslov-parse + replay
  end-to-end without a controlled browser. (Confirm reuse specifics with a
  Norwegian university library / NB; informed guidance, not legal advice.)

## Bottom line

The Sondre repo buys **no information beyond (current Lovdata dumps + Norsk
Lovtidend 2001+)** - it is those two inputs reconstructed into a dated git
history, so it inherits their exact limits (2001 floor, current-text-as-baseline;
confirmed: aksjeloven's 2001 baseline blob is byte-identical to its 2026 current
blob despite 94 amendments). It saves building the replay engine; that is all.

For a 2001-onward window it is likely all we need, respecting the baseline
caveat. Genuine pre-2001 (and a correct early-window base) needs a *different*
input: either **Lovdata Pro historical versions** (back to 1998, clean but
Pro-gated) or the **free NB route** above (Norges Lover printed base + NB
Lovtidend PDF archive, OCR-heavy).
