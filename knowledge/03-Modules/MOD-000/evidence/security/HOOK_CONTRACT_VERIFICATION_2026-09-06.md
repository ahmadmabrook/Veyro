---
doc: HOOK_CONTRACT_VERIFICATION
status: VERIFIED (2026-09-06) — PreToolUse can technically enforce Bash execution
found_by: this session, verified against the installed Claude Code binary and live docs
---

# PreToolUse hook contract — verified against installed Claude Code

## Environment

`claude --version` → **2.1.167 (Claude Code)**, installed at
`/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code` (npm package
`@anthropic-ai/claude-code`), binary
`bin/claude.exe` (Mach-O 64-bit arm64, 220,038,816 bytes).

## Verification method (two independent sources, cross-checked, not assumed)

1. **Embedded documentation extracted directly from the installed binary**
   via `strings bin/claude.exe`, locating the bundled "Hooks
   Configuration" reference text this exact build ships with (this is
   what this Claude Code instance's own runtime references, not a guess
   about some other version).
2. **Live docs** fetched from `https://code.claude.com/docs/en/hooks.md`
   (the canonical URL this project's own bundled "Live Documentation
   Sources" index names for hook schema questions), specifically the
   `PreToolUse`-focused page's full field/schema listing.

Both sources agree on every field name and semantic below — no
discrepancy found. Nothing here is inferred from prior conversation or
example schemas from earlier phases; it is re-derived from the actual
installed tool.

## Verified contract

### Hook registration shape (`.claude/settings.json`)

```json
"hooks": {
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        { "type": "command", "command": "<script>", "timeout": <seconds> }
      ]
    }
  ]
}
```

- `matcher` filters by **tool name** (`"Bash"`, `"Edit|Write"`, or a regex
  like `"mcp__.*"`).
- An optional `if` field on an individual hook entry supports Claude
  Code's own permission-rule syntax (e.g. `"if": "Bash(rm *)"`) for
  matcher-level pre-filtering, with documented best-effort behavior for
  `VAR=value` stripping, `&&`-chain splitting, and `$()`/backtick
  extraction. **Not used for this guard** — the guard is registered with
  a bare `"matcher": "Bash"` (no `if`) so it runs on every Bash
  invocation and performs its own complete analysis internally, rather
  than relying on the harness's own best-effort pre-filter for the
  security-critical decision.
- Hook `type: "command"` runs a shell command; stdin carries the JSON
  payload below. `"timeout"` is in seconds (default 600s, some events
  default lower).

### Input payload (stdin JSON, verified fields used by this guard)

```json
{
  "session_id": "...",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "rm -rf /tmp/build",
    "description": "...",
    "timeout": 120000,
    "run_in_background": false
  },
  "tool_use_id": "..."
}
```

The guard reads exactly `tool_name` (to confirm it is `"Bash"`, defensive
— the matcher already guarantees this) and `tool_input.command` (the
actual shell command string to analyze). No other field is required for
this guard's function.

### Output payload (stdout JSON, exit 0)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "BLOCKED: DESTRUCTIVE_GIT_OPERATION — ..."
  }
}
```

- `permissionDecision`: `"allow"` | `"deny"` | `"ask"`. `"deny"` **requires**
  `permissionDecisionReason` (verified in both sources).
- When the guard finds no violation, it prints **nothing** and exits 0 —
  this is a valid "no decision" response; Claude Code then falls through
  to the existing `permissions.deny`/`allow`/`defaultMode` logic in
  `.claude/settings.json`, exactly as it does today. This is what
  implements "keep deny patterns as defense-in-depth, add the guard on
  top" — the guard only actively intervenes when it identifies a
  prohibited pattern; otherwise it steps out of the way.

### Exit-code semantics (verified)

| Exit code | Behavior |
|---|---|
| 0 | Success; `hookSpecificOutput.permissionDecision` (if present and valid JSON) is honored. Empty/no stdout = no decision, normal flow applies. |
| 2 | **Hard block regardless of JSON.** stderr becomes the shown reason. |
| other (1, 3, ...) | Non-blocking; tool call proceeds; a valid JSON decision on stdout is still honored if present. |

**This guard's convention:** always exit 0. Deny decisions are expressed
via the JSON `permissionDecision: "deny"` path, not via exit 2 — this
keeps the guard's own crash/bug behavior from being silently equivalent
to "hard deny everything" and makes its decisions individually
inspectable in the JSON. The one exception is the guard's own internal
parse-failure fail-closed path (see `bash_guard.py`'s `main()`), which
still uses exit 0 + an explicit `deny` JSON (not exit 2), so the reason
string is always visible and consistent.

## Conclusion

**PreToolUse can technically enforce Bash execution in this installed
Claude Code version (2.1.167).** Not BLOCKED. Proceeding to build
`.claude/security/bash_guard.py` against this exact verified contract.
