"""Read-only, loopback-only Veyro Engineering Mission Control (runner v2 queue + read-only v1 history)."""
import json
import re
import sys
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
MEANINGFUL_EVENTS = {"enqueue", "dispatch", "task-done", "task-failed", "task-cancelled", "task-retry", "recovered",
                     "command-applied", "runner-start", "runner-exit", "handoff-request", "handoff-result"}


def module_records(repo, cfg=None):
    """The module's recorded verdict as COMMITTED at HEAD (an uncommitted edit is not a record); CI freshness is separate.
    With `cfg`, a conditional module also reports whether its preserved v1 receipt reverifies offline; that satisfies a dependent
    prerequisite but is never shown as unconditional acceptance."""
    out = {}
    tree = runner.head_files(repo, "knowledge/03-Modules/")
    for item in catalog_for(repo):
        module = item["id"]
        rel = runner.module_record_path(module)
        if rel not in tree:
            continue
        try:
            body = (runner.head_blob(repo, tree[rel]) or "")
            if not body.startswith(f"# {module}"):
                continue
            header = body[:1000]
            match = re.search(r"\*\*Status:\s*([^*\n]+)\*\*", header)
            status = match.group(1).strip() if match else "UNKNOWN"
            recorded = bool(re.match(r"ACCEPTED\b", status, re.I))
            certificate_status = None
            cert_sha = tree.get(f"knowledge/03-Modules/{module}/APPROVAL.md")
            if cert_sha:
                cert = (runner.head_blob(repo, cert_sha) or "")[:1500]
                cert_match = re.search(r"\*\*Status:\s*([^*\n]+)\*\*", cert)
                certificate_status = cert_match.group(1).strip() if cert_match else "UNKNOWN"
            discrepancy = None
            if recorded and certificate_status and not re.match(r"APPROVED\b", certificate_status, re.I):
                discrepancy = "Module header says accepted, but approval certificate is not approved."
            elif recorded and certificate_status and "PENDING" in certificate_status.upper():
                discrepancy = ("Approval certificate still records an activation condition as pending; this runner does "
                               "not observe CI, so this module cannot be shown as accepted on that condition alone.")
            elif recorded and not certificate_status and "gatekeeper" not in header.lower():
                discrepancy = "No approval certificate or gatekeeper reference was found in the module header."
            section = re.search(r"(?m)^## Requirements[^\n]*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
            requirements = ([line.strip()[2:] for line in section.group(1).splitlines()
                             if line.strip().startswith("- ")][:24] if section else [])
            next_section = re.search(r"(?m)^## Exact next action[^\n]*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
            next_action = (next((line.strip() for line in next_section.group(1).splitlines() if line.strip()), None)
                           if next_section else None)
            record_valid = recorded and not (discrepancy and "not approved" in discrepancy)
            # An ACCEPTED header that is conditional on exact-SHA CI or a receipt is NOT acceptance here: this runner observes
            # neither, so it must neither show green nor count as recorded acceptance.
            conditional = record_valid and runner.module_record_state(repo, module) == "conditional"
            receipt = None
            if conditional:
                receipt_why = runner.receipt_problem(cfg, module) if cfg is not None else "not checked"
                receipt = {"verified": receipt_why is None, "detail": receipt_why}
                discrepancy = " ".join(filter(None, [discrepancy, "Accepted only conditionally (exact-SHA CI / receipt); this "
                                                    "runner does not observe the condition, so it is not shown as accepted."
                                                    + (" A preserved v1 receipt reverifies offline, so it satisfies dependent "
                                                       "prerequisites." if receipt["verified"] else "")]))
            out[module] = {"accepted": record_valid and not conditional, "recorded_accepted": record_valid and not conditional,
                           "conditional": conditional, "receipt": receipt, "header_accepted": recorded, "status": status,
                           "certificate_status": certificate_status, "discrepancy": discrepancy,
                           "requirements": requirements, "next_action": next_action,
                           "updated_at": None, "path": rel}
        except (OSError, UnicodeError, ValueError):
            continue
    return out


def catalog_for(repo):
    """A protected dashboard install follows the checkout's committed module catalog."""
    if not (Path(repo) / ".git").exists():
        return CATALOG  # projection-only fixtures; no live checkout is present
    return runner.load_catalog(repo)


LEGACY_REASON = "Legacy v1 record: read-only history, never executed by runner v2"
ACTIONABLE = ("PENDING", "RUNNING")


# Failures that mean runner integrity or the host needs the owner (not a routine, retryable product failure).
OWNER_REASONS = ("STATE_CORRUPT", "HEAD_MOVED", "SCOPE_VIOLATION", "REVIEW_WROTE_FILES", "CRASH_HEAD_MOVED",
                 "VERIFY_MUTATED_REPO", "ORPHAN_PROCESS_GROUP", "VERIFY_SANDBOX_UNAVAILABLE", "REPO_STATE_UNREADABLE",
                 "ESCAPED_PROCESS", "PROCESS_SCAN_UNAVAILABLE")
OWNER_HANDOFF = ("PLANNER_POLICY_UNPROVEN", "PLANNER_RUNTIME_UNPROVEN", "ORCHESTRATOR_SANDBOX_UNAVAILABLE",
                 "UNATTRIBUTED_CHANGES_DURING_HANDOFF")


def task_projection(tasks, legacy=()):
    """v2 tasks with an honest lifecycle, then v1 history flagged read-only. A FAILED task stays an active blocker until a
    COMPLETED task explicitly linked to it (`remediates`) exists; later same-module work is never taken as resolution.
    Legacy records are history, never runner blockers."""
    projected = []
    for t in tasks:
        evidence, route = t.get("evidence") or {}, t.get("route") or {}
        fixer = next((o.get("id") for o in tasks if o.get("remediates") == t.get("id") and o.get("status") == "COMPLETED"), None)
        status = t.get("status")
        lifecycle = ("active-blocker" if status == "FAILED" and not fixer else
                     "historical" if status == "FAILED" else str(status).lower())
        projected.append({k: t.get(k) for k in ("id", "module", "role", "title", "status", "stage", "attempts", "max_attempts",
                                                  "started_at", "finished_at", "updated_at", "last_error", "child_pid", "waiting",
                                                  "depends_on", "review_of", "retry_in")}
                         | {"lane": status, "legacy": False, "lifecycle": lifecycle, "blocked_reason": t.get("reason"),
                            "history_reason": f"Remediated by completed task {fixer}" if lifecycle == "historical" else None,
                            "kind": ("owner" if t.get("reason") in OWNER_REASONS else "routine") if lifecycle == "active-blocker" else None,
                            "model": route.get("primary") if route.get("verdict") == "VERIFIED" else None,
                            "permission_denied": bool((t.get("result") or {}).get("permission_denied")),
                            "route_verdict": route.get("verdict"), "review_outcome": evidence.get("review_outcome"),
                            "verify": evidence.get("verify"), "changed": [x.get("path") for x in evidence.get("changed", [])]})
    for t in legacy:
        evidence, route = t.get("evidence") or {}, t.get("route") or {}
        projected.append({k: t.get(k) for k in ("id", "module", "role", "title", "status", "started_at", "finished_at",
                                                  "updated_at", "last_error")}
                         | {"lane": "LEGACY", "legacy": True, "lifecycle": "historical", "history_reason": LEGACY_REASON,
                            "blocked_reason": t.get("blocked_reason"), "model": route.get("primary"),
                            "route_verdict": route.get("verdict"), "review_outcome": evidence.get("review_outcome"),
                            "verify": evidence.get("verify"),
                            "changed": [x.get("path") for x in evidence.get("changed", []) if isinstance(x, dict)]})
    return projected


def module_projection(catalog, records, tasks):
    live = [t for t in tasks if not t["legacy"]]
    running = {t["module"] for t in live if t["status"] == "RUNNING"}
    active = next((m["id"] for m in catalog if m["id"] in running), None)
    if active is None:
        known = {m["id"] for m in catalog}
        active = next((t["module"] for t in reversed(live) if t["module"] in known
                       and t["status"] in ("PENDING", "COMPLETED") and not records.get(t["module"], {}).get("accepted")), None)
    result = {}
    for m in catalog:
        mid = m["id"]
        if mid == active:
            result[mid] = "current"
        elif records.get(mid, {}).get("accepted"):
            result[mid] = "accepted"
        elif records.get(mid, {}).get("conditional"):
            result[mid] = "conditional"
        elif any(t["module"] == mid and t["lifecycle"] == "active-blocker" for t in live):
            result[mid] = "blocked"
        else:
            result[mid] = "not-started"
    return active, result


def agent_projection(state, tasks):
    current = next((t for t in tasks if t["status"] == "RUNNING" and not t["legacy"]), None)
    lock = state.get("writer_lock") or {}
    alive = bool(state.get("runner_alive"))
    working_family = None
    if current and alive and lock.get("state") == "held":
        working_family = "sonnet" if current["role"] in runner.WRITE_ROLES else "opus"
    agents = []
    for family, name, role in (("sonnet", "Claude Sonnet", "Implementation & tests"), ("opus", "Claude Opus", "Independent review")):
        latest = max((t for t in tasks if t.get("model") and family in t["model"].lower()),
                     key=lambda t: t.get("finished_at") or "", default=None)
        busy = working_family == family
        agents.append({"name": name, "role": role, "status": "working" if busy else "idle" if alive else "unavailable",
                       "task": current["title"] if busy else None, "since": current["started_at"] if busy else None,
                       "last_activity": current["started_at"] if busy else latest.get("finished_at") if latest else None,
                       "identity": f"Invoked --model {family}; actual model recorded after the run" if busy
                                   else latest["model"] if latest else "No verified invocation recorded"})
    return agents


def runner_execution(state, tasks):
    live = [t for t in tasks if not t["legacy"]]
    if state.get("control") == "STOP":
        return "stopped"
    if state.get("control") == "PAUSE":
        return "paused"
    if state.get("state_error"):
        return "unavailable"
    if not state.get("runner_alive"):
        return "stale" if any(t["status"] == "RUNNING" for t in live) else "unavailable"
    if any(t["status"] == "RUNNING" for t in live):
        return "running"
    if any(t["status"] == "PENDING" for t in live):
        return "waiting"
    h = state.get("handoff") or {}
    if h.get("request_open"):
        return "planning"
    if h.get("status") == "waiting_for_owner":
        return "waiting_for_owner"
    return "blocked" if any(t["lifecycle"] == "active-blocker" for t in live) or h.get("status") == "blocked" else "idle"


def build_state(snapshot, repo, cfg=None):
    catalog = catalog_for(repo)
    records = module_records(repo, cfg)
    tasks = task_projection(snapshot.get("tasks") or [], snapshot.get("legacy_tasks") or [])
    live = [t for t in tasks if not t["legacy"]]
    active, modules = module_projection(catalog, records, tasks)
    events = [e for e in snapshot.get("events", []) if e.get("kind") in MEANINGFUL_EVENTS]
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    blockers = [t for t in live if t["lifecycle"] == "active-blocker"]
    if snapshot.get("state_error"):
        blockers.append({"id": "runner-state", "module": active, "role": "runner", "title": "Runner state unreadable",
                         "status": "FAILED", "lifecycle": "active-blocker", "blocked_reason": "STATE_CORRUPT", "kind": "owner",
                         "last_error": snapshot["state_error"], "legacy": False})
    owner_actions = [t for t in blockers if t.get("kind") == "owner"]
    h = snapshot.get("handoff") or {}
    detail = str(h.get("detail") or "")
    if h.get("status") == "waiting_for_owner" or (h.get("status") == "blocked" and any(k in detail for k in OWNER_HANDOFF)):
        owner_actions.append({"id": "handoff", "module": active, "role": "planner", "kind": "owner", "legacy": False,
                              "title": "OpenClaw planner needs the owner" if h.get("status") == "waiting_for_owner"
                                       else "OpenClaw planner is blocked", "last_error": detail,
                              "blocked_reason": str(h.get("status")).upper()})
    # genuinely unresolved v1 product blockers stay visible as read-only context (never as runner blockers)
    legacy_open = [{k: t.get(k) for k in ("id", "module", "title", "status", "blocked_reason", "last_error")}
                   for t in tasks if t["legacy"] and t.get("status") in ("BLOCKED", "FAILED")
                   and not records.get(t.get("module"), {}).get("accepted")]
    latest_ok = max((t for t in live if t["status"] == "COMPLETED" and t.get("route_verdict") == "VERIFIED"),
                    key=lambda t: t.get("finished_at") or "", default=None)
    return {"generated_at": snapshot.get("generated_at"), "runner_alive": snapshot.get("runner_alive"),
            "heartbeat_age_s": snapshot.get("heartbeat_age_s"), "runner": snapshot.get("runner"),
            "control": snapshot.get("control"), "state_error": snapshot.get("state_error"),
            "legacy_error": snapshot.get("legacy_error"), "writer_lock": snapshot.get("writer_lock"),
            "current_module": active, "modules": modules, "runner_execution": runner_execution(snapshot, tasks),
            "last_successful_worker": ({"title": latest_ok["title"], "module": latest_ok["module"], "model": latest_ok["model"],
                                        "at": latest_ok["finished_at"]} if latest_ok else None),
            "module_catalog": catalog, "module_records": records, "tasks": tasks,
            "actionable_tasks": [t for t in live if t["status"] in ACTIONABLE or t["lifecycle"] == "active-blocker"],
            "active_blockers": blockers, "owner_action_blockers": owner_actions, "legacy_unresolved": legacy_open,
            "legacy_count": len(tasks) - len(live), "historical_blocked_count": sum(t["lifecycle"] == "historical" for t in tasks),
            "agents": agent_projection(snapshot, tasks), "events": events[:80], "recent_events": events[:5],
            "usage": snapshot.get("usage") or {}, "ci": None, "handoff": snapshot.get("handoff"),
            "accepted_count": sum(v.get("accepted", False) for v in records.values()),
            "conditional_count": sum(v.get("conditional", False) for v in records.values()),
            "recorded_accepted_count": sum(v.get("recorded_accepted", False) for v in records.values()),
            "total_modules": len(catalog)}


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
                state = build_state(runner.snapshot(cfg), cfg.repo, cfg)
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
