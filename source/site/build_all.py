# INTENT: site build entry point. Hands the SiteConfig in site.py to
# sitekit.build_site() and exits with its return code.
# REASONING: sitekit (the shared rendering machinery) lives in the sibling
# research-kit repo. In some environments the system venv is read-only, so a
# `pip install -e` is impossible; we add sitekit to sys.path instead.
# ASSUMES: this file sits at pipelines/lovhistorie/source/site/build_all.py,
# five parents below the workspace root that also holds research-kit/.
#
# Usage: python3 -m source.site.build_all
from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH_KIT_SITEKIT = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "research-kit"
    / "sitekit"
)
if str(_RESEARCH_KIT_SITEKIT) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_KIT_SITEKIT))

from sitekit import build_site  # noqa: E402
from source.site.site import config  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(build_site(config))
