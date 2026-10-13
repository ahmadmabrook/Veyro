"""R04 gate mutation kill-check (ADR-010 N26 / D5.3).

Every mutant is applied to a COPY of `tools/validate_architecture_gates.py`
inside a temporary mirror of the files the suites need. The real tool is
opened read-only, never written; its SHA-256 is asserted unchanged at the end
of every run, in `finally`, at interpreter exit, and on SIGINT/SIGTERM, so an
interrupted run still proves (or visibly fails to prove) the real file is intact.

Each mutant must be killed by the gate unit suite (mirror copy) and/or the
Colima RLS integration suite (mirror copy, run with the real backend venv).
A survivor or an anchor that no longer matches exactly once fails the run.
"""

from __future__ import annotations

import atexit
import hashlib
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
REAL_TOOL = ROOT / "tools" / "validate_architecture_gates.py"
PY = str(ROOT / "backend" / ".venv" / "bin" / "python")
REAL_SHA = hashlib.sha256(REAL_TOOL.read_bytes()).hexdigest()


def _assert_real_tool_unchanged() -> None:
    now = hashlib.sha256(REAL_TOOL.read_bytes()).hexdigest()
    if now != REAL_SHA:
        print(f"REAL TOOL CHANGED: {REAL_SHA} -> {now}", flush=True)
        sys.exit(3)


atexit.register(_assert_real_tool_unchanged)
for _sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(_sig, lambda *_: (_assert_real_tool_unchanged(), sys.exit(130)))


def _build_mirror() -> Path:
    """Copy what the suites import or read: the tool and its tests, backend tests and
    pyproject, the fixed RLS manifest, and the ADR/OWN records the resolver reads."""
    mirror = Path(tempfile.mkdtemp(prefix="veyro-killcheck-"))
    for rel in ("tools/validate_architecture_gates.py",
                "tools/tests/test_validate_architecture_gates.py",
                "backend/pyproject.toml", "backend/migrations/rls-manifest.json",
                "knowledge/00-System/OWNER_APPROVALS.md"):
        (mirror / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, mirror / rel)
    shutil.copytree(ROOT / "backend" / "tests", mirror / "backend" / "tests",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "knowledge" / "04-Decisions", mirror / "knowledge" / "04-Decisions")
    return mirror


