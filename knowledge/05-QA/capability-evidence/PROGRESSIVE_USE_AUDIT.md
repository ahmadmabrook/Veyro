---
doc: PROGRESSIVE_USE_AUDIT
status: EXECUTED (2026-09-12) — SCN-MOD000-083
date: 2026-09-12
---

# SCN-MOD000-083 — Capability progressive use: loaded only when relevant, no blanket loading

## What was missing

Previously "informally true, not formally audited" — believed correct
by direct observation but never captured as a dedicated evidence file.

## What was run

Read `module-capabilities.yaml`'s `used_for` field for all 7 registered
capabilities — this field is the durable record of *why* each capability
was invoked, authored at the time each was actually put to use, not
retrofitted:

| Capability | Declared `used_for` | Task-specific? |
|---|---|---|
| CAP-001 (Notion MCP) | Notion Engineering Control Plane (9 databases) as live operational mirror | Yes — narrow to the Control Plane mirror, not general Notion use |
| CAP-002 (TestSprite CLI) | TestSprite capability discovery/qualification drill | Yes — narrow to its own qualification chunk |
| CAP-003 (`docx` skill) | Reading governing baseline `.docx` files during bootstrap | Yes — narrow to baseline reading |
| CAP-004 (Bash/Read/Write/Edit) | All filesystem/shell operations building the control plane | First-party harness core tools, exempted by policy — not a third-party capability subject to this scenario's concern |
| CAP-005 (Browser tools) | Manual-QA evidence gathering | Yes — narrow to §12.1 drill evidence |
| CAP-006 (iOS Simulator) | Manual-QA evidence gathering | Yes — narrow to §12.1 drill evidence, stock Apple apps only |
| CAP-007 (Bash guard) | PreToolUse security hook closing BUG-013/022/023 | Yes — narrow to the exact defect it was built to close |

Every non-exempt capability's registered scope is a specific task or
task-class, not "capabilities the project might someday need." No
capability was registered speculatively ahead of an actual need — each
row's own `used_for` text names the real, concrete trigger. Cross-
checked against this project's own tool-call history across all prior
chunks (Phases 1-8): CAP-001 calls are Notion Control Plane writes only;
CAP-002 calls are TestSprite CLI invocations only; CAP-005/006 calls
occur only during the two manual-QA drill chunks (Phase 6, plus Phase 5
reruns); CAP-007 usage is confined to the Bash guard's own build/review/
activation chunks. No capability was invoked outside its own declared
scope.

## Result vs. pass criteria

Pass criteria: no capability loaded speculatively for a use it wasn't
actually needed for. **Confirmed across all 7 registered capabilities.**

## Status: PASS
