"""The reconstruction entrypoint — the ONLY thing the autonomous loop improves.

INTENT: expose one function, `reconstruct(target_law, as_of)`, that rebuilds a law's
    provisions from PUBLIC-DOMAIN inputs only — the enactment base (gazette) + the
    ordered Lovtidend amendment ops — and never from the current/final consolidated
    text. The eval gate (source/eval/gate.py) drives this toward convergence.
REASONING: keeping the whole reconstruction behind one import boundary lets the gate
    prove input-isolation mechanically: this module (and everything it imports) must
    NOT import the harness package `source.eval`, which is where the answer key lives.
    Break that and the gate's static guard fails — the anti-gaming contract in code.
ASSUMES: amendments.load_for gives ordered ops; replay applies them; enactment_base
    supplies the starting text. enactment_base is the current frontier of the work
    (see its docstring) — today it returns {} so convergence measures amendments
    alone; wiring the gazette base is the main lever to raise it.
"""
from __future__ import annotations

import functools
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

from source.parse import amendments, replay

_REPO = Path(__file__).resolve().parents[2]
_ENACTMENT = _REPO / "data" / "enactment"
_SEGMENTS = _REPO / "data" / "segments.jsonl"
_FROZEN_DIR = _REPO / "data" / "lovtidend_text"
_PARA = re.compile(r"§\s*(\d+(?:-\d+)?)([a-z])?")
# Recover a SPACED single-letter suffix ('§ 38 b første ledd', 'Ny § 15 a skal lyde') that the
# no-space _PARA drops. A genuine suffix is a lone letter FLANKED by a space and FOLLOWED by a
# real word — which excludes (a) the ordinal ABBREVIATIONS the `target` field uses ('§ 11 f' =
# første, '§ 11 t' = tredje — a bare trailing letter with no following word) and (b) the
# preposition 'i' ('§ 5 i loven'; Norwegian statutes skip 'i' as a suffix letter anyway).
_SPACED_SUFFIX = re.compile(r"§\s*\d+(?:-\d+)?\s+([a-hj-z])(?=\s+[a-zæøå])")


def _para_at(s: str, m: "re.Match") -> str:
    """Build '§N' / '§Nx' from a _PARA match `m` in `s`, recovering a spaced suffix at m.start()."""
    suf = m.group(2)
    if not suf:
        sm = _SPACED_SUFFIX.match(s, m.start())
        if sm:
            suf = sm.group(1)
    return "§" + m.group(1) + (suf or "")

# A provision-body HEADING at the start of a string: '§ 5-8 a.Opplysninger…' -> '§5-8a'.
# The suffix letter is frequently rendered/OCR'd with a space before it ('§ 5-8 a.'), which
# _PARA drops (it captures '§5-8'). The TRAILING PERIOD anchors the letter as a genuine
# suffix, so a following word or Norwegian preposition ('§ 5 i loven', '§ 27 første ledd' —
# no period) can never be mistaken for one. Digits, optional space+single letter, period.
_HEAD_ID = re.compile(r"§\s*(\d+(?:-\d+)?)\s*([a-z])?\.")


def _heading_id(s: str | None):
    """Canonical id from a period-anchored provision heading at the START of `s`, with any
    space before the suffix letter removed ('§ 5-8 a.' -> '§5-8a'). None if `s` does not
    open with such a heading. This is the ONLY place a spaced suffix is accepted — and only
    because the period makes it unambiguous."""
    if not s:
        return None
    m = _HEAD_ID.match(s.lstrip())
    return "§" + m.group(1) + (m.group(2) or "") if m else None


def _clean_para(s: str | None):
    """First '§ N' anywhere in `s` -> '§N' (or '§Nx' for a genuine spaced suffix — '§ 38 b
    første ledd' -> '§38b'). For target fields that NAME the provision ('§ 1-9', '§ 6 n').
    NOT for new_text bodies — their first § is often a cross-ref."""
    if not s:
        return None
    m = _PARA.search(s)
    return _para_at(s, m) if m else None


def _leading_para(new_text: str | None):
    """'§ N' ONLY if new_text opens with its own heading ('§ 4.Vedtak…' -> '§4';
    '§ 5-8 a.…' -> '§5-8a'). Start-anchored so a body cross-reference ('Vedtak etter
    §§ 2, 3…') never matches. Prefers the period-anchored heading id (recovers a spaced
    letter suffix); falls back to the bare '§ N' form for headings without a period."""
    if not new_text:
        return None
    st = new_text.lstrip()
    m = _PARA.match(st)
    return _heading_id(new_text) or (_para_at(st, m) if m else None)


