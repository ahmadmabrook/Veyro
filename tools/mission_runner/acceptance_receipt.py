"""Offline, bounded, fail-closed verifier for preserved v1 product-acceptance receipts (stdlib only, no network, read-only).

A receipt `<evidence>/acceptances/<module>.json` is the v1 operator's CLAIM. It is trusted only after every part is re-verified
here, with the semantics of the v1 runner's verify_receipt: the receipt file is byte-for-byte the pinned copy; the activation commit
is an ancestor of the repo HEAD; the recorded CI evidence is a completed, successful push run of the CI workflow on exactly that
commit; and two DISTINCT review outputs (a gatekeeper and an activation review), each hashed in the receipt, bound to that commit,
parse as a CLI json success whose single standalone verdict line is APPROVED and whose every meaningfully-used model is Opus.

CI itself cannot be observed offline: the recorded run is the operator's evidence, bound here to the activation sha and nothing
more. Completing a task is never acceptance; this module only answers 'does this preserved receipt still verify'. It never writes.
Any missing, malformed, oversized, symlinked, unpinned or mismatching input raises ReceiptError.
"""
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

RECEIPT_SCHEMA = 1
RECEIPT_MAX_BYTES = 64 * 1024
REVIEW_MAX_BYTES = 8 * 1024 * 1024
MAX_REVIEWS = 10
CI_WORKFLOW_NAME = "Veyro Foundation CI"
REVIEW_KINDS = ("gatekeeper", "activation-review")
MODULE_RE = re.compile(r"^MOD-\d{3}$")
SHA_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
VERDICT_LINE_RE = re.compile(
    r"^(?:OUTCOME:\s*(APPROVED|CHANGES_REQUESTED|BLOCKED)\s*|\*\*OUTCOME:\s*(APPROVED|CHANGES_REQUESTED|BLOCKED)\.?\*\*.*)$")
FAMILIES = ("opus", "sonnet", "haiku")
TOKEN_FIELDS = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")


class ReceiptError(Exception):
    """The receipt does not verify. The message names the first failed predicate."""


