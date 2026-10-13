---
doc: CAP-008_COLIMA_OPUS_REVIEW
status: BLOCKED — P0=0, P1=2
reviewed_at: 2026-10-01 22:55 UTC (2026-10-02 01:55 Asia/Amman)
review_session: veyro-cap008-colima-opus-review-20261001
review_model: claude-opus-5-5 (mr_verify.py PASS, 32 turns)
---

# CAP-008 Colima/Lima independent security review — first round

This is a transcription of the read-only independent reviewer verdict, not an approval or a new qualification drill. The review session's ACPX id is `a6e8e31d-1d24-44f1-bfcb-e63a9c36fae7`; its saved transcript is the primary review evidence. The reviewer independently attested both its own Opus tier and the Sonnet qualifier's 147-turn transcript, and verified that the positive and unreachable-engine negative drills had real raw output. It returned **BLOCKED, P0=0, P1=2** for the current Colima binding. CAP-008 remains `QUALIFIED`, not `APPROVED`; BUG-038 remains OPEN.

## P1-1 — harness can silently select the superseded Docker Desktop engine

`backend/tests/harness/postgres.py::_docker` uses the first `docker` on PATH and the ambient Docker context. This host retains a `desktop-linux` context, Docker.app CLI links and Desktop credential-store configuration. Starting Desktop or changing PATH could run the harness against the unapproved Desktop binding without an error. The reviewer requires a fail-closed Colima binding: isolated Docker config without Desktop credentials/context; explicit Colima socket unless caller overrides it for a negative drill; pre-run engine identity check; consistent routing for cleanup; and a wrong-engine negative control. Because this is GOV-01-R02 tenant-isolation harness code, route implementation through `veyro-critical-engineer` under ADR-005 and follow with independent code review.

## P1-2 — VM image and engine package provenance omitted from registration

The reviewer read-only verified the Colima 0.10.3 cached Ubuntu 24.04 Docker VM image against the upstream `colima-core` v0.10.4 image's published SHA-512 and the checksum compiled into Colima; it also checked Colima/Lima, Docker CLI and the correctly tagged `moby/moby` `docker-v29.5.2` licences. The registry still omits the VM image itself. Record the exact image URL, full SHA-512, Ubuntu 24.04.4/kernel identity, and the in-VM `docker-ce` package origin (`colima ssh -- apt-cache policy docker-ce`) in evidence and registry. Replace the proposal's default-branch Moby-licence caveat with the per-tag result.

## Other reviewer observations

Six non-blocking P2s were disclosed: the writable home-directory mount is broader than the registry scope says; host-side loopback forwarding was not independently observed; version drift is not checked; aggregate/drift validators were run before the final registry edit; the qualification stage table retained historical Desktop statuses without a complete current-state table; and the negative drill record lacks a directly reproducible command/script. Four editorial findings include UTC/local-date confusion, one stale Docker CLI formula version, Desktop names in front matter, and stale current handoff/state. They are not promoted to P1 here.

The reviewer judged that no owner-reserved product/architecture/scope decision is needed: the same Docker API harness, pinned image, loopback/synthetic scope and fail-closed rollback remain, while only the local runtime provenance changes. No reviewer edits, Docker Desktop activation, real data, spend, R04 work, bug closure, or commit/push occurred.

Next: remediate both P1s, repeat synthetic positive, unreachable-engine negative and wrong-engine negative drills, obtain independent code review and fresh Opus CAP-008 re-review. Do not mark APPROVED before that verdict.
