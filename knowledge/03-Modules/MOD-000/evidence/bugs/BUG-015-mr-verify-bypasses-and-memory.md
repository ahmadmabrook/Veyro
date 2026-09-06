---
doc: BUG-015
status: FIXED (2026-09-06)
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-security-reviewer (SEC-08, SEC-09), veyro-performance-reviewer (PERF-03)
severity: P2
---

# BUG-015: `mr_verify.py` tier-enforcement bypasses and unbounded memory use

## What is wrong

Three real bypasses of the model-tier enforcement `mr_verify.py` exists
to provide, proven live by a fresh-context `veyro-security-reviewer`:

1. **Label normalization (SEC-08).** `EXPECTED_TIER_BY_AGENT` was
   consulted only on an exact dict-key match. `"veyro-code-reviewer "`
   (trailing space), `"Veyro-Code-Reviewer"` (different case), or an
   omitted label all fell through to the caller-supplied tier with no
   cross-check — reproducing the exact defect N-9 was supposed to have
   closed, via a trivially different string.
2. **Row-type/sentinel gap (SEC-09).** `extract_models` read the `model`
   field off any JSON object with a `message` dict, not just
   `type: "assistant"` rows, and treated the harness's own out-of-band
   `<synthetic>` rate-limit sentinel as a real (inconsistent) model
   value — producing a false "possible substitution/fallback" diagnosis
   on any transcript that had ever hit a rate limit, confirmed against
   the real main-session transcript.
3. **Unreadable-transcript gap (SEC-09).** A missing/unreadable path
   raised a bare `FileNotFoundError` instead of this tool's own
   `BLOCKED:` convention.
4. **Memory amplification (PERF-03,** `veyro-performance-reviewer`**).**
   `Path(path).read_text()` + `.splitlines()` materialized the whole
   transcript plus a full line-list copy — measured ~4.9x RSS
   amplification (a 25.8 MB transcript peaked at 142.3 MB RSS).

## Remediation applied (2026-09-06)

`agent_label` is now normalized (`.strip().lower()`) before the registry
lookup and is mandatory at the CLI (exits 2 if omitted, so tier is always
taken from the registered map, never an unverified caller string alone).
`extract_models` now filters to `type == "assistant"` rows only and
explicitly ignores the `<synthetic>` sentinel rather than folding it into
the substitution-detection bucket. File access is wrapped in try/except,
emitting the standard `BLOCKED:` verdict shape on any I/O error. The tool
now streams the transcript file line-by-line via a plain file-object
iterator instead of reading the whole file into memory.

**Live-verified, all 4:** trailing-space and different-case labels now
correctly `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` (registered-tier
mismatch); an omitted label now exits 2 with usage text; a non-assistant
row with a spoofed model field is correctly ignored (falls through to
"no assistant-turn model field found"); a missing file now emits the
`BLOCKED:` JSON shape, not a traceback; a regression check against a
genuine 5-turn Opus transcript still returns `PASS`. Re-run for real
against the actual main-session transcript (13,438 lines, 26.4 MB) with
the fix in place: clean, consistent `claude-sonnet-5` result (no more
false "inconsistent model" diagnosis) — see `BUG-012` for that result's
use as SEC-01 evidence. Re-run against a real Phase 7 subagent transcript
(98 turns): `PASS`, `claude-opus-5`, confirming no regression.

## Follow-up finding and fix (2026-09-06, Phase 7 re-review RR-4)

An independent re-review found the SEC-08 fix only cross-checked the
tier when the normalized label landed EXACTLY in
`EXPECTED_TIER_BY_AGENT`. A near-miss label — `"veyro_code_reviewer"`
(underscores instead of hyphens) or `"veyro-code-reviewer-phase7"` (an
extra suffix) — still fell straight through to the caller-supplied tier
with no cross-check, letting a Sonnet transcript attest clean for an
Opus-designated role via a one-character label change: the same defect
class as N-9/SEC-08, not actually closed by the first fix. Fixed same
day: labels are now also compared in canonicalized (alphanumeric-only)
form against the registry — an exact canonical match (e.g. the
underscore case) is treated as the real role; a canonical label that
merely contains or is contained by a registered role's canonical form,
without being an exact match, is refused outright
(`BLOCKED: MODEL_ASSURANCE_UNVERIFIED`, "ambiguous near-miss label")
rather than silently accepted. Re-verified: both the reviewer's own
underscore and suffix reproductions now correctly `BLOCKED`; an exact
registered match and the genuinely distinct/unregistered
`"main-orchestrating-session-mod000"` label (needed for `BUG-012`/SEC-01
evidence) both still behave correctly; a real Opus transcript still
`PASS`es.

## Certification impact

Does not block Phase 7 on its own (P2, now fixed, including the
follow-up) — but its fix was a precondition for producing honest
evidence for `BUG-012`/SEC-01, which did block until resolved.

## Affected

`knowledge/05-QA/tools/mr_verify.py`.
