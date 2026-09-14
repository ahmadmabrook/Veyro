---
doc: BUG-028
status: CLOSED
module: MOD-001
severity: P1 (blocked GOV-01 requirement materialization; never blocked MOD-001 activation/bookkeeping)
opened: 2026-09-13
closed: 2026-09-14
---

# BUG-028 — No guard-compliant docx read path for the governing EIP/TSD

## Finding

This project's `.claude/security/bash_guard.py` (CAP-007, ACTIVE since
2026-09-08) is allow-by-construction: only an explicit command-family
allowlist is permitted, everything else denies. That allowlist has no
shape for `pandoc`, `unzip`, or inline `python3` execution — confirmed
by direct denied attempts this session, not assumed:

- `pandoc -t markdown "Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx" -o /tmp/eip.md` → `BLOCKED: UNKNOWN_COMMAND — 'pandoc' is not an allowlisted command`
- `unzip -l "Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx"` → `BLOCKED: UNKNOWN_COMMAND — 'unzip' is not an allowlisted command`
- The Claude Code `Read` tool (not gated by `bash_guard.py`) refuses the
  file outright: `This tool cannot read binary files. The file appears
  to be a binary .docx file.`

No durable markdown mirror of the EIP or TSD exists in `knowledge/` (the
design bundle has one for the Blueprint only —
`veyro-product-experience-design/project/blueprint.md`). A prior
session evidently *did* read the EIP via `pandoc` — `DEVELOPMENT_CONSTITUTION.md`
line 94-96 cites `/tmp/eip_full.md` as its source for the 9 DC rules it
added on 2026-09-05, which predates CAP-007's 2026-09-08 activation —
but that extract lived only in `/tmp`, which is not durable, and was
confirmed gone this session (`Read` on `/tmp/eip_full.md` →
`File does not exist`).

## Why this matters for MOD-001 specifically

MOD-000 never needed to re-read the EIP/TSD after the guard activated —
its own Scenario Catalog and `REQUIREMENTS.md` were authored in chunk 1
(2026-09-01), before CAP-007 existed. MOD-001 is the first module whose
planning genuinely requires *fresh* docx access (the MOD-001 EIP
execution card, GOV-01-R01..R08's exact text, TSD §24.1's six
architecture gates, Appendix G/H) under a session that is already
guarded. This is a previously-latent gap in the project's own
architecture, not a MOD-001-specific defect — any future module's
planning stage would hit the same wall.

## Options considered (not unilaterally decided — routed to the owner)

1. Best-effort materialization from the mission brief's own supplied
   text + whatever MOD-000's vault already cites, explicitly flagged as
   not independently docx-verified (mirrors the existing precedent in
   `.claude/rules/admin-privileged-console-baseline.md`).
2. Owner extracts the EIP/TSD to markdown outside this guarded session
   (own terminal, `pandoc`) and commits the mirrors under
   `knowledge/00-System/` — durable, guard-compliant, reusable by every
   future session, closest analogue to the design bundle's `blueprint.md`.
3. Extend `bash_guard.py`'s allowlist with a narrow, read-only
   `pandoc -t markdown` shape restricted to the 4 governing baseline
   paths — closes the gap for all future sessions without owner
   involvement each time, but is itself a security-relevant change to
   CAP-007 and would need the same independent security re-review every
   prior guard change has gone through before being trusted.
4. Stop entirely until resolved.

## Decision

**Owner chose option 2** ("you extract, I continue"), 2026-09-13. Exact
commands handed to the owner to run in their own terminal:

```bash
pandoc -t markdown "Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx" -o knowledge/00-System/EIP_MIRROR.md
```

```bash
pandoc -t markdown "Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx" -o knowledge/00-System/TSD_MIRROR.md
```

**Status: CLOSED (2026-09-14).** Owner ran `pandoc` outside this guarded
session and committed both mirrors (`knowledge/00-System/EIP_MIRROR.md`,
22433 lines; `knowledge/00-System/TSD_MIRROR.md`, 18070 lines). This
session independently verified, not merely trusted:

1. `verify_baselines.py` re-run — **PASS, 4/4** governing baseline
   hashes unchanged. The mirrors are new files alongside the baselines,
   not edits to them.
2. Each mirror's own identity text matches the artifact it claims to be:
   `EIP_MIRROR.md` line 46 reads `Document ID  VEYRO-EIP-1.4.1-20260827`
   (exact match to `PROJECT_INDEX.md`'s bound identity); `TSD_MIRROR.md`'s
   Document Control table (lines 30-60) reads `Document: Veyro Technical
   System Design`, `Version: 1.4.1`.
3. Read real MOD-001-relevant content out of both mirrors and confirmed
   it is genuinely substantive, not boilerplate or truncated: the full
   §21.2 MOD-001 execution card (`EIP_MIRROR.md` lines 4099-4302), the
   GOV-01-R01..R08 Appendix B traceability rows (lines 17540-17580,
   matching the mission brief's own GOV-01 text exactly — cross-check
   passed), Appendix G's three category-matrix tables showing MOD-001's
   full required-category row (lines 19585, 19748, 19911), Appendix H's
   capability-governance sections (lines 20581+), and TSD §24.1 "Pipeline
   Gates" (`TSD_MIRROR.md` lines 11595-11654, confirming the "six
   architecture gates" are: RLS lint, module dependency/SQL lint, event
   contract lint, permission lint, screen contract lint, and domain
   contract uniqueness lint).

**The docx-read capability gap for this session's MOD-001 planning is
genuinely resolved.** The residual — no *durable, guard-compliant*
extraction path exists for a *future* guarded session without repeating
this same owner round-trip — is real but explicitly out of scope for
this bug (this bug was about unblocking MOD-001 planning now, not about
building CAP-007 allowlist infrastructure). If a later module's planning
hits the same wall, re-open a fresh bug rather than reopening this one;
option 3 from the original decision set (a reviewed, narrow
`bash_guard.py` allowlist addition) remains available if the owner wants
a standing fix instead of repeating the manual extraction each time.

## Non-goals of this fix

The mirrors are a **read convenience for guarded sessions only** — they
are not, and must never be treated as, a governing baseline. The 4
governing baseline artifacts (hash-pinned in `PROJECT_INDEX.md`) remain
the sole source of truth; on any divergence between a mirror and the
real docx, the docx (re-hashed via `verify_baselines.py`) wins. This bug
does not authorize, and this session did not perform, any edit to the
governing `.docx` files themselves.
