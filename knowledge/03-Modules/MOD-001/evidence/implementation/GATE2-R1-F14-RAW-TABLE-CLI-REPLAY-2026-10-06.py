"""Replay R1-F14's synthetic CLI text/JSON corpus from its durable capture."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CAPTURE = Path(__file__).with_name("GATE2-R1-F14-RAW-TABLE-CLI-CAPTURE-2026-10-06.json")
CLI = ROOT / "tools/validate_architecture_gates.py"


def main():
    record = json.loads(CAPTURE.read_text())
    for label, case in record["cases"].items():
        with tempfile.TemporaryDirectory(prefix="veyro-f14-replay-") as tmp:
            base = Path(tmp)
            for relpath, content in record["fixtureFiles"].items():
                target = base / relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((case["sql"] + "\n") if relpath.endswith("/repo.sql") else content)
            manifest = base / "manifest.json"
            manifest.write_text(json.dumps(record["fixtureManifest"]))
            for mode in ("text", "json"):
                cmd = [sys.executable, str(CLI), "--gate", "module-deps",
                       "--modules-dir", str(base / "app/modules"),
                       "--module-manifest", str(manifest)]
                if mode == "json":
                    cmd.append("--json")
                run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
                expected = case[mode]
                assert (run.returncode, run.stdout, run.stderr) == (
                    expected["exitCode"], expected["stdout"], expected["stderr"]), (label, mode)
            print(f"{label}: text/JSON exact replay PASS")
    print(f"{len(record['cases'])} cases / {2 * len(record['cases'])} CLI invocations exact replay PASS")


if __name__ == "__main__":
    main()