# name -> (exact anchor in the tool, replacement). Anchors must match exactly once.
M: dict[str, tuple[str, str]] = {
    # --- RLS: tenant-table rules (TSD §24.1, ADR-010 D4.1)
    "R01 ENABLE check removed": ("            if not rel.rls_enabled:", "            if False:"),
    "R02 FORCE check removed": ("            if not rel.rls_forced:", "            if False:"),
    "R03 nullable tenant_id ignored": ("            if not rel.tenant_id_not_null:", "            if False:"),
    "R04 non-uuid tenant_id ignored (D4.1)": ("            if not rel.tenant_id_uuid:", "            if False:"),
    "R05 no-policy accepted": ('        return ["no RLS policy defined"]', "        return []"),
    "R06 unclassified tables skipped": (
        '                if manifest.platform_scope_relations.get(q) != "table":',
        "                if False:"),
    "R07 vacuous scan passes": ('    vacuous = None if checked else "no tenant table',
                                '    vacuous = None if True else "no tenant table'),
    # --- D4.3 predicate: deparse match and dependency closure
    "R08 USING deparse not judged": ('p.command in ("*", "r", "w", "d") and p.using != predicate:',
                                     'p.command in ("*", "r", "w", "d") and False:'),
    "R09 WITH CHECK deparse not judged": ('p.command in ("*", "a", "w") and check != predicate:',
                                          'p.command in ("*", "a", "w") and False:'),
    "R10 dependency closure ignored": ("        if p.foreign_dependencies:", "        if False:"),
    "R11 unpinned major accepted": (
        "    predicate = PINNED_TENANT_PREDICATES.get(catalog.server_version_num // 10000)",
        "    predicate = CANONICAL_TENANT_PREDICATE"),
    # --- D1 envelope
    "R12 D1.1 REPLICATION ignored": ('("REPLICATION", role.replication)', '("REPLICATION", False)'),
    "R13 D1.1 BYPASSRLS ignored": ('("BYPASSRLS", role.bypassrls)', '("BYPASSRLS", False)'),
    "R14 D1.1 CREATEROLE/CREATEDB ignored": (
        '("CREATEROLE", role.createrole),', '("CREATEROLE", False),'),
    "R15 D1.2 predefined roles ignored": (
        '        if role.oid < FIRST_NORMAL_OBJECT_ID or role.name.startswith("pg_"):',
        "        if False:"),
    "R16 D1.3 ownership ignored": ("    for cls, identity in catalog.owned:  # D1.3",
                                   "    for cls, identity in ():  # D1.3"),
    "R17 D1.3 pg_shdepend owner rows dropped": ("   WHERE s.deptype = 'o' AND",
                                                "   WHERE s.deptype = 'x' AND"),
    "R18 D1.4 allow-table ignored": (
        '        if gr.privilege not in allowed or (gr.grantee == "PUBLIC" and gr.obj_class in _NO_PUBLIC):',
        "        if False:"),
    "R19 D1.4 PUBLIC on tables allowed": ('_NO_PUBLIC = frozenset({"table", "view", "sequence"})',
                                          "_NO_PUBLIC: frozenset[str] = frozenset()"),
    "R20 D1.4 table allow-row widened (R1 TRUNCATE/TRIGGER/REFERENCES)": (
        '    "table": _DML,', '    "table": _DML | {"TRUNCATE", "TRIGGER", "REFERENCES"},'),
    "R21 D1.4 closure membership dropped (SET ROLE paths)": (
        "   WHERE {exists} AND pg_catalog.pg_has_role(%(rt)s::pg_catalog.oid, r.oid, 'MEMBER')",
        "   WHERE {exists} AND r.oid = %(rt)s::pg_catalog.oid"),
    "R22 D1.5 system ACL changes ignored": (
        "            if not gr.in_initial and not _information_schema_pinned(gr, info_pin):",
        "            if False:"),
    # --- ADR-010 Amendment A1 (system-object definition, D1.5a exact pin) incl. N32
    "A01 N32 class-level pin (any table/view name)": (
        '            and pin.get(gr.relation.split(".", 1)[1]) == gr.obj_class)',
        '            and gr.obj_class in ("table", "view"))'),
    "A02 N32 oid check dropped from system definition": (
        "        system = bool((sys_ns and stock) or has_init)  # ADR-010 A1.2",
        "        system = bool(sys_ns or has_init)  # ADR-010 A1.2"),
    "A03 N32 pin applied to any major": (
        "    info_pin = PINNED_INFORMATION_SCHEMA_SELECT.get(catalog.server_version_num // 10000)",
        "    info_pin = PINNED_INFORMATION_SCHEMA_SELECT.get(16)"),
    "A04 N32 pinned relname dropped": ('"tables": "view", ', ""),
    "A05 N32 relname added (_pg_user_mappings)": (
        "PINNED_INFORMATION_SCHEMA_SELECT: dict[int, dict[str, str]] = {16: {\n    ",
        "PINNED_INFORMATION_SCHEMA_SELECT: dict[int, dict[str, str]] = {16: {\n    "
        '"_pg_user_mappings": "view", '),
    "A06 non-stock system objects ignored": ("        if gr.non_stock:  # A1.2", "        if False:  # A1.2"),
    "A07 temp namespaces treated as system": (
        "\"AND {ns} !~ '^pg_(toast_)?temp_[0-9]+$')\")", "\"AND true)\")"),
    "A08 SECURITY DEFINER query keeps bare namespace test": (
        ' AND o.oid < {FIRST_NORMAL_OBJECT_ID})\n            OR EXISTS',
        ')\n            OR EXISTS'),
    "A09 pin ignores pg_init_privs presence": ("or gr.has_init_privs or gr.grantee", "or gr.grantee"),
    "A10 pin ignores grantee": ('gr.grantee != "PUBLIC"\n', 'False\n'),
    "A11 pin admits column ACLs": (" and gr.identity == gr.relation\n", "\n"),
    "A13 A1.7 non-stock grant also emits SYSTEM_ACL_MODIFIED (exclusivity)": (
        '                                  f"{gr.privilege}@{gr.grantee}")\n            continue\n'
        "        if gr.system:",
        '                                  f"{gr.privilege}@{gr.grantee}")\n'
        '            elevated(gr.identity, f"SYSTEM_ACL_MODIFIED:{gr.identity}:'
        '{gr.privilege}@{gr.grantee}")\n            continue\n        if gr.system:'),
    "A12 pin admits any schema privilege": (
        '        return gr.identity == "information_schema" and gr.privilege == "USAGE"',
        '        return gr.identity == "information_schema"'),
    "R23 D1.6 out-of-scope grants ignored": ('        if name.split(".", 1)[0] not in scanned:',
                                             "        if False:"),
    "R24 D1.7 tenant-context defaults ignored": (
        "    for source in catalog.tenant_context_defaults:  # D1.7",
        "    for source in ():  # D1.7"),
    "R25 D1.4 lo_compat_privileges ignored": ("    if catalog.lo_compat_privileges:", "    if False:"),
    # --- D2 inspector discipline
    "R26 D2.1 search_path pin removed": (
        '        conn.execute(f"SET search_path = {PINNED_SEARCH_PATH}")',
        '        conn.execute("SELECT 1")'),
    "R27 D2.1 read-back not verified": (
        "            if not got or got[0][0] != PINNED_SEARCH_PATH:", "            if False:"),
    # --- D3 manifest and approval resolver
    "R28 D3.4 ADR status not checked": (
        '        if not status or not status.group(1).startswith(("DECIDED", "ACCEPTED")):',
        "        if False:"),
    "R29 D3.4 ADR key containment not checked": ("        if key not in text:", "        if False:"),
    "R30 D3.4 OWN key containment not checked": ("    if key not in rows[0]:", "    if False:"),
    "R31 D3.2 symlinked manifest accepted": ("    if path.is_symlink() or not path.is_file():",
                                             "    if not path.exists():"),
    "R32 D3.3 manifest v1 accepted": (
        'raw["version"] != 2):\n        raise GateInputError(\n            "RLS manifest',
        'raw["version"] not in (1, 2)):\n        raise GateInputError(\n            "RLS manifest'),
    "R33 D3.5 manifest kind mismatch ignored": (
        '        elif {"table": ("r", "p"), "matview": ("m",)}[kind].count(rel.kind) == 0:',
        "        elif False:"),
    # --- D4.4 relation kinds
    "R34 D4.4 view without security_invoker allowed": (
        '            if rel.kind == "v" and not rel.security_invoker:',
        '            if rel.kind == "v" and False:'),
    "R35 D4.4 unlisted matview allowed": (
        'or manifest.platform_scope_relations.get(q) != "matview"):', "or False):"),
    "R36 D4.4 foreign table allowed": ('            elif rel.kind == "f":', "            elif False:"),
    "R37 security definer review ignored": (
        "        if key not in manifest.reviewed_security_definer_functions:", "        if False:"),
    # --- permission gate: ADR-009 (retained) and ADR-010 D5
    "P01 registry name check skipped": ("    if name not in registry:", "    if False:"),
    "P02 missing declaration accepted": ('        return f"no {DECLARATION_KEY} declaration"',
                                         "        return None"),
    "P03 unknown path-item keys ignored (R1 P1-B)": (
        "        if unknown:\n            raise GateInputError(",
        "        if False:\n            raise GateInputError("),
    "P04 OpenAPI 3.0/3.2 accepted (ADR-009 D1.2)": (
        '_OPENAPI_VERSION_RE = re.compile(r"3\\.1\\.[0-9]+")',
        '_OPENAPI_VERSION_RE = re.compile(r"3\\..*")'),
    "P05 two-key class match skipped (ADR-009 D4.2)": (
        "    if permission and registry[permission].authentication != auth:", "    if False:"),
    "P06 authenticated allows {} (ADR-009 D4.3)": ("        if any(not r for r in reqs):",
                                                    "        if False:"),
    "P07 authenticated without security (ADR-009 D4.3)": (
        '        if not reqs:\n            return "authenticated operation has no',
        '        if False:\n            return "authenticated operation has no'),
    "P08 anonymous may inherit (ADR-009 D4.3)": (
        '        if not (explicit and op["security"] == []):', "        if False:"),
    "P09 non-session may inherit root (D5.2)": ("    elif not explicit:  # ADR-010",
                                                "    elif False:  # ADR-010"),
    "P10 justification not required (ADR-009 D2)": (
        "            if not (isinstance(just, str) and just.strip()):", "            if False:"),
    "P11 missing authentication class accepted (ADR-009 D4.1)": (
        '        problems.append(f"no {AUTH_KEY} declaration")\n        return problems, None, permission',
        "        return problems, None, permission"),
    "P12 webhooks not refused": ('    if "webhooks" in doc:', "    if False:"),
    "P13 operation callbacks not refused": ('            if "callbacks" in op:', "            if False:"),
    "P14 components.pathItems/callbacks not refused": (
        '    for key in ("pathItems", "callbacks"):', "    for key in ():"),
    "P15 cross-document duplicates not refused": ("        _cross_document_duplicates(ops)\n", ""),
    "P16 path params not normalised": ('_PATH_PARAM_RE.sub("{}", path)', "path"),
    "P17 symlinked contract files accepted": ("        if entry.is_symlink():", "        if False:"),
    "P18 inventory hidden (ADR-009 D4.4)": (
        '    report.inventory = sorted(inventory, key=lambda r: r["endpoint"])',
        "    report.inventory = []"),
    "P19 duplicate JSON keys last-wins": ("    if dupes:\n        raise ValueError",
                                          "    if False:\n        raise ValueError"),
    "P20 match instead of fullmatch": (
        "    if not (isinstance(action, str) and _ACTION_RE.fullmatch(action)):",
        "    if not (isinstance(action, str) and _ACTION_RE.match(action)):"),
    "P21 D5.1 approval not resolved": ("            resolve_approval(approval, name, resolver_root)",
                                       "            pass"),
    "P22 D5.1 registry v1 accepted": (
        'raw["version"] != 2):\n        raise GateInputError(\'registry',
        'raw["version"] not in (1, 2)):\n        raise GateInputError(\'registry'),
    "P23 D5.2 security schemes not validated": (
        '    schemes = _validate_security_schemes(components.get("securitySchemes", {}), source)',
        '    schemes = set(components.get("securitySchemes", {}) or {})'),
    "P24 D5.2 explicit null security treated as absent": (
        "            if explicit or effective is not None else None)",
        "            if effective is not None else None)"),
    "P25 D5.2 root null security accepted": ('    if "security" in doc:  # null or',
                                             "    if root_security is not None:  # null or"),
    "P26 D5.2 apiKey location not checked": (
        '        if kind == "apiKey" and scheme["in"] not in', '        if False and scheme["in"] not in'),
    "P27 D5.2 $ref scheme accepted": ('        if not isinstance(scheme, dict) or "$ref" in scheme:',
                                      "        if not isinstance(scheme, dict):"),
    "P28 D5.2 undefined scheme accepted": (
        "    if undefined:\n        raise GateInputError(f\"{where}: security names undefined",
        "    if False:\n        raise GateInputError(f\"{where}: security names undefined"),
    "P29 deferred gate reports PASS": ("        report = GateReport(args.gate, ERROR, [Violation(\n",
                                       "        report = GateReport(args.gate, PASS, [Violation(\n"),
}


