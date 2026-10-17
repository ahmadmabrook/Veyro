"""Deterministic fixture tests for the MOD-002 governance validator.
Run: python3 -m unittest discover -s tools/governance/tests -t tools/governance
Every test builds its own temporary repository root; the real repository is never read as a root or written.
"""
import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import governance_check as G  # noqa: E402

ROWS = ["A.docx", "B.docx", "design/"]
OWNER = "knowledge/00-Decisions/OWNER-2026-10-16-baseline.md"
OWNER2 = "knowledge/00-Decisions/OWNER-2026-10-17-change.md"
OWNER2_STEM = "OWNER-2026-10-17-change"
OWNER_TEXT = ("# owner change approval\n\n- Covers: PROJECT_INDEX.md, A.docx, B.docx, design/, "
              "knowledge/00-Decisions/OWNER-2026-10-18-next.md, knowledge/00-Decisions/ADR-0002-deploy.md\n"
              "- Actions: production-deploy, defer-GOV-02-R06\n\n## Decision\nfixture\n")
REQS = G.REQ_IDS


def adr_text(**h):
    base = {"ID": "ADR-0001", "Status": "ACCEPTED", "Decision-Key": "governance-change-control",
            "Covers": "governance/, tools/governance/, knowledge/00-Decisions/, .github/workflows/",
            "Review": "REV-001 APPROVED"}
    base.update(h)
    lines = [f"# {base['ID']} fixture", ""] + [f"- {k}: {v}" for k, v in base.items() if v is not None]
    return "\n".join(lines) + "\n\n## Context\nfixture\n"


class Fx:
    def __init__(self, tc):
        self.root = Path(tempfile.mkdtemp(prefix="gov-fx-"))
        tc.addCleanup(shutil.rmtree, self.root, True)
        self.write("PROJECT_INDEX.md", "# index\n" + "".join(f"| `{n}` | `{'a' * 64}` |\n" for n in ROWS))
        self.write("tools/mission_runner/module_catalog.json",
                   json.dumps([{"id": m} for m in ("MOD-001", "MOD-002", "MOD-003")]))
        self.write(OWNER, "owner approval\n")
        self.write(OWNER2, OWNER_TEXT)
        self.write("knowledge/03-Modules/MOD-002/evidence.md", "evidence\n")
        self.write("knowledge/00-Decisions/ADR-0001-change-control.md", adr_text())
        self.reg = {
            "schema": G.SCHEMA, "module": "MOD-002", "module_catalog": "tools/mission_runner/module_catalog.json",
            "index": {"sha256": hashlib.sha256((self.root / "PROJECT_INDEX.md").read_bytes()).hexdigest(),
                      "authority_rows": list(ROWS)},
            "baseline": {"owner_decision": OWNER},
            "reserved_actions": ["production-deploy"],
            "classification": {"anchor": "GOV-02", "tier": 2, "classification": "confidential",
                               "tenant_scoped": True, "invariant": "INV-GOV-02", "runbook": "RB-GOV-02",
                               "ai_system": "none", "storage_concept": "governance-records"},
            "requirements": [{"id": i, "owner": "MOD-002", "status": "FOUNDATION",
                              "evidence": ["knowledge/03-Modules/MOD-002/evidence.md"]} for i in REQS],
        }
        self.save()

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def save(self):
        self.write("governance/registry.json", json.dumps(self.reg))

    def req(self, n):
        return self.reg["requirements"][n - 1]

    def adr(self, name, **h):
        self.write(f"knowledge/00-Decisions/{name}.md", adr_text(**h))


def run(*argv, stdin=""):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = G.main(list(argv), stdin=io.StringIO(stdin))
    return code, json.loads(out.getvalue())


class Base(unittest.TestCase):
    def setUp(self):
        self.fx = Fx(self)

    def check(self):
        return run("check", "--root", str(self.fx.root))

    def change(self, decision, *paths):
        return run("check-change", "--root", str(self.fx.root), "--decision", decision, stdin="\n".join(paths) + "\n")

    def assertBlocked(self, code_name, res=None):
        code, out = res or self.check()
        self.assertEqual(code, 1, out)
        self.assertIn(code_name, [v["code"] for v in out["violations"]], out)

    def assertMalformed(self, res):
        self.assertEqual(res[0], 2, res[1])
        self.assertEqual(res[1]["result"], "MALFORMED")


