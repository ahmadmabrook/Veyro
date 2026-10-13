---
doc: BUG-056
module: MOD-001
status: FIXED_LOCAL_AWAITING_SHARED_ASSURANCE
priority: P2
requirement: GOV-01-R03
scenarios: SCN-MOD001-039, SCN-MOD001-040
---

# BUG-056 — UI foundation lint denies valid accessible names and automatic RTL direction

Runner `ba207c34-a3d7-4e7a-a646-b6d2a4105278` produced a local synthetic HTML a11y/RTL lint candidate. Independent post-implementation probes show three false denials: `<button>Save</button>` and `<a href="/">Home</a>` each return `MISSING_ARIA_LABEL`, while `<div dir="auto">مرحبا</div>` returns `RTL_TEXT_NOT_RTL`. All are valid patterns for the respective check. The focused suite's 24/24 PASS does not exercise them. No real screen or UI content exists in MOD-001 and no user data was used.

Primary standards evidence: W3C WAI's accessible-name practice says a button or link may derive its accessible name from child text and that `aria-label` is useful when visible text cannot serve as the name (https://www.w3.org/WAI/ARIA/apg/practices/names-and-descriptions/); W3C's G211 gives `<button>Send</button>` and text links as positive accessible-name examples (https://www.w3.org/WAI/WCAG21/Techniques/general/G211). W3C Internationalization recommends `dir=auto` for dynamically inserted unknown-direction text and demonstrates correct Arabic direction handling (https://www.w3.org/International/questions/qa-html-dir). No stricter Veyro rule requiring explicit ARIA or rejecting `dir=auto` was found.

**Status: FIXED LOCALLY, AWAITING SHARED ASSURANCE.** Within the existing C06 UI lint boundary, make text content a valid name source for applicable button/link/role elements while preserving denial for an actually nameless control; accept `dir=auto` when its effective first-strong direction is RTL while preserving denial for an unhandled RTL case. Add direct positive/negative regressions. This is a local candidate correctness correction, not a new plan operation or independent review entitlement. SCN-039/040 remain NOT EXECUTED; CI and shared assurance remain pending.

## Bounded correction and verification (2026-10-09)

Runner `ad0f6e12-34ac-4b4c-a0de-d5195ea6aae4` made one guarded IMPLEMENTATION dispatch configured for `claude-sonnet-5-5`, exit 0. The adapter warned that this exact model was not in its advertised list and forwarded it to Claude Code; this record asserts configured routing, not independently attested resolved runtime identity. The worker changed only `tools/validate_ui_foundations.py` (SHA-256 `b57dd1ea918bc72703d16d528439e1db52bfc4b015b40029b11b819b7b2c093c`) and its focused tests (SHA-256 `680566fd93d3986e6bdb18bd657acd196ca77eccaaefe31a710c12e6a84826ea`). `ACTIVE_OPERATION.json` is COMPLETED/exit 0 but has no material checkpoint: the worker looked in the wrong directory for `operation_budget.py`. This is disclosed, not backfilled.

Independent replay: focused pytest **29 passed**; Ruff check and format check on both files **PASS**; `py_compile` **PASS**. Direct positives—text-labelled button, text link, and Arabic-first `dir=auto`—returned no findings. Direct negatives—empty button, Arabic without direction, and LTR-first `dir=auto` containing Arabic—returned the expected `MISSING_ARIA_LABEL`/`RTL_TEXT_NOT_RTL` findings. The correction accepts child text only for applicable name-from-content controls and handles first-strong automatic direction; the fail-closed malformed/unreadable checks remain in the focused suite.

This closes only BUG-056’s **local reproduction**. There is no CI blocking proof, qualified shared assurance, real UI run or formal scenario disposition. SCN-039/040 and all 13 C06 IDs remain NOT EXECUTED. C06 W5 completed 0/2; compressed MOD-001 remainder 19.
