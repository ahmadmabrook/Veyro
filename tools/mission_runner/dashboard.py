"""Read-only, loopback-only engineering command center for the Veyro Mission Runner."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import runner

UI_DIR = Path(__file__).resolve().parent
CSS = (UI_DIR / "dashboard.css").read_text()
JS = (UI_DIR / "dashboard.js").read_text()
HTML = (UI_DIR / "dashboard.html").read_text()
CATALOG = json.loads((UI_DIR / "module_catalog.json").read_text())


def module_records(repo):
    """Bounded, read-only module-file projection; absence is not a status claim."""
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
            requirements = []
            section = re.search(r"(?m)^## Requirements[^\n]*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
            if section:
                requirements = [line.strip()[2:] for line in section.group(1).splitlines()
                                if line.strip().startswith("- ")][:24]
            next_section = re.search(r"(?m)^## Exact next action[^\n]*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
            next_action = next((x.strip() for x in next_section.group(1).splitlines() if x.strip()), None) if next_section else None
            out[module] = {"accepted": bool(re.search(r"\*\*Status: ACCEPTED\b", body[:1000])),
                           "requirements": requirements, "next_action": next_action,
                           "updated_at": path.stat().st_mtime, "path": str(path.relative_to(repo))}
        except (OSError, UnicodeError, ValueError):
            continue
    return out

CI_WORKFLOW = "Veyro Foundation CI"


def ci_confirms_head(ci):
    """Fail-closed: True only for a fresh main-push snapshot whose exact local head has a completed successful
    named push run and no pending or failed push run. A display gate only, not module certification."""
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
        return False  # pending, failed, cancelled or unknown on the exact head blocks
    return any(r.get("name") == CI_WORKFLOW and r.get("ref") == "main" for r in exact)


def worktree_clean(repo):
    """Fail-closed: True only when a bounded, non-shell `git status` succeeds and reports nothing, untracked included.
    Any error, timeout or output means False, so uncommitted module content never earns a status claim."""
    try:
        p = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
                           capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL,
                           env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return p.returncode == 0 and p.stdout == ""


def gate_module_records(records, ci, clean=False):
    """API projection: a header-ACCEPTED record is reported accepted only while the worktree is clean (`clean`,
    from worktree_clean) and the CI snapshot confirms the head."""
    confirmed = clean is True and ci_confirms_head(ci)
    return {m: dict(rec, accepted=rec["accepted"] and confirmed, header_accepted=rec["accepted"])
            for m, rec in records.items()}


ASSETS = {"/": ("text/html; charset=utf-8", HTML), "/app.css": ("text/css; charset=utf-8", CSS),
          "/app.js": ("text/javascript; charset=utf-8", JS)}


def make_handler(cfg, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        server_version = "VeyroDash"

        def log_message(self, *a):
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
            self.wfile.write(b)

        def do_GET(self):
            if self.headers.get("Host") not in allowed_hosts:  # DNS-rebinding guard
                return self._send(403, "text/plain", "forbidden host")
            path = self.path.split("?")[0]
            if path == "/api/state":
                state = runner.snapshot(cfg)
                state["module_catalog"] = CATALOG
                state["module_records"] = gate_module_records(module_records(cfg.repo), state.get("ci"),
                                                                worktree_clean(cfg.repo))
                return self._send(200, "application/json", json.dumps(state))
            if path in ASSETS:
                return self._send(200, *ASSETS[path])
            self._send(404, "text/plain", "not found")

        def _no_write(self):
            self._send(405, "text/plain", "dashboard is read-only", [("Allow", "GET")])

        do_POST = do_PUT = do_DELETE = do_PATCH = _no_write

    return H


def make_server(cfg, port=8766):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg, 0))  # bound first so port 0 resolves
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