class StaticCheck(Base):
    def test_valid_fixture_passes(self):
        code, out = self.check()
        self.assertEqual((code, out), (0, {"result": "PASS", "violations": []}))

    def test_deferred_and_foundation_mix_passes(self):
        self.fx.req(6).update(status="DEFERRED", deferred_to="MOD-003", reason="AI platform is a later module",
                              product_pass=False, owner_approval=OWNER2)
        self.fx.save()
        self.assertEqual(self.check()[0], 0)

    def test_drifted_index(self):
        (self.fx.root / "PROJECT_INDEX.md").write_text("tampered\n" + "".join(f"| `{n}` | `{'a' * 64}` |\n" for n in ROWS))
        self.assertBlocked("INDEX_DRIFT")

    def test_missing_authority_row(self):
        text = "# index\n" + "".join(f"| `{n}` | `{'a' * 64}` |\n" for n in ROWS[:-1])
        (self.fx.root / "PROJECT_INDEX.md").write_text(text)
        self.fx.reg["index"]["sha256"] = hashlib.sha256(text.encode()).hexdigest()
        self.fx.save()
        self.assertBlocked("INDEX_ROW_MISSING")

    def test_unexpected_authority_row(self):
        self.fx.reg["index"]["authority_rows"] = ROWS[:-1]
        self.fx.save()
        self.assertBlocked("INDEX_ROW_UNEXPECTED")

    def test_missing_index_file(self):
        (self.fx.root / "PROJECT_INDEX.md").unlink()
        self.assertBlocked("INDEX_MISSING")

    def test_baseline_decision_missing(self):
        (self.fx.root / OWNER).unlink()
        self.assertBlocked("BASELINE_DECISION_MISSING")

    def test_baseline_decision_must_be_owner_record(self):
        self.fx.reg["baseline"]["owner_decision"] = "knowledge/03-Modules/MOD-002/evidence.md"
        self.fx.save()
        self.assertBlocked("BASELINE_DECISION_MISSING")

    def test_owner_problems(self):
        for owner, code in ((["MOD-002", "MOD-001"], "REQ_OWNER_MULTIPLE"), ("MOD-999", "REQ_OWNER_UNKNOWN"),
                            (None, "REQ_OWNER_INVALID"), ("", "REQ_OWNER_INVALID"), ("MOD-001", "REQ_OWNER_MISMATCH")):
            with self.subTest(owner=owner):
                self.setUp()
                self.fx.req(2)["owner"] = owner
                self.fx.save()
                self.assertBlocked(code)

    def test_requirement_id_set(self):
        cases = {"missing": lambda rs: rs.pop(),
                 "shorthand": lambda rs: rs[0].update(id="GOV-02.1"),
                 "duplicate": lambda rs: rs[7].update(id="GOV-02-R01"),
                 "extra": lambda rs: rs.append(dict(rs[0], id="GOV-02-R09"))}
        for name, mutate in cases.items():
            with self.subTest(name):
                self.setUp()
                mutate(self.fx.reg["requirements"])
                self.fx.save()
                self.assertBlocked("REQ_ID_SET")

    def test_evidence_escape_absolute_missing(self):
        for path, code in (("../outside.md", "EVIDENCE_PATH_INVALID"), ("/etc/passwd", "EVIDENCE_PATH_INVALID"),
                           ("a/../../x", "EVIDENCE_PATH_INVALID"), ("nope.md", "EVIDENCE_MISSING")):
            with self.subTest(path=path):
                self.setUp()
                self.fx.req(1)["evidence"] = [path]
                self.fx.save()
                self.assertBlocked(code)

    def test_evidence_empty_blocked(self):
        self.fx.req(1)["evidence"] = []
        self.fx.save()
        self.assertBlocked("REQ_EVIDENCE_MISSING")

    def test_evidence_symlink_file_and_dir(self):
        outside = Path(tempfile.mkdtemp(prefix="gov-out-"))
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "secret.md").write_text("x")
        (self.fx.root / "link.md").symlink_to(outside / "secret.md")
        (self.fx.root / "linkdir").symlink_to(outside, target_is_directory=True)
        for path in ("link.md", "linkdir/secret.md"):
            with self.subTest(path=path):
                self.fx.req(1)["evidence"] = [path]
                self.fx.save()
                self.assertBlocked("EVIDENCE_SYMLINK")

    def test_product_pass_never_implied(self):
        for patch in ({"status": "PASS"}, {"status": "ACCEPTED"}, {"product_pass": True}):
            with self.subTest(patch=patch):
                self.setUp()
                self.fx.req(3).update(patch)
                self.fx.save()
                self.assertBlocked("REQ_PRODUCT_PASS_CLAIM")

    def test_invalid_status_and_deferred_shape(self):
        self.fx.req(1)["status"] = "DONE"
        self.fx.save()
        self.assertBlocked("REQ_STATUS_INVALID")
        self.setUp()
        self.fx.req(4)["status"] = "DEFERRED"  # no deferred_to / reason
        self.fx.save()
        self.assertBlocked("REQ_DEFERRED_INVALID")
        self.setUp()
        self.fx.req(4).update(deferred_to="MOD-003", reason="x")  # deferred fields on FOUNDATION
        self.fx.save()
        self.assertBlocked("REQ_DEFERRED_INVALID")

    def test_unknown_requirement_field(self):
        self.fx.req(5)["database"] = "postgres"
        self.fx.save()
        self.assertBlocked("REQ_FIELD_UNKNOWN")

    def test_classification_claims(self):
        cases = ({"tier": 3}, {"tier": True}, {"classification": "public"}, {"tenant_scoped": False},
                 {"ai_system": "copilot"}, {"invariant": "INV-GOV-03"}, {"runbook": "RB-GOV-01"},
                 {"anchor": "GOV-03"}, {"database": "x"})
        for patch in cases:
            with self.subTest(patch=patch):
                self.setUp()
                self.fx.reg["classification"].update(patch)
                self.fx.save()
                self.assertBlocked("CLASSIFICATION_MISMATCH")

    def test_storage_must_be_concept_only(self):
        for s in ("postgres-cluster", "S3 bucket", 5, None):
            with self.subTest(storage=s):
                self.setUp()
                self.fx.reg["classification"]["storage_concept"] = s
                self.fx.save()
                self.assertBlocked("STORAGE_CLAIM")

    def test_unknown_registry_field(self):
        self.fx.reg["ai_engine"] = "x"
        self.fx.save()
        self.assertBlocked("REGISTRY_FIELD_UNKNOWN")

    def test_owner_module_not_in_catalog(self):
        self.fx.reg["module"] = "MOD-777"
        self.fx.save()
        self.assertBlocked("MODULE_UNKNOWN")


