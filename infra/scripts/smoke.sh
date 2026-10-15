#!/usr/bin/env bash
# Smoke check: smoke.sh <expected-environment> <expected-release> [port]
# Retries /healthz, then requires exact environment and release match.
set -euo pipefail
env_expected="${1:?environment}"
release_expected="${2:?release}"
port="${3:-${VEYRO_PORT:-8000}}"
expected="{\"status\":\"ok\",\"service\":\"veyro-api\",\"environment\":\"${env_expected}\",\"release\":\"${release_expected}\"}"
for _ in $(seq 1 20); do
  body="$(curl -fsS "http://127.0.0.1:${port}/healthz" 2>/dev/null || true)"
  if [ "$body" = "$expected" ]; then
    echo "smoke OK: $body"
    exit 0
  fi
  sleep 1
done
echo "smoke FAILED: expected $expected, last body: ${body:-<none>}" >&2
exit 1
