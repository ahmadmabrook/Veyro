---
doc: BUG-041
module: MOD-000 (tool: knowledge/05-QA/tools/mr_verify.py)
severity: P3 (no real-transcript impact found; still fails closed, contradicts documented contract shape)
status: OPEN (2026-09-29)
filed: 2026-09-29 by veyro-security-reviewer (Opus), final BUG-037 verification review
---

# BUG-041 — `extract_models()` raises a bare Python exception on certain malformed rows instead of this tool's own `BLOCKED:` convention

## Finding

`extract_models()` assumes every valid-JSON line that parses is a JSON
object (`dict`). A line that parses as valid JSON but is a list, string,
or `null` (e.g. `[1,2]`, `"x"`, `null`) raises `AttributeError` when the
code calls `.get("type")` on it, rather than being treated as noise
(the same way a JSON-parse failure already is) or triggering the tool's
own `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` verdict shape.

Separately, if an assistant-type row's `message.model` field is present
but is a non-string JSON value (a list, a dict, or mixed with a string
value across different rows in the same transcript), the code raises
`TypeError` inside `set()`/`sorted()` in `verify()`, for the same
reason.

The tool still fails closed in the sense that it never emits a false
PASS in either case (a Python traceback + non-zero exit is not a PASS)
— but it contradicts the docstring's own stated contract ("Emits
BLOCKED: MODEL_ASSURANCE_UNVERIFIED... on any of: no assistant messages
found, inconsistent model values... or an unreadable transcript file" —
a malformed-row case isn't listed and doesn't get that treatment).

## Impact

None of the 146 real transcripts in this project currently contains
such a row (checked directly by the filing reviewer). This is a
robustness/contract-completeness gap, not an active false-clean risk.

## Suggested fix

In `extract_models()`, add `if not isinstance(obj, dict): continue`
right after the `json.loads` try/except (treating a non-object row the
same as a JSON-parse failure — noise, not a finding). For the
`message.model` field, add `isinstance(model, str)` before appending to
`models` — a non-string `model` value should be treated as anomalous
(worth its own explicit BLOCKED reason, e.g. "model field is not a
string") rather than silently dropped or allowed to crash downstream.
Add regression tests for both malformed-row shapes.
