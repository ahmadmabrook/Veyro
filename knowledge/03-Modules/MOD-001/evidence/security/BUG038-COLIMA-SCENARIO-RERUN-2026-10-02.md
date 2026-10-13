---
doc: BUG038_COLIMA_SCENARIO_RERUN
date: 2026-10-02
status: SCN-MOD001-027 PASS; SCN-MOD001-067 harness half PASS, overall BLOCKED on R04
---

# Fresh scenario evidence on approved CAP-008

Command: `backend/.venv/bin/python -m pytest backend/tests/integration/test_authn_harness.py backend/tests/integration/test_tenant_isolation_harness.py -q -rP`

Exit code **0**, result **31 passed in 1.83s**, executed 2026-10-02 approximately 04:42:18–04:42:20 UTC. Unmodified raw stdout/stderr: `BUG038-COLIMA-SCENARIO-RERUN-RAW-2026-10-02.txt` (SHA-256 `42db33d67283cafc08fa777aeb1e3dd8b3b9a367e669f76d11b5af0acc0e6523`). It contains 13 named SCN-027 cases, with expected reason, one failure audit event each, and byte-identical observer state fingerprints before/after; also SCN-067 cross-tenant ground truth, Postgres RLS denial log, five deliberate fixture breakages, and privileged-role self-checks. The test's session fixture routes through `disposable_postgres()`; its reviewed engine-identity check fails closed before container creation on a wrong engine.

Independent post-run provenance capture from isolated Docker config and explicit Colima socket: `docker info` returned `colima | 29.5.2 | Ubuntu 24.04.4 LTS`. The daemon's retained events for `veyro-mod001-harness-f73c2a63` showed `create` and `start` at Unix second `1790916138`, then `kill`, `die`, and `destroy` at `1790916140`, all for `postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`. No harness container remained in `docker ps -a`. These events are ephemeral; this record preserves the observed lines and identity, independently corroborated by the reviewer.

SHA-256 at review: `postgres.py` `3e4c7d451aaa23e1bfec42a1c7d4e8774eecb72eafec0f2f35b842a4cf1f5f67`; `authn.py` `2dc6403648b9d3bab19a983a9878802a840f79948606ee85c5c17f827ce271be`; `test_authn_harness.py` `4becc478f6b193c73d1929056196a8e11d7381e8d6fd203d86aa9eb04554771a`; `test_tenant_isolation_harness.py` `f6a5fb8fdfa7f482998a54808af6a621d2a76f63be2cb718e06b283ade65e398`. The `authn.py` change only adds `state_before`/`state_after` to the emitted evidence; assertions are unchanged.

Fresh independent Opus review: `BUG038-COLIMA-SCENARIO-REVIEW-2026-10-02.md`. SCN-027 PASS; SCN-067 harness half PASS, but overall remains BLOCKED until R04's RLS-lint gate itself catches disabled RLS on `access_grant`.
