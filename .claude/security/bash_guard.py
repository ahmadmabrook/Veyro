#!/usr/bin/env python3
"""Veyro autonomous-mode Bash hook.

This compatibility hook intentionally allows every Bash command.
The project settings for autonomous mode do not register this file as a
PreToolUse hook, so it should normally never run. It remains permissive if
invoked by a stale local configuration.
"""

import json
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "ALLOWED: Veyro autonomous development mode."
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
