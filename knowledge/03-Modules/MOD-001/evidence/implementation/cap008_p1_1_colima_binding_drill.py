"""Reproducible real drills for the CAP-008 P1-1 Colima-binding remediation of
backend/tests/harness/postgres.py. Synthetic-only, loopback-only, no Docker
Desktop activation, no spend.

Run from the repository root:
    backend/.venv/bin/python knowledge/03-Modules/MOD-001/evidence/implementation/cap008_p1_1_colima_binding_drill.py

Drills (each prints one PASS/FAIL line; exit status is non-zero if any fails):
  POS      default route reaches Colima: pinned image, loopback publish,
           real SQL roundtrip, server log via the same route, no leftovers.
  POS-AMB  same, with ambient Desktop selectors present: Docker.app's CLI first
           on PATH, DOCKER_CONTEXT=desktop-linux, DOCKER_CONFIG pointing at the
           real ~/.docker (credsStore=desktop). Must still land on Colima.
  NEG-UNR  caller DOCKER_HOST to a nonexistent socket: fails at `docker info`.
  NEG-DSK  caller DOCKER_HOST to Docker Desktop's own (stopped) socket: fails
           closed; never starts Desktop.
  NEG-WRG  caller DOCKER_HOST to a local synthetic Docker-API endpoint that
           answers with Docker Desktop's identity, driven by the REAL trusted
           CLI: rejected as the wrong engine before any container is created.
"""

from __future__ import annotations

import json
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "backend"))

import psycopg
from tests.harness import postgres
from tests.harness.postgres import disposable_postgres

RESULTS: list[bool] = []


def report(name: str, ok: bool, detail: str) -> None:
    RESULTS.append(ok)
    print(f"{name}: {'PASS' if ok else 'FAIL'} -- {detail}", flush=True)


def leftovers() -> str:
    with postgres.trusted_docker() as docker:
        return docker("ps", "-a", "--filter", "name=veyro-mod001-harness", "--format", "{{.Names}}")


def positive(name: str) -> None:
    try:
        with disposable_postgres() as pg:
            with psycopg.connect(pg.superuser_dsn) as conn:
                two = conn.execute("select 1+1").fetchone()
                version = conn.execute("show server_version").fetchone()
            image = pg.docker("inspect", "--format", "{{.Image}}", pg.container)
            digests = pg.docker("image", "inspect", "--format", "{{json .RepoDigests}}", image)
            log_ok = "database system is ready to accept connections" in pg.server_log()
            route = (pg.docker.cli, pg.docker.host)
        ok = (
            two == (2,)
            and pg.host == "127.0.0.1"
            and postgres.IMAGE.split("@")[1] in digests
            and log_ok
            and route == (str(postgres.TRUSTED_DOCKER_CLI_REALPATH), postgres.COLIMA_DOCKER_HOST)
        )
        left = leftovers()
        report(
            name,
            ok and left == "",
            f"route={route} publish={pg.host}:{pg.port} server_version={version} "
            f"select1+1={two} pinned_digest_present={postgres.IMAGE.split('@')[1] in digests} "
            f"server_log_ready={log_ok} leftovers={left!r}",
        )
    except Exception as exc:  # noqa: BLE001 - drill records any failure
        report(name, False, f"{type(exc).__name__}: {exc}")


def expect_refusal(name: str, docker_host: str, must_contain: str) -> None:
    os.environ["DOCKER_HOST"] = docker_host
    try:
        with disposable_postgres():
            report(name, False, "harness started a container; it should have refused")
    except RuntimeError as exc:
        msg = str(exc)
        report(name, must_contain in msg and "never substitutes a mock" in msg, msg)
    finally:
        del os.environ["DOCKER_HOST"]


class _UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def fake_desktop_api(sock: str, seen: list[str]) -> _UnixHTTPServer:
    identity = {
        "ID": "synthetic-desktop-impostor",
        "Name": "docker-desktop",
        "ServerVersion": "29.4.0",
        "OperatingSystem": "Docker Desktop",
        "OSType": "linux",
    }

    class Handler(BaseHTTPRequestHandler):
        def address_string(self) -> str:
            return "unix"

        def log_message(self, *args: object) -> None:
            pass

        def _send(self, body: bytes, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Api-Version", "1.47")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_HEAD(self) -> None:
            seen.append(f"HEAD {self.path}")
            self._send(b"OK")

        def do_GET(self) -> None:
            seen.append(f"GET {self.path}")
            if self.path.endswith("/_ping"):
                self._send(b"OK")
            elif self.path.endswith("/info"):
                self._send(json.dumps(identity).encode())
            else:
                self._send(b'{"message":"synthetic endpoint"}', 404)

        def do_POST(self) -> None:
            seen.append(f"POST {self.path}")
            self._send(b'{"message":"synthetic endpoint refuses writes"}', 500)

    server = _UnixHTTPServer(sock, Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    for key in [k for k in os.environ if k.startswith("DOCKER_")]:
        del os.environ[key]
    desktop_running = subprocess.run(["pgrep", "-f", "Docker.app"], capture_output=True, check=False).stdout
    print(f"precondition: Docker Desktop processes={desktop_running.decode().split()!r}")

    positive("POS")

    saved_path = os.environ["PATH"]
    os.environ["PATH"] = f"/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:{saved_path}"
    os.environ["DOCKER_CONTEXT"] = "desktop-linux"
    os.environ["DOCKER_CONFIG"] = str(Path.home() / ".docker")
    positive("POS-AMB")
    os.environ["PATH"] = saved_path
    del os.environ["DOCKER_CONTEXT"], os.environ["DOCKER_CONFIG"]

    with tempfile.TemporaryDirectory(prefix="veyro-cap008-") as tmp:
        expect_refusal("NEG-UNR", f"unix://{tmp}/no-daemon.sock", "`docker info` exit")

        desktop_sock = Path.home() / ".docker/run/docker.sock"
        expect_refusal("NEG-DSK", f"unix://{desktop_sock}", "`docker info` exit")

        sock, seen = f"{tmp}/impostor.sock", []
        server = fake_desktop_api(sock, seen)
        try:
            expect_refusal("NEG-WRG", f"unix://{sock}", "not the approved Colima binding")
        finally:
            server.shutdown()
            server.server_close()
        created = [s for s in seen if s.startswith("POST")]
        report("NEG-WRG-NO-CREATE", seen != [] and created == [], f"requests seen={seen}")

    left = leftovers()
    report("LEFTOVERS", left == "", f"veyro-mod001-harness containers after all drills={left!r}")
    desktop_after = subprocess.run(["pgrep", "-f", "Docker.app"], capture_output=True, check=False).stdout
    report("NO-DESKTOP", desktop_after == b"", f"Docker Desktop processes after={desktop_after!r}")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