def _op_para(d: dict):
    """Clean paragraf id: the fields that NAME the target first; new_text's own
    leading heading only as a last resort (never a mid-body §-reference)."""
    return (_clean_para(d.get("paragraph"))
            or _clean_para(d.get("target"))
            or _clean_para(d.get("instruction"))
            or _leading_para(d.get("new_text")))


# Split points: line-start provision headings '§ N.' (spaced suffix tolerated: '§ 5-8 a.').
_BLOCK = re.compile(r"(?m)(?=^\s*§\s*\d+(?:-\d+)?\s*[a-z]?\.)")


def _split_block(new_text: str):
    """A '§ X skal lyde' / 'Kapittel N skal lyde' new_text can carry SEVERAL
    provisions ('§ 1-1.…\\n§ 1-2.…'). Split on line-start '§ N.' headings into
    [(para, piece_with_heading)] so each provision is set from its own slice, not all
    dumped onto the first. Body cross-references ('… jf. § 2-2') are mid-line and
    never split. Returns [] if there is no leading heading."""
    pieces = []
    for part in _BLOCK.split(new_text):
        para = _heading_id(part)
        if para:
            pieces.append((para, part.strip()))
    return pieces


# A whole-CHAPTER add ("4de kapitel. <title> § 38 a. <title> <body> § 38 b. …") carries several
# NEW provisions inline. The op extractor emits this as ONE op (para "§kapittelN"), burying §38a/
# §38b; splitting it here recovers them.
_CHAP_HEAD = re.compile(r"^\s*(?:\d+\s*(?:de|te|dje|ne|nde)?\.?\s+kapi(?:t|tt)el|"
                        r"(?:nytt?\s+)?kapittel\s+\d+)", re.I)
# Provision-heading candidate inside a chapter block: '§ N[-M][letter].' — NB no space/capital
# required after the period (OCR renders it both "§ 38 a. Virkeområde" and "§ 38 a.Virkeområde").
_CHAP_HEADING = re.compile(r"§\s*(\d+)(?:-(\d+))?\s*([a-zæøå])?\s*\.")


def _prov_sortkey(pid: str):
    """(chapter, section, suffix) order key for a provision id like §38a / §5-8a."""
    m = re.match(r"§(\d+)(?:-(\d+))?([a-zæøå])?$", pid)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), m.group(3) or "")


def _split_chapter(new_text: str):
    """[(para, piece_with_heading)] for the provisions inside a chapter-add block; [] if none.

    Splits on '§ N[letter].' headings, but keeps ONLY the strictly-ASCENDING run of them (chapter
    provisions ascend: §38a→§38b; body cross-references like 'jf. § 2-2' are lower/out-of-order and
    are skipped). This is robust to OCR spacing after the period — where the old capital-after-space
    boundary silently failed on the authoritative external stream ("§ 38 a.Virkeområde")."""
    cands = []
    for m in _CHAP_HEADING.finditer(new_text):
        pid = _heading_id(new_text[m.start():])
        k = _prov_sortkey(pid) if pid else None
        if k:
            cands.append((m.start(), pid, k))
    kept, last = [], None
    for pos, pid, k in cands:
        if last is None or k > last:          # strictly ascending → real chapter provision
            kept.append((pos, pid)); last = k
    pieces = []
    for i, (pos, pid) in enumerate(kept):
        end = kept[i + 1][0] if i + 1 < len(kept) else len(new_text)
        pieces.append((pid, new_text[pos:end].strip()))
    return pieces


