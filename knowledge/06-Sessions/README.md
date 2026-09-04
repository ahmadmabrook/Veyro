---
doc: SESSIONS_README
status: LIVE
updated: 2026-09-05
---

# Sessions

Appendix D: "Immutable session summaries/handoffs; no secrets/restricted
data."

This directory did not exist before the 2026-09-05 vault migration
(BUG-017) — a real gap, not previously populated. `CURRENT_HANDOFF.md`
has served as the de facto (mutable, overwritten-each-session) handoff
record since project inception; this directory is for *immutable*
per-session archives going forward.

**Not backfilled retroactively.** Reconstructing 14 chunks of prior
session history into individual immutable files after the fact would
risk misrepresenting what was actually known/decided at each point in
time, and the real record already exists faithfully in Git commit
history (`git log`) and the superseded-but-preserved sections inside
`CURRENT_HANDOFF.md`'s own history via Git. Going forward, sessions
should archive a copy of their final `CURRENT_HANDOFF.md` content here
before the next session overwrites it, named `SESSION-<YYYYMMDD>-<NNN>.md`.
