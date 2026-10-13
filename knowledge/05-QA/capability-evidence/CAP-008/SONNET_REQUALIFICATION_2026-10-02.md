---
doc: CAP-008_SONNET_REQUALIFICATION
capability: CAP-008 — Colima binding, post-P1-1-remediation re-qualification
status: STAGE 5 RE-RUN AGAINST REVIEWED HARNESS — PASS; review_status remains QUALIFIED, NOT APPROVED
run_by: Sonnet (claude-sonnet-5), 2026-10-02
precondition: first Opus capability review BLOCKED P0=0/P1=2; harness P1-1 remediated by veyro-critical-engineer; harness code review APPROVED P0=0/P1=0; P1-2 (VM/engine provenance) recorded separately by the orchestrator in COLIMA_VM_PROVENANCE_2026-10-02.md
---

# CAP-008 — Sonnet stage-5 re-qualification against the P1-1-reviewed harness

This re-runs stage 5 (positive + the requested negative variants) against
`backend/tests/harness/postgres.py` as it stands **after** `veyro-critical-engineer`'s
P1-1 fail-closed-routing remediation and the independent code review's
`APPROVED, P0=0/P1=0` verdict — not the pre-remediation harness any earlier
CAP-008 evidence file drilled against. This file does not re-litigate P1-1's
implementation or its code review (see
`knowledge/03-Modules/MOD-001/evidence/implementation/CAP008-P1-1-colima-binding-harness-remediation-2026-10-02.md`
and `.../evidence/code-review/CAP008-P1-1-colima-binding-code-review-2026-10-02.md`)
and does not touch P1-2 (`COLIMA_VM_PROVENANCE_2026-10-02.md`, not erased,
not duplicated here).

## Preconditions verified first (read-only)

