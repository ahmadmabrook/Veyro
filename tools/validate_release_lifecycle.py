"""
Release-lifecycle lint (MOD-001, GOV-01-R08; SCN-MOD001-108 and 125).

Two checks, one small CLI:

    validate_release_lifecycle.py train RELEASE_TRAIN.md
    validate_release_lifecycle.py record RELEASE_RECORD.json

`train` requires two non-empty sections in RELEASE_TRAIN.md, matched by
Markdown heading text (case-insensitive): "Maintenance policy" and
"Customer-communication template".

`record` validates one per-release JSON object (distinct from the RB-GOV-01
rollback-incident evidence record). Exactly these keys, no others:

    {
      "release_id": "synthetic-train-2026.01",
      "lifecycle_stage": "beta",              # exactly beta | GA | deprecated
      "previous_lifecycle_stage": "beta",     # optional; omit for a first record
      "re_release_path": {                    # optional; see below
        "new_release_id": "synthetic-train-2026.02",
        "approval_ref": "SYNTHETIC-APPROVAL-1"
      }
    }

Order is beta -> GA -> deprecated. With `previous_lifecycle_stage` present,
the same stage or one forward step is valid. Any other move (skipping a stage,
or going backward such as deprecated -> beta) is denied unless a governed
`re_release_path` with non-empty `new_release_id` and `approval_ref` is given,
and then only for backward moves. There is no stage beyond `deprecated`.

Exit 0 on pass; exit 1 with one named defect per line on stdout otherwise.
Unreadable or malformed input fails closed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS = ("Maintenance policy", "Customer-communication template")
STAGES = ("beta", "GA", "deprecated")
_RECORD_KEYS = {"release_id", "lifecycle_stage", "previous_lifecycle_stage", "re_release_path"}
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")


def _named(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def check_train(text: str) -> list[str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            current = m.group(1).strip().lower()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    problems = []
    for name in REQUIRED_SECTIONS:
        body = sections.get(name.lower())
        if body is None:
            problems.append(f"MISSING_SECTION: {name}")
        elif not "".join(body).strip():
            problems.append(f"EMPTY_SECTION: {name}")
    return problems


def check_record(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["MALFORMED_RECORD: top level must be a JSON object"]
    problems = [f"UNKNOWN_FIELD: {k}" for k in sorted(set(data) - _RECORD_KEYS)]
    if not _named(data.get("release_id")):
        problems.append("MISSING_RELEASE_ID")
    stage = data.get("lifecycle_stage")
    if "lifecycle_stage" not in data:
        problems.append("MISSING_LIFECYCLE_STAGE")
    elif stage not in STAGES:
        problems.append(f"UNKNOWN_LIFECYCLE_STAGE: {stage!r}")
    prev = data.get("previous_lifecycle_stage")
    if "previous_lifecycle_stage" in data and prev not in STAGES:
        problems.append(f"UNKNOWN_PREVIOUS_LIFECYCLE_STAGE: {prev!r}")
    if stage in STAGES and prev in STAGES:
        step = STAGES.index(stage) - STAGES.index(prev)
        path = data.get("re_release_path")
        governed = (
            isinstance(path, dict)
            and _named(path.get("new_release_id"))
            and _named(path.get("approval_ref"))
        )
        if step < 0 and not governed:
            problems.append(f"INVALID_TRANSITION: {prev} -> {stage} without governed re_release_path")
        elif step > 1:
            problems.append(f"INVALID_TRANSITION: {prev} -> {stage} skips a stage")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("train", "record"):
        print("usage: validate_release_lifecycle.py {train|record} PATH")
        return 2
    try:
        raw = Path(argv[2]).read_text(encoding="utf-8")
        problems = check_train(raw) if argv[1] == "train" else check_record(json.loads(raw))
    except (OSError, ValueError) as exc:
        problems = [f"UNREADABLE_INPUT: {exc}"]
    for p in problems:
        print(p)
    if not problems:
        print("PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