class AdrChecks(Base):
    def test_accepted_without_review(self):
        self.fx.adr("ADR-0001-change-control", Review=None)
        self.assertBlocked("ADR_REVIEW_INVALID")

    def test_accepted_with_invalid_review(self):
        self.fx.adr("ADR-0001-change-control", Review="REV-001 CHANGES_REQUESTED")
        self.assertBlocked("ADR_REVIEW_INVALID")

    def test_proposed_needs_no_review(self):
        self.fx.adr("ADR-0002-x", ID="ADR-0002", Status="PROPOSED", Review=None, **{"Decision-Key": "other-key"})
        self.assertEqual(self.check()[0], 0)

    def test_duplicate_accepted_decision_key(self):
        self.fx.adr("ADR-0002-dup", ID="ADR-0002")
        self.assertBlocked("ADR_DUPLICATE_ACCEPTED")

    def test_header_problems(self):
        for kwargs in ({"Decision-Key": None}, {"Status": "MAYBE"}, {"Bogus": "x"}, {"ID": "ADR-0009"},
                       {"Covers": "../escape/"}, {"Decision-Key": "Bad Key"}):
            with self.subTest(kwargs=kwargs):
                self.setUp()
                self.fx.adr("ADR-0001-change-control", **kwargs)
                self.assertBlocked("ADR_HEADER")

    def test_bad_adr_filename_and_duplicate_header(self):
        self.fx.write("knowledge/00-Decisions/ADR-bad.md", adr_text())
        self.assertBlocked("ADR_FILENAME")
        self.setUp()
        self.fx.write("knowledge/00-Decisions/ADR-0001-change-control.md",
                      adr_text().replace("- Status: ACCEPTED\n", "- Status: ACCEPTED\n- Status: ACCEPTED\n"))
        self.assertBlocked("ADR_HEADER")

    def test_adr_symlink(self):
        d = self.fx.root / "knowledge/00-Decisions"
        (d / "ADR-0002-link.md").symlink_to(d / "ADR-0001-change-control.md")
        self.assertBlocked("ADR_SYMLINK")

    def test_dc16_reserved_action_needs_owner_approval(self):
        self.fx.adr("ADR-0002-deploy", ID="ADR-0002", **{"Decision-Key": "deploy", "Reserved-Action": "production-deploy"})
        self.assertBlocked("ADR_DC16_APPROVAL_MISSING")
        self.fx.adr("ADR-0002-deploy", ID="ADR-0002",
                    **{"Decision-Key": "deploy", "Reserved-Action": "production-deploy", "Owner-Approval": "nope.md"})
        self.assertBlocked("ADR_DC16_APPROVAL_MISSING")
        self.fx.adr("ADR-0002-deploy", ID="ADR-0002",
                    **{"Decision-Key": "deploy", "Reserved-Action": "production-deploy", "Owner-Approval": OWNER})
        self.assertBlocked("ADR_DC16_APPROVAL_MISSING")  # baseline record can never approve production-deploy
        self.fx.write(OWNER, "- Actions: production-deploy\n")
        self.assertBlocked("ADR_DC16_APPROVAL_MISSING")
        self.fx.adr("ADR-0002-deploy", ID="ADR-0002",
                    **{"Decision-Key": "deploy", "Reserved-Action": "production-deploy", "Owner-Approval": OWNER2})
        self.assertEqual(self.check()[0], 0)

    def test_dc16_owner_without_action_coverage(self):
        for text in ("- Covers: A.docx\n", "- Actions: defer-GOV-02-R06\n", "- Actions: production-deploy-all\n",
                     "- Actions: production-deploy\n- Actions: production-deploy\n", "- Actions: bad action\n"):
            with self.subTest(text=text):
                self.fx.write(OWNER2, text)
                self.fx.adr("ADR-0002-deploy", ID="ADR-0002", **{
                    "Decision-Key": "deploy", "Reserved-Action": "production-deploy", "Owner-Approval": OWNER2})
                self.assertEqual(self.check()[0], 1)

    def test_dc16_approval_bound_to_specific_adr(self):
        deploy = {"Reserved-Action": "production-deploy", "Owner-Approval": OWNER2}
        self.fx.adr("ADR-0002-deploy", ID="ADR-0002", **{"Decision-Key": "deploy", **deploy})
        self.assertEqual(self.check()[0], 0)
        # a second, unrelated ADR reusing the same OWNER record must BLOCK
        self.fx.adr("ADR-0003-other", ID="ADR-0003", **{"Decision-Key": "other", **deploy})
        self.assertBlocked("ADR_DC16_APPROVAL_NOT_BOUND")
        # directory prefix, other ADR file, or missing Covers do not bind
        for covers in ("- Covers: knowledge/00-Decisions/\n", "- Covers: knowledge/00-Decisions/ADR-0002-deploy.md\n",
                       ""):
            with self.subTest(covers=covers):
                self.fx.write(OWNER2, covers + "- Actions: production-deploy\n")
                self.assertBlocked("ADR_DC16_APPROVAL_NOT_BOUND")
        # explicitly covering the second ADR file makes it pass
        self.fx.write(OWNER2, "- Covers: knowledge/00-Decisions/ADR-0002-deploy.md, "
                              "knowledge/00-Decisions/ADR-0003-other.md\n- Actions: production-deploy\n")
        self.assertEqual(self.check()[0], 0)

    def test_dc16_unknown_reserved_action(self):
        self.fx.adr("ADR-0002-x", ID="ADR-0002", **{"Decision-Key": "x-key", "Reserved-Action": "launch-rocket",
                                                  "Owner-Approval": OWNER})
        self.assertBlocked("ADR_RESERVED_UNKNOWN")

    def _chain(self, old=None, new=None):
        self.fx.adr("ADR-0001-change-control", **(old or {"Status": "SUPERSEDED", "Superseded-By": "ADR-0002"}))
        self.fx.adr("ADR-0002-change-control", ID="ADR-0002", **(new or {"Supersedes": "ADR-0001"}))

    def test_valid_supersession_passes(self):
        self._chain()
        self.assertEqual(self.check()[0], 0)
        self.assertEqual(self.change("ADR-0002", "governance/registry.json")[0], 0)
        self.assertEqual(self.change("ADR-0001", "governance/registry.json")[0], 1)

    def test_broken_supersession(self):
        cases = {"target-not-marked": ({"Status": "ACCEPTED"}, None),
                 "superseded-without-pointer": ({"Status": "SUPERSEDED"}, {"Decision-Key": "governance-change-control"}),
                 "unknown-target": (None, {"Supersedes": "ADR-0042"}),
                 "key-differs": (None, {"Supersedes": "ADR-0001", "Decision-Key": "other-key"}),
                 "self": ({"Status": "SUPERSEDED", "Superseded-By": "ADR-0001"}, {"Supersedes": "ADR-0002", "Status": "PROPOSED"})}
        for name, (old, new) in cases.items():
            with self.subTest(name):
                self.setUp()
                self._chain(old, new)
                self.assertBlocked("ADR_SUPERSESSION")