- HEAD unchanged: `e516bedabf3d654ad3ae16d948b8f3522739ddc2`.
- 105 pre-existing uncommitted/untracked paths preserved (count only;
  contents not altered by this file's work).
- `pgrep -fl "Docker.app"` → no match, both before and after every drill
  below. Docker Desktop was not activated at any point.
- `colima status` → running (already running; not started by this session).
- `realpath /opt/homebrew/bin/docker` → `/opt/homebrew/Cellar/docker/29.6.0/bin/docker`,
  matching `TRUSTED_DOCKER_CLI_REALPATH` exactly.
- A read-only `trusted_docker()` call succeeded, confirming the pinned
  engine identity check passes on this host right now (`Name=colima`,
  `ServerVersion=29.5.2`, `OperatingSystem=Ubuntu 24.04.4 LTS`).

## 1. Focused unit suite, real run

```
$ backend/.venv/bin/python -m pytest backend/tests/unit/test_harness_postgres_fail_closed.py -v
...
collected 16 items
test_missing_trusted_cli_is_an_error_not_a_skip PASSED
test_docker_on_path_is_never_used PASSED
test_desktop_cli_symlinked_at_trusted_path_is_rejected PASSED
test_cli_version_drift_is_rejected_before_engine_contact PASSED
test_ambient_desktop_context_config_and_creds_are_not_used PASSED
test_desktop_engine_on_default_route_is_rejected_before_run PASSED
test_caller_docker_host_cannot_bypass_engine_identity PASSED
test_engine_identity_drift_is_rejected[ServerVersion-29.5.3] PASSED
test_engine_identity_drift_is_rejected[OperatingSystem-Docker Desktop] PASSED
test_engine_identity_drift_is_rejected[Name-lima-default] PASSED
test_engine_reporting_server_errors_is_rejected PASSED
test_unreachable_engine_fails_closed_before_run PASSED
test_superuser_password_never_in_docker_argv_or_error PASSED
test_port_and_cleanup_use_the_same_trusted_route PASSED
test_non_loopback_publish_is_rejected_and_cleaned_up PASSED
test_server_log_uses_the_same_trusted_route PASSED
============================== 16 passed in 7.04s ==============================
```
**16/16, exit 0.** Confirms the code review's corrected count (not the
implementation record's original "17/17" typo it itself flagged).

## 2. Full backend suite, real run (integration runs for real against Colima)

```
$ backend/.venv/bin/python -m pytest backend/tests -q
...
51 tests collected
51 passed in 8.96s
```
**51/51, exit 0.** (A narrower invocation naming only `unit component
integration` subdirectories collected 50 — `backend/tests/unit/test_scaffold_live.py::test_unit_harness_is_live`
sits outside that exact three-path selector pytest resolved; running the
whole `backend/tests` tree, as above, is the accurate 51-test count and
matches the implementation record's claim exactly.)

## 3. Lint/type checks, real run

```
$ (cd backend && .venv/bin/python -m ruff check .)
All checks passed!
$ (cd backend && .venv/bin/python -m mypy tests app)
Success: no issues found in 20 source files
```
Both clean, exit 0.

## 4. Reproducible drill script — the four requested drill types plus the script's own full set

Ran exactly as documented in the script's own docstring, from the repo root:

```
$ backend/.venv/bin/python knowledge/03-Modules/MOD-001/evidence/implementation/cap008_p1_1_colima_binding_drill.py
precondition: Docker Desktop processes=[]
POS: PASS -- route=('/opt/homebrew/Cellar/docker/29.6.0/bin/docker', 'unix:///Users/[REDACTED-USER]/.colima/default/docker.sock') publish=127.0.0.1:32777 server_version=('16.15',) select1+1=(2,) pinned_digest_present=True server_log_ready=True leftovers=''
POS-AMB: PASS -- route=('/opt/homebrew/Cellar/docker/29.6.0/bin/docker', 'unix:///Users/[REDACTED-USER]/.colima/default/docker.sock') publish=127.0.0.1:32778 server_version=('16.15',) select1+1=(2,) pinned_digest_present=True server_log_ready=True leftovers=''
NEG-UNR: PASS -- `docker info` exit 1: failed to connect to the docker API at unix:///Users/[REDACTED-USER]/.openclaw/tmp/veyro-cap008-_fgpj_mo/no-daemon.sock; check if the path is correct and if the daemon is running: dial unix [...]: connect: no such file or directory; the GOV-01-R02 harness needs the approved local Colima Docker engine and never substitutes a mock
NEG-DSK: PASS -- `docker info` exit 1: Cannot connect to the Docker daemon at unix:///Users/[REDACTED-USER]/.docker/run/docker.sock. Is the docker daemon running?; the GOV-01-R02 harness needs the approved local Colima Docker engine and never substitutes a mock
NEG-WRG: PASS -- engine at unix:///Users/[REDACTED-USER]/.openclaw/tmp/veyro-cap008-_fgpj_mo/impostor.sock is not the approved Colima binding: observed {'Name': 'docker-desktop', 'ServerVersion': '29.4.0', 'OperatingSystem': 'Docker Desktop'}, expected {'Name': 'colima', 'ServerVersion': '29.5.2', 'OperatingSystem': 'Ubuntu 24.04.4 LTS'}; the GOV-01-R02 harness needs the approved local Colima Docker engine and never substitutes a mock
NEG-WRG-NO-CREATE: PASS -- requests seen=['HEAD /_ping', 'GET /v1.47/info']
LEFTOVERS: PASS -- veyro-mod001-harness containers after all drills=''
NO-DESKTOP: PASS -- Docker Desktop processes after=b''
$ echo EXIT:$?
EXIT:0
```

**8/8 PASS, exit 0.** Redaction note: the home-directory username segment
in socket paths was replaced with `[REDACTED-USER]` above; nothing else
was redacted because the script never prints the Postgres password (it is
passed only via the `docker run` environment, by name, per the harness's
own design) — independently confirmed by grepping this same run's output
for `password|secret|token`: no match.

Mapping to the four drill types this continuation specifically asked for:

1. **Real positive `disposable_postgres` on Colima, pinned digest, loopback, SQL roundtrip, cleanup** → `POS`. Confirmed: `pinned_digest_present=True`, `publish=127.0.0.1:...`, `select1+1=(2,)`, `leftovers=''` after teardown.
2. **Unreachable Unix socket negative** → `NEG-UNR`. Confirmed: `docker info` fails at a nonexistent socket path, clean `RuntimeError`, never substitutes a mock.
3. **Wrong-engine/Desktop-identity negative using a safe local fake endpoint, no container create** → `NEG-WRG` + `NEG-WRG-NO-CREATE`. The fake endpoint is a synthetic Python `http.server` bound to a local Unix socket inside a throwaway temp directory, impersonating Docker Desktop's `docker info` identity fields only — it is not Docker Desktop and never starts it. Confirmed rejected before any `run`; the endpoint's own request log shows only `HEAD /_ping` and `GET /v1.47/info`, zero `POST` (no container-create attempt reached it).
4. **Ambient Docker Desktop PATH/context/credsStore substitution negative** → `POS-AMB`. Note on framing: this is a **positive-outcome** proof, not an error-raising negative — with Docker.app's CLI placed first on `PATH`, `DOCKER_CONTEXT=desktop-linux`, and `DOCKER_CONFIG` pointed at the real `~/.docker` (`credsStore: desktop`), the harness still correctly ignores every ambient selector and lands on the same Colima route (`route=` identical to the clean-environment `POS` run). Reporting it as a "negative" in the sense of "the substitution attempt does not succeed" would be accurate; reporting it as a drill that raises an error would not be — it does not raise, by design, because the ambient selectors never reach the trusted route. Stated plainly here rather than silently reframed, per the no-false-PASS instruction.

## 5. No-leftover and Docker Desktop checks, independently repeated after everything above

```
$ (trusted_docker ps -a --filter name=veyro-mod001-harness --format '{{.Names}}')
''
$ pgrep -fl "Docker.app"
(no output — not running)
```

## Disposition

All requested drills PASS, real, exit 0, against the actual post-P1-1-remediation
harness. No leftover containers at any point. Docker Desktop never
activated. No real data. No spend.

**This re-qualification does not by itself change `review_status`.**
CAP-008 was already `QUALIFIED` (not `APPROVED`) from the pre-remediation
drills; this file's purpose is to confirm that status still holds against
the harness as it exists *after* P1-1's fix and code review — it does, and
the evidence above is that confirmation. `review_status` remains
`QUALIFIED`; `approved_by`/`approved_date` remain blank pending the fresh
independent Opus capability-security re-review that P1-2's provenance
work and this file together feed into. `BUG-038` remains **OPEN**,
untouched. Slice-5's `SCN-MOD001-027`/`067` remain unpromoted; `SCN-067`'s
R04 gap is untouched. No commit or push occurred.
