---
doc: CAP008_P1_1_COLIMA_BINDING_HARNESS_REMEDIATION
module: MOD-001 (GOV-01-R02 critical slice: tenant-isolation/RLS harness)
finding: CAP-008 Opus review 2026-10-02, P1-1 only (`knowledge/05-QA/capability-evidence/CAP-008/COLIMA_OPUS_REVIEW_2026-10-02.md`)
implemented_by: veyro-critical-engineer (Opus, claude-opus-5-5), per ADR-005 Decision 1
execution_mode: DIRECTLY IMPLEMENTED (no veyro-implementer delegation, no supervised sub-work)
date: 2026-10-01 23:00-23:20 UTC (2026-10-02 Asia/Amman)
status: IMPLEMENTED — NOT SELF-REVIEWED; independent Opus code review and Sonnet stage-5 re-qualification pending
---

# CAP-008 P1-1: fail-closed Colima binding for the disposable-Postgres harness

**Execution mode (EIP §4.1 / ADR-005):** directly implemented by `veyro-critical-engineer` (Opus). Nothing was delegated or supervised. This record states what was built and observed. It is **not** a review verdict. It does not approve CAP-008, close BUG-038, or touch P1-2 (registry/provenance), which the orchestrator handles separately.

## Finding addressed

Before this change, `backend/tests/harness/postgres.py::_docker` executed the first `docker` on PATH (on this host that can be `/usr/local/bin/docker` or `~/.docker/bin/docker`, both symlinks into `/Applications/Docker.app`). It used the ambient `~/.docker/config.json` (`credsStore: desktop`, a `desktop-linux` context present) and honoured any ambient `DOCKER_HOST`/`DOCKER_CONTEXT`. Starting Desktop or reordering PATH could therefore have run GOV-01-R02 evidence on the unapproved Desktop engine without any error.

## What changed (2 code files + 1 drill script + this record)

`backend/tests/harness/postgres.py` now behaves as follows:

- **One trusted route (`DockerRoute`).** Every docker call goes through it: `run`, `port`, `logs` (via `DisposablePostgres.server_log`), and the cleanup `rm -f`. Its argv is always `<pinned CLI realpath> --config <isolated dir> --host <host> …`, and its env has every ambient `DOCKER_*` variable stripped, with `DOCKER_CONFIG` set to the isolated directory.
- **CLI identity.** PATH is never consulted. `TRUSTED_DOCKER_CLI=/opt/homebrew/bin/docker` must `realpath` exactly to `TRUSTED_DOCKER_CLI_REALPATH=/opt/homebrew/Cellar/docker/29.6.0/bin/docker` and be an executable regular file. The resolved file is what gets executed, so the checked binary is the run binary. `docker --version` must then report `29.6.0`. Docker.app's CLI cannot match.
- **Isolated config.** Each route gets a fresh `0700` temp directory containing `config.json` = `{}`. That means no credsStore, no currentContext, and no CLI plugins/hooks. The directory is deleted when the route closes.
- **Explicit host.** The default is `unix://$HOME/.colima/default/docker.sock`. A caller-set `DOCKER_HOST` is honoured only so negative drills can target an unreachable or foreign engine. It is passed as `--host` and is still subject to the identity check. `DOCKER_CONTEXT` and the other ambient selectors are ignored.
- **Pre-run engine identity.** `docker info --format '{{json .}}'` must parse, carry no `ServerErrors`, and match `APPROVED_ENGINE` exactly: `Name=colima`, `ServerVersion=29.5.2`, `OperatingSystem=Ubuntu 24.04.4 LTS`. Otherwise the run fails with `RuntimeError` before `docker run`. CLI and engine versions are pinned like the image digest: drift fails closed until it is deliberately re-qualified.
- **Loopback guard (new, small).** The published host from `docker port` must be `127.0.0.1`. Otherwise the run errors, and cleanup still runs.
- **Preserved.** No mock or fallback (every failure is a `RuntimeError` carrying the "never substitutes a mock" hint). The pinned `postgres@sha256:7218…80ea` image. Synthetic-only data. The password is passed only via the env of `docker run` (`-e POSTGRES_PASSWORD` name-only in argv) and is never in argv, error text or `repr`.

`backend/tests/unit/test_harness_postgres_fail_closed.py` was rewritten as 16 collected test cases (13 plain tests plus 3 parametrized cases; corrected after the independent code reviewer counted them). They use a scripted fake CLI installed at the trusted path through the module's pinned constants. That is a test seam, not a runtime override: the harness reads no variable that can repoint its CLI. The fake logs argv, `DOCKER_*` env, password presence and the isolated config content. The two original tests are kept and strengthened: "missing docker is an error, not a skip" now also proves a working `docker` on PATH was not used instead, and "password never in argv" now also checks error text and every logged argv against a sentinel password. The new coverage is:

- **PATH substitution:** a working fake `docker` first on PATH is never invoked.
- **Desktop CLI substitution:** a trusted path symlinked to `…/Docker.app/Contents/Resources/bin/docker` is rejected, and the Desktop fake is never invoked. CLI version drift is rejected before engine contact.
- **Ambient Desktop context:** with `DOCKER_CONFIG` set to a `credsStore: desktop` / `currentContext: desktop-linux` config, plus `DOCKER_CONTEXT=desktop-linux` and `DOCKER_TLS_VERIFY`, every call uses the isolated `{}` config and the explicit Colima host. Env is exactly `{DOCKER_CONFIG: isolated}`, the ambient file is untouched, and the isolated directory is removed afterwards.
- **Wrong engine:** a Desktop identity on the default route, and on a caller `DOCKER_HOST` (no bypass), is rejected with no `run`. Drift in each identity field and `ServerErrors` are rejected.
- **Unreachable engine:** fails at `docker info`, with no `run`.
- **Same route for run/port/rm/logs.** Cleanup removes the container that was run. A non-loopback publish is rejected and still cleaned up.