class ChangeControl(Base):
    def test_controlled_change_with_covering_accepted_adr_passes(self):
        paths = ("tools/governance/governance_check.py", ".github/workflows/foundation.yml", "governance/registry.json",
                 "knowledge/00-Decisions/ADR-0003.md")
        code, out = self.change("ADR-0001", *paths)
        self.assertEqual((code, out["result"]), (0, "PASS"), out)

    def test_workflow_check_file_is_controlled(self):
        self.assertBlocked("CONTROLLED_CHANGE_UNREFERENCED", self.change("ADR-0099", "tools/mission_runner/workflow_check.py"))
        self.fx.adr("ADR-0001-change-control", Covers="tools/mission_runner/workflow_check.py")
        self.assertEqual(self.change("ADR-0001", "tools/mission_runner/workflow_check.py")[0], 0)

    def test_unreferenced_controlled_change(self):
        for d in ("ADR-0099", "OWNER-2026-10-16-baseline", "whatever"):
            with self.subTest(decision=d):
                self.assertBlocked("CONTROLLED_CHANGE_UNREFERENCED", self.change(d, "governance/registry.json"))

    def test_adr_not_accepted_or_not_covering_or_invalid(self):
        self.fx.adr("ADR-0002-p", ID="ADR-0002", Status="PROPOSED", Review=None, **{"Decision-Key": "p-key"})
        self.assertBlocked("CHANGE_ADR_NOT_ACCEPTED", self.change("ADR-0002", "governance/registry.json"))
        self.fx.adr("ADR-0003-n", ID="ADR-0003", Covers="governance/", **{"Decision-Key": "n-key"})
        self.assertBlocked("CHANGE_ADR_NOT_COVERING", self.change("ADR-0003", "tools/governance/x.py"))
        self.fx.adr("ADR-0001-change-control", Review=None)
        self.assertBlocked("CHANGE_ADR_INVALID", self.change("ADR-0001", "governance/registry.json"))

    def test_covers_does_not_match_sibling_prefix(self):
        self.fx.adr("ADR-0001-change-control", Covers="governance/")
        self.assertBlocked("CHANGE_ADR_NOT_COVERING", self.change("ADR-0001", "tools/governance/x.py"))

    def test_frozen_baseline_change_requires_owner_approval(self):
        for p in ("PROJECT_INDEX.md", "A.docx", "design/screen.html"):
            with self.subTest(path=p):
                self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("ADR-0001", p))
                self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("OWNER-missing", p))
                self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("OWNER-2026-10-16-baseline", p))
                self.assertEqual(self.change(OWNER2_STEM, p)[0], 0)

    def test_adr_cannot_authorize_a_change_that_includes_itself(self):
        self.assertBlocked("CHANGE_SELF_AUTHORIZING", self.change(
            "ADR-0001", "governance/registry.json", "knowledge/00-Decisions/ADR-0001-change-control.md"))
        self.assertBlocked("CHANGE_SELF_AUTHORIZING", self.change(
            "ADR-0001", "Governance/registry.json", "Knowledge/00-Decisions/ADR-0001-Change-Control.md"))

    def test_owner_record_cannot_authorize_a_change_that_includes_itself(self):
        self.assertBlocked("CHANGE_SELF_AUTHORIZING", self.change(OWNER2_STEM, "A.docx", OWNER2))
        self.assertBlocked("CHANGE_SELF_AUTHORIZING", self.change(OWNER2_STEM, "A.docx", OWNER2.upper()))

    def test_case_variants_do_not_escape_frozen_or_controlled(self):
        self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("ADR-0001", "a.DOCX"))
        self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("ADR-0001", "Project_Index.md"))
        self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("ADR-0001", "DESIGN/screen.html"))
        self.assertBlocked("CONTROLLED_CHANGE_UNREFERENCED", self.change("ADR-0099", ".GitHub/Workflows/ci.yml"))

    def test_frozen_lookalike_not_frozen(self):
        self.assertEqual(self.change("ADR-0001", "design-notes/x.md", "A.docx.bak")[0], 0)

    def test_uncontrolled_change_passes(self):
        self.assertEqual(self.change("ADR-0001", "backend/app.py")[0], 0)

    def test_malformed_paths_exit_2(self):
        bad = ("/etc/passwd", "../x", "a/../../x", "a//b", "./a", "a\\b", ".git/config", "a/", " a", "C:/x", "")
        for p in bad:
            with self.subTest(path=p):
                self.assertMalformed(self.change("ADR-0001", "governance/registry.json", p))

    def test_empty_and_non_utf8_stdin(self):
        r = ("check-change", "--root", str(self.fx.root), "--decision", "ADR-0001")
        self.assertMalformed(run(*r, stdin=""))
        self.assertMalformed(run(*r, stdin="\n"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = G.main(list(r), stdin=io.BytesIO(b"\xff\xfe\n"))
        self.assertEqual(code, 2)

    def test_bad_decision_id(self):
        self.assertMalformed(self.change("../x", "governance/registry.json"))


class Hardening(Base):
    def test_frozen_requires_explicit_covers(self):
        for text in ("owner approval\n", "- Covers: B.docx\n", "- Covers: design\n", "- Covers: ../A.docx\n",
                     "- Covers: A.docx, \n", "- Covers:\n", "- Covers: A.docx\n- Covers: A.docx\n",
                     "- Actions: production-deploy\n", "## Covers\n- Covers: A.docx\n"):
            with self.subTest(text=text):
                self.fx.write(OWNER2, text)
                code, out = self.change(OWNER2_STEM, "A.docx")
                self.assertEqual(code, 1, out)
                self.assertTrue({"FROZEN_BASELINE_CHANGE", "FROZEN_NOT_COVERED"} & {v["code"] for v in out["violations"]})

    def test_frozen_positive_explicit_coverage(self):
        self.fx.write(OWNER2, "- Covers: A.docx, design/\n")
        self.assertEqual(self.change(OWNER2_STEM, "A.docx", "design/x/y.html")[0], 0)
        self.assertBlocked("FROZEN_NOT_COVERED", self.change(OWNER2_STEM, "A.docx", "B.docx"))

    def test_baseline_owner_decision_is_not_later_authority(self):
        self.fx.write(OWNER, "- Covers: A.docx, PROJECT_INDEX.md, design/\n")
        self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("OWNER-2026-10-16-baseline", "A.docx"))

    def test_owner_record_change_requires_owner_not_adr(self):
        new = "knowledge/00-Decisions/OWNER-2026-10-19-new.md"
        self.fx.write(new, "- Covers: A.docx\n")
        self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("ADR-0001", new))
        self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("ADR-0001", new.replace("OWNER", "owner")))
        # the second step of the bypass is blocked at step one; an existing OWNER must cover the new record
        self.assertBlocked("FROZEN_NOT_COVERED", self.change(OWNER2_STEM, new))
        self.assertEqual(self.change(OWNER2_STEM, "knowledge/00-Decisions/OWNER-2026-10-18-next.md")[0], 0)

    def test_frozen_set_unions_actual_index(self):
        self.fx.reg["index"]["authority_rows"] = ["B.docx", "design/"]  # A.docx deleted from registry
        self.fx.save()
        self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("ADR-0001", "A.docx"))
        self.assertBlocked("FROZEN_BASELINE_CHANGE", self.change("ADR-0001", "A.docx", "governance/registry.json"))

    def test_unreadable_index_fails_closed_for_change(self):
        (self.fx.root / "PROJECT_INDEX.md").unlink()
        self.assertMalformed(self.change("ADR-0001", "governance/registry.json"))

    def test_mixed_frozen_and_controlled_needs_both(self):
        for d in ("ADR-0001", OWNER2_STEM):
            with self.subTest(decision=d):
                code, out = self.change(d, "A.docx", "governance/registry.json")
                self.assertEqual(code, 1, out)

    def test_duplicate_accepted_key_blocks_controlled_change(self):
        self.fx.adr("ADR-0002-dup", ID="ADR-0002")
        self.assertBlocked("CHANGE_ADR_INVALID", self.change("ADR-0001", "governance/registry.json"))

    def test_inconsistent_supersession_in_other_adr_blocks_change(self):
        self.fx.adr("ADR-0002-s", ID="ADR-0002", Supersedes="ADR-0001", **{"Decision-Key": "other"})
        code, out = self.change("ADR-0001", "governance/registry.json")
        self.assertBlocked("CHANGE_ADR_INVALID", (code, out))
        self.assertIn("ADR_SUPERSESSION", json.dumps(out))

    def test_declared_id_mismatch_cannot_authorize(self):
        (self.fx.root / "knowledge/00-Decisions/ADR-0001-change-control.md").unlink()
        self.fx.adr("ADR-0002-x", ID="ADR-0001")  # file ADR-0002 claims to be ADR-0001
        self.assertBlocked("CONTROLLED_CHANGE_UNREFERENCED", self.change("ADR-0001", "governance/registry.json"))
        self.assertBlocked("CHANGE_ADR_INVALID", self.change("ADR-0002", "governance/registry.json"))

    def test_declared_id_collision_with_existing_adr_blocked(self):
        self.fx.adr("ADR-0002-x", ID="ADR-0001", **{"Decision-Key": "other"})
        self.assertBlocked("CHANGE_ADR_INVALID", self.change("ADR-0001", "governance/registry.json"))
        self.assertBlocked("CHANGE_ADR_INVALID", self.change("ADR-0002", "governance/registry.json"))

    def _defer(self, **kw):
        q = {"status": "DEFERRED", "deferred_to": "MOD-003", "reason": "later", "product_pass": False,
             "owner_approval": OWNER2}
        q.update(kw)
        self.fx.req(6).update(q)
        for k in [k for k, v in kw.items() if v is None]:
            del self.fx.req(6)[k]
        self.fx.save()

    def test_deferral_valid_explicit_approval(self):
        self._defer()
        code, out = self.check()
        self.assertEqual((code, out["result"]), (0, "PASS"), out)

    def test_deferral_missing_self_and_unrelated_approval(self):
        cases = (({"owner_approval": None}, "REQ_DEFERRAL_APPROVAL_MISSING"),
                 ({"owner_approval": "nope.md"}, "REQ_DEFERRAL_APPROVAL_MISSING"),
                 ({"owner_approval": OWNER}, "REQ_DEFERRAL_APPROVAL_MISSING"),  # baseline
                 ({"deferred_to": "MOD-002"}, "REQ_DEFERRED_SELF"),
                 ({"product_pass": None}, "REQ_DEFERRED_INVALID"))
        for kw, code in cases:
            with self.subTest(kw=kw):
                self.setUp()
                self._defer(**kw)
                self.assertBlocked(code)
        self.setUp()
        self.fx.write(OWNER2, "- Covers: A.docx\n- Actions: production-deploy, defer-GOV-02-R05\n")
        self._defer()
        self.assertBlocked("REQ_DEFERRAL_APPROVAL_UNRELATED")

    def test_validator_dependencies_are_controlled(self):
        for p in ("tools/mission_runner/runner.py", "tools/mission_runner/module_catalog.json"):
            with self.subTest(path=p):
                self.assertBlocked("CONTROLLED_CHANGE_UNREFERENCED", self.change("ADR-0099", p))
                self.assertBlocked("CHANGE_ADR_NOT_COVERING", self.change("ADR-0001", p))
                self.fx.adr("ADR-0001-change-control", Covers=p)
                self.assertEqual(self.change("ADR-0001", p)[0], 0)
                self.fx.adr("ADR-0001-change-control")


