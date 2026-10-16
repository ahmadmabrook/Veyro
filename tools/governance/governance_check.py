#!/usr/bin/env python3
"""Veyro MOD-002 governance validator (Python stdlib only, no network, never writes).

  governance_check.py check --root R
  governance_check.py check-change --root R --decision ID   (changed paths, one per line, on stdin)

Exit 0 = PASS, 1 = BLOCKED (stdout JSON lists violations), 2 = malformed input/usage (fail closed).

Registry: <root>/governance/registry.json (schema "veyro.governance.registry/1"):
  module            MOD id that owns every requirement (must be in the module catalog)
  module_catalog    repo-relative path of the catalog JSON (list of {"id": "MOD-nnn", ...})
  index             {"sha256": <PROJECT_INDEX.md sha256>, "authority_rows": [exact row names]}
  baseline          {"owner_decision": "knowledge/00-Decisions/OWNER-*.md"}
  reserved_actions  DC-16 reserved action names; an ACCEPTED ADR using one needs an owner approval
  classification    exactly the GOV-02 fields in EXPECTED_CLASSIFICATION (concept only, no engine/AI claims)
  requirements      the eight GOV-02-R01..R08 records:
                    {id, owner, status FOUNDATION|DEFERRED, evidence [paths], product_pass false (optional),
                     deferred_to + reason (DEFERRED only)}
ADRs: knowledge/00-Decisions/ADR-nnnn[-slug].md with "- Header: value" lines before the first "## ":
  required ID, Status (PROPOSED|ACCEPTED|SUPERSEDED|REJECTED), Decision-Key, Covers (comma-separated path
  prefixes; a trailing "/" means a directory); optional Review ("<review-id> APPROVED", required when ACCEPTED),
  Reserved-Action, Owner-Approval (path to an existing knowledge/00-Decisions/OWNER-*.md), Supersedes,
  Superseded-By.
check-change --decision is an ADR id (controlled paths) or an OWNER-* decision stem (frozen paths).
Frozen = registry rows UNION rows parsed from the actual PROJECT_INDEX.md, plus any OWNER-* record. A frozen path
needs a later OWNER record (never baseline.owner_decision, never itself part of the change) whose
"- Covers:" header lists the path; "- Actions:" lists reserved actions (DC-16) and "defer-<REQ id>" approvals.
A change mixing frozen and controlled paths is BLOCKED (one decision cannot be both): split it, no path goes unchecked.
Any ADR integrity violation anywhere blocks a controlled change. The ADR "Review" field is format-checked only;
the existence of the named review is NOT verified here.
A DEFERRED requirement needs deferred_to != module, product_pass false and owner_approval (OWNER record Actions
containing defer-<REQ id>); deferral never implies product PASS.
Authority row hashes of the sources are NOT re-verified here; that stays with the runner's out-of-repo pin.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path

SCHEMA = "veyro.governance.registry/1"
REGISTRY_PATH = "governance/registry.json"
INDEX_PATH = "PROJECT_INDEX.md"
ADR_DIR = "knowledge/00-Decisions"
CONTROLLED = (".github/workflows/", "governance/", "knowledge/00-Decisions/", "tools/governance/",
              "tools/mission_runner/workflow_check.py", "tools/mission_runner/runner.py",
              "tools/mission_runner/module_catalog.json")
REQ_IDS = tuple(f"GOV-02-R0{i}" for i in range(1, 9))
REQ_STATUSES = ("FOUNDATION", "DEFERRED")
REQ_KEYS = {"id", "owner", "status", "evidence", "deferred_to", "reason", "product_pass", "owner_approval"}
TOP_KEYS = {"schema", "module", "module_catalog", "index", "baseline", "reserved_actions", "classification",
            "requirements"}
EXPECTED_CLASSIFICATION = {"anchor": "GOV-02", "tier": 2, "classification": "confidential",
                           "tenant_scoped": True, "invariant": "INV-GOV-02", "runbook": "RB-GOV-02",
                           "ai_system": "none"}
STORAGE_RE = re.compile(r"^[a-z][a-z-]{2,48}$")
STORAGE_ENGINE_WORDS = ("sql", "postgres", "mysql", "sqlite", "redis", "mongo", "dynamo", "s3", "bucket",
                        "database", "kafka", "elastic")
ADR_STATUSES = ("PROPOSED", "ACCEPTED", "SUPERSEDED", "REJECTED")
ADR_REQUIRED = ("ID", "Status", "Decision-Key", "Covers")
ADR_OPTIONAL = ("Review", "Reserved-Action", "Owner-Approval", "Supersedes", "Superseded-By")
ADR_FILE_RE = re.compile(r"^(ADR-\d{4})(-[a-z0-9-]+)?\.md$")
ADR_ID_RE = re.compile(r"^ADR-\d{4}$")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,63}$")
REVIEW_RE = re.compile(r"^[A-Za-z0-9._-]{3,64} APPROVED$")
HEADER_RE = re.compile(r"^- ([A-Za-z][A-Za-z-]*):[ \t]*(.*?)[ \t]*$")
OWNER_DECISION_RE = re.compile(r"^knowledge/00-Decisions/OWNER-[A-Za-z0-9._-]+\.md$")
OWNER_STEM_RE = re.compile(r"^OWNER-[A-Za-z0-9._-]+$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class Malformed(Exception):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class Report:
    def __init__(self):
        self.violations = []

    def add(self, code, detail="", adr=None):
        v = {"code": code, "detail": detail}
        if adr:
            v["adr"] = adr
        self.violations.append(v)

    def result(self):
        vs = sorted(self.violations, key=lambda v: (v["code"], v["detail"], v.get("adr", "")))
        return {"result": "BLOCKED" if vs else "PASS", "violations": vs}


# ------------------------------------------------------------------ reuse of runner semantics
_RUNNER = None


def _runner():
    """Load the mission runner's parse_index / MOD_RE from the repo copy next to this tool (no rebuild)."""
    global _RUNNER
    if _RUNNER is None:
        path = Path(__file__).resolve().parents[1] / "mission_runner" / "runner.py"
        spec = importlib.util.spec_from_file_location("veyro_mission_runner", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _RUNNER = mod
    return _RUNNER


# ------------------------------------------------------------------ paths
def rel_problem(p, allow_dir=False):
    """Syntax check of a repo-relative POSIX path; None when acceptable."""
    if not isinstance(p, str) or not p:
        return "empty or non-string path"
    if p != p.strip() or any(c in p for c in "\0\\\n\r"):
        return "whitespace, NUL, backslash or newline in path"
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return "absolute path"
    body = p[:-1] if allow_dir and p.endswith("/") else p
    parts = body.split("/")
    if any(x in ("", ".", "..") for x in parts):
        return "empty, '.' or '..' path segment"
    if parts[0] == ".git":
        return ".git path"
    return None


def fs_problem(root, rel):
    """'missing' / 'symlink' / None for a syntactically valid rel path; any symlink component is rejected."""
    cur = Path(root)
    for part in rel.rstrip("/").split("/"):
        cur = cur / part
        try:
            st = os.lstat(cur)
        except OSError:
            return "missing"
        if stat.S_ISLNK(st.st_mode):
            return "symlink"
    return None


def read_bytes(root, rel, code):
    bad = rel_problem(rel) or fs_problem(root, rel)
    if bad:
        raise Malformed(code, f"{rel}: {bad}")
    try:
        return (Path(root) / rel).read_bytes()
    except OSError as e:
        raise Malformed(code, f"{rel}: {e}")


def covers(prefix, path):
    # case-folded: on case-insensitive filesystems "Governance/x" is the same file as "governance/x"
    base, path = prefix.rstrip("/").casefold(), path.casefold()
    return path == base or (prefix.endswith("/") and path.startswith(base + "/"))


# ------------------------------------------------------------------ registry
def load_json(root, rel, code):
    try:
        return json.loads(read_bytes(root, rel, code).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Malformed(code, f"{rel}: unparseable ({e})")


def load_registry(root):
    reg = load_json(root, REGISTRY_PATH, "REGISTRY_UNREADABLE")
    if not isinstance(reg, dict) or reg.get("schema") != SCHEMA:
        raise Malformed("REGISTRY_SCHEMA", f"expected object with schema {SCHEMA}")
    shape = {"module": str, "module_catalog": str, "index": dict, "baseline": dict, "reserved_actions": list,
             "classification": dict, "requirements": list}
    for k, t in shape.items():
        if not isinstance(reg.get(k), t):
            raise Malformed("REGISTRY_SHAPE", f"{k} missing or not {t.__name__}")
    idx, rows = reg["index"], reg["index"].get("authority_rows")
    if not (isinstance(idx.get("sha256"), str) and HEX64_RE.match(idx["sha256"])):
        raise Malformed("REGISTRY_SHAPE", "index.sha256 must be 64 lowercase hex")
    if not (isinstance(rows, list) and rows and all(isinstance(x, str) and not rel_problem(x, True) for x in rows)):
        raise Malformed("REGISTRY_SHAPE", "index.authority_rows must be a non-empty list of safe names")
    if not isinstance(reg["baseline"].get("owner_decision"), str):
        raise Malformed("REGISTRY_SHAPE", "baseline.owner_decision must be a string")
    if not all(isinstance(x, str) and ID_RE.match(x) for x in reg["reserved_actions"]):
        raise Malformed("REGISTRY_SHAPE", "reserved_actions must be a list of id-like strings")
    if not all(isinstance(x, dict) for x in reg["requirements"]):
        raise Malformed("REGISTRY_SHAPE", "requirements must be a list of objects")
    return reg


def load_catalog(root, reg):
    cat = load_json(root, reg["module_catalog"], "CATALOG_UNREADABLE")
    mod_re = _runner().MOD_RE
    if not (isinstance(cat, list) and all(isinstance(m, dict) and isinstance(m.get("id"), str)
                                          and mod_re.match(m["id"]) for m in cat)):
        raise Malformed("CATALOG_INVALID", "catalog must be a list of objects with MOD-nnn ids")
    return {m["id"] for m in cat}


def same(a, b):
    return type(a) is type(b) and a == b


# ------------------------------------------------------------------ static rules
def check_index(root, reg, r):
    bad = fs_problem(root, INDEX_PATH)
    if bad:
        return r.add("INDEX_MISSING", f"{INDEX_PATH} {bad}")
    data = (Path(root) / INDEX_PATH).read_bytes()
    if hashlib.sha256(data).hexdigest() != reg["index"]["sha256"]:
        r.add("INDEX_DRIFT", f"{INDEX_PATH} sha256 differs from registry")
    try:
        names = [n for n, _ in _runner().parse_index(data.decode("utf-8"))]
    except UnicodeDecodeError:
        return r.add("INDEX_UNPARSEABLE", f"{INDEX_PATH} is not UTF-8")
    want = reg["index"]["authority_rows"]
    if len(set(names)) != len(names) or len(set(want)) != len(want):
        r.add("INDEX_ROW_DUPLICATE", "duplicate authority row name")
    for n in sorted(set(want) - set(names)):
        r.add("INDEX_ROW_MISSING", n)
    for n in sorted(set(names) - set(want)):
        r.add("INDEX_ROW_UNEXPECTED", n)


def owner_decision_problem(root, rel):
    if not isinstance(rel, str) or not OWNER_DECISION_RE.match(rel):
        return "not a knowledge/00-Decisions/OWNER-*.md path"
    return fs_problem(root, rel)


def owner_record(root, reg, rel):
    """(record, None) for a usable later-change OWNER record, else (None, problem).

    Header lines "- Covers: <path prefixes>" and "- Actions: <reserved action / defer-<REQ id> names>" before the
    first "## ". The registry baseline decision is never later-change authority."""
    bad = owner_decision_problem(root, rel)
    if bad:
        return None, bad
    if rel.casefold() == reg["baseline"]["owner_decision"].casefold():
        return None, "baseline owner decision is not authority for later changes"
    try:
        text = (Path(root) / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, "unreadable"
    hdr = {}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        h = HEADER_RE.match(line)
        if h:
            if h.group(1) in hdr:
                return None, f"duplicate header {h.group(1)}"
            hdr[h.group(1)] = h.group(2)
    covers_l = [c.strip() for c in hdr["Covers"].split(",")] if hdr.get("Covers") else []
    actions = [c.strip() for c in hdr["Actions"].split(",")] if hdr.get("Actions") else []
    if any(rel_problem(c, True) for c in covers_l):
        return None, "malformed Covers entry"
    if not all(ID_RE.match(x) for x in actions):
        return None, "malformed Actions entry"
    return {"covers": covers_l, "actions": actions}, None


def check_baseline(root, reg, r):
    bad = owner_decision_problem(root, reg["baseline"]["owner_decision"])
    if bad:
        r.add("BASELINE_DECISION_MISSING", f"{reg['baseline']['owner_decision']}: {bad}")


def check_classification(reg, r):
    c = reg["classification"]
    for k, want in EXPECTED_CLASSIFICATION.items():
        if k not in c or not same(c[k], want):
            r.add("CLASSIFICATION_MISMATCH", f"{k} must be {want!r}")
    s = c.get("storage_concept")
    if not (isinstance(s, str) and STORAGE_RE.match(s)) or any(w in s for w in STORAGE_ENGINE_WORDS):
        r.add("STORAGE_CLAIM", "storage_concept must be a plain concept name, not an engine or service")
    for k in sorted(set(c) - set(EXPECTED_CLASSIFICATION) - {"storage_concept"}):
        r.add("CLASSIFICATION_MISMATCH", f"unexpected field {k}")


def check_requirements(root, reg, catalog, r):
    ids = [q.get("id") for q in reg["requirements"]]
    if sorted(map(str, ids)) != sorted(REQ_IDS):
        r.add("REQ_ID_SET", f"need exactly {REQ_IDS[0]}..{REQ_IDS[-1]} once each, got {ids}")
    for q in reg["requirements"]:
        rid = str(q.get("id"))
        for k in sorted(set(q) - REQ_KEYS):
            r.add("REQ_FIELD_UNKNOWN", f"{rid}: {k}")
        owner = q.get("owner")
        if isinstance(owner, (list, dict)):
            r.add("REQ_OWNER_MULTIPLE", rid)
        elif not isinstance(owner, str) or not owner:
            r.add("REQ_OWNER_INVALID", rid)
        elif owner not in catalog:
            r.add("REQ_OWNER_UNKNOWN", f"{rid}: {owner}")
        elif owner != reg["module"]:
            r.add("REQ_OWNER_MISMATCH", f"{rid}: {owner} != {reg['module']}")
        status = q.get("status")
        if status in ("PASS", "ACCEPTED", "COMPLETE") or ("product_pass" in q and q["product_pass"] is not False):
            r.add("REQ_PRODUCT_PASS_CLAIM", rid)
        elif status not in REQ_STATUSES:
            r.add("REQ_STATUS_INVALID", f"{rid}: {status!r}")
        ev = q.get("evidence")
        if not (isinstance(ev, list) and ev and all(isinstance(e, str) for e in ev)):
            r.add("REQ_EVIDENCE_MISSING", rid)
        else:
            for e in ev:
                bad = rel_problem(e)
                if bad:
                    r.add("EVIDENCE_PATH_INVALID", f"{rid}: {e!r}: {bad}")
                    continue
                bad = fs_problem(root, e)
                if bad:
                    r.add("EVIDENCE_" + bad.upper(), f"{rid}: {e}")
        if status == "DEFERRED":
            if not (isinstance(q.get("deferred_to"), str) and q["deferred_to"] in catalog) or not (isinstance(q.get("reason"), str) and q["reason"].strip()):
                r.add("REQ_DEFERRED_INVALID", f"{rid}: needs catalog deferred_to and a reason")
            elif q["deferred_to"] == reg["module"]:
                r.add("REQ_DEFERRED_SELF", f"{rid}: deferred_to must differ from {reg['module']}")
            if q.get("product_pass") is not False:
                r.add("REQ_DEFERRED_INVALID", f"{rid}: DEFERRED needs explicit product_pass false")
            # GOV-02-R01..R08 are Critical/Foundation: deferral needs an explicit owner approval, not free text
            appr = q.get("owner_approval")
            rec, bad = owner_record(root, reg, appr) if isinstance(appr, str) else (None, "owner_approval missing")
            if rec is None:
                r.add("REQ_DEFERRAL_APPROVAL_MISSING", f"{rid}: {bad}")
            elif f"defer-{rid}" not in rec["actions"]:
                r.add("REQ_DEFERRAL_APPROVAL_UNRELATED", f"{rid}: {appr} Actions does not list defer-{rid}")
        elif "deferred_to" in q or "reason" in q:
            r.add("REQ_DEFERRED_INVALID", f"{rid}: deferred_to/reason only allowed when DEFERRED")


# ------------------------------------------------------------------ ADRs
def parse_adr(root, name, r):
    m = ADR_FILE_RE.match(name)
    if not m:
        return r.add("ADR_FILENAME", name, adr=name)
    fid, rel = m.group(1), f"{ADR_DIR}/{name}"
    if fs_problem(root, rel):
        return r.add("ADR_SYMLINK", name, adr=fid)
    try:
        text = (Path(root) / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return r.add("ADR_HEADER", f"{name} unreadable", adr=fid)
    hdr, ok = {}, True
    for line in text.splitlines():
        if line.startswith("## "):
            break
        h = HEADER_RE.match(line)
        if h:
            if h.group(1) in hdr:
                ok = False
                r.add("ADR_HEADER", f"duplicate header {h.group(1)}", adr=fid)
            hdr[h.group(1)] = h.group(2)
    for k in sorted(set(hdr) - set(ADR_REQUIRED) - set(ADR_OPTIONAL)):
        ok = False
        r.add("ADR_HEADER", f"unknown header {k}", adr=fid)
    for k in ADR_REQUIRED:
        if not hdr.get(k):
            ok = False
            r.add("ADR_HEADER", f"missing header {k}", adr=fid)
    if not ok:
        return None
    a = {"id": hdr["ID"], "file_id": fid, "file": rel, "status": hdr["Status"], "key": hdr["Decision-Key"],
         "covers": [c.strip() for c in hdr["Covers"].split(",")], "review": hdr.get("Review", ""),
         "reserved": hdr.get("Reserved-Action", ""), "approval": hdr.get("Owner-Approval", ""),
         "supersedes": hdr.get("Supersedes", ""), "superseded_by": hdr.get("Superseded-By", "")}
    if a["id"] != fid or not ADR_ID_RE.match(a["id"]):
        r.add("ADR_HEADER", f"ID {a['id']!r} must equal filename id {fid}", adr=fid)
    if a["status"] not in ADR_STATUSES:
        r.add("ADR_HEADER", f"bad Status {a['status']!r}", adr=fid)
    if not KEY_RE.match(a["key"]):
        r.add("ADR_HEADER", f"bad Decision-Key {a['key']!r}", adr=fid)
    if any(rel_problem(c, True) for c in a["covers"]):
        r.add("ADR_HEADER", "bad Covers entry", adr=fid)
    for k in ("supersedes", "superseded_by"):
        if a[k] and not ADR_ID_RE.match(a[k]):
            r.add("ADR_HEADER", f"bad {k} {a[k]!r}", adr=fid)
    return a


def check_adrs(root, reg, r):
    adrs, d = [], Path(root) / ADR_DIR
    names = sorted(n for n in os.listdir(d) if n.startswith("ADR-")) if d.is_dir() and not d.is_symlink() else []
    for n in names:
        a = parse_adr(root, n, r)
        if a:
            adrs.append(a)
    by_id, seen = {}, set()  # keyed by FILENAME id: a declared ID can never make a file answer for another
    for a in adrs:
        if a["id"] in seen or a["file_id"] in seen:
            r.add("ADR_DUPLICATE_ID", a["id"], adr=a["id"])
        seen.update((a["id"], a["file_id"]))
        by_id[a["file_id"]] = a
    accepted = {}
    for a in adrs:
        if a["status"] == "ACCEPTED":
            accepted.setdefault(a["key"], []).append(a["id"])
            if not REVIEW_RE.match(a["review"]):
                r.add("ADR_REVIEW_INVALID", "ACCEPTED needs 'Review: <review-id> APPROVED'", adr=a["id"])
            if a["reserved"]:
                if a["reserved"] not in reg["reserved_actions"]:
                    r.add("ADR_RESERVED_UNKNOWN", a["reserved"], adr=a["id"])
                else:
                    rec, bad = owner_record(root, reg, a["approval"])
                    if rec is None:
                        r.add("ADR_DC16_APPROVAL_MISSING",
                              f"{a['reserved']} needs an existing non-baseline OWNER-* Owner-Approval: {bad}", adr=a["id"])
                    elif a["reserved"] not in rec["actions"]:
                        r.add("ADR_DC16_ACTION_NOT_COVERED",
                              f"{a['approval']} Actions does not list {a['reserved']}", adr=a["id"])
                    elif a["file"].casefold() not in (c.casefold() for c in rec["covers"]):
                        # approval is bound to this ADR's exact file; a directory prefix or another ADR's file never counts
                        r.add("ADR_DC16_APPROVAL_NOT_BOUND",
                              f"{a['approval']} Covers does not list {a['file']}", adr=a["id"])
    for key, ids in sorted(accepted.items()):
        if len(ids) > 1:
            r.add("ADR_DUPLICATE_ACCEPTED", f"{key}: {sorted(ids)}")
    for a in adrs:
        t, s = by_id.get(a["supersedes"]), by_id.get(a["superseded_by"])
        if a["supersedes"] and (t is None or t is a or a["status"] not in ("ACCEPTED", "SUPERSEDED")
                                or t["status"] != "SUPERSEDED" or t["superseded_by"] != a["id"]
                                or t["key"] != a["key"]):
            r.add("ADR_SUPERSESSION", f"{a['id']} supersedes {a['supersedes']} inconsistently", adr=a["id"])
        if a["status"] == "SUPERSEDED":
            if s is None or s is a or s["status"] not in ("ACCEPTED", "SUPERSEDED") or s["supersedes"] != a["id"]:
                r.add("ADR_SUPERSESSION", f"{a['id']} lacks a valid Superseded-By", adr=a["id"])
        elif a["superseded_by"]:
            r.add("ADR_SUPERSESSION", f"{a['id']} has Superseded-By but is {a['status']}", adr=a["id"])
    return by_id


def check(root):
    reg, r = load_registry(root), Report()
    for k in sorted(set(reg) - TOP_KEYS):
        r.add("REGISTRY_FIELD_UNKNOWN", k)
    catalog = load_catalog(root, reg)
    if reg["module"] not in catalog:
        r.add("MODULE_UNKNOWN", reg["module"])
    check_index(root, reg, r)
    check_baseline(root, reg, r)
    check_classification(reg, r)
    check_requirements(root, reg, catalog, r)
    check_adrs(root, reg, r)
    return r.result()


# ------------------------------------------------------------------ change control
def read_paths(text):
    paths = text.split("\n")
    if paths and paths[-1] == "":
        paths.pop()
    if not paths:
        raise Malformed("CHANGE_PATHS_EMPTY", "no changed paths on stdin")
    for p in paths:
        bad = rel_problem(p)
        if bad:
            raise Malformed("CHANGE_PATH_INVALID", f"{p!r}: {bad}")
    return paths


def index_names(root):
    bad = fs_problem(root, INDEX_PATH)
    if bad:
        raise Malformed("INDEX_UNREADABLE", f"{INDEX_PATH} {bad}")
    try:
        data = (Path(root) / INDEX_PATH).read_bytes().decode("utf-8")
        return [n for n, _ in _runner().parse_index(data)]
    except (OSError, UnicodeDecodeError) as e:
        raise Malformed("INDEX_UNREADABLE", f"{INDEX_PATH}: {e}")


def check_change(root, decision, paths):
    reg, r = load_registry(root), Report()
    if not ID_RE.match(decision):
        raise Malformed("DECISION_INVALID", repr(decision))
    # frozen set = registry rows UNION rows parsed from the actual index (a registry edit cannot unfreeze a row)
    frozen_names = ([n.rstrip("/") for n in reg["index"]["authority_rows"]] + [INDEX_PATH]
                    + [n.rstrip("/") for n in index_names(root)])
    folded = {p.casefold() for p in paths}
    frozen = sorted(p for p in set(paths)
                    if any(p.casefold() == n.casefold() or p.casefold().startswith(n.casefold() + "/")
                           for n in frozen_names))
    # OWNER-* records are owner-level: never authorizable by an ADR, so they are frozen, not merely controlled
    owner_prefix = f"{ADR_DIR}/OWNER-".casefold()
    frozen = sorted(set(frozen) | {p for p in set(paths) if p.casefold().startswith(owner_prefix)})
    controlled = sorted(p for p in set(paths) if p not in frozen
                        and (any(covers(c, p) for c in CONTROLLED) or p.casefold() == reg["module_catalog"].casefold()))
    if frozen:
        owner_rel = f"{ADR_DIR}/{decision}.md"
        if owner_rel.casefold() in folded:
            r.add("CHANGE_SELF_AUTHORIZING", f"{owner_rel} is part of the change it would authorize")
        rec, bad = ((None, "--decision must be an OWNER-* record") if not OWNER_STEM_RE.match(decision)
                    else owner_record(root, reg, owner_rel))
        if rec is None:
            r.add("FROZEN_BASELINE_CHANGE", f"owner approval required for {frozen}: {bad}")
        else:
            for p in frozen:
                if not any(covers(c, p) for c in rec["covers"]):
                    r.add("FROZEN_NOT_COVERED", f"{decision} Covers does not list {p}")
    if controlled:
        scratch = Report()
        adrs = check_adrs(root, reg, scratch)
        a = adrs.get(decision)
        # any ADR integrity violation anywhere blocks a controlled change, not only the selected ADR's
        for v in scratch.violations:
            r.add("CHANGE_ADR_INVALID", f"{v['code']}: {v['detail']}", adr=v.get("adr"))
        if a is None:
            r.add("CONTROLLED_CHANGE_UNREFERENCED", f"{decision} is not an ADR in {ADR_DIR}")
        elif a["status"] != "ACCEPTED":
            r.add("CHANGE_ADR_NOT_ACCEPTED", f"{decision} is {a['status']}")
        else:
            if a["file"].casefold() in folded:
                r.add("CHANGE_SELF_AUTHORIZING", f"{a['file']} is part of the change it would authorize", adr=decision)
            for p in controlled:
                if not any(covers(c, p) for c in a["covers"]):
                    r.add("CHANGE_ADR_NOT_COVERING", f"{decision} does not cover {p}")
    return r.result()


# ------------------------------------------------------------------ CLI
def main(argv=None, stdin=None):
    ap = argparse.ArgumentParser(prog="governance_check", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "check-change"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True)
        if name == "check-change":
            p.add_argument("--decision", required=True)
    args = ap.parse_args(argv)  # usage errors exit 2
    try:
        root = Path(os.path.realpath(args.root))
        if not root.is_dir():
            raise Malformed("ROOT_INVALID", args.root)
        if args.cmd == "check":
            out = check(root)
        else:
            try:
                text = (stdin if stdin is not None else sys.stdin.buffer).read()
                text = text.decode("utf-8") if isinstance(text, bytes) else text
            except UnicodeDecodeError:
                raise Malformed("CHANGE_PATH_INVALID", "stdin is not UTF-8")
            out = check_change(root, args.decision, read_paths(text))
    except Malformed as e:
        out = {"result": "MALFORMED", "violations": [{"code": e.code, "detail": e.detail}]}
    except Exception as e:  # fail closed on anything unexpected
        out = {"result": "MALFORMED", "violations": [{"code": "INTERNAL_ERROR", "detail": repr(e)}]}
    print(json.dumps(out, indent=1, sort_keys=True))
    return {"PASS": 0, "BLOCKED": 1}.get(out["result"], 2)


if __name__ == "__main__":
    sys.exit(main())
