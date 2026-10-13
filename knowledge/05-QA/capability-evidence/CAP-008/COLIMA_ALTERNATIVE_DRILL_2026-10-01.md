# CAP-008 candidate runtime re-scope drill — 2026-10-01

Status: **synthetic positive drill executed; variant NOT independently qualified or approved.** This is a proposed replacement for Docker Desktop, not a claim that the existing Docker Desktop CAP-008 row is approved.

## Provenance and licence

Homebrew metadata on this host reported Colima 0.10.3 (MIT) and its Lima 2.2.0 dependency (Apache-2.0). Both were installed with `brew install colima`; no paid service or Docker Desktop activation was used. `colima start --cpu 2 --memory 4 --disk 20` created a local macOS Virtualization.Framework VM with Docker runtime. `docker context show` returned `colima`; `docker info` identified Docker Engine 29.5.2 on Ubuntu 24.04.4 LTS. The Docker Desktop app remained unused. Licence/provenance of the complete VM image and engine distribution still requires independent stage-4 evaluation; Homebrew metadata alone is not a full supply-chain audit.

## Bounded positive and negative evidence

Before Colima started, `disposable_postgres()` failed closed with a `RuntimeError` reporting the unavailable Docker daemon; no mock substitution occurred. After Colima started, the same `backend/tests/harness/postgres.py` fixture launched the pinned image `postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`. A synthetic-only connection confirmed loopback binding, PostgreSQL `16.15`, and `SELECT 1 -> 1`. A first probe had an incorrectly quoted diagnostic SQL query and failed after successful connection; fixture cleanup ran. The corrected probe passed. `docker image inspect` returned that exact digest and arm64 architecture. `docker ps -a --filter name=veyro-mod001-harness` returned no containers after both probes. No real data was used.

## Required before progression

Update the CAP-008 definition/manifest/registry only through a governed material-change cycle naming Colima/Lima/Engine/image exact versions and scope; repeat stage-5 positive and fail-closed negative under the revised binding; obtain a fresh independent Opus security evaluation and runtime/model attestation. Until then **CAP-008 remains PENDING, BUG-038 OPEN, Slice-5 security gate BLOCKED, and R04 untouched**. This alternative removes the unresolved Docker Desktop free-use category from the candidate runtime, but does not retrospectively approve the Desktop binding or authorize a product gate.

## 2026-10-01 13:55 UTC independent local continuation (candidate drill only)

With `colima status` reporting the macOS Virtualization.Framework VM running and `docker context show` = `colima`, the unmodified Slice-5 synthetic backend integration+unit suite ran against the candidate runtime: `backend/.venv/bin/python3 -m pytest backend/tests/integration backend/tests/unit -q` -> **35 passed in 2.33s**, exit 0. This count is the selected integration+unit subset, not a claim that every backend or governed test passed. The fixture's real Postgres container was removed: `docker ps -a --filter name=veyro-mod001-harness` returned no rows. `docker image inspect` independently returned the exact pinned digest `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`, architecture `arm64`.

Negative control in a separate process set `DOCKER_HOST=unix:///tmp/veyro-cap008-no-daemon.sock`, invoked the real `disposable_postgres()` fixture, and got the expected `RuntimeError` containing `needs a local Docker engine and never substitutes a mock`; exit 0 from the assertion script. Homebrew's installed formula metadata reported Colima 0.10.3/MIT, Lima 2.2.0/Apache-2.0, Docker CLI formula [**corrected 2026-10-02, flagged as a stale/inconsistent value by the first independent Opus capability review**: this line previously read "29.8.2"; every other check in this evidence set — `docker --version`, the per-tag `docker/cli` licence check in `COLIMA_VM_PROVENANCE_2026-10-02.md`, and this session's own re-verification — consistently reports] 29.6.0/Apache-2.0. This metadata does not establish provenance/licence for the entire VM image or Engine installation. No Docker Desktop activation, real data, spend, code change, CAP-008 approval, Slice-5 gate promotion, BUG-038 closure, or R04 work followed.

The final independent recovery-record re-review remains pending after the earlier Claude provider session-limit result; the current candidate still needs governed re-binding and a fresh Opus security evaluation before real reliance.