class MalformedInput(Base):
    def test_missing_registry(self):
        (self.fx.root / "governance/registry.json").unlink()
        self.assertMalformed(self.check())
        self.assertMalformed(self.change("ADR-0001", "governance/registry.json"))

    def test_unparseable_and_wrong_schema_registry(self):
        self.fx.write("governance/registry.json", "{not json")
        self.assertMalformed(self.check())
        self.fx.write("governance/registry.json", json.dumps(dict(self.fx.reg, schema="other/9")))
        self.assertMalformed(self.check())
        self.fx.write("governance/registry.json", "[]")
        self.assertMalformed(self.check())

    def test_registry_shape_errors(self):
        for mutate in (lambda r: r.pop("classification"), lambda r: r["index"].update(sha256="xyz"),
                       lambda r: r["index"].update(authority_rows=[]), lambda r: r.update(requirements=["x"]),
                       lambda r: r["index"].update(authority_rows=["/abs"]), lambda r: r.update(reserved_actions="x")):
            with self.subTest():
                self.setUp()
                mutate(self.fx.reg)
                self.fx.save()
                self.assertMalformed(self.check())

    def test_registry_symlink_rejected(self):
        reg = self.fx.root / "governance/registry.json"
        real = self.fx.root / "real.json"
        reg.rename(real)
        reg.symlink_to(real)
        self.assertMalformed(self.check())

    def test_bad_catalog(self):
        self.fx.write("tools/mission_runner/module_catalog.json", '[{"id": "nope"}]')
        self.assertMalformed(self.check())
        self.fx.write("tools/mission_runner/module_catalog.json", "garbage")
        self.assertMalformed(self.check())

    def test_catalog_path_escape(self):
        self.fx.reg["module_catalog"] = "../catalog.json"
        self.fx.save()
        self.assertMalformed(self.check())

    def test_root_not_a_directory(self):
        self.assertMalformed(run("check", "--root", str(self.fx.root / "absent")))

    def test_usage_errors_exit_2(self):
        for argv in ([], ["check"], ["check-change", "--root", "."], ["bogus", "--root", "."]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    G.main(argv)
                self.assertEqual(cm.exception.code, 2)


NEW = "knowledge/00-Decisions/OWNER-2026-10-18-next.md"
NEW_STEM = "OWNER-2026-10-18-next"
EVID = "knowledge/03-Modules/MOD-002/evidence.md"


class FirstPublication(Base):
    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
        self.fx.write(NEW, OWNER_TEXT)
        self.ext = Path(tempfile.mkdtemp(prefix="gov-att-"))
        self.addCleanup(shutil.rmtree, self.ext, True)
        self.att = self.ext / "att.json"
        self.attest()
        self.git("add", "--", NEW)

    def git(self, *a):
        subprocess.run(["git", "-C", str(self.fx.root), *a], check=True, capture_output=True)

    def head(self):
        return subprocess.run(["git", "-C", str(self.fx.root), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()

    def attest(self, **over):
        d = {"schema": "veyro.owner-attestation/1", "owner_id": "gateway-owner",
             "source": "openclaw:webchat:direct", "owner_choice_quote": "I choose option B", "source_prompt_message_id": "msg-123",
             "record_path": NEW, "record_sha256": hashlib.sha256((self.fx.root / NEW).read_bytes()).hexdigest(),
             "expected_head": self.head()}
        d.update(over)
        self.att.write_text(json.dumps(d))

    def publish(self, decision=NEW_STEM, *paths, att=None):
        return run("check-change", "--root", str(self.fx.root), "--decision", decision,
                   "--first-publish-owner-attestation", str(att or self.att),
                   stdin="\n".join(paths or (NEW,)) + "\n")

    def assertPublishBlocked(self, res):
        self.assertEqual(res[0], 1, res[1])
        self.assertIn("FIRST_PUBLISH_BLOCKED", [v["code"] for v in res[1]["violations"]], res[1])

    def assertPublishBlockedBy(self, res, detail):
        self.assertPublishBlocked(res)
        self.assertIn(detail, " | ".join(v["detail"] for v in res[1]["violations"]), res[1])

    def test_exact_new_sole_record_passes_with_audit(self):
        code, out = self.publish()
        self.assertEqual((code, out["result"]), (0, "PASS"), out)
        self.assertEqual(out["first_publish_audit"]["attestation_sha256"],
                         hashlib.sha256(self.att.read_bytes()).hexdigest())

    def test_staged_new_record_passes(self):
        self.git("add", NEW)
        self.assertEqual(self.publish()[0], 0)

    def test_staged_x_then_attested_working_y_blocks(self):
        self.git("add", NEW)
        self.fx.write(NEW, OWNER_TEXT + "harmless\n")
        self.attest()
        self.assertPublishBlocked(self.publish())
        self.git("add", NEW)
        self.assertEqual(self.publish()[0], 0)

    def test_staged_then_modified_and_typechange_block(self):
        self.git("add", NEW)
        (self.fx.root / NEW).unlink()
        (self.fx.root / NEW).symlink_to(self.fx.root / OWNER)
        self.assertPublishBlocked(self.publish())
        # MM: record committed at HEAD, staged edit, further working edit
        self.git("rm", "-f", "-q", "--cached", "--", NEW)
        (self.fx.root / NEW).unlink()
        self.fx.write(NEW, OWNER_TEXT)
        self.git("add", NEW)
        self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "n")
        self.fx.write(NEW, OWNER_TEXT + "one\n")
        self.git("add", NEW)
        self.fx.write(NEW, OWNER_TEXT + "two\n")
        self.attest()
        self.assertPublishBlocked(self.publish())

    def test_untracked_record_blocks(self):
        self.git("rm", "-q", "--cached", "--", NEW)
        self.assertPublishBlocked(self.publish())

    def test_extra_staged_tracked_edit_blocks(self):
        reg = self.fx.root / "governance/registry.json"
        reg.write_text(reg.read_text() + "\n")
        self.git("add", "governance/registry.json")
        self.assertPublishBlocked(self.publish())

    def test_unrelated_modified_with_assume_unchanged_blocks(self):
        reg = self.fx.root / "governance/registry.json"
        reg.write_text(reg.read_text() + "\n")
        self.git("update-index", "--assume-unchanged", "governance/registry.json")
        self.assertPublishBlocked(self.publish())
        # independent of the ls-files tag check: the raw-bytes comparison alone detects it
        self.assertIn("differs from the index", G.tree_state_problem(self.fx.root, NEW, (self.fx.root / NEW).read_bytes()))

    def test_same_size_edit_with_restored_mtime_blocks(self):
        import os
        reg = self.fx.root / EVID
        st = os.stat(reg)
        data = reg.read_bytes()
        reg.write_bytes(data[:-1] + (b"X" if data[-1:] != b"X" else b"Y"))
        os.utime(reg, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.git("config", "core.trustctime", "false")
        self.git("config", "core.checkStat", "minimal")
        self.assertPublishBlockedBy(self.publish(), f"working file differs from the index: {EVID}")
        self.assertIn("differs from the index", G.tree_state_problem(self.fx.root, NEW, (self.fx.root / NEW).read_bytes()))

    def test_clean_filter_trick_blocks(self):
        reg = self.fx.root / EVID
        orig = self.ext / "orig.md"
        orig.write_bytes(reg.read_bytes())
        data = reg.read_bytes()
        reg.write_bytes(data[:-1] + (b"X" if data[-1:] != b"X" else b"Y"))
        (self.fx.root / ".git/info").mkdir(exist_ok=True)
        (self.fx.root / ".git/info/attributes").write_text(f"{EVID} filter=x\n")
        self.git("config", "filter.x.clean", f"cat '{orig}'")
        self.assertPublishBlockedBy(self.publish(), f"working file differs from the index: {EVID}")
        self.assertIn("differs from the index", G.tree_state_problem(self.fx.root, NEW, (self.fx.root / NEW).read_bytes()))

    def test_tracked_symlink_or_missing_file_blocks(self):
        reg = self.fx.root / EVID
        saved = reg.read_bytes()
        reg.unlink()
        self.assertPublishBlockedBy(self.publish(), "tracked file unreadable or not a plain regular file")
        reg.symlink_to(self.fx.root / OWNER)
        self.assertPublishBlockedBy(self.publish(), "tracked file unreadable or not a plain regular file")
        reg.unlink()
        reg.write_bytes(saved)
        self.assertEqual(self.publish()[0], 0)

    def test_assume_unchanged_hides_nothing(self):
        reg = self.fx.root / "governance/registry.json"
        reg.write_text(reg.read_text() + "\n")
        self.git("update-index", "--assume-unchanged", "governance/registry.json")
        self.assertPublishBlocked(self.publish())
        self.git("update-index", "--no-assume-unchanged", "--skip-worktree", "governance/registry.json")
        self.assertPublishBlocked(self.publish())

    def test_porcelain_entries_keep_codes(self):
        self.assertEqual(G.porcelain_entries(b"?? a\0R  new\0old\0AM x\0"),
                         [("??", "a"), ("R ", "new"), ("R ", "old"), ("AM", "x")])

    def test_absent_option_stays_blocked(self):
        self.assertBlocked("CHANGE_SELF_AUTHORIZING", self.change(NEW_STEM, NEW))

    def test_receipt_mismatches_block(self):
        for over in ({"record_sha256": "0" * 64}, {"owner_id": "someone"}, {"source": "other"},
                     {"record_path": OWNER2}, {"owner_choice_quote": " "}, {"source_prompt_message_id": ""},
                     {"owner_choice_quote": 5}, {"extra": "x"}, {"schema": "veyro.owner-attestation/2"},
                     {"schema": "veyro.owner-attestation/1 "}, {"schema": ""}, {"schema": 1}):
            with self.subTest(over=over):
                self.attest(**over)
                self.assertPublishBlocked(self.publish())

    def test_wrong_head_blocks(self):
        other = "0" * len(self.head())
        self.attest(expected_head=other)
        self.assertPublishBlockedBy(self.publish(), "does not match current HEAD")

    def test_head_move_after_attestation_blocks(self):
        self.git("rm", "-q", "--cached", "--", NEW)
        self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "--allow-empty", "-m", "move")
        self.git("add", "--", NEW)
        self.assertPublishBlockedBy(self.publish(), "does not match current HEAD")
        self.attest()
        self.assertEqual(self.publish()[0], 0)

    def test_malformed_head_blocks(self):
        good = self.head()
        for bad in (good.upper(), good[:-1], good[:7], good + "0", " " + good, good + "\n", "", "HEAD", "g" * len(good), 5, None):
            with self.subTest(bad=bad):
                self.attest(expected_head=bad)
                self.assertPublishBlocked(self.publish())

    def test_missing_head_key_blocks(self):
        d = json.loads(self.att.read_text())
        del d["expected_head"]
        self.att.write_text(json.dumps(d))
        self.assertPublishBlocked(self.publish())

    def test_missing_schema_blocks(self):
        d = json.loads(self.att.read_text())
        del d["schema"]
        self.att.write_text(json.dumps(d))
        self.assertPublishBlocked(self.publish())

    def test_malformed_receipt_blocks(self):
        for text in ("not json", "[]", '{"owner_id": "a", "owner_id": "b"}', ""):
            with self.subTest(text=text):
                self.att.write_text(text)
                self.assertPublishBlocked(self.publish())
        self.assertPublishBlocked(self.publish(att=self.ext / "missing.json"))

    def test_receipt_must_be_regular_file_outside_repo(self):
        inside = self.fx.root / "att.json"
        inside.write_text(self.att.read_text())
        self.assertPublishBlocked(self.publish(att=inside))
        link = self.ext / "link.json"
        link.symlink_to(self.att)
        self.assertPublishBlocked(self.publish(att=link))
        self.assertPublishBlocked(self.publish(att=self.ext))

    def test_existing_head_record_blocks(self):
        self.assertPublishBlocked(self.publish(OWNER2_STEM, OWNER2, att=self._att_for(OWNER2)))
        self.git("add", NEW)
        self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "n")
        self.fx.write(NEW, OWNER_TEXT + "edit\n")
        self.attest()
        self.assertPublishBlocked(self.publish())

    def _att_for(self, rel):
        p = self.ext / "other.json"
        p.write_text(json.dumps({"schema": "veyro.owner-attestation/1", "owner_id": "gateway-owner",
                                 "source": "openclaw:webchat:direct",
                                 "owner_choice_quote": "q", "source_prompt_message_id": "m", "record_path": rel,
                                 "record_sha256": hashlib.sha256((self.fx.root / rel).read_bytes()).hexdigest(),
                                 "expected_head": self.head()}))
        return p

    def test_extra_dirty_or_supplied_path_blocks(self):
        self.fx.write("backend/app.py", "x\n")
        self.assertPublishBlocked(self.publish())
        (self.fx.root / "backend/app.py").unlink()
        self.assertEqual(self.publish()[0], 0)
        (self.fx.root / "A.docx").write_text("dirty\n")
        self.assertPublishBlocked(self.publish())
        (self.fx.root / "A.docx").unlink()
        for extra in ("backend/app.py", "A.docx", "PROJECT_INDEX.md", "governance/registry.json"):
            with self.subTest(extra=extra):
                self.assertPublishBlocked(self.publish(NEW_STEM, NEW, extra))
        self.assertPublishBlocked(self.publish(NEW_STEM, NEW.upper()))
        self.assertPublishBlocked(self.publish(NEW_STEM, NEW, NEW.upper()))

    def test_frozen_baseline_and_wrong_decision_block(self):
        self.assertPublishBlocked(self.publish(NEW_STEM, OWNER))
        self.assertPublishBlocked(self.publish("OWNER-2026-10-16-baseline", OWNER))
        self.assertPublishBlocked(self.publish("ADR-0001", NEW))
        self.assertPublishBlocked(self.publish("OWNER-other", NEW))

    def test_symlink_record_blocks(self):
        (self.fx.root / NEW).unlink()
        (self.fx.root / NEW).symlink_to(self.fx.root / OWNER)
        self.assertPublishBlocked(self.publish())

    def test_oversized_receipt_blocks(self):
        self.att.write_text(" " * (G.ATTEST_MAX_BYTES + 1))
        self.assertPublishBlocked(self.publish())

    def test_read_regular_capped_helper(self):
        f = self.ext / "f.bin"
        f.write_bytes(b"abc")
        self.assertEqual(G.read_regular_capped(f, 3), b"abc")
        with self.assertRaises(OSError):
            G.read_regular_capped(f, 2)
        link = self.ext / "l.bin"
        link.symlink_to(f)
        with self.assertRaises(OSError):
            G.read_regular_capped(link, 10)
        with self.assertRaises(OSError):
            G.read_regular_capped(self.ext, 10)
        with self.assertRaises(OSError):
            G.read_regular_capped(self.ext / "missing.bin", 10)

    def test_not_a_git_repo_fails_closed(self):
        shutil.rmtree(self.fx.root / ".git")
        code, out = self.publish()
        self.assertNotEqual(code, 0, out)

    def test_porcelain_parsing(self):
        self.assertEqual(G.porcelain_paths(b""), [])
        self.assertEqual(G.porcelain_paths(b"?? a b\0R  new\0old\0 M x\0"), ["a b", "new", "old", "x"])
        for bad in (b"?? a", b"R  new\0", b"x\0"):
            with self.assertRaises(G.Malformed):
                G.porcelain_paths(bad)


class Cli(Base):
    def test_exit_codes_via_subprocess(self):
        tool = str(HERE.parent / "governance_check.py")
        root = str(self.fx.root)

        def go(*a, stdin=""):
            p = subprocess.run([sys.executable, tool, *a], input=stdin, capture_output=True, text=True, timeout=60)
            return p.returncode, json.loads(p.stdout)

        self.assertEqual(go("check", "--root", root)[0], 0)
        self.assertEqual(go("check-change", "--root", root, "--decision", "ADR-0001", stdin="governance/registry.json\n")[0], 0)
        self.assertEqual(go("check-change", "--root", root, "--decision", "ADR-0099", stdin="governance/registry.json\n")[0], 1)
        self.assertEqual(go("check-change", "--root", root, "--decision", "ADR-0001", stdin="../x\n")[0], 2)
        (self.fx.root / "governance/registry.json").unlink()
        self.assertEqual(go("check", "--root", root)[0], 2)

    def test_output_is_deterministic(self):
        self.fx.req(1)["owner"] = "MOD-999"
        self.fx.req(2)["owner"] = "MOD-998"
        self.fx.save()
        self.assertEqual(self.check(), self.check())


if __name__ == "__main__":
    unittest.main()
