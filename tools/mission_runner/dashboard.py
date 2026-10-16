"""Read-only, loopback-only Veyro Engineering Mission Control."""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import runner

UI_DIR = Path(__file__).resolve().parent
CATALOG = json.loads((UI_DIR / "module_catalog.json").read_text())
HTML = (UI_DIR / "dashboard.html").read_text()
CSS = (UI_DIR / "dashboard.css").read_text()
JS = (UI_DIR / "dashboard.js").read_text()
ASSETS = {"/": ("text/html; charset=utf-8", "dashboard.html"),
          "/app.css": ("text/css; charset=utf-8", "dashboard.css"),
          "/app.js": ("text/javascript; charset=utf-8", "dashboard.js")}
MEANINGFUL_EVENTS = {"dispatch", "task-done", "task-blocked", "command-applied", "runner-start", "runner-exit"}


def module_records(repo):
    """Read the module's recorded verdict; CI freshness is a separate observation."""
    out = {}
    for item in CATALOG:
        module = item["id"]
        path = Path(repo) / "knowledge" / "03-Modules" / module / f"{module}.md"
        if not path.is_file() or path.is_symlink():
            continue
        try:
            body = path.read_text()[:200_000]
            if not body.startswith(f"# {module}"):
                continue
            header = body[:1000]
            match = re.search(r"\*\*Status:\s*([^*\n]+)\*\*", header)
            status = match.group(1).strip() if match else "UNKNOWN"
            recorded = bool(re.match(r"ACCEPTED\b", status, re.I))
            certificate = path.parent / "APPROVAL.md"
            certificate_status = None
            if certificate.is_file() and not certificate.is_symlink():
                cert = certificate.read_text()[:1500]
                cert_match = re.search(r"\*\*Status:\s*([^*\n]+)\*\*", cert)
                certificate_status = cert_match.group(1).strip() if cert_match else "UNKNOWN"
            discrepancy = None
            if recorded and certificate_status and not re.match(r"APPROVED\b", certificate_status, re.I):
                discrepancy = "Module header says accepted, but approval certificate is not approved."
            elif recorded and certificate_status and "PENDING" in certificate_status.upper():
                discrepancy = "Approval certificate still records an activation condition as pending; current CI evidence is shown separately."
            elif recorded and not certificate_status and "gatekeeper" not in header.lower():
                discrepancy = "No approval certificate or gatekeeper reference was found in the module header."
            section = re.search(r"(?m)^## Requirements[^\n]*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
            requirements = ([line.strip()[2:] for line in section.group(1).splitlines()
                             if line.strip().startswith("- ")][:24] if section else [])
            next_section = re.search(r"(?m)^## Exact next action[^\n]*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
            next_action = (next((line.strip() for line in next_section.group(1).splitlines() if line.strip()), None)
                           if next_section else None)
            record_valid = recorded and not (discrepancy and "not approved" in discrepancy)
            out[module] = {"accepted": record_valid, "recorded_accepted": record_valid,
                           "header_accepted": recorded, "status": status,
                           "certificate_status": certificate_status, "discrepancy": discrepancy,
                           "requirements": requirements, "next_action": next_action,
                           "updated_at": path.stat().st_mtime, "path": str(path.relative_to(repo))}
        except (OSError, UnicodeError, ValueError):
            continue
    return out


CI_WORKFLOW = "Veyro Foundation CI"


def ci_confirms_head(ci):
    """Current-head display guard from the committed MOD-001 certificate."""
    if not isinstance(ci, dict) or ci.get("state") != "fresh" or ci.get("error"):
        return False
    head = ci.get("head_sha")
    if (ci.get("scope"), ci.get("branch"), ci.get("head_matches_local")) != ("main-push", "main", True) \
            or not isinstance(head, str) or not head:
        return False
    runs = ci.get("runs")
    if not isinstance(runs, list):
        return False
    exact = [r for r in runs if isinstance(r, dict) and r.get("event") == "push" and r.get("head_sha") == head]
    if any(r.get("status") != "completed" or r.get("conclusion") != "success" for r in exact):
        return False
    return any(r.get("name") == CI_WORKFLOW and r.get("ref") == "main" for r in exact)


def worktree_clean(repo):
    """Fail closed: never report current-head acceptance for uncommitted content."""
    try:
        p = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
                           capture_output=True, text=True, timeout=2, stdin=subprocess.DEVNULL,
                           env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return p.returncode == 0 and p.stdout == ""


def gate_module_records(records, ci, clean):
    confirmed = clean is True and ci_confirms_head(ci)
    return {mid: dict(rec, accepted=bool(rec.get("accepted") and confirmed),
                      recorded_accepted=bool(rec.get("recorded_accepted", rec.get("accepted"))))
            for mid, rec in records.items()}


def module_projection(catalog, records, tasks):
    def recorded(mid):
        rec = records.get(mid, {})
        return rec.get("recorded_accepted", rec.get("accepted", False))
    running = {t["module"] for t in tasks if t["status"] == "RUNNING"}
    active = next((m["id"] for m in catalog if m["id"] in running), None)
    if active is None:
        # Tasks are timestamp-sorted; the latest live-evidence task whose module
        # lacks current-head verification names the current module.
        known = {m["id"] for m in catalog}
        active = next((t["module"] for t in reversed(tasks)
                       if t["module"] in known and t["status"] in ("QUEUED", "RUNNING", "DONE")
                       and not records.get(t["module"], {}).get("accepted", False)), None)
    result = {}
    for m in catalog:
        mid = m["id"]
        if mid == active:
            status = "current"
        elif recorded(mid):
            status = "accepted"
        elif any(t["module"] == mid and t["lifecycle"] == "active-blocker" for t in tasks):
            status = "blocked"
        else:
            status = "not-started"
        result[mid] = status
    return active, result


def _epoch(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return parsed.timestamp() if parsed.tzinfo else None


def accepted_after_block(rec, task):
    """True only when a recorded acceptance was written after the task's last update; fail closed."""
    if not rec.get("recorded_accepted", rec.get("accepted", False)):
        return False
    written = rec.get("updated_at")
    if isinstance(written, bool) or not isinstance(written, (int, float)) or written != written:
        return False
    stamps = [task.get(k) for k in ("updated_at", "finished_at") if task.get(k)]
    epochs = [_epoch(s) for s in stamps]
    if not epochs or any(e is None for e in epochs):
        return False
    return written > max(epochs)


def task_projection(tasks, records):
    # state.json is serialized with sorted keys, so dictionary order is not
    # task history. Lifecycle supersession must follow recorded timestamps.
    tasks = [t for _, t in sorted(enumerate(tasks), key=lambda pair:
                                (pair[1].get("created_at") or pair[1].get("started_at") or "", pair[0]))]
    projected = []
    for index, t in enumerate(tasks):
        rec = records.get(t["module"], {})
        module_accepted = accepted_after_block(rec, t) if t["status"] == "BLOCKED" else False
        # A later task makes an earlier blocked attempt historical activity, not a
        # current queue item. It does not claim the defect was formally resolved.
        later_work = any(other["module"] == t["module"] and other["status"] in ("QUEUED", "RUNNING", "DONE")
                         for other in tasks[index + 1:])
        historical_block = t["status"] == "BLOCKED" and (module_accepted or later_work)
        history_reason = ("Module subsequently accepted" if module_accepted else
                          "Later task followed; formal resolution not recorded") if historical_block else None
        lifecycle = "historical" if historical_block else ("active-blocker" if t["status"] == "BLOCKED" else t["status"].lower())
        route = t.get("route") or {}
        evidence = t.get("evidence") or {}
        projected.append({k: t.get(k) for k in ("id", "module", "role", "title", "plan_phase", "status", "stage",
                                                  "attempts", "max_attempts", "started_at", "finished_at", "updated_at",
                                                  "blocked_reason", "last_error", "child_pid")}
                         | {"lifecycle": lifecycle, "history_reason": history_reason,
                            "model": route.get("primary") if route.get("verdict") == "VERIFIED" else None,
                            "route_verdict": route.get("verdict"), "review_outcome": evidence.get("review_outcome"),
                            "verify": evidence.get("verify"), "changed": [x.get("path") for x in evidence.get("changed", [])]})
    return projected


def agent_projection(state, tasks):
    current = next((t for t in tasks if t["status"] == "RUNNING"), None)
    dispatch = next((e for e in state.get("events", []) if e.get("kind") == "dispatch"
                     and current and e.get("task_id") == current["id"]), None)
    lock = state.get("writer_lock") or {}
    process_alive = state.get("runner_alive") or runner.pid_alive((state.get("runner") or {}).get("pid"))
    working = bool(current and process_alive and lock.get("state") == "held"
                   and lock.get("child_alive") is True and dispatch)
    receipt = state.get("orchestrator") or {}
    linked = next((t for t in tasks if t["id"] == receipt.get("worker_task_id")), None)
    recorded = receipt.get("evidence") == "recorded"
    stale = receipt.get("age_s", 10**9) > 900
    orch_state = receipt.get("state") if recorded and not stale else "unknown"
    if orch_state == "waiting" and (not linked or linked["status"] not in ("QUEUED", "RUNNING")):
        orch_state = "unknown"  # a completed handoff is not evidence of a current decision
    agents = [{"name": "Orchestrator", "status": orch_state, "role": "Mission coordination",
               "task": receipt.get("decision") if recorded else None, "since": receipt.get("decision_at") if recorded else None,
               "last_activity": receipt.get("decision_at") if recorded else None,
               "identity": (receipt.get("identity", "UNKNOWN") + " · " + (receipt.get("model") or "UNKNOWN")) if recorded
                           else "UNKNOWN · no orchestrator receipt", "last_action": receipt.get("last_action") if recorded else None}]
    for family, name in (("sonnet", "Claude Sonnet"), ("opus", "Claude Opus")):
        matching = working and dispatch.get("model_alias") == family
        latest = max((t for t in tasks if t.get("model") and family in t["model"].lower()),
                     key=lambda t: t.get("finished_at") or "", default=None)
        agents.append({"name": name, "status": "working" if matching else "idle" if process_alive else "unavailable",
                       "role": ("Implementation" if family == "sonnet" else "Independent review"),
                       "task": current["title"] if matching else None,
                       "since": current["started_at"] if matching else None,
                       "last_activity": current["started_at"] if matching else latest.get("finished_at") if latest else None,
                       "identity": "Actual model UNKNOWN · invoked --model " + family if matching
                                   else latest.get("model") if latest else "No verified invocation recorded"})
    return agents


def runner_execution(state, tasks):
    if state.get("control") == "STOP":
        return "stopped"
    if state.get("control") == "PAUSE":
        return "paused"
    if state.get("state_error"):
        return "unavailable"
    if not state.get("runner_alive"):
        return "stale" if runner.pid_alive((state.get("runner") or {}).get("pid")) else "unavailable"
    if state.get("health", {}).get("status") != "OK":
        return "blocked"
    lock = state.get("writer_lock") or {}
    running = [t for t in tasks if t["status"] == "RUNNING"]
    if running:
        if lock.get("state") == "held" and (lock.get("child_alive") is True or
                                               any(t.get("stage") == "verifying" for t in running)):
            return "running"
        return "stale"
    if any(t["status"] == "QUEUED" for t in tasks):
        return "waiting"
    if any(t["lifecycle"] == "active-blocker" for t in tasks):
        return "blocked"
    return "idle"


def build_state(snapshot, repo):
    raw_records = module_records(repo)
    ci = snapshot.get("ci")
    clean = worktree_clean(repo) if any(r.get("recorded_accepted", r.get("accepted"))
                                       for r in raw_records.values()) else False
    records = gate_module_records(raw_records, ci, clean)
    tasks = task_projection(snapshot.get("tasks") or [], records)
    active, modules = module_projection(CATALOG, records, tasks)
    # CI is cached; accepted is an operational current-head display guard,
    # while recorded_accepted preserves the signed module decision.
    events = [e for e in snapshot.get("events", []) if e.get("kind") in MEANINGFUL_EVENTS]
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    actionable = [t for t in tasks if t["status"] in ("QUEUED", "RUNNING") or t["lifecycle"] == "active-blocker"]
    latest_success = max((t for t in tasks if t["status"] == "DONE" and t.get("route_verdict") == "VERIFIED"),
                         key=lambda t: t.get("finished_at") or "", default=None)
    health = snapshot.get("health") or {}
    health_blockers = []
    if health.get("status") == "BLOCKED":
        health_blockers.append({"id": "runner-health", "module": active, "role": "runner-health",
                                "title": "Runner baseline health blocked", "status": "BLOCKED",
                                "lifecycle": "active-blocker", "blocked_reason": health.get("code") or "Runner health blocked",
                                "last_error": health.get("detail")})
    task_blockers = [t for t in tasks if t["lifecycle"] == "active-blocker"]
    return {"generated_at": snapshot.get("generated_at"), "runner_alive": snapshot.get("runner_alive"),
            "heartbeat_age_s": snapshot.get("heartbeat_age_s"), "runner": snapshot.get("runner"),
            "control": snapshot.get("control"), "health": snapshot.get("health"), "state_error": snapshot.get("state_error"),
            "writer_lock": snapshot.get("writer_lock"), "baseline_pin": snapshot.get("baseline_pin"),
            "baseline": snapshot.get("baseline"), "pending_commands": snapshot.get("pending_commands"),
            "current_module": active, "modules": modules, "runner_execution": runner_execution(snapshot, tasks),
            "orchestrator": snapshot.get("orchestrator") or {"identity": "UNKNOWN", "model": "UNKNOWN", "state": "unknown"},
            "last_successful_worker": ({"title": latest_success["title"], "module": latest_success["module"],
                                        "model": latest_success["model"], "at": latest_success["finished_at"]}
                                       if latest_success else None),
            "module_catalog": CATALOG, "module_records": records, "tasks": tasks, "actionable_tasks": actionable,
            "active_blockers": task_blockers + health_blockers,
            "owner_action_blockers": [t for t in tasks if t["lifecycle"] == "active-blocker" and
                                      (t.get("blocked_reason") or "").startswith(("OWNER_", "BASELINE_", "RUN_ABORTED_BASELINE_", "POST_RUN_BASELINE_"))] + health_blockers,
            "historical_blocked_count": sum(t["lifecycle"] == "historical" for t in tasks),
            "agents": agent_projection(snapshot, tasks), "events": events[:80], "recent_events": events[:5],
            "usage": snapshot.get("usage") or {}, "ci": ci,
            "accepted_count": sum(v.get("accepted", False) for v in records.values()),
            "recorded_accepted_count": sum(v.get("recorded_accepted", False) for v in records.values()),
            "current_head_verified": bool(clean and ci_confirms_head(ci)), "worktree_clean": clean,
            "total_modules": len(CATALOG)}


def make_handler(cfg, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        server_version = "VeyroDash"
        def log_message(self, *args):
            pass
        def _send(self, code, ctype, body, extra=()):
            b = body.encode()
            self.send_response(code)
            for k, v in (("Content-Type", ctype), ("Content-Length", str(len(b))), ("Cache-Control", "no-store"),
                         ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
                         ("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'"),
                         *extra):
                self.send_header(k, v)
            self.end_headers()
            try:
                self.wfile.write(b)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def do_GET(self):
            if self.headers.get("Host") not in allowed_hosts:
                return self._send(403, "text/plain", "forbidden host")
            path = self.path.split("?")[0]
            if path == "/api/state":
                state = build_state(runner.snapshot(cfg), cfg.repo)
                return self._send(200, "application/json", json.dumps(state, separators=(",", ":")))
            if path in ASSETS:
                kind, asset = ASSETS[path]
                return self._send(200, kind, (UI_DIR / asset).read_text())
            return self._send(404, "text/plain", "not found")
        def _no_write(self):
            self._send(405, "text/plain", "dashboard is read-only", (("Allow", "GET"),))
        do_POST = do_PUT = do_DELETE = do_PATCH = _no_write
    return H


def make_server(cfg, port=8766):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg, 0))
    srv.RequestHandlerClass = make_handler(cfg, srv.server_address[1])
    srv.daemon_threads = True
    return srv


def serve(cfg, port):
    srv = make_server(cfg, port)
    print(f"dashboard on http://127.0.0.1:{srv.server_address[1]}/ (read-only, loopback only)", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
