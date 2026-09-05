---
doc: AUTHENTICATION_FAILURE_DRILL
status: EXECUTED (2026-09-05) — SCN-MOD000-095 (AUTHN category)
date: 2026-09-05
---

# SCN-MOD000-095 — Invalid/revoked capability credential fails closed

## Step 1 (baseline, already existed): real authentication-failure instances

Two real, already-observed instances of this project correctly reporting
an authentication failure rather than masking or fabricating success:
`plugin:github:github` returning HTTP 400 "Authorization header is badly
formatted"; `claude-design` returning HTTP 403 "rejected your claude.ai
login". Both surfaced as connection failures in this project's own
tooling, correctly reported, never silently bypassed.

## Step 2 (mandatory, executed 2026-09-05): deliberate invalid-credential drill

Used CAP-002 (TestSprite CLI, already-APPROVED capability) with a
deliberately invalid, disposable credential via a **one-shot environment
variable override** — not a change to the real configured profile:

```bash
TESTSPRITE_API_KEY="ts_invalid_scratch_credential_00000000000000000000" testsprite doctor --output json
```

**Raw output:**
```json
{
  "checks": [
    {"name": "CLI version", "status": "ok", "detail": "0.8.0"},
    {"name": "Node.js", "status": "ok", "detail": "v22.23.2 (supported range: 20.19+, 22.13+, or 24+)"},
    {"name": "Profile", "status": "ok", "detail": "default"},
    {"name": "API endpoint", "status": "ok", "detail": "https://api.testsprite.com"},
    {"name": "Credentials", "status": "ok", "detail": "API key configured (profile \"default\")"},
    {"name": "Connectivity", "status": "fail", "detail": "GET /me failed (VALIDATION_ERROR)"},
    {"name": "Local tunnel", "status": "warn", "detail": "could not check (VALIDATION_ERROR)"},
    {"name": "Verify skill", "status": "warn", "detail": "not installed here; run `testsprite setup` so your agent verifies its changes"}
  ],
  "failures": 1,
  "warnings": 2
}
{"error": "doctor: 1 check(s) failed, 2 warning(s)"}
```
Exit code: 1.

**What happened:** the invalid credential was sent in a real request to
`api.testsprite.com` (`GET /me`), the server rejected it, and the CLI
reported the failure plainly (`status: fail`, non-zero exit, explicit
error message) — no silent degrade, no fabricated success. This is a
genuine, live authentication failure, not a simulated/mocked one.

**Safety and scope:** the environment variable was scoped to this single
command invocation only. Confirmed the real profile was unaffected
immediately after:

```bash
$ testsprite doctor --output json
... "failures": 0 ...
```
exit code 0 — the real credential still works, nothing was corrupted or
rotated. No billable action was attempted (per CAP-002's approved scope,
`doctor` is read-only/non-billed).

## Result vs. pass criteria

Pass criteria: "Step 2 actually executed (not skipped) and produces a
visible `BLOCKED`-class report, never masked or faked." Step 2 was
executed for real, against a live endpoint, with a genuinely invalid
credential, and produced a visible, correctly-labeled failure
(`status: fail`, exit 1). The specific literal string `BLOCKED:
AUTH_FAILURE` named in the scenario's fail-closed condition is not the
CLI's own vocabulary (its failure marker is `status: "fail"` /
non-zero exit / explicit error text) — the *behavior* required (visible,
non-silent, non-fabricated failure) is fully satisfied; the exact string
is this project's own shorthand for the class of behavior, not a literal
string the third-party CLI is expected to emit.

## Status: PASS