def main() -> int:
    original = REAL_TOOL.read_text()
    bad_anchors = [name for name, (old, _) in M.items() if original.count(old) != 1]
    if bad_anchors:
        print(f"INVALID: anchors not matching exactly once: {bad_anchors}")
        return 2
    mirror = _build_mirror()
    copy = mirror / "tools" / "validate_architecture_gates.py"
    results = []
    try:
        for name, (old, new) in M.items():
            copy.write_text(original.replace(old, new))
            unit = subprocess.run([PY, "tools/tests/test_validate_architecture_gates.py"],
                                  cwd=mirror, capture_output=True, text=True, check=False)
            killed = ["unit"] if unit.returncode != 0 else []
            if not killed:  # only pay for the Colima run when the unit suite survives
                integ = subprocess.run(
                    [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                     "tests/integration/test_architecture_gate_rls.py"],
                    cwd=mirror / "backend", capture_output=True, text=True, check=False)
                if integ.returncode != 0:
                    killed.append("integration")
            results.append((name, killed))
            print(f"{name}: {'KILLED by ' + '+'.join(killed) if killed else 'SURVIVED'}",
                  flush=True)
    finally:
        shutil.rmtree(mirror, ignore_errors=True)
        _assert_real_tool_unchanged()
    survivors = [n for n, k in results if not k]
    print(f"real tool sha256 unchanged: {REAL_SHA}")
    print(f"{len(results) - len(survivors)}/{len(results)} mutations killed; survivors={survivors}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