def read_regular(path, limit, what):
    """Bytes of a regular, non-symlink file no larger than `limit`, or ReceiptError. Never blocks on a FIFO."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        raise ReceiptError(f"{what}: cannot be opened ({type(e).__name__})")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            raise ReceiptError(f"{what}: not a regular file within {limit} bytes")
        data = b""
        while len(data) <= st.st_size:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            data += chunk
    except OSError as e:
        raise ReceiptError(f"{what}: unreadable ({type(e).__name__})")
    finally:
        os.close(fd)
    if len(data) > limit:
        raise ReceiptError(f"{what}: larger than {limit} bytes")
    return data


def receipt_path(evidence, module):
    return Path(evidence) / "acceptances" / f"{module}.json"


def receipt_sha256(evidence, module):
    """sha256 of the receipt file as it sits in the evidence tree (used to check the byte-for-byte copy against its pin)."""
    return hashlib.sha256(read_regular(receipt_path(evidence, module), RECEIPT_MAX_BYTES, f"{module} receipt")).hexdigest()


def _family(model):
    return next((f for f in FAMILIES if f in model.lower()), "unknown")


def _tokens(u, key):
    v = u.get(key)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0


def opus_verified(parsed):
    """v1 judge_route('gatekeeper', ...) == VERIFIED: token usage is reported per model, the primary (largest) model is Opus and
    no non-Opus model consumed any token. The name is `canonicalModel` when given, else the modelUsage key."""
    usage = (parsed or {}).get("modelUsage")
    models = {}
    for key, u in (usage.items() if isinstance(usage, dict) else ()):
        if not isinstance(u, dict):
            continue
        canon = u["canonicalModel"] if isinstance(u.get("canonicalModel"), str) and u.get("canonicalModel") else key
        models[canon] = models.get(canon, 0) + sum(_tokens(u, k) for k in TOKEN_FIELDS)
    used = sorted(((m, n) for m, n in models.items() if n > 0), key=lambda x: -x[1])
    return bool(used) and used[0][1] > 0 and all(_family(m) == "opus" for m, _ in used)


def review_outcome(result):
    """Verdict of an offline review: only standalone verdict LINES count (plain, or the Markdown bold form). Inline prose is
    ignored; none, several or contradictory standalone lines make it unverifiable (None)."""
    if not isinstance(result, str):
        return None
    found = [m.group(1) or m.group(2) for m in (VERDICT_LINE_RE.match(ln.strip()) for ln in result.splitlines()) if m]
    return found[0] if len(found) == 1 else None


def _under(evidence, rel, module):
    rel = Path(rel)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ReceiptError(f"{module}: review path escapes the evidence tree")
    path = Path(evidence) / rel
    if Path(evidence).resolve() not in path.resolve().parents:
        raise ReceiptError(f"{module}: review path escapes the evidence tree")
    return path


def load_review(evidence, rel, sha256, module):
    path = _under(evidence, rel, module)
    data = read_regular(path, REVIEW_MAX_BYTES, f"{module}: review {path.name}")
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ReceiptError(f"{module}: review {path.name} does not match its recorded sha256")
    try:
        parsed = json.loads(data)
    except ValueError:
        raise ReceiptError(f"{module}: review {path.name} is not CLI json")
    if not (isinstance(parsed, dict) and parsed.get("subtype") == "success" and parsed.get("is_error") is not True
            and review_outcome(parsed.get("result")) == "APPROVED" and opus_verified(parsed)):
        raise ReceiptError(f"{module}: review {path.name} is not an APPROVED, Opus-verified success")


def is_ancestor(repo, sha, git="git"):
    """True only when `git merge-base --is-ancestor sha HEAD` exits 0 (an unknown commit, a non-ancestor, a missing git, a
    timeout and every other failure are all False)."""
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "LC_ALL": "C", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    try:
        r = subprocess.run([git, "-c", "core.fsmonitor=", "-C", str(repo), "merge-base", "--is-ancestor", sha, "HEAD"],
                           capture_output=True, timeout=10, env=env, stdin=subprocess.DEVNULL)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def verify_receipt(evidence, repo, module, pin, git="git"):
    """Return {'module', 'activation_sha', 'reviews'} when the preserved receipt for `module` fully verifies, else ReceiptError.

    `pin` is the sha256 the operator recorded for the receipt file at cutover; it is mandatory."""
    if not (isinstance(module, str) and MODULE_RE.match(module)):
        raise ReceiptError(f"{module!r}: not a module id")
    if not (isinstance(pin, str) and SHA256_RE.fullmatch(pin)):
        raise ReceiptError(f"{module}: no pinned sha256 for the receipt; an unpinned copy is not evidence")
    raw = read_regular(receipt_path(evidence, module), RECEIPT_MAX_BYTES, f"{module} receipt")
    if hashlib.sha256(raw).hexdigest() != pin:
        raise ReceiptError(f"{module}: receipt is not the byte-for-byte pinned copy")
    try:
        r = json.loads(raw)
    except ValueError:
        raise ReceiptError(f"{module}: receipt is not valid JSON")
    if not isinstance(r, dict) or r.get("schema") != RECEIPT_SCHEMA or r.get("module") != module:
        raise ReceiptError(f"{module}: receipt schema/module mismatch")
    if not (isinstance(r.get("operator"), str) and r["operator"].strip() and isinstance(r.get("recorded_at"), str)):
        raise ReceiptError(f"{module}: receipt lacks operator/recorded_at")
    if r.get("mode") is not None:
        raise ReceiptError(f"{module}: receipt mode {r.get('mode')!r} is not preserved here")
    sha = r.get("activation_sha")
    if not (isinstance(sha, str) and SHA_RE.fullmatch(sha)):
        raise ReceiptError(f"{module}: activation_sha is not a full commit sha")
    ci = r.get("ci")
    if not (isinstance(ci, dict) and isinstance(ci.get("run_id"), str) and ci["run_id"].isdigit() and ci.get("event") == "push"
            and ci.get("status") == "completed" and ci.get("name") == CI_WORKFLOW_NAME and ci.get("head_sha") == sha
            and ci.get("conclusion") == "success"):
        raise ReceiptError(f"{module}: CI evidence is not a completed successful {CI_WORKFLOW_NAME} push run on the activation sha")
    if not is_ancestor(repo, sha, git):
        raise ReceiptError(f"{module}: activation sha {sha[:12]} is not an ancestor of repo HEAD (stale or unknown)")
    reviews = r.get("reviews")
    if not (isinstance(reviews, list) and 0 < len(reviews) <= MAX_REVIEWS):
        raise ReceiptError(f"{module}: receipt has no reviews")
    seen = {}
    for rv in reviews:
        if not (isinstance(rv, dict) and rv.get("kind") in REVIEW_KINDS and isinstance(rv.get("path"), str)
                and isinstance(rv.get("sha256"), str) and SHA256_RE.fullmatch(rv["sha256"])):
            raise ReceiptError(f"{module}: malformed review entry")
        if rv.get("activation_sha") != sha:
            raise ReceiptError(f"{module}: review {rv['path']} is not bound to the activation sha")
        load_review(evidence, rv["path"], rv["sha256"], module)
        seen.setdefault(rv["kind"], set()).add(rv["sha256"])
    if set(seen) != set(REVIEW_KINDS) or seen["gatekeeper"] & seen["activation-review"]:
        raise ReceiptError(f"{module}: receipt needs distinct approved gatekeeper and activation-review evidence")
    return {"module": module, "activation_sha": sha, "reviews": sorted(h for hs in seen.values() for h in hs)}