# Derived amendment stream re-parsed from the LTI acts (source.scrape.lti_amendments):
# recovers omnibus sections the external amendments stream dropped. A DERIVED public-domain
# jsonl.gz (NOT an LTI XML, NOT the answer key) — read here exactly like amendments.DATA;
# the LTI XMLs themselves are only ever touched by the offline build script (anti-gaming
# lesson #7). Absent → skipped.
_LTI_AMEND = amendments.DATA.parent / "lti_amendments.jsonl.gz"
# Derived LLM sub-provision op stream (source.llm.amend): the correctly-attributed +
# correctly-bounded ledd/punktum replace/insert ops the regex parser over-captures or
# mis-files. Boundaries-only (payloads are verbatim source slices), read exactly like the
# other derived streams; the ledd engine is idempotent (align) so overlap is safe. Absent → skipped.
_LLM_AMEND = amendments.DATA.parent / "llm_amendments.jsonl.gz"
# Derived omnibus-recovery stream (source.scrape.build_omnibus): secondary-target sections the
# external/LTI streams mono-collapsed onto an omnibus act's primary law, re-recovered via the
# format-agnostic LLM localizer + verbatim-anchored op extractor. Same schema; dedup below
# guards the boundary so an op present in another stream is not applied twice. Absent → skipped.
_OMNIBUS = amendments.DATA.parent / "omnibus_recovered.jsonl.gz"
# Derived pre-2001 gazette-OCR recovery (source.scrape.build_gazette): the same localize-then-verify
# path applied to amending-act bodies already on disk in data/lovtidend_text — recovers pre-2001
# secondary-target/flat-omnibus amendments the regex gazette parser missed, no new harvest. NB: the
# current-dump register undercounts these (many touch since-superseded text), so they help POINT-IN-
# TIME more than convergence-to-current. Absent → skipped.
_GAZETTE = amendments.DATA.parent / "gazette_recovered.jsonl.gz"
# Derived PRE-APPLIED stream (source.scrape.build_applied): for provisions whose sub-provision ops
# the deterministic ledd engine can't apply (OCR base lacks ledd markers), an OFFLINE pass replays
# them with the LLM applicator (source.llm.apply_op — localize span + splice, span-guarded) and bakes
# the FINAL provision text as a whole-provision op (carries its '§ N.' heading → replay overwrites via
# the startswith('§') path, high-confidence). Dated at the provision's last op so it applies last.
# Runtime just reads it (no LLM at runtime — rule 3). Absent → skipped.
_APPLIED = amendments.DATA.parent / "applied_ops.jsonl.gz"
_POINTER = amendments.DATA.parent / "pointer_ops.jsonl.gz"


# Streams in application order, each tagged (rank, is_recovery). rank preserves the original
# per-stream precedence for dedup (first-wins); is_recovery drives the gap-fill gate. PRIMARY =
# external + LTI-reparse + LLM sub-provision; RECOVERY = LLM omnibus + pre-2001 gazette.
def _ranked_streams():
    return [(amendments.DATA, 0, False), (_LTI_AMEND, 1, False), (_LLM_AMEND, 2, False),
            (_OMNIBUS, 3, True), (_GAZETTE, 4, True)]


def _stream_sig():
    """(path, exists+mtime) per stream — the cache key, so _grouped re-reads whenever a stream file
    changes or is toggled aside (the with/without-recovery A/B relies on this auto-invalidation)."""
    return tuple((str(p), p.stat().st_mtime if p.exists() else None) for p, _, _ in _ranked_streams())


@functools.lru_cache(maxsize=4)
def _grouped(_sig):
    """{target_law: [(rank, is_recovery, row), …]} — read each stream ONCE and group by law, so
    load_ops(law) is a dict lookup instead of a full rescan of the 99k-row national stream PER law
    (the build/A/B O(laws×streams) blowup). Rows sorted by rank to preserve stream precedence."""
    groups = defaultdict(list)
    for path, rank, is_recovery in _ranked_streams():
        if not path.exists():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                tl = d.get("target_law")
                if tl:
                    groups[tl].append((rank, is_recovery, d))
    for tl in groups:
        groups[tl].sort(key=lambda x: x[0])
    return groups


# Source-only corroboration for the overwrite gate (load_ops). A RECOVERY op may OVERWRITE a
# provision a PRIMARY stream already owns ONLY if the amending act explicitly states the FULL new
# provision — instruction "§ <id> skal lyde: …" with NOTHING between the id and "skal lyde" (so
# sub-provision ops "§X annet ledd … skal lyde" are excluded) and a substantial verbatim payload.
# This is the §36-class genuine rewrite (avtaleloven 1983) overwriting the stale 1918 base, decided
# from the public amending-act text alone (no answer key, G1-safe). Everything else stays gap-fill.
_WHOLE_REPLACE = re.compile(r"^\s*§\s*\S+\s+skal\s+lyde\b", re.I)


