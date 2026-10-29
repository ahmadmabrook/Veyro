# ADR-0004 — Govern the minimal runner's cross-user control surface

- ID: ADR-0004
- Status: ACCEPTED
- Review: MR-MOD-002-20261029-ADR0004-R2 APPROVED
- Decision-Key: minimal-runner-cross-user-control-surface
- Covers: tools/mission_runner/control.py, tools/mission_runner/veyro-ctl, tools/mission_runner/runner.py

## Decision

Place the fixed owner-to-worker control wrapper and the runner's single-writer process proof under ADR-0001 change control. Under this ADR, `runner.py` changes are limited to those the wrapper and single-writer proof require; other runner changes cite ADR-0001. The wrapper may expose only bounded status, pause, resume, stop, cancel, and enqueue operations through the runner's existing durable store; it must not start another runner, schedule tasks, grant agent tools, or decide product acceptance. A task's `source: owner` is not authentication that the owner acted, and cancellation is neither task success nor a correction-budget reset. Its installed code, interpreter, and paths must be protected from the worker's implementation agents. The v1 cutover proof and preserved evidence remain read-only and independently pinned.

This ADR supplies code-path coverage, not authority to install a sudoers rule, administer credentials, start the new runner, or enable unattended OpenClaw handoff. Those actions remain subject to `OWNER-2026-10-29-minimal-local-runner-architecture.md` and its separate cutover conditions. Product security, review, CI, module sequence, and historical task budgets are unchanged.

First publish this ADR alone under ADR-0001 with independent exact-diff review, non-force publication, and successful exact-SHA push CI. Separately add the new wrapper paths to `tools/governance/governance_check.py`'s controlled list under ADR-0001, then publish the implementation under this ADR after its own exact-diff review, non-force publication, and successful exact-SHA push CI. None of those CI runs is evidence of local runner activation.
