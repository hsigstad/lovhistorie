"""Install the curated-segmentation pre-commit gate (tracked, reproducible).

INTENT: `.git/hooks/` is not version-controlled, so the segmentation gate used to live
    only on one clone with a "reinstall by hand" note. This script IS the source of truth
    for the hook: run `python -m source.eval.install_hooks` after cloning to install it.
REASONING: a commit that stages `data/segments.jsonl` must pass BOTH halves of the gate
    (decisions.md 2026-10-04) — the STRUCTURAL invariants (`classification_qa --diff`: no
    new gap/overlap/sha-drift/klass-marker/unresolved-target) AND the base-QUALITY
    no-regression check (`segments_quality --diff`: no offset-moved law reconstructs a
    worse base vs current). Both skip cleanly when there is no HEAD baseline / answer key.
ASSUMES: run from inside the repo; writes .git/hooks/pre-commit (overwrites).
"""
from __future__ import annotations

import stat
import subprocess
from pathlib import Path

_HOOK = """#!/usr/bin/env bash
# Two-signal gate for curated-segmentation edits (decisions.md 2026-10-04).
# Installed by `python -m source.eval.install_hooks` — edit THERE, not here.
if git diff --cached --name-only | grep -qx 'data/segments.jsonl'; then
  root="$(git rev-parse --show-toplevel)"
  cd "$root" || exit 1
  PYTHONPATH=. python -m source.eval.classification_qa --diff || {
    echo "pre-commit: segments.jsonl edit worsens classification_qa invariants — blocked."; exit 1; }
  PYTHONPATH=. python -m source.eval.segments_quality --diff || {
    echo "pre-commit: segments.jsonl edit regresses a base's quality vs current — blocked."; exit 1; }
fi
exit 0
"""


def install() -> Path:
    root = Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True).strip())
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(_HOOK, encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook


if __name__ == "__main__":
    print(f"installed two-signal segmentation gate -> {install()}")
