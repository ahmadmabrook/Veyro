# Rule: Admin/Privileged-Console Baseline (MOD-029 binding)

Authored 2026-09-04 (Phase 5 remediation, F5-017 — this rule did not exist;
`SCN-MOD000-079` required it as a mandatory MOD-000 output and it had never
been authored). Grounded in EIP §4.3's Admin Web profile requirements as
cited by the Phase 5 independent review — **a future session should
re-verify the exact clause text against the EIP source docx directly**,
since this was authored from a secondhand citation, not an independent
re-read of §4.3 by this session.

This rule governs any future internal admin/support-console surface
(binds forward to MOD-029, whichever module eventually builds it — MOD-000
itself has no such surface yet). It is a baseline to be inherited, not
something MOD-000 needs to satisfy against its own current work.

## Required controls for any privileged/admin/support-console workflow

1. **Impersonation reason + approval.** Any action taken "as" or "on
   behalf of" another account requires a recorded reason and an approval
   step before the session starts, not after.
2. **Explicit start/end and time limits.** A privileged session has a
   declared start time, a declared end time or maximum duration, and
   auto-expires — no open-ended privileged access.
3. **Visible support-access banner.** Whenever an operator is acting with
   elevated/impersonated access, the UI must visibly indicate this to
   anyone who could see the session (both to the operator and, where
   applicable, to the affected user).
4. **Break-glass restriction.** Emergency/break-glass access (bypassing
   normal approval) is a separate, more restricted path with its own
   logging and mandatory after-the-fact review — never the default way to
   get privileged access.
5. **Full privileged audit.** Every privileged action is logged with
   who, what, when, why (the recorded reason from #1), and what was
   touched — durable, not just ephemeral request logs.
6. **Diagnostics redaction.** Any diagnostic/debug output surfaced during
   a privileged session redacts real member data by default; unredacted
   access requires its own explicit, logged justification.

## Fail-closed rule

A privileged-console workflow that cannot satisfy all six controls above
does not ship. This is binding on MOD-029 (or whichever module implements
the admin/support console), not on MOD-000 itself.
