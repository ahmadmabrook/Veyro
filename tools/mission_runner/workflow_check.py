#!/usr/bin/env python3
"""Deterministic shape check for the Veyro Foundation CI workflow (stdlib only, no YAML parser).

Owner decision 2026-10-16 (direct-main, GitHub Actions only): the workflow must run on push to main and
nothing else, hold read-only contents permission, deploy nothing and never touch the retired trusted gate.
Exit 0 when the shape is exactly that; exit 1 with one line per violation otherwise.
"""
import re
import sys
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/veyro-foundation-ci.yml"
JOB_NAME = "foundation (MOD-000 focused checks)"  # unchanged for continuity of the check name
TRIGGER_BLOCK = ("push:", "branches:", "- main")
FORBIDDEN = (  # (pattern, why) matched against non-comment lines
    (r"pull_request", "pull_request / pull_request_target trigger or reference"),
    (r"merge_group", "merge_group trigger"),
    (r"feature/", "feature-branch trigger"),
    (r"workflow_dispatch|workflow_run|schedule:|repository_dispatch", "extra trigger"),
    (r"VEYRO_GATE_MODE|publisher\.py\s+publish|veyro-trusted-gate", "trusted gate must stay disabled"),
    (r"checks:\s*write|statuses:\s*write|id-token:\s*write|contents:\s*write", "write permission"),
    (r"secrets\.|environment:", "secret or deployment environment"),
    (r"\bdeploy(?!\.sh)\b|docker\s+push|gh\s+release|kubectl|terraform", "deployment action"),
)


def _code_lines(text):
    return [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def _top_block(lines, key):
    """Stripped body lines of a top-level `key:` block, or None when the key is absent."""
    for i, ln in enumerate(lines):
        if ln == f"{key}:":
            body = []
            for nxt in lines[i + 1:]:
                if not nxt.startswith((" ", "\t")):
                    break
                body.append(nxt.strip())
            return body
    return None


def check(text):
    lines = _code_lines(text)
    problems = []
    on = _top_block(lines, "on")
    norm = tuple(b.replace('"', "").replace("'", "") for b in on) if on is not None else None
    if norm != TRIGGER_BLOCK:
        problems.append(f"on: must be exactly push to branches [main], found {norm!r}")
    if _top_block(lines, "permissions") != ["contents: read"]:
        problems.append("permissions: must be exactly 'contents: read'")
    if not any(ln.strip() == f"name: {JOB_NAME}" for ln in lines):
        problems.append(f"job name {JOB_NAME!r} missing")
    if any(re.match(r"concurrency\s*:", ln) for ln in lines):  # even cancel-in-progress: false replaces a pending run
        problems.append("top-level concurrency is forbidden: it can replace a pending run, so a pushed SHA might get no run")
    for ln in lines:
        for pattern, why in FORBIDDEN:
            if re.search(pattern, ln):
                problems.append(f"{why}: {ln.strip()}")
    return problems


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else WORKFLOW
    problems = check(path.read_text())
    for p in problems:
        print(f"workflow-check: {p}", file=sys.stderr)
    if not problems:
        print("workflow-check: push-to-main only, read-only permissions, gate disabled")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