def _overwrite_ok(base: dict, payload: str) -> bool:
    instr = base.get("instruction") or ""
    return (bool(_WHOLE_REPLACE.match(instr))
            and base.get("change_type") in ("change", "replace")
            and bool(payload) and len(payload) > 80)


def load_ops(target_law: str, include_applied: bool = True):
    """Ordered ops for a law WITH change_type + clean para. change_type ∈ {change, add, repeal,
    renumber, move, unknown}; renumber/move/unknown are left for replay to flag, not fabricate.
    Multi-provision new_text blocks are expanded to one op per provision.

    RECOVERY streams FILL GAPS ONLY: a recovered op is applied only if the PRIMARY streams provide
    no op for that provision — recovered content is noisier (OCR/LLM), so overriding a primary-owned
    provision CORRUPTED clean-base laws (−15 vphl / −10 foreld in the A/B); gap-fill keeps the real
    wins (new §s primary misses, e.g. avtaleloven §9a) without overwriting. dedup by
    (act, para, date, instruction). Rows come pre-grouped by law (see _grouped) for speed."""
    ops, seen, primary_paras = [], set(), set()
    for rank, is_recovery, d in _grouped(_stream_sig()).get(target_law, []):
        base = {
            "change_type": d.get("change_type"),
            "instruction": d.get("instruction"),
            "date": d.get("date_in_force_resolved") or d.get("date_in_force"),
            "act": d.get("act_refid"),
        }
        new = d.get("new_text")
        if new and _CHAP_HEAD.match(new.lstrip()):        # whole-chapter add → per-§ pieces
            pieces = _split_chapter(new)
        elif new and new.lstrip().startswith("§"):
            pieces = _split_block(new)
        else:
            pieces = []
        emit = pieces if pieces else [(_op_para(d), new)]
        for para, payload in emit:
            if is_recovery and para in primary_paras and not _overwrite_ok(base, payload):
                continue              # recovery fills gaps only — unless a corroborated whole-§ rewrite
            key = (base["act"], para, base["date"], base["instruction"])
            if key in seen:
                continue
            seen.add(key)
            if not is_recovery and para:
                primary_paras.add(para)
            ops.append({**base, "para": para, "new_text": payload})
    # PRE-APPLIED whole-provision results (offline LLM applicator). Appended last so a same-date tie
    # resolves in their favour (stable sort); each carries its '§ N.' heading → replay overwrites.
    # Excluded when building the applied stream itself (include_applied=False) to avoid a cycle.
    if include_applied and _APPLIED.exists():
        with gzip.open(_APPLIED, "rt", encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                if d.get("target_law") != target_law:
                    continue
                ops.append({
                    "change_type": d.get("change_type", "change"),
                    "instruction": d.get("instruction"),
                    "date": d.get("date_in_force_resolved") or d.get("date_in_force"),
                    "act": d.get("act_refid"), "para": d.get("paragraph"),
                    "new_text": d.get("new_text"),
                })
    # POINTER-consolidated provisions (source.scrape.build_pointer): the LLM-holistic reconstruction of
    # provisions the ledd engine mangles. Appended AFTER applied so a same-date tie resolves in their
    # favour (stable sort) — pointer_apply supersedes the per-op apply_op fallback. Each carries its
    # '§ N.' heading → replay overwrites deterministically. Same include_applied gate (offline-baked).
    if include_applied and _POINTER.exists():
        with gzip.open(_POINTER, "rt", encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                if d.get("target_law") != target_law:
                    continue
                ops.append({
                    "change_type": d.get("change_type", "change"),
                    "instruction": d.get("instruction"),
                    "date": d.get("date_in_force_resolved") or d.get("date_in_force"),
                    "act": d.get("act_refid"), "para": d.get("paragraph"),
                    "new_text": d.get("new_text"),
                })
    # S3b: UNION the corpus amend_op rows with the stream ops. The segments corpus holds ~951
    # pre-2001 amending acts absent from the post-2001 LTI stream; fallback-only (used only when
    # the streams were empty) silently DROPPED them for any law that also had post-2001 ops.
    # Dedup by amending act — where both sources have an act, keep the stream's (maturer) extraction
    # and add only segments acts the streams don't cover. (Empty-stream laws behave as before.)
    seg_ops = _amend_ops_from_segments(target_law.split("/")[-1])
    if seg_ops:
        have = {o.get("act") for o in ops}
        ops = ops + [o for o in seg_ops if o.get("act") not in have]
    ops.sort(key=lambda o: (o["date"] or "", o["act"] or ""))
    return ops


_OPKIND_CT = {"set_text": "change", "insert": "add", "repeal": "repeal",
              "renumber": "renumber", "word_replace": "word_replace"}
_SKAL_LYDE = re.compile(r"skal\s+ly[dd]e\s*:?\s*", re.I)


@functools.lru_cache(maxsize=1)
def _amend_ops_by_target() -> dict:
    """{amended-law datokode: [amend_op rows]} from the flat corpus. The op's own `datokode` is the
    AMENDING act; `target` is the amended law. Public corpus only (G1-safe)."""
    out = defaultdict(list)
    if not _SEGMENTS.exists():
        return out
    for line in open(_SEGMENTS, encoding="utf-8"):
        r = json.loads(line)
        if r.get("klass") == "amend_op" and r.get("target"):
            out[r["target"]].append(r)
    return out


def _amend_ops_from_segments(datokode: str) -> list:
    """Deterministic ops for `datokode` assembled from the corpus `amend_op` rows: parse the § from
    the instruction, map op_kind->change_type, slice the payload (text after 'skal lyde:'). In-force
    date = the amending act's own date (datokode); a delt-ikraftsetting refinement is future work."""
    ops = []
    for r in _amend_ops_by_target().get(datokode, []):
        fr = _frozen(r["issue_id"])
        if not fr:
            continue
        text = fr[r["start"]:r["end"]]
        m = _PARA.search(text)
        para = _para_at(text, m) if m else None
        kind = r.get("op_kind")
        payload = ""
        if kind in ("set_text", "insert"):
            parts = _SKAL_LYDE.split(text, maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ""
        amend_dk = r.get("datokode") or ""
        date = "-".join(amend_dk.split("-")[:3]) if amend_dk.count("-") >= 3 else None
        ops.append({"change_type": _OPKIND_CT.get(kind, "unknown"),
                    "instruction": text.split("\n", 1)[0][:120], "date": date,
                    "act": amend_dk, "para": para, "new_text": payload or None,
                    # word_replace carries the verbatim term pair ("ordet «X» erstattes med «Y»" /
                    # "«X» strykes" -> to=""); replay applies it as a str.replace on the addressed §.
                    "from": r.get("from"), "to": r.get("to")})
    return ops


# Parallel snapshot-base directory for the SEPARATE 2005-baseline pipeline (2005 -> today). A law's
# 2005 file (data/enactment_2005/<dk>.json) carries base_as_of="2005-12-31" + the Lovdata-CD-2005
# provisions; laws with no 2005 file (e.g. post-2005-enacted vphl/tjeneste) fall back to the enactment
# base. This never touches the from-enactment pipeline (base="enactment", the default).
# See docs/notes/reconstruction_2005_baseline.md.
_ENACTMENT_2005 = _ENACTMENT.parent / "enactment_2005"


def _base_path(target_law: str, base: str = "enactment") -> Path:
    """Resolve the base-json path for `base` ∈ {"enactment","2005"}. base="2005" prefers the 2005
    snapshot file, falling back to the enactment base when a law has no 2005 snapshot."""
    dk = target_law.split("/")[-1]
    if base == "2005":
        p = _ENACTMENT_2005 / f"{dk}.json"
        if p.exists():
            return p
    return _ENACTMENT / f"{dk}.json"


def enactment_base(target_law: str, base: str = "enactment") -> dict:
    """{paragraf_id: text} of the law's base — AS ORIGINALLY ENACTED (base="enactment") or the
    Lovdata-CD-2005 snapshot (base="2005").

    Reads the cached, public-domain base built OFFLINE (data/enactment/<dk>.json or
    data/enactment_2005/<dk>.json). No network, no OCR, no current text at runtime — rule 3.

    HARD RULE: the cache must come from Norsk Lovtidend (enactment) or the out-of-DB-protection
    Lovdata CD (2005), NEVER from the current consolidated text. Laws not yet built return {}.
    """
    f = _base_path(target_law, base)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8")).get("provisions", {})
    if base == "enactment":                      # S3: fall back to the curated flat corpus
        return _base_from_segments(target_law.split("/")[-1])
    return {}


@functools.lru_cache(maxsize=1)
def _segments_by_datokode() -> dict:
    """{datokode: [provision rows]} from the curated flat segments.jsonl (decisions.md 2026-10-04).
    Loaded once. Reads ONLY the public corpus — never the current dump / register (G1-safe: the
    reconstruction path builds its base from the owned segmentation, as the architecture intends)."""
    out = defaultdict(list)
    if not _SEGMENTS.exists():
        return out
    for line in open(_SEGMENTS, encoding="utf-8"):
        r = json.loads(line)
        if r.get("klass") == "provision" and r.get("datokode") and r.get("para"):
            out[r["datokode"]].append(r)
    return out


@functools.lru_cache(maxsize=256)
def _frozen(iid: str) -> str:
    f = _FROZEN_DIR / f"{iid}.jsonl.gz"
    if not f.exists():
        return ""
    return "\n".join(json.loads(l).get("text", "") for l in gzip.open(f, "rt", encoding="utf-8"))


def _base_from_segments(datokode: str) -> dict:
    """{§N: text} enactment base assembled from the flat corpus's `provision` rows for `datokode`
    — each § is the concatenation (in offset order) of its row-fragments sliced from the frozen
    issue. Furniture was split into `noise` rows at fold time, so provision text is already clean.
    {} if the law is not in the corpus (then reconstruction has no base, as before)."""
    rows = _segments_by_datokode().get(datokode) or []
    if not rows:
        return {}
    frozen = _frozen(rows[0]["issue_id"])
    if not frozen:
        return {}
    by_para = defaultdict(list)
    for r in rows:
        by_para[r["para"]].append(r)
    return {para: " ".join(frozen[x["start"]:x["end"]] for x in sorted(fr, key=lambda q: q["start"]))
            for para, fr in by_para.items()}


def is_ocr_base(target_law: str, base: str = "enactment") -> bool:
    """True if the base was OCR'd from a gazette/booklet (its `source` has no clean-LTI-XML `lti`
    key). OCR bases carry irreducible character noise, so the eval applies an OCR-calibrated τ to
    them (gate.TAU_OCR); clean LTI bases keep the strict τ. Objective + structural (the source
    provenance recorded at build time), so it can't be used to hand-pick the looser bar."""
    f = _base_path(target_law, base)
    if not f.exists():
        return False
    src = json.loads(f.read_text(encoding="utf-8")).get("source", {})
    return "lti" not in src


def base_as_of(target_law: str, base: str = "enactment") -> str | None:
    """The version boundary a SNAPSHOT base was captured at (booklet 'ajourført' / the 2005 CD date),
    or None for a pure enactment base. When set, the base already incorporates every amendment dated
    <= this, so reconstruction replays ONLY later amendments."""
    f = _base_path(target_law, base)
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8")).get("base_as_of")


def reconstruct(target_law: str, as_of: str | None = None, base: str = "enactment"):
    """Rebuild {paragraf_id: text} for `target_law` as of `as_of` (or latest).

    Returns (provisions, flags). Inputs are the base + amendment ops ONLY. `base` selects the
    pipeline: "enactment" (default; from-enactment, all ops) or "2005" (the separate 2005-baseline
    pipeline — Lovdata-CD-2005 snapshot + post-2005 amendments only, offline-baked consolidations
    skipped since those are from-enactment artifacts). For a snapshot base (base_as_of set),
    amendments dated <= base_as_of are skipped (already baked in); earlier dates are the honest floor.
    """
    b = enactment_base(target_law, base)
    ops = load_ops(target_law, include_applied=(base != "2005"))
    since = base_as_of(target_law, base)
    if since:
        ops = [o for o in ops if not o.get("date") or o["date"] >= since]
    provs, flags = replay.replay(b, ops, as_of=as_of)
    # blanket terminology reforms ("ordet «A» endres til «B»") — applied AFTER the per-provision
    # ops as a deterministic str.replace over provisions containing the term (source.parse.blanket).
    reforms = _load_reforms(target_law)
    if reforms:
        from source.parse import blanket
        blanket.apply_reforms(provs, reforms, as_of=as_of)
    return provs, flags


_BLANKET = amendments.DATA.parent / "blanket_amendments.jsonl.gz"


def _load_reforms(target_law: str):
    """Term-reform ops for a law, from the derived blanket stream (absent → none)."""
    if not _BLANKET.exists():
        return []
    out = []
    with gzip.open(_BLANKET, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("target_law") == target_law:
                out.append(d)
    return out