## Results (observed this session, host clock UTC)

| Check | Result |
|---|---|
| Focused unit file | **16/16 passed** (independent reviewer re-counted and re-ran) |
| Full backend suite (unit + component + integration; integration runs for real on Colima through the new route) | **51/51 passed** |
| `ruff check .` (backend) / `mypy tests app` (strict) | clean / clean (20 files) |
| `ruff format` | test file formatted. `postgres.py` was already not format-clean at HEAD (compact `run` argv layout); that style is kept, not reformatted |
| Mutation kill-check (10 mutants on `postgres.py`, file restored and `cmp`-verified) | **10/10 killed**: PATH CLI, no identity check, ambient `DOCKER_*` kept, no `--host`, no `--config`, no CLI version check, bare-`docker` cleanup, no loopback check (re-run alone: fails), password in argv, `ServerErrors` ignored |
| Real drills, `cap008_p1_1_colima_binding_drill.py`, 23:14 UTC, then re-run after a lint-only edit | **8/8 PASS, exit 0, both runs** |
| `verify_baselines.py` | PASS 4/4 |

The real drills printed the following (paths abbreviated):

```
precondition: Docker Desktop processes=[]
POS: PASS -- route=('/opt/homebrew/Cellar/docker/29.6.0/bin/docker', 'unix:///Users/…/.colima/default/docker.sock') publish=127.0.0.1:32772 server_version=('16.15',) select1+1=(2,) pinned_digest_present=True server_log_ready=True leftovers=''
POS-AMB: PASS -- (Docker.app CLI first on PATH, DOCKER_CONTEXT=desktop-linux, DOCKER_CONFIG=~/.docker) same Colima route, publish=127.0.0.1:32773, roundtrip OK, leftovers=''
NEG-UNR: PASS -- `docker info` exit 1: failed to connect to the docker API at unix://…/no-daemon.sock …; … never substitutes a mock
NEG-DSK: PASS -- `docker info` exit 1: Cannot connect to the Docker daemon at unix:///Users/…/.docker/run/docker.sock …; … never substitutes a mock
NEG-WRG: PASS -- engine at unix://…/impostor.sock is not the approved Colima binding: observed {'Name': 'docker-desktop', 'ServerVersion': '29.4.0', 'OperatingSystem': 'Docker Desktop'}, expected {…colima…}
NEG-WRG-NO-CREATE: PASS -- requests seen=['HEAD /_ping', 'GET /v1.47/info']
LEFTOVERS: PASS -- veyro-mod001-harness containers after all drills=''
NO-DESKTOP: PASS -- Docker Desktop processes after=b''
```

NEG-WRG uses the **real** trusted CLI against a local synthetic Docker-API unix-socket endpoint that impersonates Desktop's identity. It is not Docker Desktop, so Desktop was never started. The endpoint saw only `/_ping` and `/info` and no container-create request. NEG-DSK only dials Desktop's stopped socket, which does not start Desktop.

File hashes after this pass (SHA-256):
- `backend/tests/harness/postgres.py`: `3e4c7d45…5f67`
- `backend/tests/unit/test_harness_postgres_fail_closed.py`: `b87eb25c…b218`
- `cap008_p1_1_colima_binding_drill.py`: `ff3b0fa1…2a72`

## Limits and residuals, disclosed rather than smoothed

- **Engine identity is self-reported.** It catches accidental substitution: Desktop, a PATH or context change, or a version or VM change. It does not stop a deliberately configured impostor daemon that reports `Name=colima` with the same version and OS strings. The engine `ID` (`5a8179fa-…-0801d9150948` today) could be pinned as well. It was not pinned, because recreating the VM would then need a code bump even when nothing else changed. This is an owner/reviewer choice.
- **Bump procedure.** A `brew upgrade docker`, a Colima VM recreate, or an in-VM `docker-ce`/Ubuntu point upgrade makes the harness fail closed until `TRUSTED_DOCKER_CLI_*` / `APPROVED_ENGINE` are deliberately updated alongside a CAP-008 re-qualification. This is intentional and mirrors the `IMAGE` digest convention.
- **Host coupling.** The harness is now bound to this macOS/Homebrew/Colima host. No CI workflow exists yet (`.github/workflows/` is absent), so nothing breaks today. A future Linux CI runner needs its own qualified binding, not a relaxation of this one.
- **Untouched here:** P1-2 (VM image / `docker-ce` provenance in registry and evidence), the six P2s, `CAPABILITY_REGISTRY.md`, CAP-008 status, BUG-038, R04, and all pre-existing uncommitted work and root scratch files. Nothing was committed or pushed.

## Next (not done by this session)

1. Distinct fresh-context independent Opus code review of this diff. No self-review was done.
2. Sonnet qualifier re-runs the stage-5 drills (the script above is reproducible from the repo root).
3. Orchestrator handles P1-2. Then a fresh Opus CAP-008 re-review.
