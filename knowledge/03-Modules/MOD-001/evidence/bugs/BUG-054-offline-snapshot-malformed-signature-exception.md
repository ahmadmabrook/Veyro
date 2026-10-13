---
doc: BUG-054
module: MOD-001
status: FIXED_LOCAL_AWAITING_SHARED_ASSURANCE
priority: P2
requirement: GOV-01-R03
scenarios: SCN-MOD001-032
---

# BUG-054 — Offline fixture raises instead of denying malformed signatures

The local C06 post-implementation probe under runner `00d48d4c-7ea5-49cc-a2be-b341e28f31e0` reproduced two fail-closed verdict breaches in `tools/offline_snapshot_fixture.py`. A valid synthetic snapshot whose `signature` is replaced by a non-ASCII string (`é`) raises `TypeError` from `hmac.compare_digest` instead of returning `SnapshotVerdict(DENY, ...)`. A mapping with both string and integer extra keys raises `TypeError` while sorting unexpected envelope keys. The non-ASCII signature is valid JSON input; malformed-input denial is mandatory for the SCN-032 harness. Neither probe showed unauthorized VALID, but an exception is not the specified deny verdict.

Reproducer: construct a valid envelope with `make_snapshot(..., key=TEST_ONLY_SIGNING_KEY)`, replace `signature` with `é`, and call `validate_snapshot(..., now=issued_at+1)`; separately add both `extra` and integer key `42`. Both throw `TypeError`. See `knowledge/03-Modules/MOD-001/evidence/implementation/M1-C-06-R03-SOURCE-BOUNDARY-2026-10-09.md`.

**Status: FIXED LOCALLY, AWAITING SHARED ASSURANCE (2026-10-09).** Runner `9876779d-8458-411f-9280-2470011918bb` corrected both cases within C06: non-ASCII signatures return `DENY/SIGNATURE_NOT_ASCII`; mixed-type extra keys return `DENY/FIELD_SET_MISMATCH` with an unexpected-key count, never key values. Independent replay: 8/8 focused tests, Ruff check/format, and compile PASS. `tools/offline_snapshot_fixture.py` SHA-256 `2d348cf31b4a44a7a401bdc27a4879c61e4aced8ac0848bb95dbdde98ae28a38`; focused tests SHA-256 `67dce99c090bf0cf78c98fb22dc6c0087b70c28444a9e2c5c2070bdf0b25acb5`. SCN-032 remains NOT EXECUTED until the shared C06 scenario/CI/assurance boundary. No new review entitlement or plan operation was created.
