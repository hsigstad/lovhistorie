# INTENT: declare the project-specific shape of the lovhistorie static site
# (title, Reading-Guide cards, doc registry) and hand it to sitekit.
# REASONING: lovhistorie is a docs-only data-reconstruction PIPELINE with no
# paper/ or talk/ — the sitekit "minimal" archetype fits exactly. The package
# owns rendering, navigation, and link rewriting; this file only names the
# inputs. docs/notes/ renders in folder-mode so the one cross-link
# (roadmap.md -> notes/statutory_law_versioning.md) resolves against the
# preserved subtree instead of the flattened docs/ root.
# ASSUMES: every rel_path below exists under the project root; sitekit's
# link/citation refs are no-ops here (this repo has no AN/cite/anec/hyp docs).
from __future__ import annotations

import json
from pathlib import Path

from sitekit import SiteConfig


PROJECT_ROOT = Path(__file__).parent.parent.parent


# --- live performance snapshot (written by `python -m source.eval.status`) --------
# Headlined at the top of the landing page so the latest number is the first thing
# a visitor sees. Absent (fresh clone, never run) -> the card is simply omitted.
def _load_status():
    p = PROJECT_ROOT / "docs" / "status.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


_STATUS = _load_status()
_PERF_BRIEF = None
if _STATUS and _STATUS.get("total"):
    _pct = f"{_STATUS['convergence'] * 100:.0f}%"
    _guards = "pass" if _STATUS.get("guards_pass") else "FAIL"
    _PERF_BRIEF = (
        "docs/status.md", "docs/status.html",
        f"Performance: {_pct} convergence",
        (f"Latest reconstruction fidelity &mdash; {_STATUS['matched']}/{_STATUS['total']} "
         f"dev-set provisions rebuilt from gazette history to today&rsquo;s official "
         f"text (anti-gaming guards {_guards}). As of {_STATUS['as_of']}."),
        "Live", "priority-start",
    )


# (rel_path, title, description, category)
# Handoff notes under docs/notes/handoffs/ are ephemeral (consumed and
# git-rm'd) and are intentionally left out of the site.
DOC_REGISTRY = [
    # --- Status ---
    ("docs/status.md",                            "Performance",               "Latest convergence number and what it means",         "Status"),
    # --- Reference ---
    ("README.md",                                 "Overview",                  "What the pipeline builds and why",                    "Reference"),
    ("docs/goal.md",                              "Goal",                      "Autonomous goal + machine-checkable gate condition",  "Reference"),
    ("docs/evaluation.md",                        "Evaluation",                "Success criteria and the convergence metric",         "Reference"),
    ("docs/roadmap.md",                           "Roadmap",                   "Phased plan from gazette harvest to deliverable",     "Reference"),
    ("docs/ground_truth.md",                      "Ground Truth",              "Lovdata-Pro validation oracle (eval-only)",           "Reference"),
    ("docs/notes/statutory_law_versioning.md",    "Statutory Law Versioning",  "Technical background on point-in-time law",           "Reference"),
    # --- Working notes ---
    ("docs/notes/lessons_and_pitfalls.md",        "Lessons & Pitfalls",        "Measurement bugs mistaken for hard walls — read first", "Working notes"),
    ("docs/notes/enactment_base.md",              "Enactment Base",            "Original-enactment base construction",                "Working notes"),
    ("docs/notes/external_source_repos.md",       "External Source Repos",     "Assessment of external corpora",                      "Working notes"),
    ("docs/notes/lovdata_cd_2005.md",             "Lovdata CD 2005",           "The 2005 CD-ROM base",                                "Working notes"),
    ("BLOCKER.md",                                "Resolved Blocker",          "Record of the resolved pre-2001 blocker",             "Working notes"),
    # --- Tasks ---
    ("docs/todo.md",                              "Active Tasks",              "Open items",                                          "Tasks"),
    ("docs/done.md",                              "Work Log",                  "Completed work",                                      "Tasks"),
]


# (rel_path, href, label, description, priority, priority_class)
# The landing-page "Reading Guide" — start-here entry points, in reading order.
# The live Performance card (if a status snapshot exists) is prepended below so the
# latest number leads the page.
_BASE_GUIDE_BRIEFS = [
    ("docs/notes/lessons_and_pitfalls.md", "docs/notes/lessons_and_pitfalls.html",
     "Lessons &amp; Pitfalls",
     "Read first &mdash; nearly every &ldquo;hard wall&rdquo; here turned out to be a measurement bug, not a reconstruction limit.",
     "Start here", "priority-start"),
    ("docs/goal.md", "docs/goal.html",
     "Goal",
     "The autonomous goal and the single machine-checkable gate (<code>source.eval.gate</code>).",
     "Then this", "priority-main"),
    ("docs/evaluation.md", "docs/evaluation.html",
     "Evaluation",
     "Success criteria and the convergence metric that scores the reconstruction.",
     "Then this", "priority-main"),
    ("docs/roadmap.md", "docs/roadmap.html",
     "Roadmap",
     "The phased plan from Norsk Lovtidend harvest to the point-in-time deliverable.",
     "Reference", "priority-ref"),
    ("docs/ground_truth.md", "docs/ground_truth.html",
     "Ground Truth",
     "The Lovdata-Pro validation oracle &mdash; eval-only, never redistributed.",
     "Reference", "priority-ref"),
]

GUIDE_BRIEFS = ([_PERF_BRIEF] if _PERF_BRIEF else []) + _BASE_GUIDE_BRIEFS


config = SiteConfig(
    project_root=PROJECT_ROOT,
    project_title="Lovhistorie",
    paper_title="",
    archetype="minimal",
    doc_registry=DOC_REGISTRY,
    guide_briefs=GUIDE_BRIEFS,
    # docs/notes/ pages keep their subfolder (build/site/docs/notes/<stem>.html)
    # so roadmap.md's `notes/statutory_law_versioning.md` link resolves; the
    # notes files are registered explicitly, so no auto-discovery.
    folder_mode_subdirs=("notes",),
    folder_mode_auto_discover=False,
    # No paper — repurpose the forced hero placeholder to say so plainly.
    paper_placeholder_msg=(
        "No paper &mdash; this is a data-reconstruction <b>pipeline</b>. "
        "Start with the Goal and Evaluation cards below."
    ),
    # This repo has no AN pages, cite-refs, anecdotes, or hypotheses docs, so
    # the corresponding link rewriters are no-ops; turning them off is a small
    # speedup and a clearer contract.
    enable_an_pages=False,
    enable_cite_refs=False,
    enable_anec_refs=False,
    enable_hyp_refs=False,
)
